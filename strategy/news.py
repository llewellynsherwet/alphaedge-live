"""High-impact news blackout for the 1000 Pip Builder setup.

No free *historical* economic calendar exists, so the backtest and the live
fallback use a STATIC RULE: US Non-Farm Payrolls = first Friday of the month at
08:30 America/New_York (DST-aware). Extra known events can be listed in
``news.events_utc`` (ISO timestamps). Live only: ``news.use_feed: true`` also
pulls this week's high-impact events from the public ForexFactory-style JSON
mirror (cached 1h, fails open to the static rule). CPI / GDP / central-bank
dates are therefore NOT blocked in backtests — a known limitation.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")
FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_feed_cache = {"ts": 0.0, "events": []}

CCY = {"EUR/USD": ("EUR", "USD"), "GBP/USD": ("GBP", "USD"), "USD/JPY": ("USD", "JPY"),
       "AUD/USD": ("AUD", "USD"), "NZD/USD": ("NZD", "USD"), "USD/CAD": ("USD", "CAD"),
       "USD/CHF": ("USD", "CHF"), "EUR/JPY": ("EUR", "JPY"), "GBP/JPY": ("GBP", "JPY"),
       "CAD/JPY": ("CAD", "JPY")}


def first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def nfp_times_utc(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """NFP release instants (UTC) for every month touching [start, end]."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        ff = first_friday(y, m)
        t = datetime(ff.year, ff.month, ff.day, 8, 30, tzinfo=NY)
        out.append(pd.Timestamp(t).tz_convert("UTC"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _feed_events() -> list[tuple[pd.Timestamp, str]]:
    if time.time() - _feed_cache["ts"] < 3600:
        return _feed_cache["events"]
    ev = []
    try:
        import requests
        r = requests.get(FEED_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        for e in r.json():
            if str(e.get("impact", "")).lower() == "high":
                ev.append((pd.Timestamp(e["date"]).tz_convert("UTC"), str(e.get("country", "")).upper()))
    except Exception:
        ev = []
    _feed_cache.update(ts=time.time(), events=ev)
    return ev


def blackout(now: pd.Timestamp, symbol: str, news_cfg: dict | None) -> tuple[bool, str]:
    """True if `now` is inside the blackout window of a high-impact event."""
    cfg = news_cfg or {}
    if not cfg.get("enabled", True):
        return False, ""
    w = pd.Timedelta(minutes=float(cfg.get("window_minutes", 30)))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    events = [(t, "USD", "NFP (static rule)") for t in nfp_times_utc(now - pd.Timedelta(days=2), now + pd.Timedelta(days=2))]
    for s in cfg.get("events_utc") or []:
        events.append((pd.Timestamp(s).tz_convert("UTC") if pd.Timestamp(s).tzinfo else pd.Timestamp(s, tz="UTC"), "*", "calendar event"))
    if cfg.get("use_feed"):
        ccys = CCY.get(symbol, ())
        for t, c in _feed_events():
            if not ccys or c in ccys:
                events.append((t, c, "high-impact news (feed)"))
    for t, c, label in events:
        if c in ("*",) or not CCY.get(symbol) or c in CCY[symbol]:
            if abs(now - t) <= w:
                return True, label
    return False, ""
