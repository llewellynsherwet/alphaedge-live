"""Morning kill-zone EMA pullback with VWAP confluence (indices / gold).

Research-backed selectivity (not a promise):
  • NY morning window only (default 09:45–11:30 America/New_York) — midday/afternoon
    VWAP pullbacks historically underperform in public QQQ studies.
  • Require HTF bias + price on the correct side of session VWAP with rising/falling slope.
  • Entry on pullback into the EMA9–EMA21 "bone zone" that also tags VWAP (± touch_atr).
  • First or second touch only; confirmation close back with the trend.
  • Real volume required (yfinance futures) — FX spot typically returns None.

Target: a few high-quality alerts/day when combined with SMC + gated VWAP, not spam.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from ..checklist import score as score_checklist
from ..common import Candidate, htf_bias, parse_hhmm
from ..indicators import anchored_vwap, atr, ema

NY = ZoneInfo("America/New_York")


def evaluate(symbol, frames, cfg, setup_cfg, now, priority=99):
    tf = setup_cfg.get("entry_tf", "5m")
    df = frames.get(tf)
    if df is None or len(df) < 60:
        return None
    if float(df["Volume"].sum()) <= 0:
        return None

    now_ny = now.tz_convert(NY) if now.tzinfo else now.replace(tzinfo=NY)
    if now_ny.weekday() >= 5:
        return None

    win = setup_cfg.get("window_ny", ["09:45", "11:30"])
    if len(win) == 2:
        a0, a1 = parse_hhmm(win[0]), parse_hhmm(win[1])
        m = now_ny.hour * 60 + now_ny.minute
        if not (a0.hour * 60 + a0.minute <= m < a1.hour * 60 + a1.minute):
            return None

    anchor = parse_hhmm(setup_cfg.get("anchor_ny", "09:30"))
    open_dt = now_ny.replace(hour=anchor.hour, minute=anchor.minute, second=0, microsecond=0)
    if now_ny < open_dt + pd.Timedelta(minutes=15):
        return None

    open_utc = open_dt.tz_convert("UTC")
    start_idx = int(df.index.searchsorted(open_utc))
    if start_idx >= len(df) - 10:
        return None

    vw = anchored_vwap(df, start_idx)
    if vw is None:
        return None
    sub = df.iloc[start_idx:]
    if len(sub) != len(vw) or len(sub) < 20:
        return None

    a_full = atr(df).to_numpy()
    a_sub = a_full[start_idx:]
    cl = sub["Close"].to_numpy()
    hi = sub["High"].to_numpy()
    lo = sub["Low"].to_numpy()
    op = sub["Open"].to_numpy()
    vol = sub["Volume"].to_numpy(dtype=float)
    e9 = ema(sub["Close"], 9).to_numpy()
    e21 = ema(sub["Close"], 21).to_numpy()
    n = len(sub)
    if not np.isfinite(a_sub[-1]) or a_sub[-1] <= 0:
        return None

    # VWAP slope over last slope_bars
    slope_n = int(setup_cfg.get("slope_bars", 6))
    if n <= slope_n + 2:
        return None
    vwap_slope = float(vw[-1] - vw[-1 - slope_n])
    slope_min = float(setup_cfg.get("min_slope_atr", 0.05)) * float(a_sub[-1])

    trend_n = int(setup_cfg.get("trend_bars", 16))
    min_frac = float(setup_cfg.get("trend_min_frac", 0.7))
    look = min(trend_n, n - 3)
    window = slice(n - 1 - look, n - 1)
    above = (cl[window] > vw[window]).mean()
    below = (cl[window] < vw[window]).mean()

    if above >= min_frac and vwap_slope >= slope_min:
        side = "BUY"
    elif below >= min_frac and vwap_slope <= -slope_min:
        side = "SELL"
    else:
        return None

    sep_m = float(setup_cfg.get("min_separation_atr", 0.8))
    sep = (cl[: n - 1] - vw[: n - 1]) / np.maximum(a_sub[: n - 1], 1e-9)
    if side == "BUY" and not (sep.max() >= sep_m):
        return None
    if side == "SELL" and not (sep.min() <= -sep_m):
        return None

    touch_m = float(setup_cfg.get("touch_atr", 0.25))
    i = n - 1
    atr_i = float(a_sub[i])
    bone_lo = float(min(e9[i], e21[i]))
    bone_hi = float(max(e9[i], e21[i]))
    # Pullback into bone zone AND near VWAP
    near_vwap = abs(cl[i] - vw[i]) <= touch_m * atr_i or (
        lo[i] <= vw[i] + touch_m * atr_i and hi[i] >= vw[i] - touch_m * atr_i
    )
    in_bone = lo[i] <= bone_hi + 0.05 * atr_i and hi[i] >= bone_lo - 0.05 * atr_i
    if side == "BUY":
        confirm = cl[i] > vw[i] and cl[i] > op[i] and cl[i] >= bone_lo
    else:
        confirm = cl[i] < vw[i] and cl[i] < op[i] and cl[i] <= bone_hi
    if not (near_vwap and in_bone and confirm):
        return None

    # First/second touch after stretch peak
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

    vol_ok = False
    if peak >= 3 and i > peak:
        impulse = float(np.mean(vol[max(0, peak - 3): peak + 1]))
        pull = float(np.mean(vol[peak + 1: i + 1]))
        vol_ok = impulse > 0 and pull <= 0.9 * impulse

    tp_rr = float(cfg.get("risk", {}).get("tp_rr", 2.0))
    buf_m = float(setup_cfg.get("sl_buffer_atr", 0.2))
    max_risk = float(setup_cfg.get("max_risk_atr", 2.0))
    entry = float(cl[i])
    buf = buf_m * atr_i
    if side == "BUY":
        sl = min(float(lo[i]), float(vw[i]), bone_lo) - buf
        risk = entry - sl
        tp = entry + tp_rr * risk
    else:
        sl = max(float(hi[i]), float(vw[i]), bone_hi) + buf
        risk = sl - entry
        tp = entry - tp_rr * risk
    if risk <= 0 or risk / atr_i > max_risk:
        return None

    bias, bias_note = htf_bias(frames)
    htf_ok = (bias == "bull" and side == "BUY") or (bias == "bear" and side == "SELL")

    factors = {
        "htf_bias": htf_ok,
        "vwap_trend": True,
        "ema_bone": True,
        "vwap_slope": True,
        "confirm_close": True,
        "volume_signature": vol_ok,
        "morning_kz": True,
    }
    sc, mx, missing, lines = score_checklist(factors, setup_cfg.get("checklist", {}))
    if missing or sc < int(setup_cfg.get("min_score", 5)):
        return None

    interval = pd.Timedelta(minutes=5)
    bar_close = sub.index[i] + interval
    notes = [
        f"Morning KZ EMA+VWAP; bone {bone_lo:.5g}–{bone_hi:.5g}; VWAP {float(vw[i]):.5g}",
        bias_note,
    ]
    return Candidate(
        symbol=symbol, setup="ema_vwap_kz", label=setup_cfg.get("label", "EMA+VWAP KZ"),
        side=side, entry=entry, sl=sl, tp=tp, bar_time=bar_close,
        atr=atr_i, zone=float(vw[i]), factors=factors, notes=notes,
        score=sc, max_score=mx, priority=priority, checklist_lines=lines,
    )
