"""Live-price snapshot, futures→cash basis, freshness + drift validation.

Why this exists
---------------
Setups run on Yahoo *futures* (YM=F, NQ=F, ES=F, GC=F) because those have
volume, but Yahoo delays futures ~10 minutes and futures trade at a basis to
the cash/CFD price users actually trade (e.g. YM=F ≈ ^DJI + 350 pts,
GC=F ≈ spot XAU + $30). Quoting raw futures levels made alerts look far away
from the broker price and often already played out.

At alert time we:
  1. fetch fresh 1m data for the signal ticker and the cash/spot quote source;
  2. compute basis at a common minute (signal − quote);
  3. reject stale data, setups whose TP/SL already traded, and setups whose
     live price has already run toward TP beyond a tolerance;
  4. reprice entry to the live quote (market mode) and recompute SL/TP/R:R,
     then express levels in the quote (cash/CFD) price space.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd
import requests

from . import data as mdata

_GOLD_API = "https://api.gold-api.com/price/{sym}"
_spot_samples: dict[str, list[tuple[pd.Timestamp, float]]] = {}   # in-process history


@dataclass
class Snapshot:
    ok: bool
    reason: str = ""
    signal_ticker: str = ""
    quote_label: str = ""
    signal_last: float = float("nan")      # latest signal-feed 1m close (delayed)
    signal_age_min: float = float("nan")   # minutes since that 1m bar closed
    quote_live: float = float("nan")       # live price in quote (cash/CFD) space
    quote_age_min: float = float("nan")
    basis: float = 0.0                     # signal − quote
    basis_note: str = ""
    signal_1m: pd.DataFrame | None = None  # for "already hit" checks
    notes: list = field(default_factory=list)

    @property
    def live_signal_space(self) -> float:
        return self.quote_live + self.basis


def _fetch_1m(ticker: str):
    for period in ("1d", "5d"):
        df, err = mdata.fetch(ticker, "1m", period)
        if df is not None and len(df):
            return df, None
    return None, err


def _gold_api(sym: str):
    r = requests.get(_GOLD_API.format(sym=sym), timeout=8)
    r.raise_for_status()
    j = r.json()
    ts = pd.Timestamp(j.get("updatedAt") or pd.Timestamp.now(tz="UTC"))
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return float(j["price"]), ts.tz_convert("UTC")


def snapshot(sym_cfg: dict, cfg: dict, now: pd.Timestamp) -> Snapshot:
    ex = cfg.get("execution", {})
    max_basis_h = float(ex.get("max_basis_age_hours", 96))
    fresh_quote_min = float(ex.get("max_price_age_minutes", 10))
    sig = sym_cfg["yf"]
    snap = Snapshot(ok=False, signal_ticker=sig)

    s1, err = _fetch_1m(sig)
    if s1 is None:
        snap.reason = f"no 1m data for {sig}: {err}"
        return snap
    s1 = mdata.closed_only_minutes(s1, 1, now)
    if s1 is None or not len(s1):
        snap.reason = f"no closed 1m bars for {sig}"
        return snap
    snap.signal_1m = s1
    snap.signal_last = float(s1["Close"].iloc[-1])
    snap.signal_age_min = (now - (s1.index[-1] + pd.Timedelta(minutes=1))).total_seconds() / 60.0

    q = sym_cfg.get("quote") or {}
    src = q.get("source")
    if not src:
        # Signal feed IS the tradable price (spot FX).
        snap.quote_label = sig
        snap.quote_live = snap.signal_last
        snap.quote_age_min = snap.signal_age_min
        snap.basis = 0.0
        snap.basis_note = "no basis (spot feed)"
        snap.ok = True
        return snap

    if src == "yf":
        qt = q["ticker"]
        snap.quote_label = q.get("label", qt)
        q1, qerr = _fetch_1m(qt)
        if q1 is None:
            snap.reason = f"quote feed {qt} unavailable: {qerr}"
            return snap
        q1 = mdata.closed_only_minutes(q1, 1, now)
        # Basis at the most recent minute present in BOTH feeds
        common = s1.index.intersection(q1.index)
        if len(common):
            t = common[-1]
            age_h = (now - t).total_seconds() / 3600.0
            if age_h <= max_basis_h:
                snap.basis = float(s1.loc[t, "Close"] - q1.loc[t, "Close"])
                snap.basis_note = f"basis {snap.basis:+.2f} @ {t:%H:%M} UTC"
        if not snap.basis_note:
            snap.reason = f"no recent common minute between {sig} and {qt} for basis"
            return snap
        q_age = (now - (q1.index[-1] + pd.Timedelta(minutes=1))).total_seconds() / 60.0
        if q_age <= fresh_quote_min:
            snap.quote_live = float(q1["Close"].iloc[-1])
            snap.quote_age_min = q_age
        else:
            # Cash market closed (e.g. before NYSE open): derive from futures.
            snap.quote_live = snap.signal_last - snap.basis
            snap.quote_age_min = snap.signal_age_min
            snap.notes.append(f"{qt} closed — cash price derived from {sig} minus basis")
        snap.ok = True
        return snap

    if src == "gold_api":
        qs = q.get("ticker", "XAU")
        snap.quote_label = q.get("label", f"spot {qs}")
        try:
            px, ts = _gold_api(qs)
        except Exception as e:
            snap.reason = f"spot {qs} feed error: {e}"
            return snap
        hist = _spot_samples.setdefault(qs, [])
        hist.append((ts, px))
        del hist[:-500]
        # Basis at the spot sample nearest the latest signal bar time.
        sig_t = s1.index[-1] + pd.Timedelta(minutes=1)
        nearest = min(hist, key=lambda x: abs((x[0] - sig_t).total_seconds()))
        gap_min = abs((nearest[0] - sig_t).total_seconds()) / 60.0
        if gap_min <= 3:
            snap.basis = snap.signal_last - nearest[1]
            snap.basis_note = f"basis {snap.basis:+.2f} (aligned ±{gap_min:.0f}m)"
        else:
            snap.basis = snap.signal_last - px
            snap.basis_note = (f"basis {snap.basis:+.2f} (approx: futures {snap.signal_age_min:.0f}m "
                               f"delayed vs live spot)")
        snap.quote_live = px
        snap.quote_age_min = max(0.0, (now - ts).total_seconds() / 60.0)
        snap.ok = True
        return snap

    snap.reason = f"unknown quote source {src!r}"
    return snap


def validate_and_reprice(c, snap: Snapshot, cfg: dict, now: pd.Timestamp):
    """Mutates candidate `c` into live, quote-space levels. Returns (ok, reason)."""
    ex = cfg.get("execution", {})
    risk_cfg = cfg.get("risk", {})
    max_data_age = float(ex.get("max_data_age_minutes", 15))
    max_price_age = float(ex.get("max_price_age_minutes", 10))
    max_drift_atr = float(ex.get("max_drift_atr", 0.3))
    max_drift_frac = float(ex.get("max_drift_tp_frac", 0.25))
    mode = ex.get("entry_mode", "market")
    tp_mode = ex.get("tp_on_reprice", "keep_rr")
    tp_rr = float(risk_cfg.get("tp_rr", 2.5))
    min_rr = float(risk_cfg.get("min_rr", 2.5))

    if not snap.ok:
        return False, f"price check failed: {snap.reason}"
    if snap.signal_age_min > max_data_age:
        return False, f"signal feed stale ({snap.signal_age_min:.0f}m > {max_data_age:.0f}m)"
    if snap.quote_age_min > max(max_price_age, max_data_age):
        return False, f"live price stale ({snap.quote_age_min:.0f}m)"

    d = 1 if c.side == "BUY" else -1
    entry0, sl0, tp0 = c.entry, c.sl, c.tp        # signal (futures) space

    # 1) TP / SL already traded since the trigger candle closed?
    if ex.get("reject_if_tp_sl_hit", True) and snap.signal_1m is not None:
        after = snap.signal_1m[snap.signal_1m.index >= c.bar_time]
        if len(after):
            hi, lo = float(after["High"].max()), float(after["Low"].min())
            if (d == 1 and hi >= tp0) or (d == -1 and lo <= tp0):
                return False, "TP already reached since setup"
            if (d == 1 and lo <= sl0) or (d == -1 and hi >= sl0):
                return False, "SL already hit since setup"

    live_sig = snap.live_signal_space
    if (d == 1 and live_sig <= sl0) or (d == -1 and live_sig >= sl0):
        return False, "live price beyond SL"
    if (d == 1 and live_sig >= tp0) or (d == -1 and live_sig <= tp0):
        return False, "live price beyond TP"

    # 2) Drift toward TP beyond tolerance → move already played out
    fav = (live_sig - entry0) * d
    tp_dist = abs(tp0 - entry0)
    if fav > max_drift_atr * c.atr or (tp_dist > 0 and fav > max_drift_frac * tp_dist):
        return False, (f"price already moved {fav:.5g} toward TP "
                       f"(> {max_drift_atr}×ATR or {int(max_drift_frac*100)}% of TP distance)")

    # 3) Reprice
    c.meta = getattr(c, "meta", {}) or {}
    c.meta.update({
        "signal_entry": entry0, "signal_sl": sl0, "signal_tp": tp0,
        "signal_ticker": snap.signal_ticker, "quote_label": snap.quote_label,
        "basis": snap.basis, "basis_note": snap.basis_note,
        "signal_age_min": snap.signal_age_min, "quote_age_min": snap.quote_age_min,
        "candle_age_min": (now - c.bar_time).total_seconds() / 60.0,
        "live_quote": snap.quote_live, "drift": fav, "entry_mode": mode,
        "price_notes": list(snap.notes),
    })
    if mode == "limit":
        entry = entry0
    else:
        entry = live_sig
    risk = (entry - sl0) * d
    if risk <= 0:
        return False, "no risk room after reprice"
    if tp_mode == "keep_target":
        tp = tp0
    else:
        tp = entry + d * tp_rr * risk
    rr = abs(tp - entry) / risk
    if rr + 1e-9 < min_rr:
        return False, f"R:R after reprice {rr:.2f} < {min_rr}"

    # Express in quote (cash/CFD) space
    b = snap.basis
    c.entry, c.sl, c.tp = entry - b, sl0 - b, tp - b
    c.zone = c.zone  # dedupe stays in signal space
    return True, "ok"
