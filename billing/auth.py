"""Email magic-link + Telegram Login Widget verification."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import urlencode

from . import db
from .paystack import app_base_url


def magic_link_secret() -> str:
    # Prefer dedicated secret; fall back to Paystack secret / random-ish env
    return (
        os.environ.get("MAGIC_LINK_SECRET", "").strip()
        or os.environ.get("PAYSTACK_SECRET_KEY", "").strip()
        or "alphaedge-dev-magic-link-change-me"
    )


def telegram_bot_token() -> str:
    """Bot token used to verify Telegram Login Widget hashes (may differ from alert bot)."""
    return (
        os.environ.get("TELEGRAM_LOGIN_BOT_TOKEN", "").strip()
        or os.environ.get("TG_TOKEN", "").strip()
    )


def telegram_bot_username() -> str:
    return os.environ.get("TELEGRAM_LOGIN_BOT_USERNAME", "").strip()


def issue_magic_link(email: str) -> dict[str, Any]:
    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return {"ok": False, "error": "Enter a valid email address"}
    token = db.create_magic_link(email)
    link = f"{app_base_url()}/?ae_magic={token}"
    # Also expose a same-host relative form for Streamlit demo clicks
    relative = f"?ae_magic={token}"
    # MVP: no SMTP wired — caller shows the link when EMAIL_SMTP not configured.
    smtp_ready = bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_FROM"))
    emailed = False
    if smtp_ready:
        emailed = _try_send_email(email, link)
    return {
        "ok": True,
        "email": email,
        "emailed": emailed,
        "link": None if emailed else link,
        "relative_link": None if emailed else relative,
        "message": "Check your inbox for the sign-in link." if emailed else "Demo mode: use the link below (SMTP not configured).",
    }


def _try_send_email(to: str, link: str) -> bool:
    import smtplib
    from email.message import EmailMessage
    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", "")
    try:
        msg = EmailMessage()
        msg["Subject"] = "Your AlphaEdge sign-in link"
        msg["From"] = from_addr
        msg["To"] = to
        msg.set_content(
            f"Sign in to AlphaEdge:\n\n{link}\n\nThis link expires in 2 hours. If you did not request it, ignore this email."
        )
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            if user:
                s.login(user, password)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[billing] SMTP send failed: {e!r}", flush=True)
        return False


def complete_magic_login(token: str) -> dict[str, Any]:
    email = db.consume_magic_link(token)
    if not email:
        return {"ok": False, "error": "Magic link invalid or expired"}
    uid = db.upsert_email_user(email)
    session = db.create_session(uid)
    return {"ok": True, "session": session, "user": db.get_user(uid)}


def verify_telegram_login(payload: dict) -> dict[str, Any]:
    """Verify Telegram Login Widget data-check-string HMAC-SHA256."""
    token = telegram_bot_token()
    if not token:
        return {"ok": False, "error": "Telegram login not configured (TELEGRAM_LOGIN_BOT_TOKEN)"}
    check_hash = str(payload.get("hash") or "")
    if not check_hash:
        return {"ok": False, "error": "Missing hash"}
    pairs = []
    for k in sorted(payload.keys()):
        if k == "hash":
            continue
        if payload[k] is None or payload[k] == "":
            continue
        pairs.append(f"{k}={payload[k]}")
    data_check = "\n".join(pairs)
    secret_key = hashlib.sha256(token.encode()).digest()
    calc = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, check_hash):
        return {"ok": False, "error": "Telegram auth failed (bad hash)"}
    auth_date = int(payload.get("auth_date") or 0)
    if auth_date and time.time() - auth_date > 86400:
        return {"ok": False, "error": "Telegram login expired — try again"}
    uid = db.upsert_telegram_user(
        str(payload.get("id")),
        username=payload.get("username"),
        display_name=" ".join(
            x for x in [payload.get("first_name"), payload.get("last_name")] if x
        ) or None,
    )
    session = db.create_session(uid)
    return {"ok": True, "session": session, "user": db.get_user(uid)}


def telegram_login_widget_html() -> str:
    bot = telegram_bot_username()
    if not bot:
        return (
            "<div style='color:#888;font-size:12px;padding:8px 0'>"
            "Telegram login: set TELEGRAM_LOGIN_BOT_USERNAME (+ bot token) to enable the widget."
            "</div>"
        )
    # Widget posts to our app via data-auth-url or we use onauth callback → query params.
    # Streamlit can't easily receive JS postMessage, so we use data-auth-url with redirect.
    auth_url = f"{app_base_url()}/?ae_tg=1"
    return f'''
<div style="margin:8px 0">
  <script async src="https://telegram.org/js/telegram-widget.js?22"
    data-telegram-login="{bot}"
    data-size="large"
    data-userpic="false"
    data-auth-url="{auth_url}"
    data-request-access="write"></script>
</div>
'''
