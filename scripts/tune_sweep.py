#!/usr/bin/env python3
"""Variant sweep for the Confluence Day Template (2026-10-08 tune).

Two phases, so many variants can be compared on identical data:
  1. COLLECT — replay every 5m step over the longest window yfinance allows
     (5m data ≈ 60 calendar days) and record EVERY raw setup hit with the
     checklist made permissive (all items optional, min_score 0). The pattern
     detection itself is unchanged; only the final checklist filter is
     deferred. For each hit we store its checklist factors and the TP/SL path
     outcome at several R multiples.
  2. GATE — for each variant, re-apply the checklist (required items +
     min_score) and the live engine's gate_candidates() (caps, cooldowns,
     dedupe, correlation groups) step-by-step, exactly like live.

Outcome rule (same as backtest_confluence.py): TP-before-SL on the following
5m path; SL+TP inside one bar = LOSS. Trades still open at the end are marked
to market in R. No spread/slippage/commission.
Telegram env vars are removed at start — this never sends messages.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from pathlib import Path

os.environ.pop("TG_TOKEN", None)
os.environ.pop("TG_CHAT_ID", None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from strategy import data as mdata  # noqa: E402
from strategy.checklist import score as score_checklist  # noqa: E402
from strategy.common import Candidate  # noqa: E402
from strategy.config_loader import load_config  # noqa: E402
from strategy.engine import _empty_day, gate_candidates, record_emits  # noqa: E402
from strategy.setups import REGISTRY  # noqa: E402

DATA_CACHE = Path("/tmp/alphaedge_tune_data.pkl")
HITS_CACHE = Path("/tmp/alphaedge_tune_hits.pkl")
RRS = (1.0, 1.5, 2.0, 2.5)
SETUPS = ("smc_sweep", "vwap_pullback", "ema_vwap_kz", "orb_open")
INDEX_GOLD = {"US 30", "NASDAQ 100", "S&P 500", "GOLD"}


def load_data(cfg):
    if DATA_CACHE.exists() and time.time() - DATA_CACHE.stat().st_mtime < 6 * 3600:
        return pickle.loads(DATA_CACHE.read_bytes())
    out = {}
    for sym in cfg["symbols"]:
        df5, e5 = mdata.fetch(sym["yf"], "5m", "60d")
        df1h, e1 = mdata.fetch(sym["yf"], "1h", "60d")
        if df5 is None or df1h is None:
            print(f"skip {sym['name']}: {e5 or e1}", flush=True)
            continue
        out[sym["name"]] = (df5, df1h)
        print(f"{sym['name']:<11} 5m {df5.index[0]:%Y-%m-%d} → {df5.index[-1]:%Y-%m-%d %H:%M}  "
              f"({len(df5)} bars)", flush=True)
    DATA_CACHE.write_bytes(pickle.dumps(out))
    return out


def permissive(scfg):
    s = deepcopy(scfg)
    s["min_score"] = 0
    s["checklist"] = {k: {**(v or {}), "required": False} for k, v in (s.get("checklist") or {}).items()}
    return s


def path_outcomes(side, entry, sl, df5, bar_time):
    """For each RR: (result, R) where result in win/loss/open."""
    after = df5[df5.index >= bar_time]
    hi = after["High"].to_numpy(); lo = after["Low"].to_numpy(); cl = after["Close"].to_numpy()
    risk = abs(entry - sl)
    res = {}
    for rr in RRS:
        tp = entry + rr * risk if side == "BUY" else entry - rr * risk
        r = ("open", None)
        for h, l in zip(hi, lo):
            if side == "BUY":
                if l <= sl:
                    r = ("loss", -1.0); break
                if h >= tp:
                    r = ("win", rr); break
            else:
                if h >= sl:
                    r = ("loss", -1.0); break
                if l <= tp:
                    r = ("win", rr); break
        if r[0] == "open":
            last = cl[-1] if len(cl) else entry
            mtm = ((last - entry) if side == "BUY" else (entry - last)) / risk
            r = ("open", float(max(-1.0, min(rr, mtm))))
        res[rr] = r
    return res


def collect_symbol(args):
    name, sym, cfg, df5, df1h, t0, t1 = args
    sl_ = mdata.FrameSlicer(df5, df1h)
    cfg1 = deepcopy(cfg)
    cfg1["risk"]["tp_rr"] = 1.0
    grid = pd.date_range(t0, t1, freq="5min", tz="UTC")
    setups = [s for s in SETUPS if s == "smc_sweep" or name in INDEX_GOLD]
    pcfg = {s: permissive(cfg["setups"][s]) for s in setups}
    hits = []
    for t in grid:
        frames = None
        for s in setups:
            if pcfg[s].get("entry_tf") == "15m" and t.minute % 15 != 0:
                continue
            if frames is None:
                frames = sl_.at(t)
            try:
                c = REGISTRY[s](name, frames, cfg1, pcfg[s], t, priority=int(sym.get("priority", 99)))
            except Exception:
                continue
            if c is None:
                continue
            hits.append({
                "t": t, "symbol": name, "setup": s, "label": c.label, "side": c.side,
                "entry": c.entry, "sl": c.sl, "bar_time": c.bar_time, "atr": c.atr,
                "zone": c.zone, "factors": dict(c.factors), "priority": c.priority,
                "out": path_outcomes(c.side, c.entry, c.sl, df5, c.bar_time),
            })
    return name, hits


def collect(cfg, data, n_days):
    if HITS_CACHE.exists() and time.time() - HITS_CACHE.stat().st_mtime < 6 * 3600:
        return pickle.loads(HITS_CACHE.read_bytes())
    end = min(d[0].index[-1] for d in data.values()) + pd.Timedelta(minutes=5)
    t1 = end.floor("5min")
    t0 = (t1 - pd.Timedelta(days=n_days)).ceil("1D")
    syms = {s["name"]: s for s in cfg["symbols"]}
    jobs = [(n, syms[n], cfg, d[0], d[1], t0, t1) for n, d in data.items()]
    hits = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for name, h in ex.map(collect_symbol, jobs):
            print(f"  collected {name}: {len(h)} raw hits", flush=True)
            hits.extend(h)
    out = {"t0": t0, "t1": t1, "hits": hits}
    HITS_CACHE.write_bytes(pickle.dumps(out))
    return out


def run_variant(cfg, coll, v):
    """v: dict with keys setups{name:{required:[...], min_score}}, risk{...},
    symbols_setups{name:[...]} optional. Returns stats + trades."""
    vcfg = deepcopy(cfg)
    vcfg["risk"].update(v.get("risk", {}))
    rr = float(vcfg["risk"]["tp_rr"])
    vcfg["risk"]["min_rr"] = min(float(vcfg["risk"].get("min_rr", rr)), rr)
    enabled = v["setups"]
    by_t = {}
    for h in coll["hits"]:
        sv = enabled.get(h["setup"])
        if sv is None:
            continue
        if sv.get("only") and h["symbol"] not in sv["only"]:
            continue
        ck = {k: {"weight": 1, "required": k in sv["required"]} for k in h["factors"]}
        sc, mx, missing, lines = score_checklist(h["factors"], ck)
        if missing or sc < sv["min_score"]:
            continue
        by_t.setdefault(h["t"], []).append((h, sc, mx))
    trades = []
    state, cur = None, None
    for t in sorted(by_t):
        day = t.strftime("%Y-%m-%d")
        if day != cur:
            cur, state = day, _empty_day(day)
        cands = []
        for h, sc, mx in by_t[t]:
            risk = abs(h["entry"] - h["sl"])
            tp = h["entry"] + rr * risk if h["side"] == "BUY" else h["entry"] - rr * risk
            c = Candidate(symbol=h["symbol"], setup=h["setup"], label=h["label"], side=h["side"],
                          entry=h["entry"], sl=h["sl"], tp=tp, bar_time=h["bar_time"], atr=h["atr"],
                          zone=h["zone"], factors=h["factors"], score=sc, max_score=mx,
                          priority=h["priority"])
            c._h = h
            cands.append(c)
        acc, _ = gate_candidates(cands, state, vcfg, t)
        if not acc:
            continue
        state = record_emits(state, acc, t)
        for c in acc:
            res, r = c._h["out"][rr]
            trades.append({"t": t, "day": day, "symbol": c.symbol, "setup": c.setup, "side": c.side,
                           "score": f"{c.score}/{c.max_score}", "result": res, "R": r})
    return trades


def stats(trades, t0, t1):
    n_days = max(1, (t1 - t0).days)
    w = sum(x["result"] == "win" for x in trades)
    l = sum(x["result"] == "loss" for x in trades)
    o = len(trades) - w - l
    rs = [x["R"] for x in trades]
    cum = np.cumsum(rs) if rs else np.array([0.0])
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    dd = float((peak - np.concatenate([[0.0], cum])).max())
    wkday = [x for x in trades if pd.Timestamp(x["day"]).weekday() < 5]
    return {
        "n": len(trades), "per_day": round(len(trades) / n_days, 2),
        "win": w, "loss": l, "open": o,
        "wr": round(100 * w / (w + l), 1) if w + l else None,
        "avg_R": round(float(np.mean(rs)), 3) if rs else None,
        "net_R": round(float(np.sum(rs)), 2) if rs else 0.0,
        "max_dd_R": round(dd, 2),
        "weekday_per_day": round(len(wkday) / max(1, np.busday_count(t0.date(), t1.date())), 2),
    }


def split_stats(trades, t0, t1):
    mid = t0 + (t1 - t0) / 2
    a = [x for x in trades if x["t"] < mid]
    b = [x for x in trades if x["t"] >= mid]
    return stats(a, t0, mid), stats(b, mid, t1)


ALL6 = ["htf_bias", "premium_discount", "liquidity_sweep", "mss_bos", "pd_array", "kill_zone"]
CORE = ["liquidity_sweep", "mss_bos", "pd_array"]
VWAP_REQ = ["htf_bias", "vwap_trend", "pullback_touch", "confirm_close", "active_hours"]
EMA_REQ = ["htf_bias", "vwap_trend", "ema_bone", "vwap_slope", "confirm_close", "morning_kz"]
ORB_REQ = ["htf_bias", "breakout_close", "strong_candle", "vwap_side"]
BASE_RISK = {"tp_rr": 2.0, "min_rr": 2.0, "daily_max_signals": 4, "per_symbol_max": 1}


def V(name, smc_req, smc_min, risk=None, extra=None, vwap=True):
    s = {"smc_sweep": {"required": smc_req, "min_score": smc_min}}
    if vwap:
        s["vwap_pullback"] = {"required": VWAP_REQ, "min_score": 5, "only": INDEX_GOLD}
    s.update(extra or {})
    return {"name": name, "setups": s, "risk": {**BASE_RISK, **(risk or {})}}


def variants():
    vs = []
    smc_opts = [
        ("A all-6 req (previous)", ALL6, 5),
        ("B KZ score-only, min5", CORE + ["htf_bias", "premium_discount"], 5),
        ("C PD score-only, min5", CORE + ["htf_bias", "kill_zone"], 5),
        ("D PD+KZ score-only, min5", CORE + ["htf_bias"], 5),
        ("E PD+KZ score-only, min4", CORE + ["htf_bias"], 4),
        ("G HTF score-only, PD req, min5", CORE + ["premium_discount"], 5),
        ("H core only, min4", CORE, 4),
        ("I PD req, HTF+KZ score-only, min4", CORE + ["premium_discount"], 4),
    ]
    for label, req, mn in smc_opts:
        for rr in (2.0, 1.5):
            for daily, psm in ((4, 1), (5, 1), (6, 2)):
                vs.append(V(f"{label} | {rr}R | cap{daily}/sym{psm}", req, mn,
                            risk={"tp_rr": rr, "min_rr": rr, "daily_max_signals": daily,
                                  "per_symbol_max": psm}))
    # optional extra setups on top of D/E
    for label, req, mn in [("D", CORE + ["htf_bias"], 5), ("E", CORE + ["htf_bias"], 4),
                           ("I", CORE + ["premium_discount"], 4)]:
        for rr in (2.0, 1.5):
            r = {"tp_rr": rr, "min_rr": rr, "daily_max_signals": 6, "per_symbol_max": 2}
            vs.append(V(f"{label} +ema_vwap_kz | {rr}R | cap6/sym2", req, mn, risk=r,
                        extra={"ema_vwap_kz": {"required": EMA_REQ, "min_score": 6, "only": INDEX_GOLD}}))
            vs.append(V(f"{label} +orb_open | {rr}R | cap6/sym2", req, mn, risk=r,
                        extra={"orb_open": {"required": ORB_REQ, "min_score": 5, "only": INDEX_GOLD}}))
            vs.append(V(f"{label} no vwap_pullback | {rr}R | cap6/sym2", req, mn, risk=r, vwap=False))
    return vs


def main():
    cfg = load_config()
    n_days = int(os.environ.get("TUNE_DAYS", "52"))
    data = load_data(cfg)
    coll = collect(cfg, data, n_days)
    t0, t1 = coll["t0"], coll["t1"]
    print(f"window {t0:%Y-%m-%d %H:%M} → {t1:%Y-%m-%d %H:%M} UTC ({(t1 - t0).days} days), "
          f"raw hits {len(coll['hits'])}", flush=True)
    rows = []
    for v in variants():
        tr = run_variant(cfg, coll, v)
        s = stats(tr, t0, t1)
        h1, h2 = split_stats(tr, t0, t1)
        by_setup = {}
        for x in tr:
            by_setup.setdefault(x["setup"], []).append(x)
        rows.append({"name": v["name"], **s, "h1": h1, "h2": h2,
                     "by_setup": {k: stats(xs, t0, t1) for k, xs in by_setup.items()},
                     "trades": [{**x, "t": x["t"].isoformat()} for x in tr], "variant": v})
        print(f"{v['name']:<52} n={s['n']:>3} /d={s['per_day']:<5} WR={s['wr']}% "
              f"avgR={s['avg_R']} net={s['net_R']} DD={s['max_dd_R']} | "
              f"H1 net={h1['net_R']} H2 net={h2['net_R']}", flush=True)
    out = ROOT / "reports" / "tune_2026-10-08_variants.json"
    out.write_text(json.dumps({"window_utc": [t0.isoformat(), t1.isoformat()],
                               "raw_hits": len(coll["hits"]), "rows": rows},
                              indent=1, default=lambda o: sorted(o) if isinstance(o, set) else str(o)))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
