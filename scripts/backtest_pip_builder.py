#!/usr/bin/env python3
"""Honest research backtest for the '1000 Pip Builder' setup (and the old smc_sweep
confluence setup on the SAME data/costs for comparison).

Data : 1-minute FX BID bars (scripts/fetch_histdata.py → /workspace/bt_data/<PAIR>_1m.parquet).
       5m / 15m / 1H / 4H / Daily are all derived from it (same code as live: strategy.data).
Steps: every closed 5m bar, closed candles only, exactly the setup code used live.
Entry: market fill `--latency` minutes after the trigger bar closes (live scans every ~5 min),
       at the 1m OPEN; BUY pays the spread (ask), SELL fills at the bid.
Exits: walked on 1-minute bars. SL and TP inside the same 1m bar = LOSS. SELL stops/targets are
       tested on the ASK (bid + spread). Open after `--max-hours` → closed at market (counted).
Gates: --gated applies the live engine gates (daily cap, per-symbol cap, cooldowns, correlation,
       dedupe); raw mode = one open position per pair, no caps.
Never sends anything; Telegram vars are removed.
"""
from __future__ import annotations

import argparse, json, os, sys, time
from copy import deepcopy
from multiprocessing import Pool
from pathlib import Path

os.environ.pop("TG_TOKEN", None); os.environ.pop("TG_CHAT_ID", None)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from strategy import data as mdata  # noqa: E402
from strategy.config_loader import load_config  # noqa: E402
from strategy.engine import _empty_day, gate_candidates, record_emits  # noqa: E402
from strategy.risk_sizing import pip_size  # noqa: E402
from strategy.setups import REGISTRY  # noqa: E402

DATA = Path("/workspace/bt_data")
PAIRS = ["NZDUSD", "GBPUSD", "USDCAD", "EURUSD", "EURJPY", "GBPJPY", "USDJPY"]
NAME = {p: f"{p[:3]}/{p[3:]}" for p in PAIRS}
# Typical retail all-in cost, pips (round-trip spread; ECN commission folded in). ASSUMED.
SPREAD = {"EURUSD": 0.8, "GBPUSD": 1.0, "USDJPY": 1.0, "NZDUSD": 1.4, "USDCAD": 1.4, "EURJPY": 1.8, "GBPJPY": 2.5}

_G: dict = {}


def load_pair(pair: str):
    if pair in _G:
        return _G[pair]
    m1 = pd.read_parquet(DATA / f"{pair}_1m.parquet")
    m1 = m1[~m1.index.duplicated()].sort_index()
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    def rs(rule): return m1.resample(rule, label="left", closed="left").agg(agg).dropna(subset=["Close"])
    df5, df1h = rs("5min"), rs("1h")
    _G[pair] = (m1, df5, df1h, mdata.FrameSlicer(df5, df1h))
    return _G[pair]


# ── candidate generation (the live setup code, stepped through history) ──────

def gen_task(args):
    pair, setup, cfg, start, end, step_min = args
    _, df5, _, sl = load_pair(pair)
    pip_cfg = cfg["setups"][setup]
    fn = REGISTRY[setup]
    name = NAME[pair]
    out = []
    idx = df5.index[(df5.index >= start) & (df5.index < end)]
    for t0 in idx:
        t = t0 + pd.Timedelta(minutes=5)           # decision time = close of this 5m bar
        if step_min == 15 and t.minute % 15:
            continue
        frames = sl.at(t)
        try:
            c = fn(name, frames, cfg, pip_cfg, t, priority=1)
        except Exception:
            continue
        if c is not None and c.bar_time == t:
            c.meta = dict(c.meta or {}); c.meta["pair"] = pair
            out.append(c)
    return out


def generate(cfg, setup, pairs, start, end, step_min, procs):
    with Pool(procs) as pool:
        res = pool.map(gen_task, [(p, setup, cfg, start, end, step_min) for p in pairs], chunksize=1)
    return sorted([c for r in res for c in r], key=lambda c: (c.bar_time, c.symbol))


