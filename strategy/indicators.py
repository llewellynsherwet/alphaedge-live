"""Pure indicator helpers (pandas / numpy only)."""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def pivots(high: np.ndarray, low: np.ndarray, k: int):
    """Fractal swing points. A pivot high at i is strictly higher than the k bars
    to its left and not exceeded by the k bars to its right (mirror for lows).
    A pivot at i is only *known* once bar i+k has closed."""
    n = len(high)
    ph = np.zeros(n, dtype=bool)
    pl = np.zeros(n, dtype=bool)
    if n < 2 * k + 1:
        return ph, pl
    wh = sliding_window_view(high, 2 * k + 1)
    wl = sliding_window_view(low, 2 * k + 1)
    mid_h = wh[:, k]
    mid_l = wl[:, k]
    left_h = wh[:, :k].max(axis=1)
    right_h = wh[:, k + 1:].max(axis=1)
    left_l = wl[:, :k].min(axis=1)
    right_l = wl[:, k + 1:].min(axis=1)
    ph[k:n - k] = (mid_h > left_h) & (mid_h >= right_h)
    pl[k:n - k] = (mid_l < left_l) & (mid_l <= right_l)
    return ph, pl


def anchored_vwap(df: pd.DataFrame, start_idx: int) -> np.ndarray | None:
    """VWAP of bars df.iloc[start_idx:], returned aligned to that slice.
    Returns None when the feed has no volume (e.g. yfinance spot FX)."""
    sub = df.iloc[start_idx:]
    vol = sub["Volume"].to_numpy(dtype=float)
    if len(sub) == 0 or np.nansum(vol) <= 0:
        return None
    tp = ((sub["High"] + sub["Low"] + sub["Close"]) / 3.0).to_numpy(dtype=float)
    cv = np.cumsum(vol)
    with np.errstate(invalid="ignore", divide="ignore"):
        vw = np.cumsum(tp * vol) / cv
    # leading zero-volume bars: fall back to typical price
    vw = np.where(cv > 0, vw, tp)
    return vw
