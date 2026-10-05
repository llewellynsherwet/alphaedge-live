"""Pricing — R5/day equivalent; prefer monthly for lower Paystack fee drag."""
from __future__ import annotations

SEAT_CAP = 300

# amounts in ZAR cents for Paystack
PLANS = {
    "weekly": {
        "id": "weekly",
        "label": "Weekly",
        "amount_cents": 3500,   # R35 ≈ R5/day
        "days": 7,
        "blurb": "R35 / week (~R5 per day)",
        "preferred": False,
    },
    "monthly": {
        "id": "monthly",
        "label": "Monthly",
        "amount_cents": 14900,  # R149 — preferred (better vs fees)
        "days": 30,
        "blurb": "R149 / month · best value vs card fees",
        "preferred": True,
    },
}

CURRENCY = "ZAR"