# ── outcome simulation on 1m bars ─────────────────────────────────────────────

def simulate(c, spread_mult=1.0, latency_min=5, max_hours=48, tp1_pips=None, tp1_frac=0.5, drift_check=True):
    pair = c.meta["pair"]
    m1, _, _, _ = load_pair(pair)
    pip = pip_size(c.symbol)
    spr = SPREAD[pair] * spread_mult * pip
    t_in = c.bar_time + pd.Timedelta(minutes=latency_min)
    i0 = m1.index.searchsorted(t_in)
    if i0 >= len(m1) or (m1.index[i0] - t_in) > pd.Timedelta(minutes=30):
        return None
    side = 1 if c.side == "BUY" else -1
    op = float(m1["Open"].iloc[i0])
    fill = op + spr if side == 1 else op
    risk = (fill - c.sl) * side
    reward = (c.tp - fill) * side
    if risk <= 0 or reward <= 0:
        return None
    meta = c.meta or {}
    if drift_check and (risk < float(meta.get("min_risk", 0)) or risk > float(meta.get("max_risk", 1e9))):
        return None   # same post-reprice limits as strategy/pricing.py
    # live-style execution checks (drift toward TP, TP/SL already traded, RR floor)
    if drift_check:
        fav = (op - c.entry) * side
        if fav > 0.3 * c.atr or fav > 0.25 * abs(c.tp - c.entry):
            return None
        if latency_min:
            seg = m1.iloc[m1.index.searchsorted(c.bar_time):i0]
            if len(seg) and (((seg["High"].max() + (0 if side == 1 else spr)) >= c.tp if side == 1 else (seg["Low"].min() + spr) <= c.tp)
                             or ((seg["Low"].min() <= c.sl) if side == 1 else (seg["High"].max() + spr >= c.sl))):
                return None
        if reward / risk + 1e-9 < float((c.meta or {}).get("min_rr", 1.0)):
            return None
    end_i = m1.index.searchsorted(t_in + pd.Timedelta(hours=max_hours))
    hi = m1["High"].to_numpy()[i0:end_i]; lo = m1["Low"].to_numpy()[i0:end_i]; cl = m1["Close"].to_numpy()[i0:end_i]
    if len(hi) == 0:
        return None
    if side == 1:
        sl_hit, tp_hit = lo <= c.sl, hi >= c.tp
    else:
        sl_hit, tp_hit = hi + spr >= c.sl, lo + spr <= c.tp
    si = int(np.argmax(sl_hit)) if sl_hit.any() else None
    ti = int(np.argmax(tp_hit)) if tp_hit.any() else None
    status, k = "EXP", len(hi) - 1
    if si is not None and (ti is None or si <= ti):
        status, k = "SL", si          # same-bar → loss
    elif ti is not None:
        status, k = "TP", ti
    if status == "SL":
        r = -1.0
    elif status == "TP":
        r = reward / risk
    else:
        last = cl[-1] + (0 if side == 1 else spr)
        r = (last - fill) * side / risk
    if tp1_pips:   # optional: tp1_frac closed at TP1 (no BE move); remainder as above
        d1 = tp1_pips * pip
        if d1 < reward:
            lvl = fill + side * d1
            hit1 = (hi >= lvl) if side == 1 else (lo + spr <= lvl)
            j = int(np.argmax(hit1)) if hit1.any() else None
            if j is not None and (status != "SL" or j < k):
                r = tp1_frac * (d1 / risk) + (1 - tp1_frac) * r
    return {"pair": pair, "symbol": c.symbol, "setup": c.setup, "side": c.side, "time": c.bar_time,
            "entry": fill, "sl": c.sl, "tp": c.tp, "risk_pips": risk / pip, "reward_pips": reward / pip,
            "status": status, "r": r, "pips": r * risk / pip, "pattern": (c.meta or {}).get("pattern", ""),
            "tf": (c.meta or {}).get("trigger_tf", ""), "exit_time": m1.index[i0 + k], "score": c.score}


