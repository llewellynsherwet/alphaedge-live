"""Position sizing from a fixed % account risk (FX only). Illustrative, not advice.

Pip value per 1.00 standard lot (100k units), in USD:
  xxx/USD  → 10             USD/xxx (CAD, CHF) → 10 / price
  USD/JPY  → 1000 / price   JPY crosses        → 1000 / usdjpy_ref (config; default 150)
"""
from __future__ import annotations

import math


def is_fx(symbol: str) -> bool:
    s = symbol.replace(" ", "")
    return len(s) == 7 and s[3] == "/" and s.replace("/", "").isalpha()


def pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def pip_value_per_lot_usd(symbol: str, price: float, usdjpy_ref: float = 150.0) -> float | None:
    if not is_fx(symbol):
        return None
    base, quote = symbol.replace(" ", "").split("/")
    if quote == "USD":
        return 10.0
    if base == "USD" and quote == "JPY":
        return 1000.0 / price
    if base == "USD":
        return 10.0 / price
    if quote == "JPY":
        return 1000.0 / float(usdjpy_ref)
    return None


def size_position(symbol: str, entry: float, sl: float, rcfg: dict | None, usdjpy_ref: float | None = None) -> dict | None:
    """Returns {sl_pips, risk_amount, lots, pip_value, ccy, account, risk_pct} or None."""
    rcfg = rcfg or {}
    if not rcfg.get("enabled", False) or not is_fx(symbol):
        return None
    acct = float(rcfg.get("account_size", 1000))
    pct = float(rcfg.get("risk_pct", 1.0))
    ref = float(usdjpy_ref or rcfg.get("usdjpy_ref", 150.0))
    pv = pip_value_per_lot_usd(symbol, entry, ref)
    sl_pips = abs(entry - sl) / pip_size(symbol)
    if not pv or sl_pips <= 0:
        return None
    risk_amt = acct * pct / 100.0
    step = float(rcfg.get("lot_step", 0.01))
    lots = math.floor(risk_amt / (sl_pips * pv) / step + 1e-9) * step
    lots = max(lots, 0.0)
    real_risk = lots * sl_pips * pv
    return {"sl_pips": round(sl_pips, 1), "risk_amount": round(risk_amt, 2),
            "actual_risk": round(real_risk, 2), "lots": round(lots, 2),
            "pip_value": round(pv, 4), "ccy": rcfg.get("currency", "USD"),
            "account": acct, "risk_pct": pct}
