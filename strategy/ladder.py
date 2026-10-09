"""3-target ladder (TP1/TP2/TP3) shared by the setup, live repricing, outcome tracking and backtest.

Config (setups.pip_builder.ladder):
  tp1_pips: 6      first target, fixed pips (JPY pairs: same pips, 0.01 each)
  tp2_r: 1.0       TP2 = 1R  (R = entry→SL distance)
  tp3_r: 2.0       TP3 = 2R
  split: [1,1,1]   share of the position closed at each target (normalised)
  be_after_tp1: true   after TP1 the stop of the remainder moves to entry (breakeven)

HOW RESULTS ARE COUNTED
  * Headline win = TP1 reached (tp_hit >= 1). Headline loss = stopped before TP1.
  * Net R is the REAL blended result: legs closed at TP1/TP2/TP3 pay (level-entry)/risk
    weighted by `split`; the stopped remainder pays -1R (SL) or 0R (breakeven stop).
    So a "win" at TP1 followed by a breakeven stop is only a small positive R, and without
    breakeven a later SL can make a TP1-"win" net negative. Both are shown, never hidden.
  * One stage per candle (conservative): the candle that hits a level does not also test
    the next level or the new stop; a stop and a target in the same candle = stop first.
"""
from __future__ import annotations

import numpy as np

DEFAULT = {"tp1_pips": 6.0, "tp2_r": 1.0, "tp3_r": 2.0, "split": [1, 1, 1], "be_after_tp1": True}


def cfg_of(lad: dict | None) -> dict:
    out = dict(DEFAULT)
    out.update(lad or {})
    s = [float(x) for x in out["split"]]
    out["split"] = [x / sum(s) for x in s]
    return out


def build(entry: float, sl: float, side: str, pip: float, lad: dict) -> list[float]:
    lad = cfg_of(lad)
    d = 1 if side == "BUY" else -1
    risk = abs(entry - sl)
    return [entry + d * lad["tp1_pips"] * pip, entry + d * lad["tp2_r"] * risk, entry + d * lad["tp3_r"] * risk]


def walk(side: str, fill: float, sl: float, tps: list[float], highs, lows, lad: dict,
         shift: float = 0.0, last_close: float | None = None, expire: bool = True) -> dict:
    """Walk candles (arrays, time-ordered, starting at the first bar after entry).
    `shift` is added to highs/lows for SELL ask-side tests (spread). Returns
    {tp_hit, status, r, exit_idx, hit_idx:[i1,i2,i3|None], be, both_in_bar, done}."""
    lad = cfg_of(lad)
    d = 1 if side == "BUY" else -1
    hi = np.asarray(highs, float) + (shift if d == -1 else 0.0)
    lo = np.asarray(lows, float) + (shift if d == -1 else 0.0)
    risk = abs(fill - sl)
    split = lad["split"]
    stage, hit_idx, r_done, be, both = 0, [None, None, None], 0.0, False, False

    def leg(px):
        return (px - fill) * d / risk if risk > 0 else 0.0

    n = len(hi)
    for i in range(n):
        stop = sl if (stage == 0 or not lad["be_after_tp1"]) else fill
        stop_hit = lo[i] <= stop if d == 1 else hi[i] >= stop
        tp_hit = (hi[i] >= tps[stage]) if d == 1 else (lo[i] <= tps[stage])
        if stop_hit:
            r_stop = leg(stop)
            rem = sum(split[stage:])
            r = r_done + rem * r_stop
            both = bool(tp_hit)
            return {"tp_hit": stage, "status": "SL" if stage == 0 else "TP", "r": r, "exit_idx": i,
                    "hit_idx": hit_idx, "be": stage > 0 and lad["be_after_tp1"], "both_in_bar": both,
                    "done": True, "stopped_at": "SL" if stop == sl else "BE"}
        if tp_hit:
            r_done += split[stage] * leg(tps[stage])
            hit_idx[stage] = i
            stage += 1
            if stage == 3:
                return {"tp_hit": 3, "status": "TP", "r": r_done, "exit_idx": i, "hit_idx": hit_idx,
                        "be": False, "both_in_bar": False, "done": True, "stopped_at": "TP3"}
    out = {"tp_hit": stage, "status": "OPEN", "r": None, "exit_idx": None, "hit_idx": hit_idx,
           "be": stage > 0 and lad["be_after_tp1"], "both_in_bar": False, "done": False, "stopped_at": None}
    if expire and last_close is not None:
        rem = sum(split[stage:])
        px = last_close + (shift if d == -1 else 0.0)
        out.update(status="TP" if stage else "EXPIRED", r=r_done + rem * leg(px), done=True,
                   exit_idx=n - 1, stopped_at="EXP")
    return out
