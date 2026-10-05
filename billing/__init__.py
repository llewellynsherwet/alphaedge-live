"""AlphaEdge paid gate — auth + Paystack (ZA) MVP."""
from .gate import PLANS, SEAT_CAP, access_status, is_paid, seats_remaining
from .ui import render_auth_sidebar, render_paywall, require_access

__all__ = [
    "PLANS", "SEAT_CAP", "access_status", "is_paid", "seats_remaining",
    "render_auth_sidebar", "render_paywall", "require_access",
]
