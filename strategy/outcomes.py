"""Trade outcome tracking: did an alerted trade hit TP, SL, or expire?

Lifecycle
---------
1. When a trade alert is actually delivered, the monitor calls
   `add_open_trade(state, cand, cfg, now)` → an open trade is stored under
   ``state["trades"]["open"]``. ``state["trades"]`` is carried across the daily
   reset in `engine.load_state`, so open trades survive day rollovers and
   restarts (as long as monitor_state.json survives).
2. Every monitor loop (~5 min) `check_open_trades` fetches 1m candles (5m
   fallback) of the SAME price space the alert was quoted in (cash/CFD/spot)
   since the alert was sent, and walks them in time order:
     • bar high/low touches TP → TP HIT (wicks count)
     • bar high/low touches SL → SL HIT
     • TP and SL both inside one bar → SL HIT (conservative; noted in message)
     • no hit after `outcomes.max_open_hours` → EXPIRED (marked at last price)
   A resolved trade moves to ``state["trades"]["closed"]`` exactly once, with
   ``notified: False``; the monitor then sends the Telegram follow-up and
   flips ``notified``.
3. `day_stats` feeds wins / losses / R into the daily session-close summary.

Price source per symbol (mirrors strategy.pricing at alert time):
  • no quote (spot FX)  → signal ticker 1m bars (e.g. EURUSD=X)
  • quote source "yf"   → quote ticker 1m bars (e.g. ^DJI); minutes where the
                          cash market has no bars (pre-NYSE open) use signal
                          futures bars minus the basis stored at alert time —
                          exactly how the entry was derived then
  • quote source "gold_api" → GC=F bars minus stored basis (gold-api has no
                          candles) plus the live gold-api spot print
"""
from __future__ import annotations

import html
from zoneinfo import ZoneInfo

import pandas as pd

from . import data as mdata
from .common import fmt_price

NY = ZoneInfo("America/New_York")
_OHLC = ["Open", "High", "Low", "Close"]

DEFAULTS = {"enabled": True, "max_open_hours": 48, "retain_days": 14,
            "max_notify_attempts": 3}


# ── config / state helpers ────────────────────────────────────────────────────

def outcome_cfg(cfg: dict | None) -> dict:
    out = dict(DEFAULTS)
    out.update((cfg or {}).get("outcomes") or {})
    return out


def trades_book(state: dict) -> dict:
    """Return (and create if needed) the persistent trades book on `state`."""
    book = state.get("trades")
    if not isinstance(book, dict):
        book = {}
        state["trades"] = book
    book.setdefault("open", [])
    book.setdefault("closed", [])
    return book


