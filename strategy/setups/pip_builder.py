"""'1000 Pip Builder' — experimental, forex only, DISABLED by default.

Rules turned into code from a teaching method (the author published no exact
numbers; every parameter marked (assumed) below is a guess that the research
backtest tunes — this is NOT a proven system, see docs/STRATEGY_1000PIP_BUILDER.md):

 1. Trend: Daily AND 4H structure agree (HH+HL = up, LH+LL = down); ranging → skip.
 2. Location (1H): price at a support/resistance ZONE (cluster of prior 1H swing
    points, width ≈ zone_width_atr × ATR(14) (assumed 0.3)) or at the 1H Bollinger
    Band (SMA20, 2σ). Buys only at support / lower band in an uptrend, sells only at
    resistance / upper band in a downtrend. A broken zone that is retested from the
    other side (breakout → retest → continuation) also counts.
 3. Trigger on 5m/15m, only AT the location: double bottom/top (entry on neckline
    break) or engulfing candle (close beyond the previous candle's high/low).
 4. Entry: close of the trigger bar (neckline break bar for W/M).
 5. SL: pattern extreme ± sl_buffer_pips (assumed 1.5). Reject if SL > 0.5 × ATR(1H).
 6. TP: nearest prior 1H swing high/low, opposite zone edge or opposite 1H band.
    Skip if TP < 10 pips or R:R < 1.0 (assumed).
 7. Filters: no entries ±30 min around high-impact news (static NFP rule + optional
    feed, see strategy/news.py); ATR sanity: TP distance ≤ tp_max_atr × ATR(1H).
Closed candles only (no repaint). All pivot points are confirmed ones (k bars after).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..checklist import score as score_checklist
from ..common import Candidate
from ..indicators import atr, pivots
from ..news import blackout
from ..risk_sizing import pip_size

DEFAULTS = {
    "trigger_tfs": ["5m", "15m"],
    "trend_k_daily": 2, "trend_k_4h": 2,         # swing strength for the trend filter
    "zone_swing_k": 3, "zone_lookback_bars": 150,
    "zone_width_atr": 0.3,                        # (assumed)
    "min_touches": 2,                             # swing points needed to form a zone
    "touch_tol_atr": 0.1,
    "use_bands": True, "use_zones": True, "use_retest": True,
    "retest_lookback_bars": 30,
    "bb_period": 20, "bb_sd": 2.0,
    "pattern_swing_k": 2, "db_tol_atr": 0.25, "db_min_sep_bars": 4, "db_max_sep_bars": 40,
    "db_min_height_atr": 0.15, "pattern_max_age_bars": 12,
    "use_double": True, "use_engulf": True,
    "sl_buffer_pips": 1.5,                        # (assumed)
    "sl_max_atr": 0.5, "min_sl_pips": 3.0,
    "sl_ref": "extreme",                          # or "extreme_or_zone"
    "min_tp_pips": 10.0, "min_rr": 1.0,           # (assumed R:R)
    "tp_pick": "nearest",                         # or "nearest_beyond_min"
    "tp_max_atr": 2.5,                            # (assumed) ATR sanity check
    "tp_pips": None,                              # FIXED target in pips (e.g. 6 = scalp); None = structural TP
    "tp1_pips": None,                             # optional partial target
    "active_hours_utc": None,                     # e.g. ["07:00", "20:00"]
}
_CTX_CACHE: dict = {}


def params(setup_cfg: dict | None) -> dict:
    p = dict(DEFAULTS)
    p.update({k: v for k, v in (setup_cfg or {}).items() if k in DEFAULTS})
    return p


# ── structure helpers (pure) ──────────────────────────────────────────────────

def trend_dir(df: pd.DataFrame | None, k: int, min_bars: int = 12) -> int:
    """+1 up (HH & HL), -1 down (LH & LL), 0 ranging, from CONFIRMED swing points."""
    if df is None or len(df) < min_bars:
        return 0
    hi, lo = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    ph, pl = pivots(hi, lo, k)
    ih, il = np.flatnonzero(ph), np.flatnonzero(pl)
    if len(ih) < 2 or len(il) < 2:
        return 0
    hh, hl = hi[ih[-1]] > hi[ih[-2]], lo[il[-1]] > lo[il[-2]]
    lh, ll = hi[ih[-1]] < hi[ih[-2]], lo[il[-1]] < lo[il[-2]]
    return 1 if hh and hl else -1 if lh and ll else 0


def cluster_levels(prices, width: float, min_touches: int = 2):
    """Group swing prices within `width` of the cluster's lowest member → zones."""
    xs = sorted(float(p) for p in prices)
    out, cur = [], []
    for p in xs:
        if cur and p - cur[0] > width:
            out.append(cur); cur = []
        cur.append(p)
    if cur:
        out.append(cur)
    zones = []
    for c in out:
        if len(c) >= min_touches:
            mid = sum(c) / len(c)
            zones.append((min(min(c), mid - width / 2), max(max(c), mid + width / 2), len(c)))
    return zones


