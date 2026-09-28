"""Market data: yfinance fetch, closed-candle filtering, resampling, and a
fast slicer used by the replay backtest. Every frame has a UTC bar-START index;
a bar is closed at time `now` iff start + interval <= now."""
import numpy as np
import pandas as pd

INTERVAL_MIN = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
TAIL = {"5m": 700, "15m": 400, "1h": 400, "4h": 200}
_AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def clean(df):
    if df is None or len(df) == 0:
        return None
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0)
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    df.index = idx.tz_convert("UTC")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def resample(df, rule: str):
    out = df.resample(rule, label="left", closed="left").agg(_AGG)
    return out.dropna(subset=["Close"])


def closed_only(df, interval: str, now: pd.Timestamp):
    if df is None:
        return None
    return df[df.index + pd.Timedelta(minutes=INTERVAL_MIN[interval]) <= now]


def closed_only_minutes(df, minutes: int, now: pd.Timestamp):
    if df is None:
        return None
    return df[df.index + pd.Timedelta(minutes=minutes) <= now]


def fetch(yf_symbol: str, interval: str, period: str):
    """Returns (DataFrame|None, error|None)."""
    try:
        import yfinance as yf
        df = yf.Ticker(yf_symbol).history(period=period, interval=interval, auto_adjust=False)
        df = clean(df)
        if df is None or len(df) < 5:
            return None, f"only {0 if df is None else len(df)} bars returned"
        return df, None
    except Exception as e:  # network / yahoo errors
        return None, str(e)


def build_frames(df5, df1h, now: pd.Timestamp | None = None):
    """Derive 15m from 5m and 4h from 1h. If `now` is given, keep closed bars only."""
    if now is not None:
        df5 = closed_only(df5, "5m", now)
        df1h = closed_only(df1h, "1h", now)
    frames = {"5m": df5, "1h": df1h}
    frames["15m"] = resample(df5, "15min") if df5 is not None and len(df5) else None
    frames["4h"] = resample(df1h, "4h") if df1h is not None and len(df1h) else None
    if now is not None:
        frames["15m"] = closed_only(frames["15m"], "15m", now)
        frames["4h"] = closed_only(frames["4h"], "4h", now)
    for k, v in list(frames.items()):
        if v is not None:
            frames[k] = v.tail(TAIL[k])
    return frames


def live_frames(yf_symbol: str, now: pd.Timestamp):
    """Fetch live data for one symbol. Returns (frames|None, [errors])."""
    errs = []
    df5, e1 = fetch(yf_symbol, "5m", "5d")
    if e1:
        errs.append(("5m", e1))
    df1h, e2 = fetch(yf_symbol, "1h", "60d")
    if e2:
        errs.append(("1h", e2))
    if df5 is None or df1h is None:
        return None, errs
    return build_frames(df5, df1h, now), errs


class FrameSlicer:
    """Backtest helper: full history once, then O(log n) 'what was closed at t'."""

    def __init__(self, df5, df1h):
        self.full = {"5m": df5, "1h": df1h,
                     "15m": resample(df5, "15min"), "4h": resample(df1h, "4h")}
        # Use python-int nanoseconds via .view("int64") — .asi8 is not always
        # comparable to Timestamp.value across pandas builds.
        self._close_ns = {}
        for k, df in self.full.items():
            ct = (df.index + pd.Timedelta(minutes=INTERVAL_MIN[k])).asi8
            # Normalize to ns matching Timestamp.value
            sample_v = int((df.index[0] + pd.Timedelta(minutes=INTERVAL_MIN[k])).value)
            sample_a = int(ct[0])
            scale = sample_v // sample_a if sample_a and sample_v % sample_a == 0 else 1
            self._close_ns[k] = ct.astype("int64") * scale

    def at(self, t: pd.Timestamp):
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        else:
            t = t.tz_convert("UTC")
        tn = int(t.value)
        out = {}
        for k, df in self.full.items():
            end = int(np.searchsorted(self._close_ns[k], tn, side="right"))
            out[k] = df.iloc[max(0, end - TAIL[k]):end]
        return out