def _ts(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def market_open(now: pd.Timestamp) -> bool:
    """FX / index futures / gold trade Sun 17:00 → Fri 17:00 New York time."""
    ny = _ts(now).tz_convert(NY)
    wd, h = ny.weekday(), ny.hour
    if wd == 5:                      # Saturday
        return False
    if wd == 4 and h >= 17:          # Friday after 17:00 NY
        return False
    if wd == 6 and h < 17:           # Sunday before 17:00 NY
        return False
    return True


# ── recording ─────────────────────────────────────────────────────────────────

def make_trade(c, cfg: dict, now: pd.Timestamp) -> dict:
    """Snapshot an alerted Candidate into a JSON-safe open-trade record."""
    now = _ts(now)
    sym_cfg = next((s for s in (cfg or {}).get("symbols", []) if s.get("name") == c.symbol), {}) or {}
    meta = getattr(c, "meta", None) or {}
    q = sym_cfg.get("quote") or {}
    signal_ticker = meta.get("signal_ticker") or sym_cfg.get("yf", "")
    if meta.get("signal_ticker"):
        # Live-validated alert: levels are in quote (cash/CFD/spot) space.
        source = q.get("source") or "none"
        basis = float(meta.get("basis") or 0.0)
        label = meta.get("quote_label") or q.get("label") or signal_ticker
    else:
        # Execution checks off: levels are raw signal-feed levels.
        source, basis, label = "none", 0.0, signal_ticker
    slug = "".join(ch for ch in c.symbol if ch.isalnum())
    return {
        "id": f"{now:%Y%m%d-%H%M%S}-{slug}-{c.side}",
        "symbol": c.symbol, "side": c.side,
        "setup": c.setup, "setup_label": getattr(c, "label", c.setup),
        "entry": float(c.entry), "sl": float(c.sl), "tp": float(c.tp),
        "rr": round(float(c.rr), 2),
        "quote_source": source, "quote_ticker": q.get("ticker", "") if source != "none" else "",
        "quote_label": label, "signal_ticker": signal_ticker, "basis": basis,
        "sent_ts": now.isoformat(),
    }


def add_open_trade(state: dict, c, cfg: dict, now: pd.Timestamp) -> dict:
    book = trades_book(state)
    rec = make_trade(c, cfg, now)
    known = {t["id"] for t in book["open"]} | {t["id"] for t in book["closed"]}
    if rec["id"] in known:
        rec["id"] += f"-{len(known)}"
    book["open"].append(rec)
    return rec


# ── hit detection (pure, unit-tested) ─────────────────────────────────────────

def _first_bar_start(sent: pd.Timestamp, interval_min: int) -> pd.Timestamp:
    """Earliest bar START counted for a trade: the first bar that begins at or
    after the alert, so pre-alert prices inside the alert's own bar never count."""
    return sent.ceil(f"{int(interval_min)}min")


def detect_outcome(trade: dict, bars: pd.DataFrame | None, now: pd.Timestamp,
                   max_open_hours: float | None = 48, interval_min: int = 1,
                   allow_expire: bool = True) -> dict | None:
    """Walk candles since the alert. Returns an outcome dict or None (still open).

    outcome = {status: TP|SL|EXPIRED, exit, hit_ts, r, points, both_in_bar,
               interval_min}
    """
    now = _ts(now)
    sent = _ts(trade["sent_ts"])
    side = 1 if trade["side"] == "BUY" else -1
    entry, sl, tp = float(trade["entry"]), float(trade["sl"]), float(trade["tp"])
    deadline = sent + pd.Timedelta(hours=float(max_open_hours)) if max_open_hours else None

    usable = None
    if bars is not None and len(bars):
        b = bars.sort_index()
        b = b[(b.index >= _first_bar_start(sent, interval_min)) & (b.index <= now)]
        if deadline is not None:
            b = b[b.index < deadline]
        usable = b
        for t, row in b.iterrows():
            hi, lo = float(row["High"]), float(row["Low"])
            tp_hit = hi >= tp if side == 1 else lo <= tp
            sl_hit = lo <= sl if side == 1 else hi >= sl
            if sl_hit or tp_hit:
                status = "SL" if sl_hit else "TP"
                return _outcome(trade, status, sl if sl_hit else tp, t,
                                both_in_bar=bool(sl_hit and tp_hit), interval_min=interval_min)

    if allow_expire and deadline is not None and now >= deadline:
        last = None
        if usable is not None and len(usable):
            last = float(usable["Close"].iloc[-1])
        return _outcome(trade, "EXPIRED", last, deadline, interval_min=interval_min)
    return None


def _outcome(trade, status, exit_px, hit_ts, both_in_bar=False, interval_min=1):
    side = 1 if trade["side"] == "BUY" else -1
    entry, sl = float(trade["entry"]), float(trade["sl"])
    risk = abs(entry - sl)
    if exit_px is None:
        r = pts = None
    else:
        pts = (float(exit_px) - entry) * side
        r = round(pts / risk, 2) if risk > 0 else 0.0
    return {"status": status, "exit": None if exit_px is None else float(exit_px),
            "hit_ts": _ts(hit_ts).isoformat(), "r": r, "points": pts,
            "both_in_bar": both_in_bar, "interval_min": int(interval_min)}


# ── price fetch in the alert's quote space ───────────────────────────────────

def _fetch_window(ticker, fetch, interval):
    df, err = fetch(ticker, interval, "5d")
    return (df[_OHLC] if df is not None and len(df) else None), err


def fetch_quote_bars(trade: dict, now: pd.Timestamp, fetch=None, gold_fn=None):
    """Returns (bars|None, interval_min|None, note). Bars are UTC bar-start
    indexed OHLC in the same price space as the alert's entry/SL/TP."""
    fetch = fetch or mdata.fetch
    src = trade.get("quote_source") or "none"
    sig = trade.get("signal_ticker")
    basis = float(trade.get("basis") or 0.0)
    errs = []
    for interval, mins in (("1m", 1), ("5m", 5)):
        if src == "none":
            df, err = _fetch_window(sig, fetch, interval)
            if df is not None:
                return df, mins, f"{sig} {interval}"
            errs.append(f"{sig} {interval}: {err}")
            continue

        s, serr = _fetch_window(sig, fetch, interval) if sig else (None, "no signal ticker")
        s_adj = s - basis if s is not None else None
        if src == "yf":
            qt = trade.get("quote_ticker")
            q, qerr = _fetch_window(qt, fetch, interval)
            if q is not None and s_adj is not None:
                return q.combine_first(s_adj), mins, f"{qt} {interval} (+{sig}−basis off-hours)"
            if q is not None:
                return q, mins, f"{qt} {interval}"
            if s_adj is not None:
                return s_adj, mins, f"{sig} {interval} − basis"
            errs.append(f"{qt}/{sig} {interval}: {qerr} / {serr}")
            continue
        if src == "gold_api":
            frames = [s_adj] if s_adj is not None else []
            try:
                from .pricing import _gold_api
                px, ts = (gold_fn or _gold_api)(trade.get("quote_ticker") or "XAU")
                frames.append(pd.DataFrame({k: [px] for k in _OHLC},
                                           index=pd.DatetimeIndex([_ts(ts).floor("min")])))
            except Exception as e:  # spot feed down — futures−basis alone is fine
                errs.append(f"gold-api: {e}")
            if frames:
                return pd.concat(frames).sort_index(), mins, f"{sig} {interval} − basis + spot"
            errs.append(f"{sig} {interval}: {serr}")
            continue
        return None, None, f"unknown quote source {src!r}"
    return None, None, "; ".join(errs)


def check_open_trades(state: dict, cfg: dict, now: pd.Timestamp, fetch_bars=None):
    """Resolve open trades. Mutates `state`; returns the list of newly closed
    records (each with notified=False). Never raises per-trade."""
    now = _ts(now)
    ocfg = outcome_cfg(cfg)
    book = trades_book(state)
    if not book["open"]:
        _prune(book, now, ocfg)
        return []
    max_h = ocfg.get("max_open_hours")
    max_h = float(max_h) if max_h else None
    is_open = market_open(now)
    fetch_bars = fetch_bars or (lambda tr, n: fetch_quote_bars(tr, n))
    cache: dict = {}
    still, closed_now = [], []
    for tr in book["open"]:
        try:
            past_deadline = max_h is not None and now >= _ts(tr["sent_ts"]) + pd.Timedelta(hours=max_h)
            if not is_open and not past_deadline:
                still.append(tr)                       # weekend: nothing trades
                continue
            key = (tr.get("quote_source"), tr.get("quote_ticker"), tr.get("signal_ticker"),
                   round(float(tr.get("basis") or 0), 6))
            if key not in cache:
                cache[key] = fetch_bars(tr, now)
            bars, mins, note = cache[key]
            if bars is None:
                # Feed down: keep waiting, but don't hold a trade forever.
                grace = past_deadline and now >= _ts(tr["sent_ts"]) + pd.Timedelta(hours=max_h + 1)
                if grace:
                    oc = _outcome(tr, "EXPIRED", None, now)
                    oc["note"] = f"no price data ({note})"
                    closed_now.append({**tr, **oc, "closed_ts": now.isoformat(), "notified": False,
                                       "notify_attempts": 0})
                else:
                    print(f"[outcomes] {tr['id']}: price fetch failed — {note}", flush=True)
                    still.append(tr)
                continue
            oc = detect_outcome(tr, bars, now, max_h, interval_min=mins or 1)
            if oc is None:
                still.append(tr)
                continue
            oc["source_note"] = note
            closed_now.append({**tr, **oc, "closed_ts": now.isoformat(), "notified": False,
                               "notify_attempts": 0})
        except Exception as e:
            print(f"[outcomes] {tr.get('id')}: check error {e!r}", flush=True)
            still.append(tr)
    book["open"] = still
    book["closed"].extend(closed_now)
    _prune(book, now, ocfg)
    return closed_now


def _prune(book, now, ocfg):
    keep_days = float(ocfg.get("retain_days", 14) or 14)
    cutoff = now - pd.Timedelta(days=keep_days)
    book["closed"] = [t for t in book["closed"] if _ts(t.get("closed_ts", now)) >= cutoff]


def pending_notifications(state: dict, cfg: dict | None = None) -> list:
    max_attempts = int(outcome_cfg(cfg).get("max_notify_attempts", 3))
    return [t for t in trades_book(state)["closed"]
            if not t.get("notified") and int(t.get("notify_attempts", 0)) < max_attempts]


# ── formatting ────────────────────────────────────────────────────────────────

def is_fx(trade: dict) -> bool:
    return "/" in trade.get("symbol", "") and abs(float(trade.get("entry", 0))) < 1000


def pip_size(trade: dict) -> float:
    return 0.01 if "JPY" in trade.get("symbol", "").upper() else 0.0001


def fmt_move(trade: dict, points: float | None) -> str:
    if points is None:
        return "n/a"
    if is_fx(trade):
        return f"{points / pip_size(trade):+,.1f} pips"
    d = 1 if abs(trade["entry"]) >= 1000 else 2
    return f"{points:+,.{d}f} pts"


def fmt_duration(seconds: float) -> str:
    m = max(0, int(round(seconds / 60)))
    d, m = divmod(m, 1440)
    h, m = divmod(m, 60)
    if d:
        return f"{d}d {h}h {m:02d}m"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def fmt_r(r) -> str:
    return "n/a" if r is None else f"{r:+.2f}R"


_HEAD = {"TP": "✅ <b>TP HIT</b>", "SL": "❌ <b>SL HIT</b>", "EXPIRED": "⌛ <b>EXPIRED</b>"}


def format_outcome_message(rec: dict, escape=None, max_open_hours=None) -> str:
    esc = escape or (lambda s: html.escape(str(s), quote=False))
    sent = _ts(rec["sent_ts"])
    hit = _ts(rec["hit_ts"])
    entry = rec["entry"]
    side = "🟢 BUY" if rec["side"] == "BUY" else "🔴 SELL"
    if rec["status"] == "EXPIRED":
        exit_line = (f"🏁 <b>Marked at:</b> {fmt_price(rec['exit'], entry)} (last price, closed)"
                     if rec.get("exit") is not None else "🏁 <b>Marked at:</b> n/a (no price data)")
        hrs = max_open_hours or round((hit - sent).total_seconds() / 3600)
        extra = f"\nℹ️ No TP/SL within {esc(f'{hrs:g}')}h — tracking stopped."
        if rec.get("note"):
            extra += f"\nℹ️ {esc(rec['note'])}"
    else:
        lvl = "TP" if rec["status"] == "TP" else "SL"
        exit_line = f"🏁 <b>Exit ({lvl}):</b> {fmt_price(rec['exit'], entry)}"
        extra = ""
        if rec.get("both_in_bar"):
            extra = (f"\n⚠️ TP and SL both traded inside the same {rec.get('interval_min', 1)}m "
                     f"candle — counted as SL (conservative).")
    return (
        f"{_HEAD[rec['status']]} — {esc(rec['symbol'])} {side}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🧩 <b>Setup:</b> {esc(rec.get('setup_label') or rec.get('setup', ''))}\n"
        f"💰 <b>Entry:</b> {fmt_price(entry, entry)}\n"
        f"{exit_line}\n"
        f"🎯 TP {fmt_price(rec['tp'], entry)} · 🛑 SL {fmt_price(rec['sl'], entry)}\n"
        f"📐 <b>Result:</b> {fmt_r(rec.get('r'))} · {esc(fmt_move(rec, rec.get('points')))}\n"
        f"⏱ <b>Open:</b> {fmt_duration((hit - sent).total_seconds())} "
        f"(alert {sent:%H:%M} → {hit:%H:%M UTC %d/%m})\n"
        f"🏦 <b>Price:</b> {esc(rec.get('quote_label', ''))}"
        f"{extra}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice.</i>"
    )


def _closed_day(t) -> str:
    return _ts(t.get("closed_ts")).strftime("%Y-%m-%d")


def day_stats(state: dict, day: str | None = None) -> dict:
    """Outcomes that closed on `day` (UTC YYYY-MM-DD, default state['day']),
    plus any earlier closes not yet included in a summary (e.g. a TP hit
    overnight or at the weekend), so every result lands in exactly one summary."""
    day = day or state.get("day")
    book = state.get("trades") or {}
    closed = [t for t in book.get("closed", [])
              if _closed_day(t) == day or not t.get("summarized")]
    wins = [t for t in closed if t["status"] == "TP"]
    losses = [t for t in closed if t["status"] == "SL"]
    expired = [t for t in closed if t["status"] == "EXPIRED"]
    net = sum(float(t.get("r") or 0) for t in wins + losses)
    return {"closed": closed, "wins": len(wins), "losses": len(losses),
            "expired": len(expired), "net_r": round(net, 2),
            "open": len(book.get("open", []))}


def mark_summarized(state: dict, day: str | None = None) -> None:
    for t in day_stats(state, day)["closed"]:
        t["summarized"] = True


def format_day_outcomes(state: dict, day: str | None = None, escape=None) -> str:
    esc = escape or (lambda s: html.escape(str(s), quote=False))
    s = day_stats(state, day)
    decided = s["wins"] + s["losses"]
    head = (f"🏁 <b>Outcomes today:</b> {s['wins']}W / {s['losses']}L"
            + (f" / {s['expired']} expired" if s["expired"] else "")
            + f" · net {s['net_r']:+.2f}R"
            + (f" · win rate {100 * s['wins'] / decided:.0f}%" if decided else ""))
    icon = {"TP": "✅", "SL": "❌", "EXPIRED": "⌛"}
    day = day or state.get("day")
    rows = [f"{icon[t['status']]} {esc(t['symbol'])} {t['side']} {fmt_r(t.get('r'))}"
            + (" (expired, not in net)" if t["status"] == "EXPIRED" else "")
            + ("" if _closed_day(t) == day else f" (closed {_ts(t['closed_ts']):%d/%m %H:%M})")
            for t in s["closed"]]
    tail = f"⏳ Still open: {s['open']}" if s["open"] else ""
    return "\n".join([head] + rows + ([tail] if tail else []))
