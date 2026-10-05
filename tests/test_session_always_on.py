"""24/7 scanner: always_on keeps scanning; quality gates still apply."""
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
from strategy.engine import session_info, next_session  # noqa: E402
from strategy.common import in_window, hhmm_to_minutes  # noqa: E402


BASE = {
    "session": {
        "always_on": True,
        "weekdays_only": False,
        "windows": [
            {"name": "ASIA", "start": "00:00", "end": "07:00"},
            {"name": "LONDON", "start": "07:00", "end": "17:00"},
            {"name": "LATE", "start": "17:00", "end": "24:00"},
        ],
        "kill_zones": [
            {"name": "Tokyo KZ", "start": "00:00", "end": "03:00"},
            {"name": "London KZ", "start": "07:00", "end": "10:00"},
        ],
    }
}


def test_hhmm_24_and_wrap():
    assert hhmm_to_minutes("24:00") == 1440
    assert hhmm_to_minutes("00:00") == 0
    ts = pd.Timestamp("2026-10-05 22:30:00", tz="UTC")
    assert in_window(ts, "21:00", "24:00")
    assert not in_window(ts, "00:00", "07:00")


def test_always_on_weekend_and_offpeak():
    # Sunday 03:00 UTC — weekend + Asia window
    now = pd.Timestamp("2026-10-04 03:00:00", tz="UTC")  # Sunday
    assert now.weekday() == 6
    on, name = session_info(now, BASE)
    assert on is True
    assert "ASIA" in name

    # Mid-week late
    now2 = pd.Timestamp("2026-10-05 22:00:00", tz="UTC")  # Monday
    on2, name2 = session_info(now2, BASE)
    assert on2 is True
    assert "LATE" in name2


def test_legacy_session_hours_still_gate_when_not_always_on():
    cfg = deepcopy(BASE)
    cfg["session"]["always_on"] = False
    cfg["session"]["weekdays_only"] = True
    cfg["session"]["windows"] = [
        {"name": "LONDON", "start": "07:00", "end": "17:00"},
    ]
    sat = pd.Timestamp("2026-10-03 10:00:00", tz="UTC")  # Saturday
    on, name = session_info(sat, cfg)
    assert on is False
    assert "WEEKEND" in name

    night = pd.Timestamp("2026-10-05 03:00:00", tz="UTC")  # Monday off-hours
    on2, name2 = session_info(night, cfg)
    assert on2 is False
    assert "OFF-SESSION" in name2


def test_next_session_always_on():
    now = pd.Timestamp("2026-10-05 06:00:00", tz="UTC")
    name, when = next_session(now, BASE)
    assert "LONDON" in name
