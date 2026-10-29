import pandas as pd
from strategy import zone_book as zb
from strategy.common import Candidate
from strategy.engine import gate_candidates, record_emits, scan_slot

CFG = {"risk": {"min_rr": 1.0, "daily_max_signals": 99, "per_symbol_max": 99, "max_signal_age_minutes": 999,
                "cooldown_minutes": 0, "symbol_cooldown_minutes": 0},
       "schedule": {"enabled": True, "timezone": "Africa/Johannesburg", "minute": 58, "first_hour": 5,
                    "last_hour": 18, "grace_minutes": 22, "weekdays_only": True},
       "symbols": [{"name": "EUR/USD", "yf": "EURUSD=X", "pip": 0.0001}], "setups": {"moon_wolf": {}}}


def cand(now, zid="EUR/USD|SELL|1.12|1.121", entry=1.12):
    return Candidate(symbol="EUR/USD", setup="moon_wolf", label="mw", side="SELL", entry=entry, sl=entry + 0.001,
                     tp=entry - 0.003, bar_time=now, atr=0.001, zone=1.1205, score=5, max_score=5,
                     meta={"zone_id": zid, "tps_fixed": [entry - 0.001, entry - 0.003]})


def bars(start, n, lo, hi):
    idx = pd.date_range(start, periods=n, freq="15min")
    return pd.DataFrame({"Open": hi, "High": hi, "Low": lo, "Close": lo}, index=idx)


T0 = pd.Timestamp("2026-10-27 07:58", tz="UTC")


def test_zone_blocked_next_hour_and_next_day_then_released_after_24h():
    st = record_emits({}, [cand(T0)], T0)
    for dt in (1, 2, 20):
        now = T0 + pd.Timedelta(hours=dt)
        acc, why = gate_candidates([cand(now)], st, CFG, now)
        assert not acc and "zone" in why[0]
    now = T0 + pd.Timedelta(hours=24, minutes=1)
    assert gate_candidates([cand(now)], st, CFG, now)[0]


def test_zone_released_when_trade_closes():
    st = record_emits({}, [cand(T0)], T0)
    zb.update_closed(st, "EUR/USD", bars(T0 + pd.Timedelta(minutes=15), 4, 1.1195, 1.1205), T0 + pd.Timedelta(hours=1))
    assert zb.is_blocked(st, "EUR/USD|SELL|1.12|1.121", T0 + pd.Timedelta(hours=1))  # TP1 only, still open
    zb.update_closed(st, "EUR/USD", bars(T0, 4, 1.1, 1.1215), T0 + pd.Timedelta(hours=1))  # SL hit too
    now = T0 + pd.Timedelta(hours=2)
    assert gate_candidates([cand(now)], st, CFG, now)[0]


def test_other_zone_not_blocked():
    st = record_emits({}, [cand(T0)], T0)
    now = T0 + pd.Timedelta(hours=1)
    assert gate_candidates([cand(now, zid="EUR/USD|SELL|1.13|1.131")], st, CFG, now)[0]


def test_moon_wolf_zone_id_rounds():
    from strategy.setups.moon_wolf import zone_id
    assert zone_id("EUR/USD", "SELL", 1.12001, 1.12102, 0.0001) == zone_id("EUR/USD", "SELL", 1.11999, 1.12098, 0.0001)


def test_restart_rebuild_blocks_replayed_zone_and_skips_past_slots():
    now = pd.Timestamp("2026-10-27 08:05", tz="UTC")  # 10:05 SAST; 09:58 slot is current
    idx = pd.date_range(now - pd.Timedelta(days=5), now, freq="15min")
    df = pd.DataFrame({"Open": 1.12, "High": 1.1202, "Low": 1.1198, "Close": 1.12}, index=idx)
    fetch = lambda yf, iv, per: (df, None)
    calls = []

    def fake_eval(sym, frames, cfg, scfg, at, pri):
        calls.append(at)
        return cand(at)  # same zone every slot

    st = {}  # wiped disk
    rep = zb.rebuild(st, CFG, now, fetch=fetch, setup_eval=fake_eval)
    assert rep["zones"] == 1 and calls
    assert zb.is_blocked(st, "EUR/USD|SELL|1.12|1.121", now)
    # past slots (08:58 SAST and earlier) are done; only the current 09:58 slot may still scan
    assert "2026-10-27T08:58+Africa/Johannesburg" in st["scan_slots_done"]
    assert scan_slot(now, CFG, st) == "2026-10-27T09:58+Africa/Johannesburg"
    # …and the current scan cannot repeat the replayed zone
    assert not gate_candidates([cand(now)], st, CFG, now)[0]


def test_overlapping_drifted_zone_blocked():
    st = record_emits({}, [cand(T0)], T0)
    now = T0 + pd.Timedelta(hours=1)
    assert not gate_candidates([cand(now, zid="EUR/USD|SELL|1.1205|1.1215")], st, CFG, now)[0]
    assert gate_candidates([cand(now, zid="EUR/USD|BUY|1.1205|1.1215")], st, CFG, now)[0]
