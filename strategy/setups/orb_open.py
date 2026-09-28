"""NY Opening Range Breakout (cash open 09:30 America/New_York).

Builds the high/low of the first `range_minutes` after the cash open, then
looks for the first CLOSED break of that range (with optional volume /
candle / VWAP / gap / HTF filters). One attempt per symbol per session by
design — the engine's per-symbol daily cap enforces that.
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
    if df is None or len(df) < 40:
        return None

    open_t = parse_hhmm(setup_cfg.get("open_time_ny", "09:30"))
    until_t = parse_hhmm(setup_cfg.get("entry_until_ny", "11:00"))
    range_m = int(setup_cfg.get("range_minutes", 15))
    vol_mult = float(setup_cfg.get("volume_mult", 1.5))
    body_r = float(setup_cfg.get("min_body_ratio", 0.5))
    max_r_atr = float(setup_cfg.get("max_range_atr", 4.0))
    sl_mode = setup_cfg.get("sl_mode", "mid")
    tp_rr = float(cfg.get("risk", {}).get("tp_rr", 2.5))

    now_ny = now.tz_convert(NY) if now.tzinfo else now.replace(tzinfo=NY)
    if now_ny.weekday() >= 5:
        return None
    open_dt = now_ny.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
    range_end = open_dt + pd.Timedelta(minutes=range_m)
    until_dt = now_ny.replace(hour=until_t.hour, minute=until_t.minute, second=0, microsecond=0)
    if now_ny < range_end or now_ny > until_dt:
        return None

    idx_ny = df.index.tz_convert(NY)
    day_mask = idx_ny.date == now_ny.date()
    day = df[day_mask]
    if len(day) < 5:
        return None
    day_ny = day.index.tz_convert(NY)
    or_mask = (day_ny >= open_dt) & (day_ny < range_end)
    orb = day[or_mask]
    if len(orb) < max(1, range_m // 5):
        return None
    or_hi = float(orb["High"].max()); or_lo = float(orb["Low"].min())
    or_mid = (or_hi + or_lo) / 2.0
    or_h = or_hi - or_lo
    if or_h <= 0:
        return None

    a = atr(df).iloc[-1]
    if not np.isfinite(a) or a <= 0:
        return None
    if or_h > max_r_atr * a:
        return None  # wild open — skip

    # Bars after the OR that have closed
    after = day[day_ny >= range_end]
    if len(after) == 0:
        return None
    # First closed break (we evaluate on the latest closed bar; only fire if
    # THAT bar is the first break, so we don't re-alert late).
    last = after.iloc[-1]
    last_i_ny = after.index[-1].tz_convert(NY)
    # Has any earlier after-bar already broken?
    earlier = after.iloc[:-1]
    prior_break = False
    if len(earlier):
        prior_break = bool((earlier["Close"] > or_hi).any() or (earlier["Close"] < or_lo).any())
    if prior_break:
        return None

    side = None
    if float(last["Close"]) > or_hi:
        side = "BUY"
    elif float(last["Close"]) < or_lo:
        side = "SELL"
    else:
        return None

    entry = float(last["Close"])
    if sl_mode == "opposite":
        sl = or_lo if side == "BUY" else or_hi
    else:
        sl = or_mid
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    tp = entry + tp_rr * risk if side == "BUY" else entry - tp_rr * risk

    # Volume: breakout bar vs the average of the previous 20 closed 5m bars
    # (opening-range bars themselves are always heavy, so comparing to them
    # almost never passes).
    prev = df["Volume"].iloc[-21:-1]
    ref_vol = float(prev.mean()) if len(prev) and prev.sum() > 0 else 0.0
    last_vol = float(last["Volume"])
    vol_ok = ref_vol > 0 and last_vol >= vol_mult * ref_vol

    rng = float(last["High"] - last["Low"]) or 1e-9
    body_ok = abs(float(last["Close"] - last["Open"])) / rng >= body_r

    # VWAP side (anchored at cash open)
    day_start_pos = int(np.argmax(day_mask))  # first True in the full df
    # Find the first bar of the NY cash open inside `df`
    open_utc = open_dt.tz_convert("UTC")
    start_idx = int(df.index.searchsorted(open_utc))
    vw = anchored_vwap(df, start_idx)
    vwap_ok = False
    if vw is not None and start_idx < len(df):
        # last bar of df is the same as `last` (closed_only frames)
        vwap_now = float(vw[-1])
        vwap_ok = (side == "BUY" and entry > vwap_now) or (side == "SELL" and entry < vwap_now)

    # Gap direction: today's open vs yesterday's close (use 1h)
    gap_ok = False
    h1 = frames.get("1h")
    if h1 is not None and len(h1) > 20:
        h1_ny = h1.index.tz_convert(NY)
        today = h1[h1_ny.date == now_ny.date()]
        yday = h1[h1_ny.date < now_ny.date()]
        if len(today) and len(yday):
            gap = float(today["Open"].iloc[0] - yday["Close"].iloc[-1])
            gap_ok = (side == "BUY" and gap > 0) or (side == "SELL" and gap < 0)

    bias, bias_note = htf_bias(frames)
    htf_ok = (bias == "bull" and side == "BUY") or (bias == "bear" and side == "SELL")

    factors = {
        "htf_bias": htf_ok,
        "breakout_close": True,
        "strong_candle": body_ok,
        "volume_confirm": vol_ok,
        "vwap_side": vwap_ok,
        "gap_align": gap_ok,
    }
    sc, mx, missing, lines = score_checklist(factors, setup_cfg.get("checklist", {}))
    if missing or sc < int(setup_cfg.get("min_score", 4)):
        return None

    interval = pd.Timedelta(minutes=5)
    bar_close = after.index[-1] + interval
    notes = [
        f"OR {range_m}m: {or_lo:.5g}–{or_hi:.5g} (mid {or_mid:.5g})",
        f"First closed break @ {last_i_ny.strftime('%H:%M')} NY",
        bias_note,
    ]
    return Candidate(
        symbol=symbol, setup="orb_open", label=setup_cfg.get("label", "ORB"),
        side=side, entry=entry, sl=sl, tp=tp, bar_time=bar_close,
        atr=float(a), zone=or_mid, factors=factors, notes=notes,
        score=sc, max_score=mx, priority=priority, checklist_lines=lines,
    )
