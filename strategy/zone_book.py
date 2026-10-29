"""Zone-level dedupe that survives restarts without a disk.

* ``state["zone_book"]``: {zone_id: {symbol, side, sl, tp, ts, closed}}. NOT reset daily.
  A zone that signalled is blocked until its trade closed (SL or final TP traded in
  15m bars after the signal) or 24h passed — whichever is first.
* Render's free plan loses monitor_state.json on restart. ``rebuild`` therefore
  re-derives the book on boot by deterministically replaying the last 24h of
  schedule slots on the same yfinance data (no new secret / service). Past slots are
  marked done so they are never rescanned; the current slot may still scan, but any
  zone it already signalled is in the rebuilt book and is blocked.
"""
from __future__ import annotations

import pandas as pd

HOLD_HOURS = 24


def book(state: dict) -> dict:
    return state.setdefault("zone_book", {})


def _ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t


def prune(state: dict, now: pd.Timestamp, hold_hours: float = HOLD_HOURS) -> dict:
    b = book(state)
    for k in [k for k, v in b.items() if v.get("closed") or (now - _ts(v["ts"])) >= pd.Timedelta(hours=hold_hours)]:
        b.pop(k, None)
    return b


def _parse(zid: str):
    try:
        sym, side, lo, hi = zid.rsplit("|", 3)
        return sym, side, float(lo), float(hi)
    except Exception:
        return None


def is_blocked(state: dict, zid: str, now: pd.Timestamp, hold_hours: float = HOLD_HOURS) -> bool:
    """Blocked if the same zone id — or an overlapping zone for the same symbol+side
    (a 1H zone whose edges drift as new bars print) — has an open signal < hold_hours old."""
    me = _parse(zid)
    for k, v in book(state).items():
        if v.get("closed") or (now - _ts(v["ts"])) >= pd.Timedelta(hours=hold_hours):
            continue
        if k == zid:
            return True
        o = _parse(k)
        if me and o and me[:2] == o[:2] and me[2] <= o[3] and o[2] <= me[3]:
            return True
    return False


def add(state: dict, c, now: pd.Timestamp) -> None:
    tps = (c.meta or {}).get("tps") or (c.meta or {}).get("tps_fixed") or [c.tp]
    book(state)[c.zone_key] = {"symbol": c.symbol, "side": c.side, "sl": float(c.sl),
                               "tp": float(tps[-1]), "ts": now.isoformat(), "closed": False}


def update_closed(state: dict, symbol: str, bars: pd.DataFrame | None, now: pd.Timestamp) -> None:
    """Mark book entries for `symbol` closed when SL or final TP traded after the signal."""
    if bars is None or not len(bars):
        return
    for v in book(state).values():
        if v.get("closed") or v.get("symbol") != symbol:
            continue
        after = bars[(bars.index > _ts(v["ts"])) & (bars.index <= now)]
        if not len(after):
            continue
        hi, lo = float(after["High"].max()), float(after["Low"].min())
        if v["side"] == "BUY":
            v["closed"] = lo <= v["sl"] or hi >= v["tp"]
        else:
            v["closed"] = hi >= v["sl"] or lo <= v["tp"]


def frames_at(h1, m15, d1, now):
    """Closed-bar frames as the live fetch would have seen them at `now`."""
    f = {}
    if h1 is not None:
        f["1h"] = h1[(h1.index + pd.Timedelta(hours=1) <= now) & (h1.index >= now - pd.Timedelta(days=60))]
    if m15 is not None:
        f["15m"] = m15[(m15.index + pd.Timedelta(minutes=15) <= now) & (m15.index >= now - pd.Timedelta(days=5))]
    if d1 is not None:
        f["1d_long"] = d1[d1.index < now.normalize()]
    return f


def past_slots(now: pd.Timestamp, cfg: dict, hours: float = HOLD_HOURS):
    """(slot_key, slot_utc) for every schedule slot that STARTED in the last `hours`, oldest first."""
    from zoneinfo import ZoneInfo
    sch = cfg.get("schedule") or {}
    tz = ZoneInfo(sch.get("timezone", "Africa/Johannesburg"))
    minute, first, last = int(sch.get("minute", 58)), int(sch.get("first_hour", 5)), int(sch.get("last_hour", 18))
    loc = now.tz_convert(tz)
    t = (loc - pd.Timedelta(hours=hours)).replace(minute=minute, second=0, microsecond=0)
    out = []
    while t <= loc:
        if first <= t.hour <= last and not (sch.get("weekdays_only", True) and t.weekday() >= 5) \
                and t > loc - pd.Timedelta(hours=hours):
            out.append((t.strftime("%Y-%m-%dT%H:%M") + "+" + str(tz), t.tz_convert("UTC")))
        t += pd.Timedelta(hours=1)
    return out


def rebuild(state: dict, cfg: dict, now: pd.Timestamp, fetch=None, hours: float = HOLD_HOURS,
            setup_eval=None) -> dict:
    """Boot-time reconstruction (see module doc). Returns a small report dict."""
    from .data import fetch as _fetch
    from .setups.moon_wolf import evaluate as _mw
    fetch = fetch or _fetch
    setup_eval = setup_eval or _mw
    scfg = (cfg.get("setups") or {}).get("moon_wolf") or {}
    slots = past_slots(now, cfg, hours)
    rep = {"slots": len(slots), "zones": 0, "errors": []}
    if not slots:
        return rep
    # every slot already started is treated as done (the current one is re-checked by the caller)
    done = list(state.get("scan_slots_done") or [])
    for key, start in slots:
        if now - start >= pd.Timedelta(minutes=int((cfg.get("schedule") or {}).get("grace_minutes", 22))) \
                and key not in done:
            done.append(key)
    state["scan_slots_done"] = done[-48:]
    for i, sym in enumerate(cfg.get("symbols", [])):
        try:
            h1, e1 = fetch(sym["yf"], "1h", "90d")
            m15, e2 = fetch(sym["yf"], "15m", "10d")
            d1, e3 = fetch(sym["yf"], "1d", "1y")
        except Exception as e:  # noqa: BLE001
            rep["errors"].append(f"{sym['name']}: {e!r}"); continue
        if h1 is None or m15 is None:
            rep["errors"].append(f"{sym['name']}: {e1 or e2}"); continue
        for _key, start in slots:
            at = start + pd.Timedelta(minutes=2)   # what the live scan saw ~2 min into the slot
            if at > now:
                continue
            update_closed(state, sym["name"], m15, at)
            try:
                c = setup_eval(sym["name"], frames_at(h1, m15, d1, at), cfg, scfg, at, i)
            except Exception as e:  # noqa: BLE001
                rep["errors"].append(f"{sym['name']}: {e!r}"); break
            if c is None or is_blocked(state, c.zone_key, at, hours):
                continue
            add(state, c, at)
            rep["zones"] += 1
        update_closed(state, sym["name"], m15, now)
    prune(state, now, hours)
    return rep
