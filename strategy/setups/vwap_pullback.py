"""First pullback to session VWAP after a clear trend-day stretch.

Requires real volume (yfinance futures / equity) — spot FX typically has no
usable volume and will simply return None.
"""
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from ..checklist import score as score_checklist
from ..common import Candidate, htf_bias, parse_hhmm
from ..indicators import anchored_vwap, atr

NY = ZoneInfo("America/New_York")


def evaluate(symbol, frames, cfg, setup_cfg, now, priority=99):
    tf = setup_cfg.get("entry_tf", "5m")
    df = frames.get(tf)
    if df is None or len(df) < 50:
        return None
    if float(df["Volume"].sum()) <= 0:
        return None  # no volume → no VWAP strategy

    now_ny = now.tz_convert(NY) if now.tzinfo else now.replace(tzinfo=NY)
    if now_ny.weekday() >= 5:
        return None

    avoid = setup_cfg.get("avoid_ny", ["11:30", "13:30"])
    if len(avoid) == 2:
        a0, a1 = parse_hhmm(avoid[0]), parse_hhmm(avoid[1])
        m = now_ny.hour * 60 + now_ny.minute
        if a0.hour * 60 + a0.minute <= m < a1.hour * 60 + a1.minute:
            active_hours = False
        else:
            active_hours = True
    else:
        active_hours = True

    anchor = parse_hhmm(setup_cfg.get("anchor_ny", "09:30"))
    open_dt = now_ny.replace(hour=anchor.hour, minute=anchor.minute, second=0, microsecond=0)
    if now_ny < open_dt + pd.Timedelta(minutes=30):
        return None  # need room for a stretch before the first pullback

    open_utc = open_dt.tz_convert("UTC")
    start_idx = int(df.index.searchsorted(open_utc))
    if start_idx >= len(df) - 5:
        return None
    vw = anchored_vwap(df, start_idx)
    if vw is None:
        return None

    # Align VWAP array to the post-open slice
    sub = df.iloc[start_idx:]
    if len(sub) != len(vw):
        return None
    a_full = atr(df).to_numpy()
    a_sub = a_full[start_idx:]
    cl = sub["Close"].to_numpy(); hi = sub["High"].to_numpy(); lo = sub["Low"].to_numpy()
    vol = sub["Volume"].to_numpy(dtype=float)
    n = len(sub)
    if n < 25 or not np.isfinite(a_sub[-1]) or a_sub[-1] <= 0:
        return None

    trend_n = int(setup_cfg.get("trend_bars", 18))
    min_frac = float(setup_cfg.get("trend_min_frac", 0.8))
    sep_m = float(setup_cfg.get("min_separation_atr", 1.5))
    touch_m = float(setup_cfg.get("touch_atr", 0.15))
    buf_m = float(setup_cfg.get("sl_buffer_atr", 0.2))
    max_risk = float(setup_cfg.get("max_risk_atr", 2.5))
    tp_rr = float(cfg.get("risk", {}).get("tp_rr", 2.5))

    # Determine trend side from the stretch BEFORE the last few bars
    look = min(trend_n, n - 3)
    window = slice(n - 1 - look, n - 1)  # exclude current bar
    above = (cl[window] > vw[window]).mean()
    below = (cl[window] < vw[window]).mean()
    if above >= min_frac:
        side = "BUY"
    elif below >= min_frac:
        side = "SELL"
    else:
        return None

    # Must have stretched away from VWAP earlier in the day
    sep = (cl[:n - 1] - vw[:n - 1]) / np.maximum(a_sub[:n - 1], 1e-9)
    if side == "BUY" and not (sep.max() >= sep_m):
        return None
    if side == "SELL" and not (sep.min() <= -sep_m):
        return None

    # Last bar: first touch of VWAP + confirmation close back on trend side
    i = n - 1
    atr_i = float(a_sub[i])
    if side == "BUY":
        touched = lo[i] <= vw[i] + touch_m * atr_i
        confirm = cl[i] > vw[i] and cl[i] > sub["Open"].iloc[i]
    else:
        touched = hi[i] >= vw[i] - touch_m * atr_i
        confirm = cl[i] < vw[i] and cl[i] < sub["Open"].iloc[i]
    if not (touched and confirm):
        return None

    # Allow the first OR second confirmed VWAP touch after the stretch peak
    # (third+ is usually a choppy range day — skip).
    if side == "BUY":
        peak = int(np.argmax(sep))
        prior_n = sum(
            1 for j in range(peak + 1, i)
            if lo[j] <= vw[j] + touch_m * a_sub[j] and cl[j] > vw[j]
        )
    else:
        peak = int(np.argmin(sep))
        prior_n = sum(
            1 for j in range(peak + 1, i)
            if hi[j] >= vw[j] - touch_m * a_sub[j] and cl[j] < vw[j]
        )
    if prior_n >= 2:
        return None

    # Volume signature: recent pullback bars quieter than the impulse into the peak
    vol_ok = False
    if peak >= 3 and i - peak >= 1:
        impulse = float(np.mean(vol[max(0, peak - 3):peak + 1]))
        pull = float(np.mean(vol[peak + 1:i + 1])) if i > peak else impulse
        vol_ok = impulse > 0 and pull <= 0.85 * impulse

    entry = float(cl[i])
    buf = buf_m * atr_i
    if side == "BUY":
        sl = min(float(lo[i]), float(vw[i])) - buf
        risk = entry - sl
        tp = entry + tp_rr * risk
    else:
        sl = max(float(hi[i]), float(vw[i])) + buf
        risk = sl - entry
        tp = entry - tp_rr * risk
    if risk <= 0 or risk / atr_i > max_risk:
        return None

    bias, bias_note = htf_bias(frames)
    htf_ok = (bias == "bull" and side == "BUY") or (bias == "bear" and side == "SELL")

    factors = {
        "htf_bias": htf_ok,
        "vwap_trend": True,
        "pullback_touch": True,
        "confirm_close": True,
        "volume_signature": vol_ok,
        "active_hours": active_hours,
    }
    sc, mx, missing, lines = score_checklist(factors, setup_cfg.get("checklist", {}))
    if missing or sc < int(setup_cfg.get("min_score", 4)):
        return None

    interval = pd.Timedelta(minutes=5)
    bar_close = sub.index[i] + interval
    notes = [
        f"Session VWAP {float(vw[i]):.5g}; first pullback after {sep_m}×ATR stretch",
        bias_note,
    ]
    return Candidate(
        symbol=symbol, setup="vwap_pullback", label=setup_cfg.get("label", "VWAP PB"),
        side=side, entry=entry, sl=sl, tp=tp, bar_time=bar_close,
        atr=atr_i, zone=float(vw[i]), factors=factors, notes=notes,
        score=sc, max_score=mx, priority=priority, checklist_lines=lines,
    )
