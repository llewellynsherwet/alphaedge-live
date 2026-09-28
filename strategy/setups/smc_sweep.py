"""Liquidity sweep + Break-of-Structure with a fresh FVG / Order Block entry.

Strict definitions (closed candles only):
  • Sweep: wick beyond a confirmed swing high/low, body closes back inside.
  • BOS:   after the sweep, a displacement candle closes beyond the opposite
           swing with body ≥ displacement_atr × ATR.
  • FVG:   classic 3-candle imbalance (bull: Low[i] > High[i-2];
           bear: High[i] < Low[i-2]), gap ≥ min_fvg_atr × ATR, not yet filled.
  • OB:    last opposite-colour candle *before* the displacement, followed by
           a gap (next open beyond that candle's high/low) — not 'any opposite'.
Entry on the first closed candle that retests the FVG or OB after the BOS.
"""
import numpy as np
import pandas as pd

from ..checklist import score as score_checklist
from ..common import Candidate, htf_bias, in_any, premium_discount
from ..indicators import atr, pivots


def evaluate(symbol, frames, cfg, setup_cfg, now, priority=99):
    tf = setup_cfg.get("entry_tf", "15m")
    df = frames.get(tf)
    if df is None or len(df) < 40:
        return None

    k = int(setup_cfg.get("swing_strength", 3))
    look = int(setup_cfg.get("sweep_lookback_bars", 16))
    disp_m = float(setup_cfg.get("displacement_atr", 1.0))
    fvg_m = float(setup_cfg.get("min_fvg_atr", 0.15))
    max_risk = float(setup_cfg.get("max_risk_atr", 3.0))
    min_risk = float(setup_cfg.get("min_risk_atr", 0.4))
    buf_m = float(setup_cfg.get("sl_buffer_atr", 0.1))
    tp_rr = float(cfg.get("risk", {}).get("tp_rr", 2.5))

    a = atr(df).to_numpy()
    hi = df["High"].to_numpy(); lo = df["Low"].to_numpy()
    op = df["Open"].to_numpy(); cl = df["Close"].to_numpy()
    n = len(df)
    if not np.isfinite(a[-1]) or a[-1] <= 0:
        return None

    ph, pl = pivots(hi, lo, k)
    # A pivot at j is only known once bar j+k has closed.
    last = n - 1

    def last_pivot_before(arr_mask, before, max_back=60):
        """Most recent pivot index p with p + k < before (confirmed before `before`)."""
        for p in range(before - k - 1, max(before - max_back, k) - 1, -1):
            if arr_mask[p]:
                return p
        return None

    def try_setup(sweep_i, side):
        """Full pattern check for a sweep at bar sweep_i. Returns dict or None."""
        # Liquidity level = most recent confirmed swing before the sweep bar
        if side == "BUY":
            p = last_pivot_before(pl, sweep_i)
            if p is None or not (lo[sweep_i] < lo[p] and cl[sweep_i] > lo[p]):
                return None
            # Level not already taken between pivot and sweep
            if p + 1 < sweep_i and lo[p + 1:sweep_i].min() < lo[p]:
                return None
            liq_px = float(lo[p])
            # Sweep extreme must hold until now
            if sweep_i + 1 <= last and lo[sweep_i + 1:last + 1].min() < lo[sweep_i]:
                return None
            # MSS level: most recent confirmed swing HIGH before the sweep
            q = last_pivot_before(ph, sweep_i + 1, max_back=80)
            if q is None:
                return None
            mss_px = float(hi[q])
        else:
            p = last_pivot_before(ph, sweep_i)
            if p is None or not (hi[sweep_i] > hi[p] and cl[sweep_i] < hi[p]):
                return None
            if p + 1 < sweep_i and hi[p + 1:sweep_i].max() > hi[p]:
                return None
            liq_px = float(hi[p])
            if sweep_i + 1 <= last and hi[sweep_i + 1:last + 1].max() > hi[sweep_i]:
                return None
            q = last_pivot_before(pl, sweep_i + 1, max_back=80)
            if q is None:
                return None
            mss_px = float(lo[q])

        # BOS: first close beyond the MSS level after the sweep, with a
        # displacement candle (body >= disp × ATR) somewhere in that leg.
        bos_i = None
        for i in range(sweep_i + 1, last):          # BOS must be before the entry bar
            if side == "BUY" and cl[i] > mss_px:
                bos_i = i
                break
            if side == "SELL" and cl[i] < mss_px:
                bos_i = i
                break
        if bos_i is None:
            return None
        leg = range(sweep_i + 1, bos_i + 1)
        if side == "BUY":
            disp_ok = any(cl[j] > op[j] and (cl[j] - op[j]) >= disp_m * a[j] for j in leg)
        else:
            disp_ok = any(cl[j] < op[j] and (op[j] - cl[j]) >= disp_m * a[j] for j in leg)
        if not disp_ok:
            return None

        # PD array inside the displacement leg: prefer FVG, else strict OB.
        zone = None
        for j in range(bos_i, sweep_i + 1, -1):     # j = third candle of the FVG
            if j - 2 < sweep_i or j >= last:
                continue
            if side == "BUY" and lo[j] - hi[j - 2] >= fvg_m * a[j]:
                zone = ("FVG", float(hi[j - 2]), float(lo[j]), j)
                break
            if side == "SELL" and lo[j - 2] - hi[j] >= fvg_m * a[j]:
                zone = ("FVG", float(hi[j]), float(lo[j - 2]), j)
                break
        if zone is None:
            # Strict OB: last opposite-colour candle from the sweep up to the
            # displacement, and the NEXT candle must open/close beyond it
            # (i.e. price left the block with intent, not a random candle).
            for j in range(bos_i - 1, sweep_i - 1, -1):
                if side == "BUY" and cl[j] < op[j] and cl[j + 1] > hi[j]:
                    zone = ("OB", float(lo[j]), float(hi[j]), j + 1)
                    break
                if side == "SELL" and cl[j] > op[j] and cl[j + 1] < lo[j]:
                    zone = ("OB", float(lo[j]), float(hi[j]), j + 1)
                    break
        if zone is None:
            return None
        kind_z, z_lo, z_hi, formed = zone

        # Zone must be unmitigated (not fully filled) and this must be the
        # FIRST retest: no bar between formation+1 and the entry bar touched it.
        for j in range(max(formed + 1, bos_i + 1), last):
            if side == "BUY" and lo[j] <= z_hi:
                return None
            if side == "SELL" and hi[j] >= z_lo:
                return None

        # Entry bar (last closed) retests the zone and closes back in bias.
        if side == "BUY":
            if not (lo[last] <= z_hi and cl[last] > z_lo and lo[last] > lo[sweep_i]):
                return None
        else:
            if not (hi[last] >= z_lo and cl[last] < z_hi and hi[last] < hi[sweep_i]):
                return None
        return {"sweep_i": sweep_i, "liq_px": liq_px, "mss_px": mss_px,
                "zone": (kind_z, z_lo, z_hi)}

    found = None
    side = None
    for s_i in range(last - 2, max(last - look, 2 * k + 1) - 1, -1):
        for sd in ("BUY", "SELL"):
            r = try_setup(s_i, sd)
            if r is not None:
                found, side = r, sd
                break
        if found:
            break
    if found is None:
        return None

    sweep_i = found["sweep_i"]
    swing_px = found["liq_px"]
    kind = "bsl" if side == "BUY" else "ssl"
    zone_kind, zone_lo, zone_hi = found["zone"]
    i = last
    entry = float(cl[i])
    buf = buf_m * float(a[i])
    if side == "BUY":
        sl = min(float(lo[sweep_i]), zone_lo) - buf
        risk = entry - sl
        tp = entry + tp_rr * risk
    else:
        sl = max(float(hi[sweep_i]), zone_hi) + buf
        risk = sl - entry
        tp = entry - tp_rr * risk
    if risk <= 0:
        return None
    risk_atr = risk / float(a[i])
    if risk_atr > max_risk or risk_atr < min_risk:
        return None

    # --- checklist factors -----------------------------------------------------
    bias, bias_note = htf_bias(frames)
    htf_ok = (bias == "bull" and side == "BUY") or (bias == "bear" and side == "SELL")
    pd_ok, pd_note = premium_discount(frames, side, entry)
    kz_ok = in_any(now, cfg.get("session", {}).get("kill_zones", []))

    factors = {
        "htf_bias": htf_ok,
        "premium_discount": pd_ok,
        "liquidity_sweep": True,
        "mss_bos": True,
        "pd_array": True,
        "kill_zone": kz_ok,
    }
    sc, mx, missing, lines = score_checklist(factors, setup_cfg.get("checklist", {}))
    if missing or sc < int(setup_cfg.get("min_score", cfg.get("confluence", {}).get("min_score", 4))):
        return None

    interval = pd.Timedelta(minutes={"5m": 5, "15m": 15, "1h": 60}[tf])
    bar_close = df.index[i] + interval
    notes = [
        f"Sweep of {'sell-side' if kind == 'bsl' else 'buy-side'} liquidity @ {swing_px:.5g}",
        f"BOS displacement on {tf}",
        f"Entry zone: {zone_kind} {zone_lo:.5g}–{zone_hi:.5g}",
        bias_note, pd_note,
    ]
    return Candidate(
        symbol=symbol, setup="smc_sweep", label=setup_cfg.get("label", "SMC Sweep"),
        side=side, entry=entry, sl=sl, tp=tp, bar_time=bar_close,
        atr=float(a[i]), zone=(zone_lo + zone_hi) / 2.0,
        factors=factors, notes=notes, score=sc, max_score=mx,
        priority=priority, checklist_lines=lines,
    )
