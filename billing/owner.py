"""Owner / operator unlock for paywall toggle + Dev helpers.

Visitors never see owner controls. Unlock with:
  - Env OWNER_PIN (or AE_OWNER_PIN) + query ?owner_pin=<pin>
  - Or the same pin entered in the owner unlock form (only rendered when
    ?owner=1 is present, so casual visitors never see a "dev" teaser).

Once unlocked, st.session_state["ae_owner"] stays true for the Streamlit session.
If OWNER_PIN is unset, owner controls stay hidden (secure default).
"""
from __future__ import annotations

import hmac
import os

OWNER_SESSION_KEY = "ae_owner"


def owner_pin() -> str | None:
    pin = (os.environ.get("OWNER_PIN") or os.environ.get("AE_OWNER_PIN") or "").strip()
    return pin or None


def _qp_get(name: str):
    try:
        import streamlit as st
        v = st.query_params.get(name)
        if isinstance(v, list):
            return v[0] if v else None
        return v
    except Exception:
        return None


def _qp_del(*names: str):
    try:
        import streamlit as st
        for n in names:
            if n in st.query_params:
                del st.query_params[n]
    except Exception:
        pass


def is_owner() -> bool:
    """True when this Streamlit session is unlocked as owner."""
    try:
        import streamlit as st
        if st.session_state.get(OWNER_SESSION_KEY):
            return True
    except Exception:
        return False

    pin = owner_pin()
    if not pin:
        return False

    # Auto-unlock from query secret (then strip it from the URL).
    q = _qp_get("owner_pin")
    if q is not None and hmac.compare_digest(str(q), pin):
        try:
            import streamlit as st
            st.session_state[OWNER_SESSION_KEY] = True
        except Exception:
            return False
        _qp_del("owner_pin")
        return True
    return False


def try_unlock(candidate: str) -> bool:
    pin = owner_pin()
    if not pin or not candidate:
        return False
    if hmac.compare_digest(str(candidate).strip(), pin):
        import streamlit as st
        st.session_state[OWNER_SESSION_KEY] = True
        return True
    return False


def lock_owner() -> None:
    try:
        import streamlit as st
        st.session_state.pop(OWNER_SESSION_KEY, None)
    except Exception:
        pass
