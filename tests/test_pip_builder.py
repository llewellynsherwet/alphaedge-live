"""Offline tests for the '1000 Pip Builder' setup, news filter, sizing, signal log."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from strategy import news, outcomes as oc, risk_sizing, signal_log  # noqa: E402
from strategy.common import Candidate  # noqa: E402
from strategy.config_loader import load_config  # noqa: E402
from strategy.engine import (_empty_day, _has_enabled_setup, attach_sizing,  # noqa: E402
                             format_trade_message, gate_candidates)
from strategy.pricing import Snapshot, validate_and_reprice  # noqa: E402
import importlib  # noqa: E402
from strategy.setups import REGISTRY  # noqa: E402

pb = importlib.import_module("strategy.setups.pip_builder")

P = pb.params({})
PIP = 0.0001


def frame(rows, start="2026-10-08 10:00", freq="5min"):
    """rows: list of (open, high, low, close)."""
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["Open", "High", "Low", "Close"]).assign(Volume=0)


def ctx(**kw):
    base = dict(atr1h=0.0025, bb_lo=1.0950, bb_up=1.1100, bb_mid=1.102, last_close=1.1000,
                support=[(1.0993, 1.0997, "support")], resistance=[(1.1048, 1.1052, "resistance")],
                swing_highs=[1.1030, 1.1070], swing_lows=[1.0990], trend_d=1, trend_4h=1)
    base.update(kw)
    return pb.Ctx(**base)


# ── config / registry ─────────────────────────────────────────────────────────

def test_enabled_as_second_strategy_with_6pip_tp():
    cfg = load_config()
    assert "pip_builder" in REGISTRY
    pbc = cfg["setups"]["pip_builder"]
    assert pbc["enabled"] is True and pbc["ladder"]["tp1_pips"] == 6 and (pbc["sl_min_pips"], pbc["sl_max_pips"]) == (20, 30)
    assert cfg["risk"]["per_setup_max"]["pip_builder"] <= cfg["risk"]["daily_max_signals"] // 2
    assert "Pip Builder" in pbc["label"]
    assert cfg["setups"]["smc_sweep"]["enabled"] is True          # old strategy untouched
    assert cfg["risk_per_trade"]["enabled"] is False               # sizing opt-in
    assert any(s["name"] == "NZD/USD" and _has_enabled_setup(s, cfg) for s in cfg["symbols"])


def test_old_strategy_params_unchanged():
    r = load_config()["risk"]
    assert (r["tp_rr"], r["daily_max_signals"], r["per_symbol_max"]) == (1.5, 6, 2)


# ── structure helpers ─────────────────────────────────────────────────────────

def test_trend_dir_up_down_range():
    up = [1, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10, 13, 12, 15, 14]
    rows = lambda xs: [(x, x + 0.5, x - 0.5, x) for x in xs]
    assert pb.trend_dir(frame(rows(up), freq="4h"), 1, 5) == 1
    assert pb.trend_dir(frame(rows([20 - x for x in up]), freq="4h"), 1, 5) == -1
    assert pb.trend_dir(frame(rows([1, 3, 1, 3, 1, 3, 1, 3, 1, 3, 1, 3, 1]), freq="4h"), 1, 5) == 0
    assert pb.trend_dir(None, 2) == 0


def test_cluster_levels_needs_touches():
    z = pb.cluster_levels([1.1000, 1.1002, 1.1003, 1.1200], 0.0005, 2)
    assert len(z) == 1 and z[0][2] == 3 and z[0][0] <= 1.1000 and z[0][1] >= 1.1003
    assert len(pb.cluster_levels([1.1, 1.2], 0.0005, 2)) == 0
    assert len(pb.cluster_levels([1.1, 1.2], 0.0005, 1)) == 2


def test_trend_requires_both_timeframes():
    assert ctx(trend_d=1, trend_4h=1).trend == 1
    assert ctx(trend_d=1, trend_4h=-1).trend == 0
    assert ctx(trend_d=0, trend_4h=0).trend == 0


# ── triggers ──────────────────────────────────────────────────────────────────

def _flat(n, px=1.1000):
    return [(px, px + 0.0002, px - 0.0002, px)] * n


def test_bullish_engulfing_close_beyond_prev_high():
    rows = _flat(40) + [(1.1000, 1.1001, 1.0990, 1.0992), (1.0991, 1.1006, 1.0990, 1.1004)]
    tr = pb.detect_triggers(frame(rows), ctx(), pb.params({"use_double": False}), PIP)
    assert [t["kind"] for t in tr] == ["bullish engulfing"]
    assert tr[0]["extreme"] == 1.0990 and tr[0]["side"] == "BUY"


def test_engulfing_requires_close_beyond_high():
    rows = _flat(40) + [(1.1000, 1.1001, 1.0990, 1.0992), (1.0991, 1.1000, 1.0990, 1.1000)]  # close == prev high? 1.1000 < 1.1001
    assert pb.detect_triggers(frame(rows), ctx(), pb.params({"use_double": False}), PIP) == []


def test_double_top_neckline_break_sell():
    # up to 1.1060 (M top 1), pull back to 1.1040, up to 1.1060 again, then break below 1.1040
    path = [1.1000 + 0.0001 * i for i in range(0, 61, 4)]                   # rise 15 bars to 1.1060
    path += [1.1060 - 0.0005 * i for i in range(1, 5)]                      # fall to 1.1040
    path += [1.1040 + 0.0005 * i for i in range(1, 5)]                      # rise to 1.1060
    path += [1.1055, 1.1050, 1.1045, 1.1035]                                # fall, last closes under neckline
    rows = [(c, c + 0.0001, c - 0.0001, c) for c in path]
    rows = _flat(25, 1.1000) + rows
    tr = pb.detect_triggers(frame(rows), ctx(), pb.params({"use_engulf": False, "pattern_swing_k": 2,
                                                          "db_min_sep_bars": 4}), PIP)
    assert any(t["side"] == "SELL" and "double top" in t["kind"] for t in tr), tr


def test_location_buy_sell_and_band():
    c = ctx()
    assert pb.location("BUY", 1.0990, c, P)[0]                 # inside support zone
    assert not pb.location("BUY", 1.1030, c, P)[0]             # mid-air
    assert pb.location("BUY", 1.0952, c, pb.params({"use_zones": False}))[0]   # lower band touch
    assert pb.location("SELL", 1.1051, c, P)[0]                # resistance
    assert not pb.location("SELL", 1.0990, c, P)[0]            # sell at support is not allowed
    assert pb.location("SELL", 1.1105, c, pb.params({"use_zones": False}))[0]


def test_pick_tp_nearest_and_min_pips():
    c = ctx(swing_highs=[1.1008, 1.1030], resistance=[], bb_up=1.1100)
    assert pb.pick_tp("BUY", 1.1000, c, P, PIP) == 1.1008                       # 8 pips: nearest (later filtered <10p)
    assert pb.pick_tp("BUY", 1.1000, c, pb.params({"tp_pick": "nearest_beyond_min"}), PIP) == 1.1030
    assert pb.pick_tp("SELL", 1.1000, ctx(swing_lows=[1.0950], support=[], bb_lo=1.09), P, PIP) == 1.0950


# ── evaluate (gating rules) ───────────────────────────────────────────────────

NOW = pd.Timestamp("2026-10-08 14:00", tz="UTC")     # Thursday: no NFP


def _eval(monkeypatch, c, rows, setup_cfg=None, now=NOW, symbol="EUR/USD"):
    monkeypatch.setattr(pb, "get_context", lambda *a, **k: c)
    f5 = frame(rows, start=now - pd.Timedelta(minutes=5 * len(rows)))
    return pb.evaluate(symbol, {"5m": f5, "15m": None}, {"news": {"enabled": True}}, setup_cfg or {}, now)


BUY_ROWS = _flat(40, 1.0998) + [(1.0999, 1.1000, 1.0995, 1.0996), (1.0996, 1.1004, 1.0994, 1.1003)]


def test_evaluate_buy_at_support(monkeypatch):
    cand = _eval(monkeypatch, ctx(), BUY_ROWS)
    assert cand is not None and cand.side == "BUY" and cand.setup == "pip_builder"
    assert cand.sl < 1.0994 and abs(cand.tp - 1.1030) < 1e-9          # nearest swing high above
    assert cand.meta["tp_on_reprice"] == "keep_target" and cand.rr >= 1.0
    assert cand.score == cand.max_score == 6


def test_evaluate_rejects_counter_trend_and_range(monkeypatch):
    assert _eval(monkeypatch, ctx(trend_d=-1, trend_4h=-1), BUY_ROWS) is None
    assert _eval(monkeypatch, ctx(trend_d=1, trend_4h=0), BUY_ROWS) is None


def test_evaluate_rejects_when_not_at_zone(monkeypatch):
    assert _eval(monkeypatch, ctx(support=[], bb_lo=1.0900), BUY_ROWS) is None


def test_evaluate_rejects_wide_sl_and_short_tp(monkeypatch):
    assert _eval(monkeypatch, ctx(atr1h=0.0004), BUY_ROWS) is None                       # SL > 0.5 ATR
    assert _eval(monkeypatch, ctx(swing_highs=[1.1008], resistance=[], bb_up=1.1008), BUY_ROWS) is None  # TP < 10p


def test_evaluate_blocks_nfp_window(monkeypatch):
    nfp = pd.Timestamp("2026-10-02 12:35", tz="UTC")            # first Friday Oct 2026, 08:30 EDT = 12:30 UTC
    assert _eval(monkeypatch, ctx(), BUY_ROWS, now=nfp) is None


def test_evaluate_stale_bar_ignored(monkeypatch):
    f5 = frame(BUY_ROWS, start=NOW - pd.Timedelta(minutes=5 * len(BUY_ROWS) + 60))
    monkeypatch.setattr(pb, "get_context", lambda *a, **k: ctx())
    assert pb.evaluate("EUR/USD", {"5m": f5}, {"news": {}}, {}, NOW) is None


# ── news ──────────────────────────────────────────────────────────────────────

def test_nfp_static_rule_dst_aware():
    summer = news.nfp_times_utc(pd.Timestamp("2026-10-05", tz="UTC"), pd.Timestamp("2026-10-20", tz="UTC"))
    winter = news.nfp_times_utc(pd.Timestamp("2026-12-01", tz="UTC"), pd.Timestamp("2026-12-20", tz="UTC"))
    assert summer[0] == pd.Timestamp("2026-10-02 12:30", tz="UTC")
    assert winter[0] == pd.Timestamp("2026-12-04 13:30", tz="UTC")


def test_blackout_window_and_custom_events():
    t = pd.Timestamp("2026-12-04 13:50", tz="UTC")
    assert news.blackout(t, "EUR/USD", {"enabled": True})[0]
    assert not news.blackout(t + pd.Timedelta(minutes=30), "EUR/USD", {"enabled": True})[0]
    assert not news.blackout(t, "EUR/USD", {"enabled": False})[0]
    ev = {"enabled": True, "events_utc": ["2026-10-28T18:00:00Z"]}
    assert news.blackout(pd.Timestamp("2026-10-28 18:20", tz="UTC"), "GBP/USD", ev)[0]


# ── sizing ────────────────────────────────────────────────────────────────────

RC = {"enabled": True, "account_size": 1000, "risk_pct": 1.0}


def test_sizing_usd_quote_pair():
    s = risk_sizing.size_position("EUR/USD", 1.1000, 1.0990, RC)       # 10 pips, $10 risk, $10/pip/lot
    assert s["sl_pips"] == 10.0 and s["lots"] == 0.10 and s["actual_risk"] == 10.0


def test_sizing_jpy_and_cad_and_disabled():
    j = risk_sizing.size_position("USD/JPY", 150.0, 149.80, RC)         # 20 pips, pip=$6.67/lot
    assert j["sl_pips"] == 20.0 and abs(j["lots"] - 0.07) < 1e-9
    assert risk_sizing.size_position("USD/CAD", 1.4, 1.399, RC)["lots"] > 0
    assert risk_sizing.size_position("EUR/USD", 1.1, 1.099, {**RC, "enabled": False}) is None
    assert risk_sizing.size_position("GOLD", 2000, 1990, RC) is None


def test_attach_sizing_and_message_has_disclaimer():
    c = Candidate(symbol="EUR/USD", setup="pip_builder", label="x", side="BUY", entry=1.1, sl=1.099, tp=1.103,
                  bar_time=NOW, atr=0.001, zone=1.1, score=6, max_score=6, meta={"min_rr": 1.0})
    attach_sizing(c, {"risk_per_trade": RC})
    assert c.meta["sizing"]["lots"] == 0.10
    msg = format_trade_message(c, "NY")
    assert "Size:" in msg and "0.10 lots" in msg and "Not financial advice" in msg


# ── gates / pricing overrides ─────────────────────────────────────────────────

def _cand(rr_tp=1.1010, **meta):
    return Candidate(symbol="EUR/USD", setup="pip_builder", label="x", side="BUY", entry=1.1000, sl=1.0995,
                     tp=rr_tp, bar_time=NOW, atr=0.001, zone=1.0995, score=6, max_score=6, meta=meta)


def test_gate_honours_setup_min_rr():
    cfg = load_config()                                         # global min_rr is 1.5
    low = _cand(1.1005, min_rr=1.0)                             # RR 1.0
    acc, why = gate_candidates([low], _empty_day("2026-10-08"), cfg, NOW)
    assert acc == [low], why
    acc, why = gate_candidates([_cand(1.1005)], _empty_day("2026-10-08"), cfg, NOW)
    assert acc == [] and "R:R" in why[0]


def _snap(px):
    s = Snapshot(ok=True, signal_ticker="EURUSD=X", quote_label="spot", signal_last=px, signal_age_min=1,
                 quote_live=px, quote_age_min=0.5, basis=0.0)
    s.signal_1m = None
    return s


def test_reprice_keeps_structural_target_and_limits():
    cfg = {"risk": {"tp_rr": 1.5, "min_rr": 1.5},
           "execution": {"tp_on_reprice": "keep_rr", "max_drift_atr": 0.3, "max_drift_tp_frac": 0.25}}
    c = _cand(1.1030, min_rr=1.0, tp_on_reprice="keep_target", min_risk=0.0003, max_risk=0.00065)
    ok, why = validate_and_reprice(c, _snap(1.1001), cfg, NOW)
    assert ok, why
    assert c.tp == 1.1030                                       # not overwritten with 1.5R
    c2 = _cand(1.1030, min_rr=1.0, tp_on_reprice="keep_target", min_risk=0.0003, max_risk=0.00065)
    ok, why = validate_and_reprice(c2, _snap(1.0999), cfg, NOW)   # risk 4 pips
    assert ok
    c3 = _cand(1.1030, min_rr=1.0, tp_on_reprice="keep_target", min_risk=0.0003, max_risk=0.00065)
    ok, why = validate_and_reprice(c3, _snap(1.1000 + 0.00025), cfg, NOW)  # entry moved → risk 7.5 pips > max
    assert not ok


def test_old_setups_still_use_keep_rr():
    cfg = {"risk": {"tp_rr": 1.5, "min_rr": 1.5}, "execution": {"tp_on_reprice": "keep_rr"}}
    c = _cand(1.1030)
    ok, _ = validate_and_reprice(c, _snap(1.1000), cfg, NOW)
    assert ok and abs((c.tp - c.entry) / (c.entry - c.sl) - 1.5) < 1e-9


# ── signal log ────────────────────────────────────────────────────────────────

def test_signal_log_roundtrip(tmp_path):
    p = tmp_path / "log.csv"
    tr = {"id": "20261008-140000-EURUSD-BUY", "sent_ts": NOW.isoformat(), "symbol": "EUR/USD", "side": "BUY",
          "setup": "pip_builder", "entry": 1.1, "sl": 1.099, "tp": 1.103, "rr": 3.0, "score": "6/6",
          "pattern": "bullish engulfing", "sl_pips": 10.0, "sizing": {"lots": 0.1, "actual_risk": 10.0, "sl_pips": 10.0}}
    signal_log.log_signal(tr, True, path=p)
    signal_log.log_signal(tr, True, path=p)                        # idempotent
    df = signal_log.read_log(p)
    assert len(df) == 1 and df.loc[0, "status"] == "OPEN" and df.loc[0, "lots"] == 0.1
    signal_log.log_outcome({**tr, "status": "TP", "exit": 1.103, "r": 3.0, "closed_ts": "2026-10-08T16:00:00+00:00"}, path=p)
    df = signal_log.read_log(p)
    assert df.loc[0, "status"] == "TP" and float(df.loc[0, "r"]) == 3.0
    s = signal_log.summary(df)
    assert s["wins"] == 1 and s["net_r"] == 3.0 and s["win_rate"] == 100.0
    assert signal_log.read_log(tmp_path / "missing.csv").empty


def test_daily_frame_present_in_slicer():
    from strategy import data as d
    idx = pd.date_range("2026-09-01", periods=24 * 20, freq="1h", tz="UTC")
    h1 = pd.DataFrame({"Open": 1.0, "High": 1.1, "Low": 0.9, "Close": 1.0, "Volume": 0}, index=idx)
    m5 = h1.resample("5min").ffill().dropna()
    f = d.FrameSlicer(m5, h1).at(pd.Timestamp("2026-09-20 12:00", tz="UTC"))
    assert "1d" in f and len(f["1d"]) >= 15


def _tp6(monkeypatch, c, rows, jpy=False, **cfg):
    sc = {"tp_pips": 6, "min_rr": 0.5, **cfg}
    return _eval(monkeypatch, c, rows, sc)


def test_fixed_6_pip_tp(monkeypatch):
    cand = _tp6(monkeypatch, ctx(), BUY_ROWS)
    assert cand is not None and abs(cand.tp - cand.entry - 0.0006) < 1e-9
    assert cand.meta["tp_pips"] == 6.0 and cand.rr < 1.0           # honest: RR below 1:1 here


def test_fixed_tp_rr_floor_rejects(monkeypatch):
    assert _tp6(monkeypatch, ctx(), BUY_ROWS, min_rr=1.0) is None   # 6p TP vs ~10p SL → RR 0.57


def test_fixed_6_pip_tp_jpy_pip_size():
    assert risk_sizing.pip_size("USD/JPY") * 6 == 0.06


def test_per_setup_cap_in_gate():
    cfg = load_config()
    cfg["risk"].update(per_symbol_max=9, cooldown_minutes=0, symbol_cooldown_minutes=0, daily_max_signals=6)
    cfg["risk"]["per_setup_max"] = {"pip_builder": 1}
    cfg["correlation_groups"] = []
    st = _empty_day("2026-10-08")
    a = _cand(1.1010, min_rr=1.0)
    b = _cand(1.1010, min_rr=1.0); b.symbol = "GBP/USD"; b.zone = 1.2
    acc, _ = gate_candidates([a], st, cfg, NOW)
    from strategy.engine import record_emits
    st = record_emits(st, acc, NOW)
    acc2, why = gate_candidates([b], st, cfg, NOW)
    assert acc2 == [] and "per-setup cap" in why[0]
    other = Candidate(symbol="US 30", setup="smc_sweep", label="x", side="BUY", entry=100, sl=98, tp=103,
                      bar_time=NOW, atr=2, zone=100, score=4, max_score=6)
    acc3, _ = gate_candidates([other], st, cfg, NOW)
    assert acc3 == [other]                                          # smc_sweep unaffected


# ── SL window + 3-target ladder ───────────────────────────────────────────────
LAD = {"tp1_pips": 6, "tp2_r": 1.0, "tp3_r": 2.0, "split": [1, 1, 1], "be_after_tp1": True}
SLC = {"sl_min_pips": 20, "sl_max_pips": 30, "ladder": LAD, "min_rr": 1.0}


def test_sl_widened_to_20_pips_and_ladder(monkeypatch):
    c = _eval(monkeypatch, ctx(), BUY_ROWS, SLC)                  # structural SL ≈ 10 pips → 20
    assert c is not None
    assert abs((c.entry - c.sl) / PIP - 20.0) < 1e-6
    t1, t2, t3 = c.meta["tps"]
    assert abs((t1 - c.entry) / PIP - 6) < 1e-6 and abs((t2 - c.entry) / PIP - 20) < 1e-6 and abs((t3 - c.entry) / PIP - 40) < 1e-6
    assert c.tp == t3 and abs(c.rr - 2.0) < 1e-6


def test_sl_over_30_pips_rejected(monkeypatch):
    rows = _flat(40, 1.0998) + [(1.0999, 1.1000, 1.0995, 1.0996), (1.0996, 1.1004, 1.0994, 1.1003)]
    # extreme 1.0994 + 1.5p buffer → 10.5 pips; force structure > 30 with a bigger buffer
    assert _eval(monkeypatch, ctx(), rows, {**SLC, "sl_buffer_pips": 25}) is None


def test_sl_stays_inside_window_when_structural(monkeypatch):
    rows = _flat(40, 1.0998) + [(1.0999, 1.1000, 1.0995, 1.0996), (1.0996, 1.1004, 1.0994, 1.1003)]
    c = _eval(monkeypatch, ctx(), rows, {**SLC, "sl_buffer_pips": 14})   # 10.5 − 1.5 + 14 = ~23 pips
    assert c is not None and 20 <= (c.entry - c.sl) / PIP <= 30


def test_ladder_walk_be_and_blended_r():
    from strategy import ladder as L
    tps = L.build(1.1000, 1.0980, "BUY", PIP, LAD)                   # 6p / 20p / 40p
    # TP1 then back to entry → breakeven stop
    r = L.walk("BUY", 1.1000, 1.0980, tps, [1.1007, 1.1002, 1.1001], [1.1000, 1.0999, 1.0999], LAD)
    assert r["tp_hit"] == 1 and r["status"] == "TP" and r["stopped_at"] == "BE"
    assert abs(r["r"] - (1 / 3) * 0.3) < 1e-9                         # 6p / 20p risk = 0.3R, ⅓ weight
    # all three
    r = L.walk("BUY", 1.1000, 1.0980, tps, [1.1007, 1.1021, 1.1041], [1.1001, 1.1006, 1.1020], LAD)
    assert r["tp_hit"] == 3 and abs(r["r"] - (0.3 + 1 + 2) / 3) < 1e-9
    # SL first
    r = L.walk("BUY", 1.1000, 1.0980, tps, [1.1001], [1.0979], LAD)
    assert r["status"] == "SL" and r["r"] == -1.0
    # no breakeven: stopped at SL after TP1 → blended negative
    r = L.walk("BUY", 1.1000, 1.0980, tps, [1.1007, 1.1001], [1.1000, 1.0979], {**LAD, "be_after_tp1": False})
    assert r["tp_hit"] == 1 and r["status"] == "TP" and r["r"] < 0
    # same candle: stop and TP1 → stop first
    r = L.walk("BUY", 1.1000, 1.0980, tps, [1.1010], [1.0979], LAD)
    assert r["status"] == "SL" and r["both_in_bar"]


def test_ladder_sell_with_spread_shift():
    from strategy import ladder as L
    tps = L.build(1.1000, 1.1020, "SELL", PIP, LAD)
    r = L.walk("SELL", 1.1000, 1.1020, tps, [1.1001], [1.0995], LAD, shift=0.0001)   # ask low 1.0996 > TP1 1.0994
    assert r["tp_hit"] == 0 and not r["done"]


def test_outcome_tracking_ladder_progress_and_final():
    tr = {"id": "t", "symbol": "EUR/USD", "side": "BUY", "setup": "pip_builder", "setup_label": "PB",
          "entry": 1.1000, "sl": 1.0980, "tp": 1.1040, "tps": [1.1006, 1.1020, 1.1040], "ladder": LAD,
          "rr": 2.0, "quote_source": "none", "quote_label": "x", "sent_ts": "2026-10-08T14:00:00+00:00",
          "tp_hit": 0, "tp_notified": 0}
    idx = pd.date_range("2026-10-08 14:01", periods=3, freq="1min", tz="UTC")
    b = pd.DataFrame({"High": [1.1007, 1.1004, 1.1003], "Low": [1.1001, 1.1001, 1.0999], "Close": [1.1005] * 3,
                      "Open": [1.1] * 3}, index=idx)
    now = pd.Timestamp("2026-10-08 14:10", tz="UTC")
    assert oc.detect_outcome(tr, b.iloc[:2], now) is None and tr["tp_hit"] == 1
    state = {"trades": {"open": [tr], "closed": []}}
    assert oc.pending_progress(state) == [tr]
    assert "TP1 HIT" in oc.format_progress_message(tr) and "breakeven" in oc.format_progress_message(tr)
    out = oc.detect_outcome(tr, b, now)                               # price returns to entry → BE stop
    assert out["status"] == "TP" and out["tp_hit"] == 1 and out["stopped_at"] == "BE" and out["r"] > 0
    msg = oc.format_outcome_message({**tr, **out})
    assert "TP1 HIT" in msg and "breakeven" in msg and "Not financial advice" in msg
    sl = oc.detect_outcome({**tr, "tp_hit": 0}, pd.DataFrame({"High": [1.1001], "Low": [1.0979], "Close": [1.098], "Open": [1.1]}, index=idx[:1]), now)
    assert sl["status"] == "SL" and sl["r"] == -1.0 and "SL HIT" in oc.format_outcome_message({**tr, **sl})


def test_day_summary_counts_ladder():
    closed = [{"id": "a", "symbol": "EUR/USD", "side": "BUY", "status": "TP", "tps": [1, 2, 3], "tp_hit": 3, "r": 1.1,
               "closed_ts": "2026-10-08T15:00:00+00:00"},
              {"id": "b", "symbol": "GBP/USD", "side": "BUY", "status": "SL", "tps": [1, 2, 3], "tp_hit": 0, "r": -1.0,
               "closed_ts": "2026-10-08T16:00:00+00:00"}]
    st = {"day": "2026-10-08", "trades": {"open": [], "closed": closed}}
    s = oc.day_stats(st)
    assert (s["tp1"], s["tp2"], s["tp3"], s["ladder_trades"]) == (1, 1, 1, 2)
    txt = oc.format_day_outcomes(st)
    assert "Ladder: TP1 1 · TP2 1 · TP3 1" in txt and "TP3" in txt


def test_alert_shows_three_targets_and_sizing(monkeypatch):
    c = _eval(monkeypatch, ctx(), BUY_ROWS, SLC)
    attach_sizing(c, {"risk_per_trade": RC})
    msg = format_trade_message(c, "NY")
    assert "TP1:" in msg and "TP2:" in msg and "TP3:" in msg and "(+6 pips)" in msg
    assert c.meta["sizing"]["sl_pips"] == 20.0 and c.meta["sizing"]["lots"] == 0.05   # $10 / (20p × $10)… 0.05 lots
    assert "Not financial advice" in msg


def test_reprice_rebuilds_ladder_from_live_entry(monkeypatch):
    c = _eval(monkeypatch, ctx(), BUY_ROWS, SLC)
    cfg = {"risk": {"tp_rr": 1.5, "min_rr": 1.5},
           "execution": {"tp_on_reprice": "keep_rr", "max_drift_atr": 0.5, "max_drift_tp_frac": 0.25}}
    px = c.entry + 0.0002
    ok, why = validate_and_reprice(c, _snap(px), cfg, NOW + pd.Timedelta(minutes=0))
    assert ok, why
    assert abs((c.meta["tps"][0] - c.entry) / PIP - 6) < 1e-6 and c.tp == c.meta["tps"][2]
