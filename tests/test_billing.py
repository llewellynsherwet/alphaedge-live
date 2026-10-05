import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["AE_BILLING_DB"] = "/tmp/alphaedge_billing_test.db"
os.environ["AE_PAYWALL_OVERRIDE"] = "/tmp/alphaedge_paywall_override_test.json"
# Force gate ON for subscription-flow assertions (default is OFF = free Pro).
os.environ["PAYWALL_ENABLED"] = "true"
try:
    os.remove("/tmp/alphaedge_billing_test.db")
except FileNotFoundError:
    pass
try:
    os.remove("/tmp/alphaedge_paywall_override_test.json")
except FileNotFoundError:
    pass

from billing import db, auth, paystack, gate  # noqa: E402
from billing.plans import PLANS, SEAT_CAP  # noqa: E402


def test_plans_and_cap():
    assert SEAT_CAP == 300
    assert PLANS["weekly"]["amount_cents"] == 3500
    assert PLANS["monthly"]["amount_cents"] == 14900
    assert PLANS["monthly"]["preferred"] is True


def test_paywall_defaults_off_grants_pro():
    # Clear override + unset env → default OFF → everyone is Pro.
    gate.clear_paywall_override()
    os.environ.pop("PAYWALL_ENABLED", None)
    assert gate.paywall_enabled() is False
    assert gate.is_paid(None) is True
    status = gate.access_status(None)
    assert status["paid"] is True
    assert status["paywall_enabled"] is False
    # Restore for other tests
    os.environ["PAYWALL_ENABLED"] = "true"


def test_paywall_toggle_override():
    os.environ["PAYWALL_ENABLED"] = "true"
    gate.clear_paywall_override()
    assert gate.paywall_enabled() is True
    gate.set_paywall_enabled(False)
    assert gate.paywall_enabled() is False
    assert gate.is_paid(None) is True
    gate.set_paywall_enabled(True)
    assert gate.paywall_enabled() is True
    assert gate.is_paid(None) is False
    gate.clear_paywall_override()
    assert gate.paywall_enabled() is True  # back to env


def test_magic_link_login_and_demo_pay():
    os.environ["PAYWALL_ENABLED"] = "true"
    gate.clear_paywall_override()
    res = auth.issue_magic_link("trader@example.com")
    assert res["ok"] and res["link"]
    token = res["link"].split("ae_magic=")[1]
    done = auth.complete_magic_login(token)
    assert done["ok"]
    user = done["user"]
    assert gate.is_paid(user) is False
    init = paystack.initialize_transaction(user, "monthly")
    assert init["ok"] and init.get("demo") is True
    ver = paystack.verify_transaction(init["reference"])
    assert ver["ok"]
    user2 = db.get_user(user["id"])
    assert gate.is_paid(user2) is True
    assert gate.seats_remaining() == SEAT_CAP - 1


def test_owner_pin_gate():
    from billing import owner as ow
    # No pin → never owner
    os.environ.pop("OWNER_PIN", None)
    os.environ.pop("AE_OWNER_PIN", None)
    assert ow.owner_pin() is None
    assert ow.try_unlock("secret") is False

    os.environ["OWNER_PIN"] = "test-pin-9"
    assert ow.owner_pin() == "test-pin-9"
    assert ow.try_unlock("wrong") is False
    # try_unlock needs streamlit session_state — skip full unlock here;
    # compare_digest path is covered by wrong-pin False above.
    os.environ.pop("OWNER_PIN", None)
