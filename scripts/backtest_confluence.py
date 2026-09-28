#!/usr/bin/env python3
"""Replay backtest for the Confluence Day Template.

Runs the SAME setup + gate code as live over the last N session days of
yfinance intraday data (5m ≈ 60 calendar-day limit), stepping every 5 minutes
on closed candles only. TP-before-SL is judged on the subsequent 5m path;
if SL and TP are both inside one 5m bar it is counted as a LOSS (conservative).

Usage:
  python scripts/backtest_confluence.py [--days 30] [--set risk.tp_rr=1.5 ...]
                                        [--live] [--out backtest_report]
Telegram env vars are removed at start — this never sends messages.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

os.environ.pop("TG_TOKEN", None)
os.environ.pop("TG_CHAT_ID", None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from strategy import data as mdata  # noqa: E402
from strategy.config_loader import load_config  # noqa: E402
from strategy.engine import (  # noqa: E402
    _empty_day, evaluate_display, gate_candidates, record_emits, session_info,
)
from strategy.setups import REGISTRY  # noqa: E402

CACHE = Path("/tmp/alphaedge_bt_cache.pkl")


def apply_overrides(cfg, sets):
    for s in sets or []:
        key, val = s.split("=", 1)
        node = cfg
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        try:
            v = json.loads(val)
        except Exception:
            v = val
        node[parts[-1]] = v
    return cfg


def load_history(symbols, use_cache=True):
    cache = {}
    if use_cache and CACHE.exists() and time.time() - CACHE.stat().st_mtime < 3600:
        cache = pickle.loads(CACHE.read_bytes())
    out = {}
    for sym in symbols:
        yfs = sym["yf"]
        if yfs not in cache:
            df5, e5 = mdata.fetch(yfs, "5m", "60d")
            df1h, e1 = mdata.fetch(yfs, "1h", "60d")
            if df5 is None or df1h is None:
                print(f"  skip {sym['name']}: {e5 or e1}", flush=True)
                continue
            cache[yfs] = (df5, df1h)
        df5, df1h = cache[yfs]
        out[sym["name"]] = (sym, mdata.FrameSlicer(df5, df1h), df5)
    CACHE.write_bytes(pickle.dumps(cache))
    return out


def outcome(c, df5):
    after = df5[df5.index >= c.bar_time]
    hi = after["High"].to_numpy(); lo = after["Low"].to_numpy()
    for h, l in zip(hi, lo):
        if c.side == "BUY":
            if l <= c.sl:
                return "loss"
            if h >= c.tp:
                return "win"
        else:
            if h >= c.sl:
                return "loss"
            if l <= c.tp:
                return "win"
    return "open"


def replay(cfg, hist, n_days=30, verbose=False):
    end = min(h[2].index[-1] for h in hist.values()) + pd.Timedelta(minutes=5)
    start = end - pd.Timedelta(days=n_days + 16)
    grid = pd.date_range(start.floor("5min"), end.floor("5min"), freq="5min", tz="UTC")
    times = [t for t in grid if session_info(t, cfg)[0]]
    days = sorted({t.strftime("%Y-%m-%d") for t in times})[-n_days:]
    keep = set(days)
    times = [t for t in times if t.strftime("%Y-%m-%d") in keep]

    by_day = defaultdict(list)
    raw_by_day = defaultdict(int)
    alerts = []
    state, cur = None, None
    for t in times:
        day = t.strftime("%Y-%m-%d")
        if day != cur:
            cur, state = day, _empty_day(day)
        cands = []
        for name, (sym, sl, _df5) in hist.items():
            frames = sl.at(t)
            for sname in sym.get("setups", []):
                scfg = cfg["setups"].get(sname) or {}
                if not scfg.get("enabled", True):
                    continue
                if scfg.get("entry_tf") == "15m" and t.minute % 15 != 0:
                    continue
                try:
                    c = REGISTRY[sname](name, frames, cfg, scfg, t, priority=int(sym.get("priority", 99)))
                except Exception as e:  # keep replay going
                    if verbose:
                        print(f"  err {name}/{sname} @ {t}: {e!r}")
                    continue
                if c is not None:
                    cands.append(c)
        raw_by_day[day] += len(cands)
        if not cands:
            continue
        acc, _ = gate_candidates(cands, state, cfg, t)
        if not acc:
            continue
        state = record_emits(state, acc, t)
        for c in acc:
            o = outcome(c, hist[c.symbol][2])
            rec = {"day": day, "time_utc": t.strftime("%H:%M"), "symbol": c.symbol,
                   "setup": c.setup, "side": c.side, "score": f"{c.score}/{c.max_score}",
                   "rr": round(c.rr, 2), "entry": c.entry, "sl": c.sl, "tp": c.tp, "outcome": o}
            by_day[day].append(rec)
            alerts.append(rec)
            if verbose:
                print(f"  ALERT {day} {rec['time_utc']} {c.symbol} {c.setup} {c.side} "
                      f"{rec['score']} RR {c.rr:.1f} -> {o}")

    apd = [len(by_day[d]) for d in days]
    wins = sum(a["outcome"] == "win" for a in alerts)
    losses = sum(a["outcome"] == "loss" for a in alerts)
    closed = wins + losses
    tp_rr = float(cfg["risk"].get("tp_rr", 2.5))
    exp_r = ((wins * tp_rr - losses) / closed) if closed else None
    by_setup = {}
    for s in sorted({a["setup"] for a in alerts}):
        xs = [a for a in alerts if a["setup"] == s]
        w = sum(a["outcome"] == "win" for a in xs); l = sum(a["outcome"] == "loss" for a in xs)
        by_setup[s] = {"n": len(xs), "win": w, "loss": l, "open": len(xs) - w - l,
                       "win_rate_pct": round(100 * w / (w + l), 1) if w + l else None}
    return {
        "days": len(days), "day_range": [days[0], days[-1]] if days else None,
        "alerts": len(alerts),
        "alerts_per_day_mean": round(float(np.mean(apd)), 2) if apd else 0.0,
        "alerts_per_day_median": float(np.median(apd)) if apd else 0.0,
        "alerts_per_day_max": int(max(apd)) if apd else 0,
        "raw_candidates_per_day_mean": round(float(np.mean([raw_by_day[d] for d in days])), 2) if days else 0.0,
        "histogram": {str(k): int(v) for k, v in sorted(pd.Series(apd).value_counts().items())} if apd else {},
        "wins": wins, "losses": losses, "open": len(alerts) - closed,
        "win_rate_pct": round(100 * wins / closed, 1) if closed else None,
        "breakeven_win_rate_pct": round(100 / (1 + tp_rr), 1),
        "expectancy_R": round(exp_r, 3) if exp_r is not None else None,
        "by_setup": by_setup,
        "trades": alerts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    cfg = apply_overrides(deepcopy(load_config()), args.set)

    if args.live:
        now = pd.Timestamp.now(tz="UTC")
        print(f"LIVE scan @ {now:%Y-%m-%d %H:%M} UTC — session {session_info(now, cfg)}")
        for sym in cfg["symbols"]:
            sig, e, tp, sl, reason, _ = evaluate_display(sym["name"], now=now, cfg=cfg)
            extra = f" entry {e:.5g} SL {sl:.5g} TP {tp:.5g}" if sig != "WAIT" else ""
            print(f"  {sym['name']:<11} {sig}{extra}")

    hist = load_history(cfg["symbols"])
    res = replay(cfg, hist, args.days, verbose=args.verbose)
    summary = {k: v for k, v in res.items() if k != "trades"}
    print(json.dumps(summary, indent=2))
    if args.out:
        Path(args.out + ".json").write_text(json.dumps(
            {"generated_utc": datetime.now(timezone.utc).isoformat(),
             "overrides": args.set, **res}, indent=2, default=str))
        print(f"wrote {args.out}.json")


if __name__ == "__main__":
    main()
