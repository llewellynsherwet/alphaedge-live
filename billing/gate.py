"""Access control: unpaid teaser vs paid full dashboard.

Paywall is a toggle (not removed):
  - Env PAYWALL_ENABLED defaults to false → full Pro for everyone.
  - Optional durable override via paywall_override.json (sidebar switch).
  - When OFF: is_paid / access_status treat everyone as Pro (no checkout needed).
  - When ON: unpaid users see teaser; paid see full dashboard.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import db
from .plans import PLANS, SEAT_CAP

__all__ = [
    "PLANS",
    "SEAT_CAP",
    "is_paid",
    "seats_remaining",
    "access_status",
    "paywall_enabled",
    "set_paywall_enabled",
    "clear_paywall_override",
    "paywall_source",
]

_OVERRIDE_PATH = Path(
    os.environ.get("AE_PAYWALL_OVERRIDE", "paywall_override.json")
)


def _truthy(val: str | None) -> bool:
    if val is None:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on")


def _read_override() -> bool | None:
    """Return True/False if a durable override exists, else None."""
    try:
        if not _OVERRIDE_PATH.is_file():
            return None
        raw = _OVERRIDE_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        if isinstance(data, dict) and "enabled" in data:
            return bool(data["enabled"])
        if isinstance(data, bool):
            return data
    except Exception:
        return None
    return None


def paywall_enabled() -> bool:
    """True only when the paywall gate is ON (teaser for unpaid).

    Default OFF: unset env and no override → full Pro for everyone.
    Priority: durable override file > PAYWALL_ENABLED env (default false).
    """
    override = _read_override()
    if override is not None:
        return override
    return _truthy(os.environ.get("PAYWALL_ENABLED"))


def paywall_source() -> str:
    """Where the current on/off setting came from (for UI caption)."""
    if _read_override() is not None:
        return "sidebar override"
    if "PAYWALL_ENABLED" in os.environ:
        return "env PAYWALL_ENABLED"
    return "default (off)"


def set_paywall_enabled(enabled: bool) -> None:
    """Persist owner toggle so all visitors share the same gate state."""
    payload = {"enabled": bool(enabled)}
    _OVERRIDE_PATH.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def clear_paywall_override() -> None:
    """Remove durable override; fall back to env / default."""
    try:
        _OVERRIDE_PATH.unlink(missing_ok=True)
    except TypeError:
        # Python <3.8 missing_ok — keep compatible path anyway
        if _OVERRIDE_PATH.exists():
            _OVERRIDE_PATH.unlink()
    except Exception:
        pass


def seats_remaining() -> int:
    return max(0, SEAT_CAP - db.active_paid_count())


def is_paid(user: dict | None) -> bool:
    # Paywall OFF → treat everyone (including anonymous) as Pro.
    if not paywall_enabled():
        return True
    if not user:
        return False
    return db.user_active_subscription(int(user["id"])) is not None


def access_status(user: dict | None) -> dict:
    enabled = paywall_enabled()
    if not enabled:
        sub = None
        if user:
            sub = db.user_active_subscription(int(user["id"]))
        return {
            "authenticated": user is not None,
            "paid": True,
            "paywall_enabled": False,
            "paywall_source": paywall_source(),
            "user": user,
            "subscription": sub,
            "seats_remaining": seats_remaining(),
            "seat_cap": SEAT_CAP,
        }
    sub = db.user_active_subscription(int(user["id"])) if user else None
    return {
        "authenticated": user is not None,
        "paid": sub is not None,
        "paywall_enabled": True,
        "paywall_source": paywall_source(),
        "user": user,
        "subscription": sub,
        "seats_remaining": seats_remaining(),
        "seat_cap": SEAT_CAP,
    }
