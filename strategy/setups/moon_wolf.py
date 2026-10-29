"""🐺 Moon Wolf (15m scan) — supply/demand zones + 15m confirmation.

Ported from Moon Wolf's /workspace/fx/a.py (logic kept 1:1 where possible):
  * Trend: swing highs/lows (w=3) on the Daily (6 months) and 4H (1H resampled) charts.
    Bias = up / down / range exactly as a.py combines them; trade WITH the bias only.
  * Zones (1H last 30 days + 4H): base candle body < 50% of its range, then the next
    1–3 candles close > 1.5 × ATR(14) away. Broken zones dropped; nearest two
    non-overlapping zones on each side of price are kept.
  * Entry: 15m confirmation inside the nearest zone (tolerance 0.2 × 1H ATR) —
    double top/bottom with a neckline close within the last 8 bars (entry = neckline)
    or an engulfing candle (entry = its close).
  * SL = pattern extreme ± 0.3 × 1H ATR.  TP1 = max(1R, 10 pips).  TP2 = opposite zone edge.
    Needs R:R ≥ 1.5 to TP2 and TP2 beyond TP1. Extra live filters from Moon Wolf's spec:
    skip if price already ran to near TP1, skip ±30 min around high-impact news.
  * Pip / point sizes per symbol (sym cfg `pip`): FX 0.0001 (JPY 0.01), XAUUSD 0.10, US30 1.0,
    so "10 pips" = $1.00 on gold and 10 points on US30.
"""
from __future__ import annotations

import pandas as pd

from ..common import Candidate
from ..news import blackout

DEFAULTS = {"label": "🐺 Moon Wolf (15m scan)", "zone_atr_mult": 1.5, "tol_atr": 0.2,
            "sl_buffer_atr": 0.3, "min_tp1_pips": 10.0, "min_rr": 1.5, "look_15m": 32, "recent_15m": 8,
            "near_tp1_frac": 0.8, "h1_zone_days": 30, "daily_period": "6mo"}

_DAILY_CACHE: dict = {}


