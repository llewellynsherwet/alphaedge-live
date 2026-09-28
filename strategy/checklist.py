"""Config-driven confluence checklist scoring."""

PRETTY = {
    "htf_bias": "HTF bias aligned", "premium_discount": "Premium/discount location",
    "liquidity_sweep": "Liquidity sweep", "mss_bos": "Break of structure (displacement)",
    "pd_array": "Fresh FVG / order block", "kill_zone": "Kill-zone timing",
    "breakout_close": "Closed outside opening range", "strong_candle": "Strong breakout candle",
    "volume_confirm": "Volume confirmation", "vwap_side": "Correct side of VWAP",
    "gap_align": "Breakout with overnight gap", "vwap_trend": "VWAP trend day",
    "pullback_touch": "First pullback to VWAP", "confirm_close": "Confirmation close",
    "volume_signature": "Volume dries up into touch", "active_hours": "Active hours (no lull)",
}


def score(factors: dict, checklist_cfg: dict):
    """Returns (score, max_score, missing_required, lines)."""
    total = 0
    max_score = 0
    missing = []
    lines = []
    for name, spec in (checklist_cfg or {}).items():
        spec = spec or {}
        w = int(spec.get("weight", 1))
        ok = bool(factors.get(name, False))
        max_score += w
        if ok:
            total += w
        elif spec.get("required"):
            missing.append(name)
        lines.append(("✅ " if ok else "❌ ") + PRETTY.get(name, name))
    return total, max_score, missing, lines
