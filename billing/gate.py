"""Access control: unpaid teaser vs paid full dashboard."""
from __future__ import annotations

from . import db
from .plans import PLANS, SEAT_CAP

__all__ = ["PLANS", "SEAT_CAP", "is_paid", "seats_remaining", "access_status"]


def seats_remaining() -> int:
    return max(0, SEAT_CAP - db.active_paid_count())


def is_paid(user: dict | None) -> bool:
    if not user:
        return False
    return db.user_active_subscription(int(user["id"])) is not None


def access_status(user: dict | None) -> dict:
    sub = db.user_active_subscription(int(user["id"])) if user else None
    return {
        "authenticated": user is not None,
        "paid": sub is not None,
        "user": user,
        "subscription": sub,
        "seats_remaining": seats_remaining(),
        "seat_cap": SEAT_CAP,
    }
