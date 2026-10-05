import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["AE_BILLING_DB"] = "/tmp/alphaedge_billing_test.db"
try:
    os.remove("/tmp/alphaedge_billing_test.db")
except FileNotFoundError:
    pass

from billing import db, auth, paystack, gate  # noqa: E402
from billing.plans import PLANS, SEAT_CAP  # noqa: E402


def test_plans_and_cap():
    assert SEAT_CAP == 300
    assert PLANS["weekly"]["amount_cents"] == 3500
    assert PLANS["monthly"]["amount_cents"] == 14900
    assert PLANS["monthly"]["preferred"] is True


def test_magic_link_login_and_demo_pay():
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