@dataclass
class Ctx:
    atr1h: float
    bb_lo: float
    bb_up: float
    bb_mid: float
    support: list = field(default_factory=list)      # (lo, hi, kind)
    resistance: list = field(default_factory=list)
    swing_highs: list = field(default_factory=list)  # prices (confirmed 1H pivots)
    swing_lows: list = field(default_factory=list)
    trend_d: int = 0
    trend_4h: int = 0
    last_close: float = 0.0

    @property
    def trend(self) -> int:
        return self.trend_d if self.trend_d == self.trend_4h else 0


def build_context(frames: dict, p: dict) -> Ctx | None:
    h1 = frames.get("1h")
    if h1 is None or len(h1) < 60:
        return None
    hi, lo, cl = (h1[c].to_numpy(float) for c in ("High", "Low", "Close"))
    a = float(atr(h1).iloc[-1])
    if not np.isfinite(a) or a <= 0:
        return None
    n = int(p["bb_period"])
    win = cl[-n:]
    mid, sd = float(win.mean()), float(win.std(ddof=0))
    ctx = Ctx(atr1h=a, bb_mid=mid, bb_up=mid + p["bb_sd"] * sd, bb_lo=mid - p["bb_sd"] * sd,
              last_close=float(cl[-1]),
              trend_d=trend_dir(frames.get("1d"), int(p["trend_k_daily"]), 10),
              trend_4h=trend_dir(frames.get("4h"), int(p["trend_k_4h"]), 20))
    k = int(p["zone_swing_k"])
    ph, pl = pivots(hi, lo, k)
    start = max(0, len(h1) - int(p["zone_lookback_bars"]))
    ih = [i for i in np.flatnonzero(ph) if i >= start]
    il = [i for i in np.flatnonzero(pl) if i >= start]
    ctx.swing_highs = [float(hi[i]) for i in ih]
    ctx.swing_lows = [float(lo[i]) for i in il]
    w = p["zone_width_atr"] * a
    res = cluster_levels(ctx.swing_highs, w, int(p["min_touches"]))
    sup = cluster_levels(ctx.swing_lows, w, int(p["min_touches"]))
    ctx.resistance = [(l, h, "resistance") for l, h, _ in res]
    ctx.support = [(l, h, "support") for l, h, _ in sup]
    if p["use_retest"]:
        rb = int(p["retest_lookback_bars"])
        recent = cl[-rb:]
        last = cl[-1]
        for l, h, _ in res:   # resistance broken upwards and still above → now support
            if recent.max() > h + 0.1 * a and last > h and cl[-rb:].min() < h + 0.1 * a + 5 * a:
                ctx.support.append((l, h, "retest-support"))
        for l, h, _ in sup:   # support broken downwards and still below → now resistance
            if recent.min() < l - 0.1 * a and last < l:
                ctx.resistance.append((l, h, "retest-resistance"))
    return ctx


def get_context(symbol: str, frames: dict, p: dict) -> Ctx | None:
    h1 = frames.get("1h")
    if h1 is None or len(h1) == 0:
        return None
    key = (symbol, h1.index[-1].value, frames["4h"].index[-1].value if frames.get("4h") is not None and len(frames["4h"]) else 0,
           tuple(sorted((k, str(v)) for k, v in p.items())))
    if key not in _CTX_CACHE:
        if len(_CTX_CACHE) > 4000:
            _CTX_CACHE.clear()
        _CTX_CACHE[key] = build_context(frames, p)
    return _CTX_CACHE[key]


# ── triggers on the 5m / 15m chart ────────────────────────────────────────────

