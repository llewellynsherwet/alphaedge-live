"""Persistent log of every alerted signal and its outcome (CSV).

One row per alert, written when the alert is sent; the row is updated in place
when the outcome tracker (strategy.outcomes) resolves it (TP / SL / EXPIRED).
Default file: signal_log.csv in the repo root (config: signal_log.path).
NOTE: Render's free disk is ephemeral — the log resets on a redeploy; point
`signal_log.path` at a persistent disk or download the CSV from the app to keep it.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COLUMNS = ["id", "sent_utc", "symbol", "side", "setup", "pattern", "score", "entry", "sl", "tp", "tp1", "tp2", "tp3", "tp_hit", "rr",
           "sl_pips", "lots", "risk_amount", "delivered", "status", "exit", "r", "closed_utc"]


def log_path(cfg: dict | None = None) -> Path:
    p = ((cfg or {}).get("signal_log") or {}).get("path") or "signal_log.csv"
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def enabled(cfg: dict | None = None) -> bool:
    return bool(((cfg or {}).get("signal_log") or {}).get("enabled", True))


def read_log(path: str | os.PathLike | None = None, cfg: dict | None = None) -> pd.DataFrame:
    path = Path(path) if path else log_path(cfg)
    try:
        df = pd.read_csv(path, dtype={"id": str})
    except Exception:
        return pd.DataFrame(columns=COLUMNS)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[COLUMNS]


def _write(df: pd.DataFrame, path: Path) -> None:
    tmp = str(path) + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def log_signal(trade: dict, delivered: bool = True, path=None, cfg: dict | None = None) -> None:
    """Append a row from an `outcomes.make_trade` record (idempotent on id)."""
    path = Path(path) if path else log_path(cfg)
    sz = trade.get("sizing") or {}
    row = {"id": trade["id"], "sent_utc": trade["sent_ts"], "symbol": trade["symbol"], "side": trade["side"],
           "setup": trade.get("setup"), "pattern": trade.get("pattern"), "score": trade.get("score"),
           "entry": trade["entry"], "sl": trade["sl"], "tp": trade["tp"],
           "tp1": (trade.get("tps") or [None] * 3)[0], "tp2": (trade.get("tps") or [None] * 3)[1],
           "tp3": (trade.get("tps") or [None] * 3)[2], "tp_hit": trade.get("tp_hit", 0), "rr": trade.get("rr"),
           "sl_pips": trade.get("sl_pips") or sz.get("sl_pips"), "lots": sz.get("lots"),
           "risk_amount": sz.get("actual_risk"), "delivered": bool(delivered), "status": "OPEN",
           "exit": None, "r": None, "closed_utc": None}
    df = read_log(path)
    if (df["id"] == row["id"]).any():
        return
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True) if len(df) else pd.DataFrame([row])
    _write(df[COLUMNS], path)


def log_outcome(closed: dict, path=None, cfg: dict | None = None) -> None:
    """Update the row for a closed trade record (status / exit / r / closed time)."""
    path = Path(path) if path else log_path(cfg)
    df = read_log(path)
    m = df["id"] == closed["id"]
    if not m.any():
        log_signal({**closed, "sizing": closed.get("sizing")}, True, path)
        df = read_log(path)
        m = df["id"] == closed["id"]
    df["exit"] = df["exit"].astype("object"); df["closed_utc"] = df["closed_utc"].astype("object")
    df["status"] = df["status"].astype("object"); df["r"] = df["r"].astype("object")
    df.loc[m, ["status", "exit", "r", "closed_utc"]] = [
        closed.get("status"), closed.get("exit"), closed.get("r"), closed.get("closed_ts") or closed.get("hit_ts")]
    if closed.get("tp_hit") is not None:
        df.loc[m, "tp_hit"] = closed.get("tp_hit")
    _write(df, path)


def log_progress(trade_id: str, tp_hit: int, path=None, cfg: dict | None = None) -> None:
    """Record TP1/TP2 hits on a still-open ladder trade."""
    path = Path(path) if path else log_path(cfg)
    df = read_log(path)
    m = df["id"] == trade_id
    if m.any():
        df.loc[m, "tp_hit"] = tp_hit
        _write(df, path)


def summary(df: pd.DataFrame) -> dict:
    done = df[df["status"].isin(["TP", "SL"])]  # TP = TP1 or better reached (headline win); r is the real blended R
    wins = int((done["status"] == "TP").sum())
    r = pd.to_numeric(done["r"], errors="coerce").fillna(0)
    th = pd.to_numeric(df["tp_hit"], errors="coerce").fillna(0)
    return {"tp1": int((th >= 1).sum()), "tp2": int((th >= 2).sum()), "tp3": int((th >= 3).sum()),
            "signals": len(df), "open": int((df["status"] == "OPEN").sum()), "closed": len(done),
            "wins": wins, "losses": len(done) - wins,
            "win_rate": round(100 * wins / len(done), 1) if len(done) else None,
            "net_r": round(float(r.sum()), 2)}
