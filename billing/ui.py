"""Streamlit UI for auth + paywall."""
from __future__ import annotations

import streamlit as st

from . import auth, db, paystack
from .gate import PLANS, SEAT_CAP, access_status, is_paid, seats_remaining


SESSION_KEY = "ae_session_token"


def _qp_get(name: str):
    try:
        v = st.query_params.get(name)
        if isinstance(v, list):
            return v[0] if v else None
        return v
    except Exception:
        return None


def _qp_del(*names: str):
    try:
        for n in names:
            if n in st.query_params:
                del st.query_params[n]
    except Exception:
        pass


def bootstrap_from_query():
    """Handle magic-link / Telegram / Paystack return query params once per load."""
    if st.session_state.get("_ae_billing_bootstrapped"):
        return
    st.session_state["_ae_billing_bootstrapped"] = True

    magic = _qp_get("ae_magic")
    if magic:
        res = auth.complete_magic_login(magic)
        if res.get("ok"):
            st.session_state[SESSION_KEY] = res["session"]
            st.session_state["ae_flash"] = "Signed in via magic link."
        else:
            st.session_state["ae_flash_err"] = res.get("error") or "Magic link failed"
        _qp_del("ae_magic")

    # Telegram Login Widget redirects with id, hash, auth_date, etc.
    if _qp_get("ae_tg") or (_qp_get("hash") and _qp_get("id") and _qp_get("auth_date")):
        payload = {
            k: _qp_get(k)
            for k in (
                "id", "first_name", "last_name", "username", "photo_url",
                "auth_date", "hash",
            )
            if _qp_get(k) is not None
        }
        if payload.get("hash") and payload.get("id"):
            res = auth.verify_telegram_login(payload)
            if res.get("ok"):
                st.session_state[SESSION_KEY] = res["session"]
                st.session_state["ae_flash"] = "Signed in with Telegram."
            else:
                st.session_state["ae_flash_err"] = res.get("error") or "Telegram login failed"
        _qp_del("ae_tg", "id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash")

    pay_ref = _qp_get("ae_pay_ref")
    if pay_ref:
        res = paystack.verify_transaction(pay_ref)
        if res.get("ok"):
            sub = res.get("subscription") or {}
            uid = sub.get("user_id")
            # Paystack (and demo) return is a full navigation — re-issue a session so
            # the buyer stays signed in even if Streamlit session_state was reset.
            if uid:
                st.session_state[SESSION_KEY] = db.create_session(int(uid))
            st.session_state["ae_flash"] = (
                "Payment confirmed — AlphaEdge Pro unlocked."
                + (" (demo mode: Paystack keys not set)" if res.get("demo") else "")
            )
        else:
            st.session_state["ae_flash_err"] = res.get("error") or "Payment verification failed"
        _qp_del("ae_pay_ref", "ae_pay_demo")


def current_user():
    bootstrap_from_query()
    token = st.session_state.get(SESSION_KEY)
    return db.session_user(token)