def detect_triggers(df: pd.DataFrame, ctx: Ctx, p: dict, pip: float):
    """Closed-candle triggers on the LAST bar of `df`. Yields dicts:
    {side, kind, entry, extreme, bar_i}. Location is checked by the caller."""
    out = []
    n = len(df)
    if n < 30:
        return out
    t = df.tail(120)
    hi, lo, op, cl = (t[c].to_numpy(float) for c in ("High", "Low", "Open", "Close"))
    L = len(t) - 1
    if p["use_engulf"] and L >= 1:
        if cl[L - 1] < op[L - 1] and cl[L] > op[L] and cl[L] > hi[L - 1]:
            out.append({"side": "BUY", "kind": "bullish engulfing", "entry": cl[L], "extreme": min(lo[L], lo[L - 1])})
        if cl[L - 1] > op[L - 1] and cl[L] < op[L] and cl[L] < lo[L - 1]:
            out.append({"side": "SELL", "kind": "bearish engulfing", "entry": cl[L], "extreme": max(hi[L], hi[L - 1])})
    if p["use_double"]:
        k = int(p["pattern_swing_k"])
        ph, pl = pivots(hi, lo, k)
        tol = p["db_tol_atr"] * ctx.atr1h
        minh = p["db_min_height_atr"] * ctx.atr1h
        sep_lo, sep_hi, age = int(p["db_min_sep_bars"]), int(p["db_max_sep_bars"]), int(p["pattern_max_age_bars"])
        il = np.flatnonzero(pl)
        if len(il) >= 2:
            j, i = il[-1], il[-2]
            neck = float(hi[i:j + 1].max())
            if (sep_lo <= j - i <= sep_hi and abs(lo[i] - lo[j]) <= tol and neck - max(lo[i], lo[j]) >= minh
                    and L - j <= age and cl[L] > neck and (L - 1 <= j or cl[j + 1:L].max() <= neck)
                    and lo[j + 1:L + 1].min() >= lo[j] - 1e-12):
                out.append({"side": "BUY", "kind": "double bottom (neckline break)", "entry": cl[L],
                            "extreme": float(min(lo[i], lo[j]))})
        ih = np.flatnonzero(ph)
        if len(ih) >= 2:
            j, i = ih[-1], ih[-2]
            neck = float(lo[i:j + 1].min())
            if (sep_lo <= j - i <= sep_hi and abs(hi[i] - hi[j]) <= tol and min(hi[i], hi[j]) - neck >= minh
                    and L - j <= age and cl[L] < neck and (L - 1 <= j or cl[j + 1:L].min() >= neck)
                    and hi[j + 1:L + 1].max() <= hi[j] + 1e-12):
                out.append({"side": "SELL", "kind": "double top (neckline break)", "entry": cl[L],
                            "extreme": float(max(hi[i], hi[j]))})
    return out


def location(side: str, extreme: float, ctx: Ctx, p: dict):
    """Is the pattern extreme AT a zone / band for this side? Returns (ok, note, zone_or_None)."""
    a = ctx.atr1h
    tol = p["touch_tol_atr"] * a
    w = p["zone_width_atr"] * a
    if side == "BUY":
        if p["use_zones"]:
            for lo_, hi_, kind in ctx.support:
                if lo_ - w <= extreme <= hi_ + tol:
                    return True, f"{kind} zone {lo_:.5g}–{hi_:.5g}", (lo_, hi_)
        if p["use_bands"] and extreme <= ctx.bb_lo + tol:
            return True, f"touch of 1H lower Bollinger band {ctx.bb_lo:.5g}", None
    else:
        if p["use_zones"]:
            for lo_, hi_, kind in ctx.resistance:
                if lo_ - tol <= extreme <= hi_ + w:
                    return True, f"{kind} zone {lo_:.5g}–{hi_:.5g}", (lo_, hi_)
        if p["use_bands"] and extreme >= ctx.bb_up - tol:
            return True, f"touch of 1H upper Bollinger band {ctx.bb_up:.5g}", None
    return False, "", None


def pick_tp(side: str, entry: float, ctx: Ctx, p: dict, pip: float):
    """Nearest prior swing / opposite zone edge / opposite band beyond entry."""
    if side == "BUY":
        cands = [x for x in ctx.swing_highs if x > entry] + [z[0] for z in ctx.resistance if z[0] > entry] \
            + ([ctx.bb_up] if ctx.bb_up > entry else [])
        cands.sort()
    else:
        cands = [x for x in ctx.swing_lows if x < entry] + [z[1] for z in ctx.support if z[1] < entry] \
            + ([ctx.bb_lo] if ctx.bb_lo < entry else [])
        cands.sort(reverse=True)
    if not cands:
        return None
    if p["tp_pick"] == "nearest_beyond_min":
        for c in cands:
            if abs(c - entry) >= p["min_tp_pips"] * pip:
                return c
        return None
    return cands[0]


def _in_hours(now, hours):
    if not hours:
        return True
    hm = now.hour * 60 + now.minute
    s = int(hours[0][:2]) * 60 + int(hours[0][3:])
    e = int(hours[1][:2]) * 60 + int(hours[1][3:])
    return s <= hm < e


