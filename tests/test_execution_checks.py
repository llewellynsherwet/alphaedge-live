"""Offline tests for strategy.pricing.validate_and_reprice (no network).

Run:  python -m pytest tests -q     (or)     python tests/test_execution_checks.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.common import Candidate  # noqa: E402
from strategy.pricing import Snapshot, validate_and_reprice  # noqa: E402

NOW = pd.Timestamp("2026-09-28 14:00", tz="UTC")
CFG = {
    "risk": {"tp_rr": 2.5, "min_rr": 2.5},
    "execution": {"enabled": True, "entry_mode": "market", "tp_on_reprice": "keep_rr",
                  "max_data_age_minutes": 15, "max_price_age_minutes": 10,
                  "max_drift_atr": 0.3, "max_drift_tp_frac": 0.25, "reject_if_tp_sl_hit": True},
}


def cand(side="BUY", entry=100.0, sl=98.0, tp=105.0, atr=2.0, mins_ago=10):
    return Candidate(symbol="US 30", setup="smc_sweep", label="t", side=side, entry=entry, sl=sl,
                     tp=tp, bar_time=NOW - pd.Timedelta(minutes=mins_ago), atr=atr, zone=entry)


def snap(live_signal, basis=0.0, sig_age=10.0, q_age=0.5, bars=None):
    s = Snapshot(ok=True, signal_ticker="YM=F", quote_label="cash", signal_last=live_signal,
                 signal_age_min=sig_age, quote_live=live_signal - basis, quote_age_min=q_age,
                 basis=basis)
    s.signal_1m = bars
    return s


def bars(lo, hi, start_mins_ago=9):
    idx = pd.date_range(NOW - pd.Timedelta(minutes=start_mins_ago), periods=3, freq="1min")
    return pd.DataFrame({"Open": lo, "High": hi, "Low": lo, "Close": lo}, index=idx)


def test_accept_and_reprice_to_live_quote_space():
    c = cand()
    ok, why = validate_and_reprice(c, snap(100.2, basis=30.0), CFG, NOW)
    assert ok, why
    assert abs(c.entry - 70.2) < 1e-9          # live futures 100.2 − basis 30 → cash
    assert abs(c.sl - 68.0) < 1e-9             # structural SL kept, shifted by basis
    assert abs((c.tp - c.entry) / (c.entry - c.sl) - 2.5) < 1e-9
    assert c.meta["signal_entry"] == 100.0 and c.meta["basis"] == 30.0


def test_reject_drift_beyond_atr_tolerance():
    ok, why = validate_and_reprice(cand(), snap(100.7), CFG, NOW)   # 0.35 ATR toward TP
    assert not ok and "moved" in why


def test_adverse_drift_is_repriced_not_rejected():
    c = cand()
    ok, why = validate_and_reprice(c, snap(99.5), CFG, NOW)
    assert ok, why
    assert c.entry == 99.5 and abs(c.tp - (99.5 + 2.5 * 1.5)) < 1e-9


def test_reject_stale_feed_and_stale_quote():
    assert not validate_and_reprice(cand(), snap(100.1, sig_age=40), CFG, NOW)[0]
    assert not validate_and_reprice(cand(), snap(100.1, q_age=30), CFG, NOW)[0]


def test_reject_tp_or_sl_already_hit():
    ok, why = validate_and_reprice(cand(), snap(100.1, bars=bars(99.0, 105.5)), CFG, NOW)
    assert not ok and "TP already" in why
    ok, why = validate_and_reprice(cand(), snap(100.1, bars=bars(97.5, 100.5)), CFG, NOW)
    assert not ok and "SL already" in why


def test_reject_live_beyond_sl_sell_side():
    c = cand(side="SELL", entry=100.0, sl=102.0, tp=95.0)
    ok, why = validate_and_reprice(c, snap(102.5), CFG, NOW)
    assert not ok and "beyond SL" in why


def test_min_rr_recheck_with_keep_target():
    cfg = {**CFG, "execution": {**CFG["execution"], "tp_on_reprice": "keep_target",
                                "max_drift_atr": 5, "max_drift_tp_frac": 0.9}}
    ok, why = validate_and_reprice(cand(), snap(101.0), cfg, NOW)   # RR (105-101)/3 = 1.33
    assert not ok and "R:R" in why


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