def run_trades(cands, cfg, gated, **kw):
    sims = []
    if gated:
        state, day = None, None
        groups = list(cands)
        i = 0
        while i < len(groups):
            t = groups[i].bar_time
            batch = []
            while i < len(groups) and groups[i].bar_time == t:
                batch.append(groups[i]); i += 1
            d = t.strftime("%Y-%m-%d")
            if d != day:
                day, state = d, _empty_day(d)
            acc, _ = gate_candidates(batch, state, cfg, t)
            if acc:
                state = record_emits(state, acc, t)
                for c in acc:
                    s = simulate(c, **kw)
                    if s:
                        sims.append(s)
    else:
        busy = {}
        for c in cands:
            if busy.get(c.symbol) is not None and c.bar_time < busy[c.symbol]:
                continue
            s = simulate(c, **kw)
            if s:
                sims.append(s); busy[c.symbol] = s["exit_time"]
    return pd.DataFrame(sims)


# ── metrics ───────────────────────────────────────────────────────────────────

def maxdd(r):
    if len(r) == 0:
        return 0.0
    eq = np.cumsum(r); return float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))


def stats(df, days):
    if df is None or len(df) == 0:
        return {"trades": 0, "per_day": 0, "wr": None, "avg_r": None, "net_r": 0, "pips": 0, "maxdd_r": 0,
                "pf": None, "ci95": None, "be_wr": None}
    r = df.sort_values("time")["r"].to_numpy()
    w = int((df["r"] > 0).sum())
    gp, gl = r[r > 0].sum(), -r[r < 0].sum()
    rng = np.random.default_rng(7)
    bs = rng.choice(r, (2000, len(r))).mean(axis=1) if len(r) > 1 else np.array([r.mean()])
    avg_win = r[r > 0].mean() if (r > 0).any() else 0
    return {"trades": len(r), "per_day": round(len(r) / days, 3), "wr": round(100 * w / len(r), 1),
            "avg_r": round(float(r.mean()), 3), "net_r": round(float(r.sum()), 1),
            "pips": round(float(df["pips"].sum()), 0), "maxdd_r": round(maxdd(r), 1),
            "pf": round(float(gp / gl), 2) if gl > 0 else None,
            "ci95": [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)],
            "be_wr": round(100 / (1 + avg_win), 1) if avg_win else None,
            "avg_risk_pips": round(float(df["risk_pips"].mean()), 1), "avg_reward_pips": round(float(df["reward_pips"].mean()), 1)}


def report(df, start, end, label):
    days = max(1, (end - start).days); wdays = max(1, int(days * 5 / 7))
    mid = start + (end - start) / 2
    out = {"label": label, "all": stats(df, days), "per_weekday": round(len(df) / wdays, 3),
           "first_half": stats(df[df["time"] < mid] if len(df) else df, days / 2),
           "second_half": stats(df[df["time"] >= mid] if len(df) else df, days / 2), "per_pair": {}, "per_year": {}}
    if len(df):
        for p, g in df.groupby("pair"):
            out["per_pair"][p] = stats(g, days)
        for y, g in df.groupby(df["time"].dt.year):
            out["per_year"][int(y)] = stats(g, 365 if y not in (start.year, end.year) else days)
        out["by_pattern"] = {k: stats(g, days) for k, g in df.groupby("pattern")} if "pattern" in df else {}
    return out


# ── variants ──────────────────────────────────────────────────────────────────

