"""Paystack (South Africa) helpers. Keys from env — never hard-coded."""
from __future__ import annotations

import os
import secrets
import uuid
from typing import Any

import requests

from . import db
from .plans import CURRENCY, PLANS


def public_key() -> str:
    return os.environ.get("PAYSTACK_PUBLIC_KEY", "").strip()


def secret_key() -> str:
    return os.environ.get("PAYSTACK_SECRET_KEY", "").strip()


def keys_configured() -> bool:
    return bool(public_key() and secret_key())


def app_base_url() -> str:
    return os.environ.get("APP_BASE_URL", "http://localhost:8501").rstrip("/")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {secret_key()}",
        "Content-Type": "application/json",
    }


def new_reference(plan_id: str) -> str:
    return f"ae_{plan_id}_{uuid.uuid4().hex[:16]}"


def initialize_transaction(user: dict, plan_id: str) -> dict[str, Any]:
    """Create a Paystack transaction. Returns {ok, authorization_url?, reference?, error?, demo?}."""
    plan = PLANS.get(plan_id)
    if not plan:
        return {"ok": False, "error": "Unknown plan"}
    if not user.get("email"):
        return {"ok": False, "error": "Paystack checkout needs an email on your account. Sign in with email magic link first."}

    seats = db.active_paid_count()
    from .plans import SEAT_CAP
    if seats >= SEAT_CAP:
        return {"ok": False, "error": f"Sold out — {SEAT_CAP} paid seats are full."}

    reference = new_reference(plan_id)
    db.create_pending_subscription(int(user["id"]), plan_id, reference, plan["amount_cents"])

    if not keys_configured():
        # Demo / placeholder path: fake checkout URL pointing back with reference
        demo_url = f"?ae_pay_ref={reference}&ae_pay_demo=1"  # relative — works regardless of APP_BASE_URL host
        return {
            "ok": True,
            "demo": True,
            "reference": reference,
            "authorization_url": demo_url,
            "message": "Paystack keys not set — demo checkout only. Set PAYSTACK_SECRET_KEY + PAYSTACK_PUBLIC_KEY.",
        }

    callback = f"{app_base_url()}/?ae_pay_ref={reference}"  # absolute required by Paystack
    payload = {
        "email": user["email"],
        "amount": plan["amount_cents"],
        "currency": CURRENCY,
        "reference": reference,
        "callback_url": callback,
        "metadata": {
            "user_id": user["id"],
            "plan": plan_id,
            "product": "AlphaEdge Pro",
        },
    }
    try:
        r = requests.post(
            "https://api.paystack.co/transaction/initialize",
            headers=_headers(),
            json=payload,
            timeout=20,
        )
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Paystack request failed: {e!r}"}
    if not data.get("status"):
        return {"ok": False, "error": data.get("message") or "Paystack initialize failed"}
    d = data.get("data") or {}
    return {
        "ok": True,
        "demo": False,
        "reference": reference,
        "authorization_url": d.get("authorization_url"),
        "access_code": d.get("access_code"),
    }


def verify_transaction(reference: str) -> dict[str, Any]:
    """Verify and activate subscription on success."""
    sub = db.get_subscription_by_reference(reference)
    if not sub:
        return {"ok": False, "error": "Unknown reference"}
    plan = PLANS.get(sub["plan"]) or PLANS["monthly"]

    # Demo activation when keys missing and reference pending
    if not keys_configured():
        if sub["status"] == "active":
            return {"ok": True, "demo": True, "subscription": sub}
        activated = db.activate_subscription(reference, plan["id"], plan["days"], {"demo": True})
        return {"ok": True, "demo": True, "subscription": activated}

    try:
        r = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=_headers(),
            timeout=20,
        )
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Verify failed: {e!r}"}
    if not data.get("status"):
        return {"ok": False, "error": data.get("message") or "Verify rejected"}
    d = data.get("data") or {}
    if str(d.get("status", "")).lower() != "success":
        return {"ok": False, "error": f"Payment status: {d.get('status')}"}
    # amount check
    if int(d.get("amount") or 0) < int(plan["amount_cents"]):
        return {"ok": False, "error": "Paid amount too low"}
    activated = db.activate_subscription(reference, plan["id"], plan["days"], d)
    return {"ok": True, "demo": False, "subscription": activated}
