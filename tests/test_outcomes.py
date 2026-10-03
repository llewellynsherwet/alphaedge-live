"""Offline tests for strategy.outcomes (TP / SL / both-in-bar / expiry) and
the outcome-aware state + daily summary. No network.

Run:  python -m pytest tests -q
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import outcomes as oc  # noqa: E402
from strategy.common import Candidate  # noqa: E402
from strategy.engine import format_daily_summary, load_state, save_state  # noqa: E402

SENT = pd.Timestamp("2026-10-01 09:00:20", tz="UTC")   # Thursday


def trade(side="BUY", entry=100.0, sl=98.0, tp=105.0, sent=SENT, symbol="US 30"):
    return {"id": "t1", "symbol": symbol, "side": side, "setup": "smc_sweep",
            "setup_label": "Liquidity Sweep + BOS", "entry": entry, "sl": sl, "tp": tp,
            "rr": 2.5, "quote_source": "yf", "quote_ticker": "^DJI",
            "quote_label": "US30 cash (^DJI)", "signal_ticker": "YM=F", "basis": 0.0,
            "sent_ts": sent.isoformat()}


def bars(rows, start=pd.Timestamp("2026-10-01 09:01", tz="UTC"), freq="1min"):
    """rows: list of (high, low)."""
    idx = pd.date_range(start, periods=len(rows), freq=freq)
    hi = [r[0] for r in rows]
    lo = [r[1] for r in rows]
    cl = [(h + l) / 2 for h, l in rows]
    return pd.DataFrame({"Open": cl, "High": hi, "Low": lo, "Close": cl}, index=idx)


NOW = pd.Timestamp("2026-10-01 10:00", tz="UTC")


# ── hit detection ─────────────────────────────────────────────────────────────

def test_tp_hit_by_wick_buy():
    b = bars([(100.5, 99.5), (101, 99.8), (105.2, 100.9), (104, 103)])
    o = oc.detect_outcome(trade(), b, NOW)
    assert o["status"] == "TP" and o["exit"] == 105.0
    assert o["r"] == 2.5 and abs(o["points"] - 5.0) < 1e-9
    assert o["hit_ts"].startswith("2026-10-01T09:03")
    assert not o["both_in_bar"]


def test_sl_hit_buy_and_sell_symmetry():
    o = oc.detect_outcome(trade(), bars([(100.5, 99.5), (100, 97.9)]), NOW)
    assert o["status"] == "SL" and o["exit"] == 98.0 and o["r"] == -1.0
    s = trade(side="SELL", entry=100.0, sl=102.0, tp=95.0)
    o = oc.detect_outcome(s, bars([(100.5, 99.5), (102.01, 100)]), NOW)
    assert o["status"] == "SL" and o["r"] == -1.0 and abs(o["points"] + 2.0) < 1e-9
    o = oc.detect_outcome(s, bars([(100.5, 99.5), (99, 94.9)]), NOW)
    assert o["status"] == "TP" and o["r"] == 2.5


def test_both_in_same_bar_counts_as_sl():
    b = bars([(100.5, 99.5), (105.5, 97.5), (106, 104)])
    o = oc.detect_outcome(trade(), b, NOW)
    assert o["status"] == "SL" and o["both_in_bar"] and o["r"] == -1.0
    msg = oc.format_outcome_message({**trade(), **o})
    assert "❌ <b>SL HIT</b>" in msg and "counted as SL (conservative)" in msg


def test_first_hit_wins_and_pre_alert_bar_ignored():
    # 09:00 bar (contains the alert at 09:00:20) wicked SL before the alert → ignored
    b = bars([(100.2, 97.0), (100.5, 99.5), (105.1, 100)], start=pd.Timestamp("2026-10-01 09:00", tz="UTC"))
    o = oc.detect_outcome(trade(), b, NOW)
    assert o["status"] == "TP"


def test_still_open_returns_none():
    assert oc.detect_outcome(trade(), bars([(101, 99), (102, 99.5)]), NOW) is None
    assert oc.detect_outcome(trade(), None, NOW) is None


def test_expiry_after_max_open_hours():
    later = SENT + pd.Timedelta(hours=48, minutes=5)
    b = bars([(101, 99), (102, 99.5), (101.5, 100.5)])
    o = oc.detect_outcome(trade(), b, later, max_open_hours=48)
    assert o["status"] == "EXPIRED"
    assert o["exit"] == 101.0 and o["r"] == 0.5          # marked at last close
    assert pd.Timestamp(o["hit_ts"]) == SENT + pd.Timedelta(hours=48)
    msg = oc.format_outcome_message({**trade(), **o}, max_open_hours=48)
    assert "⌛ <b>EXPIRED</b>" in msg and "48h" in msg
    # not yet expired at 47h
    assert oc.detect_outcome(trade(), b, SENT + pd.Timedelta(hours=47), max_open_hours=48) is None


def test_hits_after_deadline_do_not_count():
    later = SENT + pd.Timedelta(hours=50)
    b = bars([(101, 99), (110, 100)], start=SENT.ceil("min") + pd.Timedelta(hours=48, minutes=1))
    o = oc.detect_outcome(trade(), b, later, max_open_hours=48)
    assert o["status"] == "EXPIRED" and o["exit"] is None and o["r"] is None


def test_5m_fallback_bars():
    b = bars([(100.5, 99.5), (105.5, 100)], start=pd.Timestamp("2026-10-01 09:05", tz="UTC"), freq="5min")
    o = oc.detect_outcome(trade(), b, NOW, interval_min=5)
    assert o["status"] == "TP" and o["interval_min"] == 5


# ── check_open_trades: close once, weekend skip, fetch failure ───────────────

def _state_with(tr):
    st = {"day": "2026-10-01"}
    oc.trades_book(st)["open"].append(tr)
    return st


def test_check_open_trades_closes_exactly_once():
    st = _state_with(trade())
    fetch = lambda tr, now: (bars([(105.5, 100)]), 1, "test")  # noqa: E731
    first = oc.check_open_trades(st, {}, NOW, fetch_bars=fetch)
    assert len(first) == 1 and first[0]["status"] == "TP" and first[0]["notified"] is False
    assert st["trades"]["open"] == [] and len(st["trades"]["closed"]) == 1
    assert oc.check_open_trades(st, {}, NOW, fetch_bars=fetch) == []
    assert len(oc.pending_notifications(st)) == 1
    st["trades"]["closed"][0]["notified"] = True
    assert oc.pending_notifications(st) == []


def test_weekend_skips_fetch_and_feed_failure_keeps_open():
    st = _state_with(trade(sent=pd.Timestamp("2026-10-02 15:00", tz="UTC")))
    sat = pd.Timestamp("2026-10-03 12:00", tz="UTC")
    assert not oc.market_open(sat) and oc.market_open(NOW)

    def boom(tr, now):
        raise AssertionError("should not fetch on weekend")
    assert oc.check_open_trades(st, {}, sat, fetch_bars=boom) == []
    assert len(st["trades"]["open"]) == 1
    fail = lambda tr, now: (None, None, "down")  # noqa: E731
    assert oc.check_open_trades(st, {}, pd.Timestamp("2026-10-02 16:00", tz="UTC"), fetch_bars=fail) == []
    assert len(st["trades"]["open"]) == 1


def test_fetch_quote_bars_yf_hybrid_uses_cash_then_futures_minus_basis():
    idx = pd.date_range("2026-10-01 09:01", periods=4, freq="1min", tz="UTC")
    fut = pd.DataFrame({k: [400.0, 401, 402, 403] for k in oc._OHLC}, index=idx)
    cash = pd.DataFrame({k: [52.5, 53.5] for k in oc._OHLC}, index=idx[2:])

    def fake_fetch(t, iv, per):
        return ({"YM=F": fut, "^DJI": cash}[t], None)
    tr = {**trade(), "basis": 350.0}
    b, mins, note = oc.fetch_quote_bars(tr, NOW, fetch=fake_fetch)
    assert mins == 1 and list(b["Close"]) == [50.0, 51.0, 52.5, 53.5]


def test_make_trade_from_candidate_uses_quote_space_meta():
    c = Candidate(symbol="GOLD", setup="smc_sweep", label="Liquidity Sweep + BOS", side="SELL",
                  entry=2650.0, sl=2660.0, tp=2625.0, bar_time=SENT, atr=5.0, zone=2650.0,
                  meta={"signal_ticker": "GC=F", "basis": 31.5, "quote_label": "XAUUSD spot"})
    cfg = {"symbols": [{"name": "GOLD", "yf": "GC=F",
                        "quote": {"source": "gold_api", "ticker": "XAU", "label": "XAUUSD spot"}}]}
    st = {}
    rec = oc.add_open_trade(st, c, cfg, SENT)
    assert rec["quote_source"] == "gold_api" and rec["basis"] == 31.5 and rec["rr"] == 2.5
    assert st["trades"]["open"][0]["id"] == rec["id"]


# ── formatting / persistence / summary ───────────────────────────────────────

def test_message_formatting_fx_pips_and_escape():
    fx = trade(symbol="USD/JPY", entry=148.200, sl=148.500, tp=147.450, side="SELL")
    o = oc.detect_outcome(fx, bars([(148.3, 147.4)]), NOW)
    msg = oc.format_outcome_message({**fx, **o, "setup_label": "A <b> & C"})
    assert "✅ <b>TP HIT</b> — USD/JPY 🔴 SELL" in msg
    assert "+75.0 pips" in msg and "+2.50R" in msg
    assert "A &lt;b&gt; &amp; C" in msg


def test_trades_survive_day_rollover(tmp_path):
    p = tmp_path / "state.json"
    st = load_state(p, now=pd.Timestamp("2026-10-01 10:00", tz="UTC"))
    st["emitted"].append({"zone_key": "z", "symbol": "US 30", "side": "BUY"})
    oc.trades_book(st)["open"].append(trade())
    save_state(st, p)
    nxt = load_state(p, now=pd.Timestamp("2026-10-02 06:00", tz="UTC"))
    assert nxt["day"] == "2026-10-02" and nxt["emitted"] == []      # daily budget reset
    assert nxt["trades"]["open"][0]["id"] == "t1"                    # trades carried
    json.dumps(nxt)


def test_daily_summary_includes_outcomes():
    st = {"day": "2026-10-01", "emitted": [{"symbol": "US 30", "side": "BUY", "setup": "smc_sweep",
                                             "score": 5, "rr": 2.5}]}
    book = oc.trades_book(st)
    close = pd.Timestamp("2026-10-01 12:00", tz="UTC").isoformat()
    book["closed"] += [
        {**trade(), "status": "TP", "r": 2.5, "closed_ts": close},
        {**trade(symbol="EUR/USD"), "status": "SL", "r": -1.0, "closed_ts": close},
        {**trade(symbol="GOLD"), "status": "EXPIRED", "r": 0.3, "closed_ts": close},
        {**trade(symbol="S&P 500"), "status": "TP", "r": 2.5, "summarized": True,
         "closed_ts": pd.Timestamp("2026-09-30 12:00", tz="UTC").isoformat()},   # already reported
    ]
    book["open"].append(trade(symbol="NASDAQ 100"))
    s = oc.day_stats(st)
    assert (s["wins"], s["losses"], s["expired"], s["net_r"], s["open"]) == (1, 1, 1, 1.5, 1)
    msg = format_daily_summary(st, "close", daily_cap=6, outcomes_enabled=True)
    assert "1W / 1L / 1 expired · net +1.50R · win rate 50%" in msg
    assert "Still open: 1" in msg and "S&amp;P" not in msg
    assert "Outcomes" not in format_daily_summary(st, "close", daily_cap=6, outcomes_enabled=False)


def test_unsummarized_earlier_close_appears_once():
    st = {"day": "2026-10-05"}
    book = oc.trades_book(st)
    sat = pd.Timestamp("2026-10-02 19:00", tz="UTC").isoformat()   # after Friday's summary
    book["closed"] += [
        {**trade(), "status": "TP", "r": 2.5, "closed_ts": sat},
        {**trade(symbol="GOLD"), "status": "SL", "r": -1.0, "closed_ts": sat, "summarized": True},
    ]
    s = oc.day_stats(st)
    assert (s["wins"], s["losses"]) == (1, 0)
    assert "(closed 02/10 19:00)" in oc.format_day_outcomes(st)
    oc.mark_summarized(st)
    assert oc.day_stats(st)["wins"] == 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