def variants():
    """One-factor-at-a-time grid around the SPEC defaults (no combinatorial fishing)."""
    v = {"spec_default": {}}
    for w in (0.2, 0.5): v[f"zone_width_{w}"] = {"zone_width_atr": w}
    for b in (1.0, 2.0): v[f"sl_buffer_{b}p"] = {"sl_buffer_pips": b}
    v["tp_nearest_beyond_10p"] = {"tp_pick": "nearest_beyond_min"}
    v["min_touches_1"] = {"min_touches": 1}
    v["double_only"] = {"use_engulf": False}
    v["engulf_only"] = {"use_double": False}
    v["tf_15m_only"] = {"trigger_tfs": ["15m"]}
    v["london_ny_07-20utc"] = {"active_hours_utc": ["07:00", "20:00"]}
    v["bands_only"] = {"use_zones": False}
    v["zones_only"] = {"use_bands": False}
    v["sl_ref_zone_edge"] = {"sl_ref": "extreme_or_zone"}
    v["tp_max_atr_4"] = {"tp_max_atr": 4.0}
    v["tp1_10p_half"] = {"tp1_pips": 10.0}
    for rr in (0.5, 0.75, 1.0):
        v[f"tp6_rr{rr}"] = {"tp_pips": 6.0, "min_rr": rr}
    v["tp6_rr0.75_london_ny"] = {"tp_pips": 6.0, "min_rr": 0.75, "active_hours_utc": ["07:00", "20:00"]}
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-02-01"); ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--pairs", default=",".join(PAIRS)); ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--only", default=""); ap.add_argument("--old", action="store_true", help="also run old smc_sweep")
    ap.add_argument("--out", default="reports/backtest_pip_builder")
    ap.add_argument("--latency", type=int, default=5)
    a = ap.parse_args()
    start, end = pd.Timestamp(a.start, tz="UTC"), pd.Timestamp(a.end, tz="UTC")
    pairs = a.pairs.split(",")
    base = load_config()
    base["news"] = {"enabled": True, "window_minutes": 30}
    results = {}
    gate_cfg = deepcopy(base)
    for name, over in variants().items():
        if a.only and name not in a.only.split(","):
            continue
        t0 = time.time()
        cfg = deepcopy(base)
        cfg["setups"]["pip_builder"] = {**cfg["setups"].get("pip_builder", {}), "enabled": True, **over}
        cands = generate(cfg, "pip_builder", pairs, start, end, 5, a.procs)
        kw = dict(latency_min=a.latency, tp1_pips=over.get("tp1_pips"))
        raw = run_trades(cands, gate_cfg, False, **kw)
        gat = run_trades(cands, gate_cfg, True, **kw)
        raw2 = run_trades(cands, gate_cfg, False, spread_mult=2.0, **kw)
        raw0 = run_trades(cands, gate_cfg, False, spread_mult=0.0, **kw)
        results[name] = {"params": over, "n_candidates": len(cands),
                         "raw": report(raw, start, end, "raw"), "gated": report(gat, start, end, "gated"),
                         "raw_spread_x2": report(raw2, start, end, "raw 2x spread")["all"],
                         "raw_zero_cost": report(raw0, start, end, "raw 0 spread")["all"]}
        if name == "spec_default":
            raw.to_csv(ROOT / f"{a.out}_trades_spec_default_raw.csv", index=False)
            gat.to_csv(ROOT / f"{a.out}_trades_spec_default_gated.csv", index=False)
        s = results[name]["raw"]["all"]
        print(f"{name:26s} cand={len(cands):5d} raw: n={s['trades']} wr={s['wr']} avgR={s['avg_r']} net={s['net_r']} dd={s['maxdd_r']}"
              f" | halves {results[name]['raw']['first_half']['net_r']}/{results[name]['raw']['second_half']['net_r']}  ({time.time()-t0:.0f}s)", flush=True)
        (ROOT / f"{a.out}_variants.json").write_text(json.dumps(results, indent=1, default=str))
    if a.old:
        cfg = deepcopy(base)
        cands = generate(cfg, "smc_sweep", pairs, start, end, 15, a.procs)
        kw = dict(latency_min=a.latency)
        for c in cands:
            c.meta["min_rr"] = 1.5
        old = {"raw": report(run_trades(cands, gate_cfg, False, **kw), start, end, "old raw"),
               "gated": report(run_trades(cands, gate_cfg, True, **kw), start, end, "old gated"),
               "n_candidates": len(cands)}
        (ROOT / f"{a.out}_old_confluence.json").write_text(json.dumps(old, indent=1, default=str))
        print("OLD", old["raw"]["all"], old["gated"]["all"])


if __name__ == "__main__":
    main()
