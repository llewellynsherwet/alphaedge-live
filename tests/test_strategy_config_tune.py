"""Guards for the 2026-10-08 "more signals" tune of strategy_config.yaml."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from strategy.checklist import score  # noqa: E402
from strategy.common import Candidate  # noqa: E402
from strategy.config_loader import load_config  # noqa: E402
from strategy.engine import _empty_day, gate_candidates, record_emits  # noqa: E402

CFG = load_config()
SMC = CFG["setups"]["smc_sweep"]


def _passes(factors):
    sc, _mx, missing, _ = score(factors, SMC["checklist"])
    return not missing and sc >= int(SMC["min_score"])


def test_risk_block_consistent():
    r = CFG["risk"]
    assert float(r["min_rr"]) <= float(r["tp_rr"])  # otherwise every alert is gated out
    assert 1 <= int(r["per_symbol_max"]) <= int(r["daily_max_signals"]) <= 8  # never spammy
    assert int(r["cooldown_minutes"]) >= 30
    assert int(r["symbol_cooldown_minutes"]) >= 60


def test_smc_core_pattern_and_pd_still_required():
    ck = SMC["checklist"]
    for k in ("liquidity_sweep", "mss_bos", "pd_array", "premium_discount"):
        assert ck[k]["required"] is True, k


def test_smc_htf_and_killzone_are_score_only():
    base = {"liquidity_sweep": True, "mss_bos": True, "pd_array": True,
            "premium_discount": True, "htf_bias": False, "kill_zone": False}
    assert _passes(base)                                  # PD-located sweep fires 24/7
    assert not _passes({**base, "premium_discount": False})  # wrong side of range never fires
    assert not _passes({**base, "pd_array": False})


def _cand(sym, side, minute, zone):
    t = pd.Timestamp("2026-10-07 08:00", tz="UTC") + pd.Timedelta(minutes=minute)
    return Candidate(symbol=sym, setup="smc_sweep", label="x", side=side, entry=100.0,
                     sl=99.0, tp=100.0 + float(CFG["risk"]["tp_rr"]), bar_time=t, atr=1.0,
                     zone=zone, score=4, max_score=6), t


def test_caps_still_limit_daily_alerts():
    syms = [s["name"] for s in CFG["symbols"]]
    state = _empty_day("2026-10-07")
    sent = 0
    # A fresh, non-correlated candidate every 5 minutes all day long.
    for i in range(0, 16 * 60, 5):
        c, t = _cand(syms[(i // 5) % len(syms)], "BUY" if (i // 5) % 2 else "SELL", i, i)
        acc, _ = gate_candidates([c], state, CFG, t)
        state = record_emits(state, acc, t)
        sent += len(acc)
    assert 2 <= sent <= int(CFG["risk"]["daily_max_signals"])
