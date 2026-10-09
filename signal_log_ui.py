"""Streamlit widgets: signal log viewer + the site-wide 'not financial advice' notice."""
import streamlit as st

from strategy import signal_log as sl

DISCLAIMER = ("⚠️ **Not financial advice.** AlphaEdge signals are educational, automated and unverified; "
              "trading leveraged FX/CFDs carries a high risk of loss. Past or back-tested results do not "
              "guarantee future results. Never risk money you cannot afford to lose.")


def render_disclaimer():
    st.markdown(f'<div style="margin:18px 0 70px 0;padding:10px 14px;border:1px solid #444;border-radius:8px;'
                f'font-size:12px;opacity:.85">{DISCLAIMER.replace("**", "")}</div>', unsafe_allow_html=True)


def render_signal_log(cfg: dict | None = None):
    with st.expander("🧾 SIGNAL LOG — every alert and its outcome", expanded=False):
        st.caption(DISCLAIMER)
        df = sl.read_log(cfg=cfg)
        if df.empty:
            st.info("No signals logged yet. Every alert the bot sends is recorded here with its TP / SL result.")
            return
        s = sl.summary(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Signals", s["signals"]); c2.metric("Closed", s["closed"])
        c3.metric("Win rate", f"{s['win_rate']}%" if s["win_rate"] is not None else "—")
        c4.metric("Net R", f"{s['net_r']:+.2f}")
        st.dataframe(df.sort_values("sent_utc", ascending=False), width="stretch", hide_index=True)
        st.download_button("⬇️ Download CSV", df.to_csv(index=False).encode(), "signal_log.csv", "text/csv")
