"""
Standalone Telegram scanner for Render.

Streamlit only executes app.py when a real browser opens the site, so the
background scanner in app.py never starts after a deploy/restart until
someone visits (uptime pingers like UptimeRobot don't count). This worker is
launched from the Render start command alongside Streamlit, so scanning and
Telegram alerts begin as soon as the service boots.

It reuses the signal/Telegram code from app.py (everything above the UI
section) so there is only one copy of the strategy.
"""
import os
import sys
import time
import logging

MARKER = "# --- TRADINGVIEW POP-UP ---"


def main():
    if not os.environ.get("TG_TOKEN") or not os.environ.get("TG_CHAT_ID"):
        print("[worker] TG_TOKEN / TG_CHAT_ID not set on this service — scanner not started", flush=True)
        return
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "app.py"), encoding="utf-8").read()
    src = src[: src.index(MARKER)]
    os.environ["MONITOR_MODE"] = "app"          # let the engine start its monitor + online ping here
    ns = {"__name__": "alphaedge_engine", "__file__": os.path.join(here, "app.py")}
    exec(compile(src, "app.py", "exec"), ns)    # defines strategies, starts monitor thread, sends online ping
    print("[worker] scanner running", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[worker] fatal: {e!r}", file=sys.stderr, flush=True)
        raise