def default_pip(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def _atr(d, n=14):
    pc = d.Close.shift()
    tr = pd.concat([d.High - d.Low, (d.High - pc).abs(), (d.Low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def trend(d, w=3):
    h = d.High; l = d.Low
    ph = [h.iloc[i] for i in range(w, len(d) - w) if h.iloc[i] == h.iloc[i - w:i + w + 1].max()]
    pl = [l.iloc[i] for i in range(w, len(d) - w) if l.iloc[i] == l.iloc[i - w:i + w + 1].min()]
    if len(ph) < 2 or len(pl) < 2:
        return "range"
    hh = ph[-1] > ph[-2]; hl = pl[-1] > pl[-2]
    return "up" if hh and hl else "down" if (not hh and not hl) else "range"


def zones(d, tf, mult=1.5):
    a = _atr(d); out = []
    for i in range(14, len(d) - 3):
        b = d.iloc[i]; A = a.iloc[i]
        if abs(b.Close - b.Open) > 0.5 * (b.High - b.Low + 1e-12):
            continue
        nxt = d.iloc[i + 1:i + 4]
        up = nxt.Close.max() - b.High; dn = b.Low - nxt.Close.min()
        if up > mult * A: typ = "demand"
        elif dn > mult * A: typ = "supply"
        else: continue
        lo, hi = b.Low, b.High; after = d.iloc[i + 4:]
        touched = (after.Low <= hi).any() if typ == "demand" else (after.High >= lo).any()
        broken = (after.Close < lo).any() if typ == "demand" else (after.Close > hi).any()
        if broken:
            continue
        out.append(dict(type=typ, lo=float(lo), hi=float(hi), tf=tf, fresh=bool(not touched), t=str(d.index[i])))
    return out


def _pick(L):
    o = []
    for z in L:
        if all(z["hi"] < y["lo"] or z["lo"] > y["hi"] for y in o):
            o.append(z)
        if len(o) == 2:
            break
    return o


def confirm15(M, z, side, a1, pip, tp2, look=32, recent=8, min_tp1_pips=10.0, min_rr=1.5):
    """Same as a.py confirm15. status: CONFIRMED / PATTERN_BUT_RR_FAIL / AT_ZONE_WAITING / NOT_AT_ZONE"""
    m = M.iloc[-look:]; tol = 0.2 * a1; px = M.Close.iloc[-1]
    reached = (m.High >= z["lo"]).any() if side == "sell" else (m.Low <= z["hi"]).any()
    out = dict(side=side, zone=z, reached=bool(reached), price=float(px))
    if not reached:
        out["status"] = "NOT_AT_ZONE"; return out
    inz = lambda hi, lo: (hi >= z["lo"] - tol and lo <= z["hi"] + tol)
    n = len(m); pats = []
    w = 2; H = m.High.values; L = m.Low.values; C = m.Close.values; O = m.Open.values
    if side == "sell":
        sw = [i for i in range(w, n - w) if H[i] == H[i - w:i + w + 1].max() and inz(H[i], H[i])]
        for a in range(len(sw)):
            for b in range(a + 1, len(sw)):
                i, j = sw[a], sw[b]
                if j - i < 3 or abs(H[i] - H[j]) > tol: continue
                neck = L[i:j + 1].min(); brk = [k for k in range(j + 1, n) if C[k] < neck]
                if brk and brk[0] >= n - recent and H[brk[0]:].max() <= max(H[i], H[j]):
                    pats.append(dict(kind="double top", k=brk[0], ib=m.index[brk[0]], entry=neck, ext=max(H[i], H[j])))
        for k in range(max(1, n - recent), n):
            if C[k-1] > O[k-1] and C[k] < O[k] and O[k] >= C[k-1] and C[k] <= O[k-1] and inz(max(H[k], H[k-1]), max(H[k], H[k-1])):
                pats.append(dict(kind="bearish engulfing", k=k, ib=m.index[k], entry=C[k], ext=max(H[k], H[k-1])))
    else:
        sw = [i for i in range(w, n - w) if L[i] == L[i - w:i + w + 1].min() and inz(L[i], L[i])]
        for a in range(len(sw)):
            for b in range(a + 1, len(sw)):
                i, j = sw[a], sw[b]
                if j - i < 3 or abs(L[i] - L[j]) > tol: continue
                neck = H[i:j + 1].max(); brk = [k for k in range(j + 1, n) if C[k] > neck]
                if brk and brk[0] >= n - recent and L[brk[0]:].min() >= min(L[i], L[j]):
                    pats.append(dict(kind="double bottom", k=brk[0], ib=m.index[brk[0]], entry=neck, ext=min(L[i], L[j])))
        for k in range(max(1, n - recent), n):
            if C[k-1] < O[k-1] and C[k] > O[k] and O[k] <= C[k-1] and C[k] >= O[k-1] and inz(min(L[k], L[k-1]), min(L[k], L[k-1])):
                pats.append(dict(kind="bullish engulfing", k=k, ib=m.index[k], entry=C[k], ext=min(L[k], L[k-1])))
    if not pats:
        out["status"] = "AT_ZONE_WAITING"; return out
    p = sorted(pats, key=lambda p: p["ib"])[-1]; sg = 1 if side == "buy" else -1
    e = float(p["entry"]); sl = float(p["ext"]) - sg * 0.3 * a1; r = abs(e - sl)
    tp1 = e + sg * max(min_tp1_pips * pip, r); rr = (tp2 - e) * sg / r if (tp2 is not None and r > 0) else 0
    out.update(pattern=p, entry=e, sl=sl, tp1=tp1, tp2=tp2, risk=r / pip, rr=rr,
               after=m.iloc[p["k"] + 1:])
    out["status"] = "CONFIRMED" if tp2 is not None and rr >= min_rr and (tp2 - tp1) * sg > 0 else "PATTERN_BUT_RR_FAIL"
    return out


def _daily(sym_cfg: dict, frames: dict, now, period: str):
    if frames.get("1d_long") is not None:            # backtest / tests inject it
        return frames["1d_long"]
    t = sym_cfg.get("yf")
    key = (t, now.strftime("%Y-%m-%d"))
    if key not in _DAILY_CACHE:
        from ..data import fetch
        df, _err = fetch(t, "1d", period)
        _DAILY_CACHE.clear() if len(_DAILY_CACHE) > 64 else None
        _DAILY_CACHE[key] = df
    df = _DAILY_CACHE[key]
    return df[df.index <= now] if df is not None else None


def analyse(symbol: str, frames: dict, cfg: dict, scfg: dict, now, sym_cfg: dict | None = None) -> dict:
    """Full a.py-style read of one symbol (used by evaluate and by the UI/tests)."""
    s = dict(DEFAULTS); s.update(scfg or {})
    sym_cfg = sym_cfg or next((x for x in cfg.get("symbols", []) if x.get("name") == symbol), {}) or {}
    pip = float(sym_cfg.get("pip") or default_pip(symbol))
    H1, M15 = frames.get("1h"), frames.get("15m")
    D = _daily(sym_cfg, frames, now, s["daily_period"])
    if D is None or H1 is None or M15 is None or len(D) < 30 or len(H1) < 50 or len(M15) < 40:
        return {"status": "NODATA"}
    H4 = H1.resample("4h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    h1 = H1[H1.index >= H1.index[-1] - pd.Timedelta(days=int(s["h1_zone_days"]))]
    px = float(M15.Close.iloc[-1]); a1 = float(_atr(h1).iloc[-1])
    td, t4 = trend(D), trend(H4)
    Z = zones(H4, "4H", s["zone_atr_mult"]) + zones(h1, "1H", s["zone_atr_mult"])
    dem = _pick(sorted([z for z in Z if z["type"] == "demand" and z["hi"] < px], key=lambda z: -z["hi"]))
    sup = _pick(sorted([z for z in Z if z["type"] == "supply" and z["lo"] > px], key=lambda z: z["lo"]))
    bias = ("up" if td == "up" and t4 != "down" or (t4 == "up" and td != "down")
            else "down" if td == "down" and t4 != "up" or (t4 == "down" and td != "up") else "range")
    kw = dict(look=int(s["look_15m"]), recent=int(s["recent_15m"]), min_tp1_pips=float(s["min_tp1_pips"]),
              min_rr=float(s["min_rr"]))
    conf = []
    if sup: conf.append(confirm15(M15, sup[0], "sell", a1, pip, dem[0]["hi"] if dem else None, **kw))
    if dem: conf.append(confirm15(M15, dem[0], "buy", a1, pip, sup[0]["lo"] if sup else None, **kw))
    for c in conf:
        c["with_bias"] = (c["side"] == "sell" and bias == "down") or (c["side"] == "buy" and bias == "up")
    return dict(status="OK", daily=td, h4=t4, bias=bias, price=px, atr1h=a1, pip=pip, dem=dem, sup=sup, conf=conf,
                trades=[c for c in conf if c["status"] == "CONFIRMED" and c["with_bias"]])


def zone_id(symbol, side, lo, hi, pip):
    """Deterministic zone identity: symbol|side|lo|hi rounded to 5 pips, so the same
    1H zone keeps the same id hour-to-hour (and across restarts)."""
    q = 5 * float(pip or 0.0001)
    return f"{symbol}|{side}|{round(lo / q) * q:.6g}|{round(hi / q) * q:.6g}"


def evaluate(symbol, frames, cfg, scfg, now, priority=99):
    s = dict(DEFAULTS); s.update(scfg or {})
    sym_cfg = next((x for x in cfg.get("symbols", []) if x.get("name") == symbol), {}) or {}
    r = analyse(symbol, frames, cfg, s, now, sym_cfg)
    if r.get("status") != "OK" or not r["trades"]:
        return None
    t = sorted(r["trades"], key=lambda c: c["pattern"]["ib"])[-1]
    sg = 1 if t["side"] == "buy" else -1
    pip = r["pip"]
    # Live filter: price already ran to near TP1 (or traded through SL) since the trigger bar
    aft = t["after"]
    tp1_dist = abs(t["tp1"] - t["entry"])
    if len(aft):
        best = float(aft.High.max() if sg == 1 else aft.Low.min())
        worst = float(aft.Low.min() if sg == 1 else aft.High.max())
        if (best - t["entry"]) * sg >= float(s["near_tp1_frac"]) * tp1_dist:
            return None
        if (worst - t["sl"]) * sg <= 0:
            return None
    if (r["price"] - t["entry"]) * sg >= float(s["near_tp1_frac"]) * tp1_dist:
        return None
    blocked, why = blackout(now, symbol, cfg.get("news"))
    if blocked:
        return None
    p = t["pattern"]; z = t["zone"]
    bar_close = pd.Timestamp(p["ib"]) + pd.Timedelta(minutes=15)
    side = "BUY" if sg == 1 else "SELL"
    dec = 3 if pip >= 0.01 and r["price"] < 1000 else 5 if pip < 0.01 else 2
    unit = "pips" if sym_cfg.get("pip_label", "pips") == "pips" else sym_cfg.get("pip_label")
    lot = sym_cfg.get("lot")
    checklist = [
        f"✅ Trend: daily {r['daily']} · 4H {r['h4']} → bias {r['bias']}",
        f"✅ {z['tf']} {'demand' if sg == 1 else 'supply'} zone {z['lo']:.{dec}f}–{z['hi']:.{dec}f} ({'fresh' if z['fresh'] else 'tested'})",
        f"✅ 15m {p['kind']}",
        f"✅ R:R to TP2 1:{t['rr']:.1f} (min {s['min_rr']})",
        "✅ News clear",
    ]
    return Candidate(
        symbol=symbol, setup="moon_wolf", label=s["label"], side=side,
        entry=float(t["entry"]), sl=float(t["sl"]), tp=float(t["tp2"]), bar_time=bar_close,
        atr=r["atr1h"], zone=(z["lo"] + z["hi"]) / 2, score=5, max_score=5, priority=priority,
        checklist_lines=checklist,
        notes=[f"🐺 {p['kind']} at {z['tf']} {'demand' if sg == 1 else 'supply'} — risk {t['risk']:.1f} {unit}"],
        meta={"tps_fixed": [float(t["tp1"]), float(t["tp2"])], "ladder": {"split": [1, 1], "be_after_tp1": False},
              "pip": pip, "pip_label": unit, "lot": lot, "entry_mode": "limit", "tp_on_reprice": "keep_target",
              "min_rr": float(s["min_rr"]), "pattern": p["kind"], "sl_pips": round(t["risk"], 1),
              "zone_id": zone_id(symbol, side, z["lo"], z["hi"], pip)},
    )
