import pandas as pd
from strategy import data as D, zone_book as zb
from strategy.config_loader import load_config
from strategy.engine import scan_slot, seconds_to_next_slot, mark_slot_done, gate_candidates, record_emits
from tests.test_zone_dedupe import cand

CFG = load_config()
SAST = lambda s: pd.Timestamp(s, tz="Africa/Johannesburg").tz_convert("UTC")


def test_slots_every_15_minutes_in_window():
    assert scan_slot(SAST("2026-10-28 05:58:30"), CFG, {}) == "2026-10-28T05:58+Africa/Johannesburg"
    assert scan_slot(SAST("2026-10-28 06:13:10"), CFG, {}) == "2026-10-28T06:13+Africa/Johannesburg"
    assert scan_slot(SAST("2026-10-28 06:20"), CFG, {}) == "2026-10-28T06:13+Africa/Johannesburg"  # within 10m grace
    assert scan_slot(SAST("2026-10-28 06:24"), CFG, {}) is None                                    # grace over
    assert scan_slot(SAST("2026-10-28 05:43:30"), CFG, {}) is None                                 # before first
    assert scan_slot(SAST("2026-10-28 18:58:30"), CFG, {}) == "2026-10-28T18:58+Africa/Johannesburg"
    assert scan_slot(SAST("2026-10-28 19:13:30"), CFG, {}) is None                                 # after last
    assert scan_slot(SAST("2026-10-31 10:13:30"), CFG, {}) is None                                 # Saturday
    st = mark_slot_done({}, "2026-10-28T06:13+Africa/Johannesburg")
    assert scan_slot(SAST("2026-10-28 06:15"), CFG, st) is None
    assert seconds_to_next_slot(SAST("2026-10-28 06:14"), CFG) == 14 * 60 + 5


def test_past_slots_24h_count():
    # 24h back from Wed 10:05 → Tue 10:13..18:58 (36) + Wed 05:58..09:58 (17)
    assert len(zb.past_slots(SAST("2026-10-28 10:05"), CFG)) == 36 + 17


def test_1h_cached_hourly(monkeypatch):
    calls = []
    df = pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0]},
                      index=[pd.Timestamp("2026-10-28 07:00", tz="UTC")])
    monkeypatch.setattr(D, "fetch", lambda s, i, p: (calls.append(i), (df, None))[1])
    D._H1_CACHE.clear()
    for t in ("08:13", "08:28", "08:43", "08:58"):
        D._cached_1h("X", pd.Timestamp(f"2026-10-28 {t}", tz="UTC"))
    assert len(calls) == 1
    D._cached_1h("X", pd.Timestamp("2026-10-28 09:13", tz="UTC"))
    assert len(calls) == 2


def test_zone_still_blocked_on_every_15m_slot():
    t0 = SAST("2026-10-28 08:13")
    st = record_emits({}, [cand(t0)], t0)
    cfg = {**CFG, "risk": {**CFG["risk"], "max_signal_age_minutes": 999}}
    for k in range(1, 9):   # next 8 slots (2h)
        now = t0 + pd.Timedelta(minutes=15 * k)
        acc, why = gate_candidates([cand(now)], st, cfg, now)
        assert not acc