def evaluate(symbol, frames, cfg, setup_cfg, now, priority=99):
    p = params(setup_cfg)
    if not _in_hours(now, p["active_hours_utc"]):
        return None
    ctx = get_context(symbol, frames, p)
    if ctx is None or ctx.trend == 0:
        return None
    pip = pip_size(symbol)
    best = None
    ivl = {"5m": 5, "15m": 15}
    for tf in p["trigger_tfs"]:
        df = frames.get(tf)
        if df is None or len(df) < 30:
            continue
        bar_close = df.index[-1] + pd.Timedelta(minutes=ivl[tf])
        if (now - bar_close).total_seconds() > 20 * 60 or (now - bar_close).total_seconds() < -60:
            continue
        for tr in detect_triggers(df, ctx, p, pip):
            side = tr["side"]
            if (ctx.trend == 1) != (side == "BUY"):
                continue
            ok, loc_note, zone = location(side, tr["extreme"], ctx, p)
            if not ok:
                continue
            entry, ext = tr["entry"], tr["extreme"]
            ref = ext
            if p["sl_ref"] == "extreme_or_zone" and zone:
                ref = min(ext, zone[0]) if side == "BUY" else max(ext, zone[1])
            buf = p["sl_buffer_pips"] * pip
            sl = ref - buf if side == "BUY" else ref + buf
            risk = abs(entry - sl)
            if risk <= 0 or risk > p["sl_max_atr"] * ctx.atr1h or risk < p["min_sl_pips"] * pip:
                continue
            if p.get("tp_pips"):
                tp = entry + (1 if side == "BUY" else -1) * float(p["tp_pips"]) * pip
                min_tp = float(p["tp_pips"])
            else:
                tp = pick_tp(side, entry, ctx, p, pip)
                min_tp = p["min_tp_pips"]
            if tp is None:
                continue
            dist = abs(tp - entry)
            if dist < min_tp * pip - 1e-12 or dist / risk < p["min_rr"] or dist > p["tp_max_atr"] * ctx.atr1h:
                continue
            blocked, why = blackout(bar_close, symbol, cfg.get("news"))
            if blocked:
                continue
            cand = (dist / risk, tf, tr, loc_note, zone, sl, tp, bar_close)
            if best is None or cand[0] > best[0]:
                best = cand
    if best is None:
        return None
    rr, tf, tr, loc_note, zone, sl, tp, bar_close = best
    side, entry = tr["side"], tr["entry"]
    factors = {"trend_agree": True, "at_zone_or_band": True, "trigger_pattern": True,
               "sl_within_atr": True, "tp_min_rr": True, "news_clear": True}
    checklist_cfg = setup_cfg.get("checklist") or {k: {"weight": 1, "required": True} for k in factors}
    sc, mx, missing, lines = score_checklist(factors, checklist_cfg)
    arrow = "up" if side == "BUY" else "down"
    notes = [
        f"Daily + 4H trend agree: {arrow}trend",
        f"Location (1H): {loc_note}",
        f"Trigger ({tf}): {tr['kind']}",
        f"SL {abs(entry - sl) / pip:.1f} pips beyond pattern extreme · TP {abs(tp - entry) / pip:.1f} pips "
        + ("(fixed scalp target)" if p.get("tp_pips") else "(nearest swing / zone / band)"),
        f"1H ATR {ctx.atr1h / pip:.1f} pips · experimental method, parameters partly assumed",
    ]
    meta = {"min_rr": float(p["min_rr"]), "tp_on_reprice": "keep_target", "trigger_tf": tf,
            "pattern": tr["kind"], "location": loc_note, "sl_pips": round(abs(entry - sl) / pip, 1),
            "tp_pips": round(abs(tp - entry) / pip, 1),
            # re-checked after live repricing (entry moves between trigger close and alert)
            "min_risk": p["min_sl_pips"] * pip, "max_risk": p["sl_max_atr"] * ctx.atr1h}
    if p.get("tp1_pips"):
        meta["tp1"] = entry + (1 if side == "BUY" else -1) * p["tp1_pips"] * pip
    zc = (zone[0] + zone[1]) / 2 if zone else (ctx.bb_lo if side == "BUY" else ctx.bb_up)
    return Candidate(symbol=symbol, setup="pip_builder", label=setup_cfg.get("label", "1000 Pip Builder"),
                     side=side, entry=float(entry), sl=float(sl), tp=float(tp), bar_time=bar_close,
                     atr=ctx.atr1h, zone=float(zc), factors=factors, notes=notes, score=sc, max_score=mx,
                     priority=priority, checklist_lines=lines, meta=meta)
