"""Confluence Day Template engine: scan → rank → gate (caps / cooldown / dedupe).

`scan_once` is used by the monitor and by the Streamlit UI.
State is date-keyed so a wiped monitor_state.json (Render free disk is
ephemeral) simply starts a fresh day — it never re-fires yesterday's alerts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import data as mdata
from .checklist import score as score_checklist  # noqa: F401  (re-export useful)
from .common import Candidate, fmt_price, in_window, minutes_of, parse_hhmm
from .config_loader import load_config
from .setups import REGISTRY
from . import pricing
from .outcomes import format_day_outcomes, outcome_cfg

_STATE_DEFAULT = Path(__file__).resolve().parent.parent / "monitor_state.json"


# ── session helpers ───────────────────────────────────────────────────────────

def session_info(now: pd.Timestamp | None = None, cfg: dict | None = None):
    """Returns (in_session: bool, session_name: str)."""
    cfg = cfg or load_config()
    now = now or pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    sess = cfg.get("session", {})
    if sess.get("weekdays_only", True) and now.weekday() >= 5:
        return False, "🔴 WEEKEND"
    for w in sess.get("windows", []):
        if in_window(now, w["start"], w["end"]):
            return True, w.get("name", "SESSION")
    return False, "🔴 OFF-SESSION"


def next_session(now: pd.Timestamp | None = None, cfg: dict | None = None):
    cfg = cfg or load_config()
    now = now or pd.Timestamp.now(tz="UTC")
    windows = cfg.get("session", {}).get("windows", [])
    if not windows:
        return "London Open", "07:00 UTC"
    m = minutes_of(now)
    for w in windows:
        start_m = minutes_of(parse_hhmm(w["start"]))
        if m < start_m and not (cfg.get("session", {}).get("weekdays_only") and now.weekday() >= 5):
            return w.get("name", "SESSION"), f"{w['start']} UTC"
    # next weekday open
    return windows[0].get("name", "SESSION") + " (next weekday)", f"{windows[0]['start']} UTC"


# ── state I/O (date-keyed, restart-safe) ──────────────────────────────────────

def _empty_day(day: str) -> dict:
    return {
        "day": day,
        "in_session": None,
        "emitted": [],          # list of {zone_key, symbol, side, setup, ts, entry, sl, tp, score}
        "last_trade_ts": None,  # ISO UTC of last trade alert
        "symbol_last_ts": {},   # symbol → ISO UTC
        "scan_count": 0,
        "summary_sent": False,
    }


def load_state(path: str | os.PathLike | None = None, now: pd.Timestamp | None = None) -> dict:
    path = Path(path) if path else _STATE_DEFAULT
    now = now or pd.Timestamp.now(tz="UTC")
    day = now.strftime("%Y-%m-%d")
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if not isinstance(st, dict):
            return _empty_day(day)
        if st.get("day") != day:
            # New day OR stale file → fresh alert budget, but the trade-outcome
            # book (open trades awaiting TP/SL + recent results) is NOT daily.
            fresh = _empty_day(day)
            if isinstance(st.get("trades"), dict):
                fresh["trades"] = st["trades"]
            return fresh
        st.setdefault("emitted", [])
        st.setdefault("symbol_last_ts", {})
        st.setdefault("scan_count", 0)
        st.setdefault("summary_sent", False)
        return st
    except Exception:
        return _empty_day(day)


def save_state(state: dict, path: str | os.PathLike | None = None):
    path = Path(path) if path else _STATE_DEFAULT
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, default=str)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[state] write failed: {e!r}", flush=True)


# ── gates ─────────────────────────────────────────────────────────────────────

def _parse_ts(s):
    if not s:
        return None
    try:
        return pd.Timestamp(s)
    except Exception:
        return None


def _corr_blocked(cand: Candidate, emitted: list, groups: list) -> bool:
    """True if an already-emitted alert is in the same correlation group and
    points the same way (after signing)."""
    for g in groups or []:
        members = g.get("members") or {}
        if cand.symbol not in members:
            continue
        my_sign = int(members[cand.symbol])
        my_dir = 1 if cand.side == "BUY" else -1
        my_exposure = my_sign * my_dir
        for e in emitted:
            if e["symbol"] not in members:
                continue
            their_sign = int(members[e["symbol"]])
            their_dir = 1 if e["side"] == "BUY" else -1
            if their_sign * their_dir == my_exposure:
                return True
    return False


def gate_candidates(cands: list[Candidate], state: dict, cfg: dict, now: pd.Timestamp):
    """Apply daily / per-symbol / cooldown / dedupe / correlation filters.
    Returns (accepted, reject_reasons). Mutates nothing; caller records accepts."""
    risk = cfg.get("risk", {})
    daily_max = int(risk.get("daily_max_signals", 6))
    per_sym = int(risk.get("per_symbol_max", 1))
    cd_min = int(risk.get("cooldown_minutes", 45))
    sym_cd = int(risk.get("symbol_cooldown_minutes", 120))
    min_rr = float(risk.get("min_rr", 2.5))
    max_age = int(risk.get("max_signal_age_minutes", 25))
    groups = cfg.get("correlation_groups", [])

    emitted = list(state.get("emitted", []))
    accepted = []
    reasons = []

    # Newest / best first
    ranked = sorted(
        cands,
        key=lambda c: (-c.score, -c.rr, c.priority, -c.bar_time.value),
    )

    last_trade = _parse_ts(state.get("last_trade_ts"))
    sym_last = {k: _parse_ts(v) for k, v in state.get("symbol_last_ts", {}).items()}
    zone_seen = {e["zone_key"] for e in emitted}
    sym_counts = {}
    for e in emitted:
        sym_counts[e["symbol"]] = sym_counts.get(e["symbol"], 0) + 1

    for c in ranked:
        tag = f"{c.symbol}/{c.setup}/{c.side}"
        if c.rr + 1e-9 < min_rr:
            reasons.append(f"{tag}: R:R {c.rr:.2f} < {min_rr}")
            continue
        age_min = (now - c.bar_time).total_seconds() / 60.0
        if age_min < -1 or age_min > max_age:
            reasons.append(f"{tag}: signal age {age_min:.0f}m outside 0–{max_age}")
            continue
        if c.zone_key in zone_seen:
            reasons.append(f"{tag}: dedupe zone already emitted")
            continue
        if len(emitted) + len(accepted) >= daily_max:
            reasons.append(f"{tag}: daily cap {daily_max} reached")
            continue
        if sym_counts.get(c.symbol, 0) >= per_sym:
            reasons.append(f"{tag}: per-symbol cap {per_sym}")
            continue
        # Global cooldown from the last *persisted* trade (and from anything
        # already accepted earlier in this same scan).
        ref = last_trade
        if accepted:
            ref = now  # one accept per scan when a cooldown is configured
        if ref is not None and (now - ref).total_seconds() < cd_min * 60:
            reasons.append(f"{tag}: global cooldown {cd_min}m")
            continue
        slast = sym_last.get(c.symbol)
        if slast is not None and (now - slast).total_seconds() < sym_cd * 60:
            reasons.append(f"{tag}: symbol cooldown {sym_cd}m")
            continue
        if _corr_blocked(c, emitted + [
            {"symbol": a.symbol, "side": a.side} for a in accepted
        ], groups):
            reasons.append(f"{tag}: correlation group already exposed")
            continue

        accepted.append(c)
        zone_seen.add(c.zone_key)
        sym_counts[c.symbol] = sym_counts.get(c.symbol, 0) + 1
        if cd_min > 0:
            # At most one trade alert per monitor loop — daily budget cannot
            # be dumped in a single 5-minute scan.
            break

    return accepted, reasons


def record_emits(state: dict, accepted: list[Candidate], now: pd.Timestamp) -> dict:
    st = dict(state)
    emitted = list(st.get("emitted", []))
    sym_last = dict(st.get("symbol_last_ts", {}))
    for c in accepted:
        emitted.append({
            "zone_key": c.zone_key,
            "symbol": c.symbol,
            "side": c.side,
            "setup": c.setup,
            "ts": now.isoformat(),
            "entry": c.entry, "sl": c.sl, "tp": c.tp,
            "score": c.score, "rr": round(c.rr, 2),
        })
        sym_last[c.symbol] = now.isoformat()
    st["emitted"] = emitted
    st["symbol_last_ts"] = sym_last
    if accepted:
        st["last_trade_ts"] = now.isoformat()
    return st


# ── scanning ──────────────────────────────────────────────────────────────────

def evaluate_symbol(sym_cfg: dict, frames: dict, cfg: dict, now: pd.Timestamp) -> list[Candidate]:
    out = []
    setups_cfg = cfg.get("setups", {})
    for setup_name in sym_cfg.get("setups", []):
        scfg = setups_cfg.get(setup_name) or {}
        if not scfg.get("enabled", True):
            continue
        fn = REGISTRY.get(setup_name)
        if fn is None:
            continue
        try:
            cand = fn(sym_cfg["name"], frames, cfg, scfg, now,
                      priority=int(sym_cfg.get("priority", 99)))
            if cand is not None:
                out.append(cand)
        except Exception as e:
            print(f"[engine] {sym_cfg['name']}/{setup_name} error: {e!r}", flush=True)
    return out


def scan_once(now: pd.Timestamp | None = None, cfg: dict | None = None,
              state: dict | None = None, fetch_fn=None, apply_gates: bool = True,
              snapshot_fn=None):
    """
    Full scan of the allowlist.
    Returns dict with keys:
      in_session, session_name, cfg, state, candidates, accepted,
      reject_reasons, data_errors, now
    `fetch_fn(yf, now) -> (frames|None, errs)` is injectable for backtests.
    """
    cfg = cfg or load_config()
    now = now or pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    state = state if state is not None else load_state(now=now)
    in_sess, sess_name = session_info(now, cfg)

    result = {
        "in_session": in_sess, "session_name": sess_name, "cfg": cfg,
        "state": state, "candidates": [], "accepted": [],
        "reject_reasons": [], "data_errors": [], "now": now,
    }
    if not in_sess:
        return result

    fetch_fn = fetch_fn or mdata.live_frames
    all_cands: list[Candidate] = []
    for sym in cfg.get("symbols", []):
        frames, errs = fetch_fn(sym["yf"], now)
        for interval, reason in errs or []:
            result["data_errors"].append((sym["name"], interval, reason))
        if not frames:
            continue
        cands = evaluate_symbol(sym, frames, cfg, now)
        if cands and cfg.get("execution", {}).get("enabled", True) and snapshot_fn is not False:
            snap = (snapshot_fn or pricing.snapshot)(sym, cfg, now)
            kept = []
            for c in cands:
                ok, why = pricing.validate_and_reprice(c, snap, cfg, now)
                if ok:
                    kept.append(c)
                else:
                    result["reject_reasons"].append(f"{c.symbol}/{c.setup}/{c.side}: {why}")
            cands = kept
        all_cands.extend(cands)

    result["candidates"] = all_cands
    if apply_gates:
        accepted, reasons = gate_candidates(all_cands, state, cfg, now)
        result["accepted"] = accepted
        result["reject_reasons"].extend(reasons)
    else:
        result["accepted"] = all_cands
    return result


def evaluate_display(display_name: str, now: pd.Timestamp | None = None, cfg: dict | None = None):
    """UI helper: run every enabled setup for one symbol (no gates) and return
    the best candidate, or a WAIT tuple compatible with the old _signal_engine.
    Returns (sig, entry, tp, sl, reason_text, meta_dict).
    """
    cfg = cfg or load_config()
    now = now or pd.Timestamp.now(tz="UTC")
    in_sess, sess_name = session_info(now, cfg)
    if not in_sess:
        return "WAIT", 0.0, 0.0, 0.0, f"Outside session ({sess_name})", {}

    sym = next((s for s in cfg.get("symbols", []) if s["name"] == display_name), None)
    if sym is None:
        # Symbol not on the alert allowlist — still try if it has a yfinance map
        # via a synthetic config so the UI keeps working for every TICKER_MAP key.
        return "WAIT", 0.0, 0.0, 0.0, (
            f"{display_name} is not on the alert allowlist "
            f"(edit strategy_config.yaml → symbols to include it)"
        ), {}

    frames, errs = mdata.live_frames(sym["yf"], now)
    if not frames:
        why = "; ".join(f"{i}: {r}" for i, r in errs) if errs else "no data"
        return "WAIT", 0.0, 0.0, 0.0, f"Data unavailable ({why})", {}

    cands = evaluate_symbol(sym, frames, cfg, now)
    if not cands:
        return "WAIT", 0.0, 0.0, 0.0, (
            f"No A-tier setup on {display_name}\n"
            f"Watching: {', '.join(sym.get('setups', []))}\n"
            f"Session: {sess_name}"
        ), {}

    rejected = []
    if cfg.get("execution", {}).get("enabled", True):
        snap = pricing.snapshot(sym, cfg, now)
        kept = []
        for c in cands:
            ok, why = pricing.validate_and_reprice(c, snap, cfg, now)
            (kept if ok else rejected).append(c if ok else f"{c.label} {c.side}: {why}")
        cands = kept
    if not cands:
        return "WAIT", 0.0, 0.0, 0.0, (
            f"Setup detected on {display_name} but rejected at live-price check:\n"
            + "\n".join(rejected)
        ), {}

    best = sorted(cands, key=lambda c: (-c.score, -c.rr, c.priority))[0]
    reason = (
        f"{best.label}  {best.score}/{best.max_score}\n"
        + "\n".join(best.checklist_lines) + "\n"
        + "-" * 24 + "\n"
        + "\n".join(best.notes) + "\n"
        + _data_line(best) + "\n"
        + f"Entry {fmt_price(best.entry, best.entry)} | SL {fmt_price(best.sl, best.entry)} | "
          f"TP {fmt_price(best.tp, best.entry)} | R:R 1:{best.rr:.1f}"
    )
    sig = "BUY" if best.side == "BUY" else "SELL"
    meta = {"candidate": best, "session": sess_name}
    return sig, best.entry, best.tp, best.sl, reason, meta


def _data_line(c: Candidate) -> str:
    m = c.meta or {}
    if not m:
        return "Data age: n/a (not live-validated)"
    parts = [
        f"Candle closed {m.get('candle_age_min', 0):.0f}m ago",
        f"feed age {m.get('signal_age_min', 0):.0f}m ({m.get('signal_ticker', '')})",
        f"price {m.get('quote_label', '')} {m.get('quote_age_min', 0):.0f}m old",
    ]
    if m.get("basis"):
        parts.append(f"futures basis {m['basis']:+.2f} removed")
    return " · ".join(parts)


def format_trade_message(c: Candidate, session_name: str) -> str:
    from html import escape
    lines = "\n".join(escape(x) for x in c.checklist_lines)
    notes = "\n".join(escape(x) for x in c.notes)
    return (
        f"🚨 <b>ALPHAEDGE SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Asset:</b> {escape(c.symbol)}\n"
        f"🧩 <b>Setup:</b> {escape(c.label)}\n"
        f"📈 <b>Signal:</b> {'🟢 BUY' if c.side == 'BUY' else '🔴 SELL'}\n"
        f"✅ <b>Score:</b> {c.score}/{c.max_score}\n"
        f"⏰ <b>Time (UTC):</b> {datetime.now(timezone.utc).strftime('%H:%M  %d/%m/%Y')}\n"
        f"🏦 <b>Session:</b> {escape(session_name)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Entry:</b>  {fmt_price(c.entry, c.entry)}"
        f"{' (LIMIT)' if c.meta.get('entry_mode') == 'limit' else ' (market @ live)' if c.meta else ''}\n"
        f"🎯 <b>TP:</b>     {fmt_price(c.tp, c.entry)}\n"
        f"🛑 <b>SL:</b>     {fmt_price(c.sl, c.entry)}\n"
        f"📐 <b>R:R:</b>    1 : {c.rr:.1f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 {escape(_data_line(c))}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Checklist</b>\n{lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{notes}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
    )


def format_daily_summary(state: dict, session_name: str, daily_cap: int | None = None,
                         outcomes_enabled: bool | None = None) -> str:
    from html import escape
    emitted = state.get("emitted", [])
    if daily_cap is None:
        try:
            daily_cap = int(load_config().get("risk", {}).get("daily_max_signals", 6))
        except Exception:
            daily_cap = 6
    if not emitted:
        body = "No A-tier setups fired today."
    else:
        rows = []
        for e in emitted:
            rows.append(
                f"• {escape(e['symbol'])} {e['side']} ({escape(e.get('setup',''))}) "
                f"score {e.get('score','?')}  R:R 1:{e.get('rr','?')}"
            )
        body = "\n".join(rows)
    if outcomes_enabled is None:
        try:
            outcomes_enabled = bool(outcome_cfg(load_config()).get("enabled", True))
        except Exception:
            outcomes_enabled = True
    outcome_block = ""
    if outcomes_enabled:
        outcome_block = f"━━━━━━━━━━━━━━━━━━━━\n{format_day_outcomes(state, escape=escape)}\n"
    return (
        f"🔴 <b>SESSION CLOSED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
        f"📊 <b>Alerts today:</b> {len(emitted)} / {daily_cap}\n"
        f"{body}\n"
        f"{outcome_block}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice.</i>"
    )
