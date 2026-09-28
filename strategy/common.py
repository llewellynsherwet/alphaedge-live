"""Shared types and context factors (HTF bias, premium/discount, time windows)."""
from dataclasses import dataclass, field
from datetime import time as dtime
from zoneinfo import ZoneInfo

import pandas as pd

from .indicators import ema

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


@dataclass
class Candidate:
    symbol: str
    setup: str
    label: str
    side: str                 # "BUY" | "SELL"
    entry: float
    sl: float
    tp: float
    bar_time: pd.Timestamp    # CLOSE time of the trigger candle (UTC)
    atr: float
    zone: float               # price used for the dedupe zone key
    factors: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    score: int = 0
    max_score: int = 0
    priority: int = 99
    checklist_lines: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def rr(self) -> float:
        return abs(self.tp - self.entry) / self.risk if self.risk > 0 else 0.0

    @property
    def zone_key(self) -> str:
        bucket = max(self.atr * 0.5, abs(self.entry) * 1e-6, 1e-9)
        return f"{self.symbol}|{self.side}|{self.setup}|{int(round(self.zone / bucket))}"


def parse_hhmm(s: str) -> dtime:
    hh, mm = str(s).split(":")
    return dtime(int(hh), int(mm))


def minutes_of(t) -> int:
    return t.hour * 60 + t.minute


def in_window(ts_utc: pd.Timestamp, start: str, end: str) -> bool:
    m = minutes_of(ts_utc)
    a, b = minutes_of(parse_hhmm(start)), minutes_of(parse_hhmm(end))
    return a <= m < b


def in_any(ts_utc, windows) -> bool:
    return any(in_window(ts_utc, w["start"], w["end"]) for w in windows or [])


def htf_bias(frames) -> tuple[str, str]:
    """4H close vs EMA20 plus 1H EMA20/EMA50 stack, closed candles only."""
    h4, h1 = frames.get("4h"), frames.get("1h")
    if h4 is None or h1 is None or len(h4) < 25 or len(h1) < 60:
        return "neutral", "HTF: insufficient data"
    c4 = h4["Close"]; c1 = h1["Close"]
    e4 = ema(c4, 20).iloc[-1]
    e20, e50 = ema(c1, 20).iloc[-1], ema(c1, 50).iloc[-1]
    if c4.iloc[-1] > e4 and e20 > e50 and c1.iloc[-1] > e50:
        return "bull", "HTF bullish (4H > EMA20, 1H EMA20 > EMA50)"
    if c4.iloc[-1] < e4 and e20 < e50 and c1.iloc[-1] < e50:
        return "bear", "HTF bearish (4H < EMA20, 1H EMA20 < EMA50)"
    return "neutral", "HTF mixed / ranging"


def premium_discount(frames, side: str, price: float, bars: int = 40) -> tuple[bool, str]:
    """Buy in the discount half / sell in the premium half of the recent 1H dealing range."""
    h1 = frames.get("1h")
    if h1 is None or len(h1) < bars:
        return False, "P/D: insufficient data"
    rng = h1.tail(bars)
    hi, lo = float(rng["High"].max()), float(rng["Low"].min())
    if hi <= lo:
        return False, "P/D: flat range"
    pos = (price - lo) / (hi - lo)
    ok = pos < 0.5 if side == "BUY" else pos > 0.5
    zone = "discount" if pos < 0.5 else "premium"
    return ok, f"price in {zone} ({pos*100:.0f}% of 1H range)"


def price_decimals(ref: float) -> int:
    ax = abs(ref)
    if ax >= 1000:
        return 1
    if ax >= 100:
        return 2
    if ax >= 10:
        return 3
    return 5


def fmt_price(x: float, ref: float | None = None) -> str:
    """Format a price; pass `ref` (e.g. the entry) so SL/TP share its decimals."""
    d = price_decimals(x if ref is None else ref)
    return f"{x:,.{d}f}"