def render_auth_sidebar():
    user = current_user()
    flash = st.session_state.pop("ae_flash", None)
    flash_err = st.session_state.pop("ae_flash_err", None)
    if flash:
        st.success(flash)
    if flash_err:
        st.error(flash_err)

    st.markdown("### 🔐 AlphaEdge Pro")
    rem = seats_remaining()
    st.caption(f"Paid seats: {SEAT_CAP - rem}/{SEAT_CAP} · {rem} left")

    if user:
        label = user.get("email") or user.get("telegram_username") or user.get("display_name") or f"user #{user['id']}"
        paid = is_paid(user)
        st.markdown(
            f"<div style='background:#111;border:1px solid #333;border-radius:6px;padding:10px;'>"
            f"<div style='color:#D4AF37;font-weight:700;font-size:12px'>{'✅ PRO' if paid else 'FREE / TEASER'}</div>"
            f"<div style='color:#ccc;font-size:12px;margin-top:4px'>Signed in as <b>{label}</b></div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("Sign out", width="stretch", key="ae_signout"):
            db.destroy_session(st.session_state.get(SESSION_KEY))
            st.session_state.pop(SESSION_KEY, None)
            st.rerun()
        return access_status(user)

    # --- sign in ---
    with st.expander("Email magic link", expanded=True):
        email = st.text_input("Email", key="ae_magic_email", placeholder="you@example.com")
        if st.button("Send magic link", width="stretch", key="ae_magic_send"):
            res = auth.issue_magic_link(email or "")
            if not res.get("ok"):
                st.error(res.get("error"))
            else:
                st.info(res.get("message"))
                if res.get("link"):
                    rel = res.get("relative_link") or res["link"]
                    st.markdown(f"[Open magic link to sign in]({rel})")
                    st.code(res["link"], language=None)
                    st.caption("SMTP not configured — use the link (set APP_BASE_URL in production).")

    st.markdown("**Or Telegram**")
    st.markdown(auth.telegram_login_widget_html(), unsafe_allow_html=True)
    # Dev helper when Telegram widget not configured
    if not auth.telegram_bot_username():
        with st.expander("Dev: simulate Telegram login"):
            tg_id = st.text_input("Telegram user id", key="ae_tg_dev_id", value="10001")
            tg_user = st.text_input("Username", key="ae_tg_dev_user", value="demo_trader")
            if st.button("Dev Telegram sign-in", key="ae_tg_dev_btn"):
                uid = db.upsert_telegram_user(tg_id, username=tg_user, display_name=tg_user)
                st.session_state[SESSION_KEY] = db.create_session(uid)
                st.rerun()

    return access_status(None)


def render_paywall(user: dict | None):
    """CTA + plan picker. Call when authenticated but unpaid (or to upsell)."""
    rem = seats_remaining()
    preferred = next(p for p in PLANS.values() if p.get("preferred"))
    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,#0a0a0a,#1a1508);border:1px solid #D4AF37;border-radius:10px;
            padding:18px 20px;margin:12px 0 18px 0;">
  <div style="color:#D4AF37;font-weight:800;font-size:18px;letter-spacing:1px;">UNLOCK ALPHAEDGE PRO</div>
  <div style="color:#bbb;font-size:13px;margin-top:8px;line-height:1.55;">
    Full live signals, immersive chart, COT, sentiment &amp; community tools.
    Teaser stays free. Paid seats capped at <b style="color:#D4AF37">{SEAT_CAP}</b>
    ({rem} remaining) · ~R5/day · Paystack (ZA).
  </div>
  <div style="margin-top:12px;display:flex;gap:10px;flex-wrap:wrap;">
    <span style="background:#D4AF37;color:#000;font-weight:700;padding:6px 10px;border-radius:4px;font-size:12px;">
      ★ {preferred['label']} R{preferred['amount_cents']//100} — preferred
    </span>
    <span style="background:#1c1c1c;color:#D4AF37;border:1px solid #333;padding:6px 10px;border-radius:4px;font-size:12px;">
      Weekly R{PLANS['weekly']['amount_cents']//100}
    </span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    if not user:
        st.info("Sign in with email magic link or Telegram (sidebar) to subscribe.")
        return

    if rem <= 0:
        st.error(f"Sold out — all {SEAT_CAP} paid seats are taken.")
        return

    if not user.get("email"):
        st.warning("Add an email via magic-link sign-in before Paystack checkout (Paystack requires email).")
        return

    cols = st.columns(2)
    for i, plan in enumerate(PLANS.values()):
        with cols[i % 2]:
            label = f"{'★ ' if plan.get('preferred') else ''}{plan['label']} — R{plan['amount_cents']//100}"
            if st.button(label, width="stretch", key=f"ae_buy_{plan['id']}"):
                res = paystack.initialize_transaction(user, plan["id"])
                if not res.get("ok"):
                    st.error(res.get("error"))
                else:
                    url = res.get("authorization_url")
                    if res.get("demo"):
                        st.warning(res.get("message") or "Demo checkout")
                    if url:
                        st.link_button("Continue to payment ➤", url, width="stretch")
                        st.caption(f"Reference: `{res.get('reference')}`")


def render_teaser_banner():
    st.markdown(
        """
<div style="background:#1a0a0a;border:1px solid #FF6B35;border-radius:6px;padding:12px 16px;margin-bottom:14px;">
  <p style="margin:0;color:#FF6B35;font-size:12px;font-weight:bold;letter-spacing:1px;">🔒 TEASER MODE</p>
  <p style="margin:6px 0 0 0;color:#aaa;font-size:12px;line-height:1.5;">
    You're seeing a limited preview. Sign in and subscribe (R149/mo or R35/wk via Paystack) for the full command centre.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )


def require_access() -> dict:
    """Return access_status; used by app to branch teaser vs full."""
    user = current_user()
    return access_status(user)
