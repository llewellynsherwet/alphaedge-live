import streamlit as st
import time
import os
import json
import html
import re
import sqlite3
import threading
import requests
import pandas as pd
import yfinance as yf

import base64
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Confluence Day Template engine (config-driven; shared with monitor_worker)
from strategy.engine import (
    session_info as _engine_session_info,
    next_session as _engine_next_session,
    load_state as _engine_load_state,
    save_state as _engine_save_state,
    scan_once as _engine_scan_once,
    evaluate_display as _engine_evaluate_display,
    format_trade_message as _engine_format_trade,
    format_daily_summary as _engine_format_summary,
    record_emits as _engine_record_emits,
    load_config as _engine_load_config,
)
from strategy.config_loader import load_config as _load_strategy_config
from strategy import outcomes as _outcomes
from strategy.common import fmt_price as _fmt_price
from ui_widgets import (persistent_chart_html, chart_bridge_html, popup_chart_html,
                        station_html, station_static_url, tv_static_url, tv_youtube_embed_url,
                        TV_CHANNELS, tv_chart_url)

from billing.ui import render_auth_sidebar, render_paywall, render_teaser_banner, require_access
from billing.gate import is_paid as _billing_is_paid

_NY_TZ = ZoneInfo("America/New_York")

# ================= 1. PAGE CONFIG & BRANDING =================
st.set_page_config(page_title="AlphaEdge | Trading Intelligence", page_icon="🅰️", layout="wide", initial_sidebar_state="expanded")

# --- EXPANDED ASSET LIST ---
TICKER_MAP = {
    "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X",
    "USD/CHF": "USDCHF=X", "AUD/USD": "AUDUSD=X", "USD/CAD": "USDCAD=X",
    "NZD/USD": "NZDUSD=X", "USD/ZAR": "USDZAR=X", "GBP/ZAR": "GBPZAR=X",
    "S&P 500": "ES=F", "NASDAQ 100": "NQ=F", "US 30": "YM=F", "VIX": "^VIX",
    "GOLD": "GC=F", "SILVER": "SI=F", "OIL (WTI)": "CL=F", "NAT GAS": "NG=F",
    "BITCOIN": "BTC-USD", "ETHEREUM": "ETH-USD", "SOLANA": "SOL-USD"
}

TV_MAP = {
    "EUR/USD": "FX:EURUSD", "GBP/USD": "FX:GBPUSD", "USD/JPY": "FX:USDJPY",
    "USD/CHF": "FX:USDCHF", "AUD/USD": "FX:AUDUSD", "USD/CAD": "FX:USDCAD",
    "NZD/USD": "FX:NZDUSD", "USD/ZAR": "FX:USDZAR", "GBP/ZAR": "FX:GBPZAR",
    # Indices: cash/CFD symbols, matching the repriced signal levels (quote: in strategy_config.yaml)
    "S&P 500": "OANDA:SPX500USD", "NASDAQ 100": "OANDA:NAS100USD", "US 30": "OANDA:US30USD",
    "VIX": "TVC:VIX", "DAX 40": "INDEX:DE40",
    "GOLD": "OANDA:XAUUSD", "SILVER": "TVC:SILVER", "OIL (WTI)": "NYMEX:CL1!",
    "BITCOIN": "BINANCE:BTCUSDT", "ETHEREUM": "BINANCE:ETHUSDT", "SOLANA": "BINANCE:SOLUSDT"
}

CHART_HEIGHT = 820
_CHART_HTML = persistent_chart_html(TV_MAP["EUR/USD"])

# Trading Station: radio-first (HTML5 audio / same-origin static page). Optional
# YouTube links open on youtube.com — we never embed or scrape YouTube here.
STATIONS = {
    "Lofi Trading Beats": {
        "radio": {
            "url": "https://lofi.stream.laut.fm/lofi",
            "title": "laut.fm lofi radio",
            "fallback": [
                "https://stream.laut.fm/lofi",
                "https://ice1.somafm.com/dronezone-128-mp3",
            ],
        },
        "youtube": "https://www.youtube.com/@LofiGirl",
    },
    "Chillout Jazz": {
        "radio": {
            "url": "https://jazz-wr04.ice.infomaniak.ch/jazz-wr04-128.mp3",
            "title": "Jazz Radio (FR)",
            "fallback": ["https://ice1.somafm.com/groovesalad-128-mp3"],
        },
        "youtube": "https://www.youtube.com/results?search_query=relaxing+jazz+piano+radio",
    },
    "Chill / Groove": {
        "radio": {
            "url": "https://ice1.somafm.com/groovesalad-128-mp3",
            "title": "SomaFM Groove Salad",
            "fallback": ["https://ice1.somafm.com/dronezone-128-mp3"],
        },
        "youtube": None,
    },
    "Pop Radio": {
        "radio": {
            "url": "https://listen.181fm.com/181-themix_128k.mp3",
            "title": "181.FM The Mix",
            "fallback": ["https://ice1.somafm.com/poptron-128-mp3"],
        },
        "youtube": None,
    },
    "Hip Hop Radio": {
        "radio": {
            "url": "https://pureplay.cdnstream1.com/6045_128.mp3",
            "title": "Hip Hop Radio",
            "fallback": ["https://ice1.somafm.com/beatblender-128-mp3"],
        },
        "youtube": None,
    },
}

PIP_MAP = {
    "USDJPY=X": 0.01, "GBPJPY=X": 0.01,
    "EURUSD=X": 0.0001, "GBPUSD=X": 0.0001, "USDCHF=X": 0.0001,
    "AUDUSD=X": 0.0001, "USDCAD=X": 0.0001, "NZDUSD=X": 0.0001,
    "USDZAR=X": 0.0001, "GBPZAR=X": 0.0001,
    "GC=F": 0.10, "SI=F": 0.005, "CL=F": 0.01, "NG=F": 0.001,
    "ES=F": 0.25, "NQ=F": 0.25, "YM=F": 1.0, "^VIX": 0.01,
    "BTC-USD": 10.0, "ETH-USD": 1.0, "SOL-USD": 0.05,
}

FOREX_TICKERS     = {"EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X","AUDUSD=X","USDCAD=X","NZDUSD=X","USDZAR=X","GBPZAR=X"}
COMMODITY_TICKERS = {"GC=F","SI=F","CL=F","NG=F"}
INDEX_TICKERS     = {"ES=F","NQ=F","YM=F","^VIX"}
CRYPTO_TICKERS    = {"BTC-USD","ETH-USD","SOL-USD"}
TICKER_DISPLAY    = {v: k for k, v in TICKER_MAP.items()}

# --- CSS ---
_css = (
    "<style>"
    ".stApp { background-color: #050505; color: #e0e0e0; }"
    "section[data-testid='stSidebar'] { background-color: #000000; border-right: 1px solid #222; }"
    ".stTabs [data-baseweb='tab-list'] { gap: 8px; background-color: #080808; padding: 10px; border-bottom: 2px solid #D4AF37; }"
    ".stTabs [data-baseweb='tab'] { height: 50px; background-color: #111; color: #888; border: 1px solid #333; border-bottom: none; padding-left: 20px; padding-right: 20px; }"
    ".stTabs [aria-selected='true'] { background-color: #D4AF37 !important; color: #000 !important; font-weight: bold; }"
    "h1, h2, h3 { color: #D4AF37 !important; text-transform: uppercase; font-family: 'Helvetica Neue', sans-serif; }"
    ".heatmap-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 13px; background-color: #080808; border: 1px solid #333; }"
    ".heatmap-table th { background-color: #111; color: #D4AF37; padding: 12px; text-align: left; border-bottom: 2px solid #D4AF37; }"
    ".heatmap-table td { padding: 10px; border-bottom: 1px solid #222; color: #ccc; }"
    ".bullish { color: #00ff88 !important; font-weight: bold; }"
    ".bearish { color: #ff4b4b !important; font-weight: bold; }"
    ".live-tag { color: #00ff88; border: 1px solid #00ff88; padding: 2px 5px; font-size: 10px; border-radius: 3px; }"
    ".ticker-footer { position: fixed; bottom: 0; left: 0; width: 100%; height: 40px; background: #000; border-top: 1px solid #D4AF37; z-index: 999999; }"
    ".main .block-container { padding-bottom: 60px; }"
    ".symbol-col { background-color: #304FFE; color: white !important; font-weight: bold; }"
    ".bull-strong { background-color: #2962FF; color: white; }"
    ".bull-med { background-color: #448AFF; color: white; }"
    ".bear-strong { background-color: #D50000; color: white; }"
    ".bear-med { background-color: #FF5252; color: white; }"
    ".kill-zone-badge { display:inline-block; background:#00ff88; color:#000; font-size:10px; font-weight:bold; padding:2px 8px; border-radius:3px; margin-left:8px; }"
    ".dead-zone-badge { display:inline-block; background:#ff4b4b; color:#fff; font-size:10px; font-weight:bold; padding:2px 8px; border-radius:3px; margin-left:8px; }"
    ".reason-box { background:#0a0f0a; border:1px solid #1a3a1a; border-left:3px solid #00ff88; border-radius:4px; padding:10px 14px; margin-top:10px; font-size:12px; color:#aaa; line-height:1.7; }"
    ".reason-box-sell { background:#0f0a0a; border:1px solid #3a1a1a; border-left:3px solid #ff4b4b; border-radius:4px; padding:10px 14px; margin-top:10px; font-size:12px; color:#aaa; line-height:1.7; }"
    ".stElementContainer:has(iframe[srcdoc*='ae-chart-bridge']) { display:none !important; }"
    "</style>"
)
st.markdown(_css, unsafe_allow_html=True)

# ================= PWA — makes app installable on phones =================
st.markdown("""
    <link rel="manifest" href="app/static/manifest.json">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="AlphaEdge">
    <meta name="theme-color" content="#D4AF37">
    <link rel="apple-touch-icon" href="app/static/icon-192.png">
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', function() {
                navigator.serviceWorker.register('app/static/sw.js')
                    .then(r => console.log('AlphaEdge SW registered'))
                    .catch(e => console.log('SW error:', e));
            });
        }
    </script>
""", unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════
# CREDENTIALS — EDIT THESE LINES ONLY
# ══════════════════════════════════════════════════════════════════════════════
# CREDENTIALS — Telegram only (no other API keys needed)
# Set these as Environment Variables on Render dashboard
# OR replace the placeholder strings below with your actual values
# ══════════════════════════════════════════════════════════════════════════════
_TG_TOKEN   = os.environ.get("TG_TOKEN", "").strip()     # from @BotFather — set on Render, never in code
_TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()   # your Telegram chat ID — set on Render

# NOTE: No Finnhub key needed. No other API keys needed.
# Signal engine uses yfinance — free, no key, works on Render.


def _tg_escape(text) -> str:
    """Escape <, > and & so Telegram's HTML parser accepts dynamic text
    (strategy reasons contain '->' and '<0.05%', which made Telegram reject
    the whole message with 'can't parse entities')."""
    return html.escape(str(text), quote=False)


def _send_telegram(message: str) -> bool:
    """Send a message to the Telegram bot. Returns True on success.
    Failures are printed to the Render logs instead of being silently ignored."""
    if not _TG_TOKEN or not _TG_CHAT_ID:
        print("[telegram] TG_TOKEN / TG_CHAT_ID not set — message skipped", flush=True)
        return False
    url = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
    payload = {"chat_id": _TG_CHAT_ID, "text": message[:4096],
               "parse_mode": "HTML", "disable_web_page_preview": True}
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.ok:
                return True
            desc = r.json().get("description", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            print(f"[telegram] send failed ({r.status_code}): {desc}", flush=True)
            if r.status_code == 400 and "parse" in str(desc).lower():
                # Formatting problem: resend as plain text so the alert still arrives
                payload.pop("parse_mode", None)
                payload["text"] = re.sub(r"</?[a-zA-Z][^>]*>", "", message)[:4096]
                continue
            if r.status_code == 429:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)))
                continue
            return False
        except Exception as e:
            print(f"[telegram] network error: {e}", flush=True)
            time.sleep(2)
    return False


def get_session_info():
    """Returns (in_session, session_name). Delegates to the config-driven engine
    (Mon–Fri, 07:00–17:00 UTC by default — see strategy_config.yaml)."""
    return _engine_session_info()


def _next_session():
    """Returns (name, time_str) of the next upcoming session window."""
    return _engine_next_session()



def _calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.where(delta > 0, 0.0).ewm(alpha=1/period, adjust=False).mean()
    loss  = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/period, adjust=False).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _calc_atr(df, period=14):
    hl  = df["High"] - df["Low"]
    hc  = (df["High"] - df["Close"].shift()).abs()
    lc  = (df["Low"]  - df["Close"].shift()).abs()
    tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _calc_macd_hist(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd     = ema_fast - ema_slow
    sig_line = macd.ewm(span=signal, adjust=False).mean()
    return macd - sig_line


def _check_entry(df, direction):
    """Simple entry check — EMA9 cross of EMA21."""
    c      = df["Close"]
    e9     = c.ewm(span=9,  adjust=False).mean()
    e21    = c.ewm(span=21, adjust=False).mean()
    if direction == "bull":
        return e9.iloc[-1] > e21.iloc[-1]
    return e9.iloc[-1] < e21.iloc[-1]


@st.cache_data(ttl=60, show_spinner=False)
def get_dashboard_data():
    """Fetch dashboard heatmap data for all 20 assets via yfinance."""
    results = {}
    for name, sym in TICKER_MAP.items():
        try:
            df = yf.Ticker(sym).history(period="5d", interval="1h")
            if df is None or len(df) < 10:
                results[name] = {"price": 0, "bias": "—", "score": 0,
                                 "trend": "—", "tech": "—", "source": "yf"}
                continue
            df   = df[["Open","High","Low","Close","Volume"]].dropna()
            c    = df["Close"]
            sma  = c.rolling(20).mean()
            rsi  = _calc_rsi(c)
            e9   = c.ewm(span=9,  adjust=False).mean()
            e21  = c.ewm(span=21, adjust=False).mean()
            price = c.iloc[-1]
            r     = rsi.iloc[-1]
            bull  = price > sma.iloc[-1] and e9.iloc[-1] > e21.iloc[-1]
            bear  = price < sma.iloc[-1] and e9.iloc[-1] < e21.iloc[-1]
            bias  = "🟢 BULL" if bull else "🔴 BEAR" if bear else "⚪ NEUTRAL"
            score = round(r, 1)
            trend = "↑ ABOVE SMA20" if price > sma.iloc[-1] else "↓ BELOW SMA20"
            tech  = f"RSI {r:.1f}"
            results[name] = {"price": price, "bias": bias, "score": score,
                             "trend": trend, "tech": tech, "source": "yf"}
        except Exception:
            results[name] = {"price": 0, "bias": "—", "score": 0,
                             "trend": "—", "tech": "—", "source": "yf"}
    return results


def _yf_candles(ticker_symbol: str, interval: str, bars: int):
    """
    Fetch OHLCV via yfinance.
    interval: '1m','5m','15m','1h','4h','1d'
    Returns DataFrame or None. Logs failures to Telegram once per session.
    """
    try:
        import yfinance as yf
        period_map = {
            "1m":  "1d",
            "5m":  "5d",
            "15m": "5d",
            "1h":  "30d",
            "4h":  "60d",
            "1d":  "180d",
        }
        period = period_map.get(interval, "30d")
        ticker = yf.Ticker(ticker_symbol)
        df     = ticker.history(period=period, interval=interval)
        if df is None or len(df) < 5:
            _log_data_error(ticker_symbol, interval, f"only {len(df) if df is not None else 0} bars returned")
            return None
        df = df[["Open","High","Low","Close","Volume"]].dropna()
        if len(df) < 5:
            _log_data_error(ticker_symbol, interval, "all NaN after dropna")
            return None
        return df.tail(bars)
    except Exception as e:
        _log_data_error(ticker_symbol, interval, str(e))
        return None


_data_errors: dict = {}   # track errors so we don't spam Telegram

def _log_data_error(symbol: str, interval: str, reason: str):
    """Send ONE Telegram alert per symbol per session if data fails."""
    key = f"{symbol}_{interval}"
    if key not in _data_errors:
        _data_errors[key] = True
        try:
            _send_telegram(
                f"⚠️ <b>DATA ERROR</b>\n"
                f"Symbol: {_tg_escape(symbol)} | Interval: {_tg_escape(interval)}\n"
                f"Reason: {_tg_escape(reason)}\n"
                f"<i>Check yfinance / network on Render</i>"
            )
        except Exception:
            pass


def _us30_open_strategy(ticker_symbol):
    # LEGACY — superseded by strategy.setups.orb_open; kept for reference.
    # The live engine never calls this.
    try:
        # NYSE cash open is 09:30 New York time. Work in NY time so the windows
        # stay correct through daylight-saving changes (13:30 UTC in summer,
        # 14:30 UTC in winter). The old code hard-coded UTC hours.
        now_ny     = datetime.now(_NY_TZ)
        h          = now_ny.hour + now_ny.minute / 60.0
        in_preopen = 7.5 <= h < 9.5     # 07:30-09:30 NY
        at_open    = 9.5 <= h < 10.5    # first hour after the open
        if now_ny.weekday() >= 5 or not (in_preopen or at_open):
            return "WAIT", 0.0, 0.0, 0.0, "US30: waiting for pre-open window (07:30-10:30 New York time)"

        score = 0
        layers = []
        box_bias = stock_bias = dxy_bias = pattern_bias = smc_bias = "neutral"

        # L1: Pre-market box
        df_5m = _yf_candles(ticker_symbol, "5m", 100)
        box_high = box_low = 0.0
        pm = None
        if df_5m is not None and len(df_5m) >= 20:
            idx_ny = df_5m.index.tz_convert(_NY_TZ)
            today  = idx_ny.date == now_ny.date()
            mins   = idx_ny.hour * 60 + idx_ny.minute
            pm     = df_5m[today & (mins >= 8 * 60 + 30) & (mins < 9 * 60 + 30)]
        if pm is not None and len(pm) >= 3:
            box_high = pm["High"].max()
            box_low  = pm["Low"].min()
            px = df_5m["Close"].iloc[-1]
            if px > box_high:
                score += 1; box_bias = "bull"
                layers.append("L1 PASS: Price ABOVE pre-market box -> BULLISH")
            elif px < box_low:
                score += 1; box_bias = "bear"
                layers.append("L1 PASS: Price BELOW pre-market box -> BEARISH")
            else:
                layers.append("L1 WAIT: Price inside pre-market box")
        else:
            layers.append("L1 SKIP: pre-market box (08:30-09:30 NY) not formed yet or 5M data unavailable")

        # L2: DOW component bias
        dow = {"UNH":"UNH","GS":"GS","MSFT":"MSFT","HD":"HD","AMGN":"AMGN","MCD":"MCD","CAT":"CAT","V":"V"}
        bc = nc = 0
        for sym in dow.values():
            try:
                ds = _yf_candles(sym, "1h", 20)
                if ds is not None and len(ds) >= 10:
                    c = ds["Close"]
                    if c.iloc[-1] > c.ewm(span=21, adjust=False).mean().iloc[-1]:
                        bc += 1
                    else:
                        nc += 1
            except Exception:
                pass
        tot = bc + nc
        if tot > 0:
            bp = bc / tot * 100
            if bp >= 62:
                score += 1; stock_bias = "bull"
                layers.append("L2 PASS: " + str(bc) + "/" + str(tot) + " DOW stocks BULLISH")
            elif bp <= 38:
                score += 1; stock_bias = "bear"
                layers.append("L2 PASS: " + str(nc) + "/" + str(tot) + " DOW stocks BEARISH")
            else:
                layers.append("L2 WAIT: DOW mixed " + str(bc) + " bull / " + str(nc) + " bear")
        else:
            layers.append("L2 SKIP: DOW data unavailable")

        # L3: DXY inverse
        df_dxy = _yf_candles("DX-Y.NYB", "1h", 20)
        if df_dxy is not None and len(df_dxy) >= 10:
            dc = df_dxy["Close"]
            de9  = dc.ewm(span=9,  adjust=False).mean()
            de21 = dc.ewm(span=21, adjust=False).mean()
            if de9.iloc[-1] < de21.iloc[-1] and dc.iloc[-1] < dc.iloc[-3]:
                score += 1; dxy_bias = "bull"
                layers.append("L3 PASS: DXY FALLING -> US30 BULLISH pressure")
            elif de9.iloc[-1] > de21.iloc[-1] and dc.iloc[-1] > dc.iloc[-3]:
                score += 1; dxy_bias = "bear"
                layers.append("L3 PASS: DXY RISING -> US30 BEARISH pressure")
            else:
                layers.append("L3 WAIT: DXY ranging")
        else:
            layers.append("L3 SKIP: DXY unavailable")

        # L4: Double top / bottom on 30M
        df_30m = _yf_candles(ticker_symbol, "30m", 20)
        if df_30m is not None and len(df_30m) >= 10:
            hh30 = df_30m["High"].values[-10:]
            ll30 = df_30m["Low"].values[-10:]
            h1i  = hh30.argmax(); tmp = hh30.copy(); tmp[h1i] = 0; h2i = tmp.argmax()
            if h1i != h2i and abs(hh30[h1i] - hh30[h2i]) / hh30[h1i] < 0.0015:
                score += 1; pattern_bias = "bear"
                layers.append("L4 PASS: DOUBLE TOP on 30M -> BEARISH reversal")
            else:
                l1i = ll30.argmin(); tmp2 = ll30.copy(); tmp2[l1i] = 999999; l2i = tmp2.argmin()
                if l1i != l2i and abs(ll30[l1i] - ll30[l2i]) / ll30[l1i] < 0.0015:
                    score += 1; pattern_bias = "bull"
                    layers.append("L4 PASS: DOUBLE BOTTOM on 30M -> BULLISH reversal")
                else:
                    layers.append("L4 WAIT: No double top/bottom detected")
        else:
            layers.append("L4 SKIP: 30M data unavailable")

        # L5: SMC 4H structure
        df_4h = _yf_candles(ticker_symbol, "4h", 21)
        if df_4h is not None and len(df_4h) >= 9:
            df_4h = df_4h.iloc[:-1]   # closed candles only
            c4 = df_4h["Close"]; h4 = df_4h["High"]; l4 = df_4h["Low"]
            e4 = c4.ewm(span=21, adjust=False).mean()
            hh = h4.iloc[-1] > h4.iloc[-3]; hl = l4.iloc[-1] > l4.iloc[-3]
            lh = h4.iloc[-1] < h4.iloc[-3]; ll = l4.iloc[-1] < l4.iloc[-3]
            if (hh or hl) and c4.iloc[-1] > e4.iloc[-1]:
                score += 1; smc_bias = "bull"
                layers.append("L5 PASS: 4H BULLISH structure (HH/HL above EMA21)")
            elif (lh or ll) and c4.iloc[-1] < e4.iloc[-1]:
                score += 1; smc_bias = "bear"
                layers.append("L5 PASS: 4H BEARISH structure (LH/LL below EMA21)")
            else:
                layers.append("L5 WAIT: 4H structure unclear")
        else:
            layers.append("L5 SKIP: 4H data unavailable")

        biases   = [box_bias, stock_bias, dxy_bias, pattern_bias, smc_bias]
        bull_pts = biases.count("bull")
        bear_pts = biases.count("bear")
        sep      = "-" * 24
        hdr = (
            "US30 OPEN STRATEGY " + str(score) + "/5\n" + sep + "\n"
            + "\n".join(layers) + "\n" + sep + "\n"
            + "Confluence: " + str(bull_pts) + " BULL / " + str(bear_pts) + " BEAR\n"
        )

        if bull_pts < 3 and bear_pts < 3:
            return "WAIT", 0.0, 0.0, 0.0, hdr + "Need 3+ layers same direction"

        direction = "bull" if bull_pts >= bear_pts else "bear"

        if in_preopen:
            bias_lbl = "BULLISH" if direction == "bull" else "BEARISH"
            return "WAIT", 0.0, 0.0, 0.0, (
                hdr + bias_lbl + " bias confirmed\n"
                + "WAIT for the 09:30 New York open candle to close\n"
                + "ENTRY: Pullback to first open 5M candle body"
            )

        if df_5m is not None and len(df_5m) >= 5:
            atr5  = _calc_atr(df_5m).iloc[-1]
            price = df_5m["Close"].iloc[-1]
            if direction == "bull":
                sl   = (box_low if box_low > 0 else price - atr5 * 3) - atr5 * 0.5
                risk = price - sl
                if risk <= 0 or risk > price * 0.05:
                    sl = price - atr5 * 3; risk = price - sl
                tp = price + max(risk * 2.5, atr5 * 5)
                rr = (tp - price) / risk if risk > 0 else 0
                return "BUY", price, tp, sl, (
                    hdr + "BUY " + str(round(price, 1))
                    + " | TP " + str(round(tp, 1))
                    + " | SL " + str(round(sl, 1))
                    + " | R:R 1:" + str(round(rr, 1))
                )
            else:
                sl   = (box_high if box_high > 0 else price + atr5 * 3) + atr5 * 0.5
                risk = sl - price
                if risk <= 0 or risk > price * 0.05:
                    sl = price + atr5 * 3; risk = sl - price
                tp = price - max(risk * 2.5, atr5 * 5)
                rr = (price - tp) / risk if risk > 0 else 0
                return "SELL", price, tp, sl, (
                    hdr + "SELL " + str(round(price, 1))
                    + " | TP " + str(round(tp, 1))
                    + " | SL " + str(round(sl, 1))
                    + " | R:R 1:" + str(round(rr, 1))
                )

        return "WAIT", 0.0, 0.0, 0.0, hdr + "Insufficient price data"

    except Exception as e:
        return "WAIT", 0.0, 0.0, 0.0, "US30 error: " + str(e)


def _smc_4h_strategy(display_name, ticker_symbol):
    # LEGACY — superseded by strategy.setups.smc_sweep; kept for reference.
    # The live engine never calls this.
    try:
        df_4h = _yf_candles(ticker_symbol, "4h", 31)
        df_1h = _yf_candles(ticker_symbol, "1h", 51)
        if df_4h is None or df_1h is None:
            return "WAIT", 0.0, 0.0, 0.0, "SMC 4H: data unavailable"
        live_price = float(df_1h["Close"].iloc[-1])
        # The last bar yfinance returns is still forming and changes every
        # minute, which made signals appear and disappear. Judge structure,
        # EMAs, RSI and MACD on CLOSED candles only; enter at the live price.
        df_4h = df_4h.iloc[:-1]
        df_1h = df_1h.iloc[:-1]
        if len(df_4h) < 8 or len(df_1h) < 20:
            return "WAIT", 0.0, 0.0, 0.0, "SMC 4H: insufficient bars"

        score = 0; layers = []

        # L1: 4H structure
        h4h = df_4h["High"]; h4l = df_4h["Low"]; h4c = df_4h["Close"]
        hh = h4h.iloc[-1] > h4h.iloc[-3]; hl = h4l.iloc[-1] > h4l.iloc[-3]
        lh = h4h.iloc[-1] < h4h.iloc[-3]; ll = h4l.iloc[-1] < h4l.iloc[-3]
        if hh and hl:
            direction = "bull"; score += 1
            layers.append("L1 PASS: 4H HH+HL -> BULLISH structure")
        elif lh and ll:
            direction = "bear"; score += 1
            layers.append("L1 PASS: 4H LH+LL -> BEARISH structure")
        elif hh or hl:
            direction = "bull"; layers.append("L1 PARTIAL: Partial bullish")
        elif lh or ll:
            direction = "bear"; layers.append("L1 PARTIAL: Partial bearish")
        else:
            return "WAIT", h4c.iloc[-1], 0.0, 0.0, "SMC 4H: ranging market, no structure"

        # L2: 4H Order block
        ob_high = ob_low = 0.0
        for i in range(len(df_4h) - 1, max(len(df_4h) - 8, -1), -1):
            o = df_4h["Open"].iloc[i]; c = df_4h["Close"].iloc[i]
            if direction == "bull" and c < o:
                ob_high = df_4h["High"].iloc[i]; ob_low = df_4h["Low"].iloc[i]
                score += 1
                layers.append("L2 PASS: OB at " + str(round(ob_low, 4)) + "-" + str(round(ob_high, 4)))
                break
            elif direction == "bear" and c > o:
                ob_high = df_4h["High"].iloc[i]; ob_low = df_4h["Low"].iloc[i]
                score += 1
                layers.append("L2 PASS: OB at " + str(round(ob_low, 4)) + "-" + str(round(ob_high, 4)))
                break
        if ob_high == 0.0:
            layers.append("L2 WAIT: No clean order block found")

        # L3: 1H EMA
        h1c  = df_1h["Close"]
        e9   = h1c.ewm(span=9,  adjust=False).mean()
        e21  = h1c.ewm(span=21, adjust=False).mean()
        price = live_price
        ab = e9.iloc[-1] > e21.iloc[-1]
        be = e9.iloc[-1] < e21.iloc[-1]
        if direction == "bull" and ab:
            score += 1; tag = "fresh" if e9.iloc[-2] <= e21.iloc[-2] else "aligned"
            layers.append("L3 PASS: 1H EMA9 above EMA21 (" + tag + ")")
        elif direction == "bear" and be:
            score += 1; tag = "fresh" if e9.iloc[-2] >= e21.iloc[-2] else "aligned"
            layers.append("L3 PASS: 1H EMA9 below EMA21 (" + tag + ")")
        else:
            layers.append("L3 WAIT: 1H EMA not confirmed")

        # L4: RSI
        rv = _calc_rsi(h1c).iloc[-1]
        if direction == "bull" and 40 <= rv <= 65:
            score += 1; layers.append("L4 PASS: RSI " + str(round(rv, 1)) + " in zone (40-65)")
        elif direction == "bear" and 35 <= rv <= 60:
            score += 1; layers.append("L4 PASS: RSI " + str(round(rv, 1)) + " in zone (35-60)")
        else:
            layers.append("L4 WAIT: RSI " + str(round(rv, 1)) + " outside zone")

        # L5: MACD
        mh = _calc_macd_hist(h1c)
        mn = mh.iloc[-1]; mp = mh.iloc[-2]
        if direction == "bull" and (mn > mp or mn > 0):
            score += 1; layers.append("L5 PASS: MACD " + ("rising" if mn > mp else "positive"))
        elif direction == "bear" and (mn < mp or mn < 0):
            score += 1; layers.append("L5 PASS: MACD " + ("falling" if mn < mp else "negative"))
        else:
            layers.append("L5 WAIT: MACD not confirming")

        sep = "-" * 24
        hdr = (
            "SMC 4H STRATEGY " + str(score) + "/5\n" + sep + "\n"
            + "\n".join(layers) + "\n" + sep + "\n"
        )

        if score < 4:
            return "WAIT", price, 0.0, 0.0, hdr + "Need 4/5 layers (currently " + str(score) + "/5)"

        atr1h  = _calc_atr(df_1h).iloc[-1]
        sw_low = df_1h["Low"].iloc[-6:].min()
        sw_hi  = df_1h["High"].iloc[-6:].max()
        sess   = "London" if datetime.now(timezone.utc).hour < 12 else "New York"

        if direction == "bull":
            sl_b = ob_low if ob_low > 0 else sw_low
            sl   = sl_b - atr1h * 0.3
            risk = price - sl
            if risk <= 0 or risk > price * 0.07:
                return "WAIT", price, 0.0, 0.0, hdr + "SL too wide, wait for better pullback"
            tp = price + max(risk * 2.5, atr1h * 3)
            rr = (tp - price) / risk
            return "BUY", price, tp, sl, (
                hdr + "Session: " + sess + "\n"
                + "Entry: " + str(round(price, 5))
                + " | TP: " + str(round(tp, 5))
                + " | SL: " + str(round(sl, 5))
                + " | R:R 1:" + str(round(rr, 1))
            )
        else:
            sl_b = ob_high if ob_high > 0 else sw_hi
            sl   = sl_b + atr1h * 0.3
            risk = sl - price
            if risk <= 0 or risk > price * 0.07:
                return "WAIT", price, 0.0, 0.0, hdr + "SL too wide, wait for better pullback"
            tp = price - max(risk * 2.5, atr1h * 3)
            rr = (price - tp) / risk if risk > 0 else 0
            return "SELL", price, tp, sl, (
                hdr + "Session: " + sess + "\n"
                + "Entry: " + str(round(price, 5))
                + " | TP: " + str(round(tp, 5))
                + " | SL: " + str(round(sl, 5))
                + " | R:R 1:" + str(round(rr, 1))
            )

    except Exception as e:
        return "WAIT", 0.0, 0.0, 0.0, "SMC 4H error: " + str(e)


def _signal_engine(display_name):
    """UI + monitor entry point. Runs the Confluence Day Template for one symbol.
    Returns (sig, entry, tp, sl, reason) — same 5-tuple the rest of the app expects.
    """
    try:
        sig, entry, tp, sl, reason, _meta = _engine_evaluate_display(display_name)
        return sig, entry, tp, sl, reason
    except Exception as e:
        return "WAIT", 0.0, 0.0, 0.0, "Engine error: " + str(e)


def _forex_signal(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        df5  = stock.history(period="5d",  interval="5m")
        df1d = stock.history(period="60d", interval="1d")
        df4h = stock.history(period="60d", interval="1h")

        if len(df5) < 30 or len(df1d) < 21 or len(df4h) < 50:
            return "⚪ WAITING", 0.0, 0.0, 0.0, ""

        close5 = df5['Close']
        high5  = df5['High']
        low5   = df5['Low']

        in_kz, session_name = get_session_info()

        daily_ema20   = df1d['Close'].ewm(span=20, adjust=False).mean()
        daily_bullish = df1d['Close'].iloc[-1] > daily_ema20.iloc[-1]
        daily_bearish = df1d['Close'].iloc[-1] < daily_ema20.iloc[-1]

        ema200_4h = df4h['Close'].ewm(span=200, adjust=False).mean()
        above_200 = df4h['Close'].iloc[-1] > ema200_4h.iloc[-1]
        below_200 = df4h['Close'].iloc[-1] < ema200_4h.iloc[-1]

        ema9    = close5.ewm(span=9,  adjust=False).mean()
        ema21   = close5.ewm(span=21, adjust=False).mean()
        c_price = close5.iloc[-1]
        c_ema9  = ema9.iloc[-1]
        c_ema21 = ema21.iloc[-1]

        delta    = close5.diff()
        ema_gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
        ema_loss = (-1 * delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
        rsi      = 100 - (100 / (1 + ema_gain / ema_loss))
        c_rsi    = rsi.iloc[-1]

        pullback_pct = abs(c_price - c_ema21) / c_ema21
        on_pullback  = pullback_pct < 0.0005

        tr    = pd.concat([high5 - low5, (high5 - close5.shift()).abs(), (low5 - close5.shift()).abs()], axis=1).max(axis=1)
        c_atr = tr.rolling(14).mean().iloc[-1]
        tp_dist = c_atr * 1.5
        sl_dist = c_atr * 1.0

        long_ok  = daily_bullish and above_200 and c_ema9 > c_ema21 and c_price > c_ema9 and 40 <= c_rsi <= 65 and on_pullback
        short_ok = daily_bearish and below_200 and c_ema9 < c_ema21 and c_price < c_ema9 and 35 <= c_rsi <= 60 and on_pullback

        if long_ok:
            reason = (
                f"✅ Session: {session_name}\n"
                f"✅ Daily bias: BULLISH — above 1D EMA20\n"
                f"✅ 4H: Price above 200 EMA\n"
                f"✅ 5m EMA: 9 crossed above 21\n"
                f"✅ RSI: {c_rsi:.1f} — mid zone\n"
                f"✅ Pullback: {pullback_pct*100:.3f}% from 21 EMA"
            )
            return "🟢 STRONG BUY", c_price, c_price + tp_dist, c_price - sl_dist, reason
        elif short_ok:
            reason = (
                f"✅ Session: {session_name}\n"
                f"✅ Daily bias: BEARISH — below 1D EMA20\n"
                f"✅ 4H: Price below 200 EMA\n"
                f"✅ 5m EMA: 9 crossed below 21\n"
                f"✅ RSI: {c_rsi:.1f} — mid zone\n"
                f"✅ Pullback: {pullback_pct*100:.3f}% from 21 EMA"
            )
            return "🔴 SELL", c_price, c_price - tp_dist, c_price + sl_dist, reason
        else:
            missing = []
            if not on_pullback: missing.append(f"price {pullback_pct*100:.3f}% from EMA 21 (need <0.05%)")
            if daily_bullish and not above_200: missing.append("price below 4H 200 EMA")
            if daily_bearish and not below_200: missing.append("price above 4H 200 EMA")
            if not (40 <= c_rsi <= 65 or 35 <= c_rsi <= 60): missing.append(f"RSI {c_rsi:.1f} outside zone")
            reason = ("Waiting: " + " | ".join(missing)) if missing else "No confluence"
            return "⚪ WAITING", c_price, 0.0, 0.0, reason
    except Exception:
        return "⚪ WAITING", 0.0, 0.0, 0.0, ""


@st.cache_data(ttl=30, show_spinner=False)
def _commodity_index_signal(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        df5  = stock.history(period="5d",  interval="5m")
        df1h = stock.history(period="30d", interval="1h")

        if len(df5) < 50 or len(df1h) < 55:
            return "⚪ WAITING", 0.0, 0.0, 0.0, ""

        close5  = df5['Close']
        high5   = df5['High']
        low5    = df5['Low']
        volume5 = df5['Volume']

        ema50_1h    = df1h['Close'].ewm(span=50, adjust=False).mean()
        htf_bullish = df1h['Close'].iloc[-1] > ema50_1h.iloc[-1]
        htf_bearish = df1h['Close'].iloc[-1] < ema50_1h.iloc[-1]

        ema21_5m    = close5.ewm(span=21, adjust=False).mean()
        ema9_5m     = close5.ewm(span=9,  adjust=False).mean()
        struct_bull = ema9_5m.iloc[-1] > ema21_5m.iloc[-1] and close5.iloc[-1] > ema21_5m.iloc[-1]
        struct_bear = ema9_5m.iloc[-1] < ema21_5m.iloc[-1] and close5.iloc[-1] < ema21_5m.iloc[-1]

        macd_line = close5.ewm(span=12, adjust=False).mean() - close5.ewm(span=26, adjust=False).mean()
        histogram = macd_line - macd_line.ewm(span=9, adjust=False).mean()
        macd_bull = histogram.iloc[-1] > 0 and histogram.iloc[-1] > histogram.iloc[-2]
        macd_bear = histogram.iloc[-1] < 0 and histogram.iloc[-1] < histogram.iloc[-2]

        delta5   = close5.diff()
        avg_gain = delta5.clip(lower=0).ewm(com=13, adjust=False).mean()
        avg_loss = (-1 * delta5.clip(upper=0)).ewm(com=13, adjust=False).mean()
        c_rsi    = (100 - (100 / (1 + avg_gain / avg_loss))).iloc[-1]
        rsi_bull = 45 <= c_rsi <= 62
        rsi_bear = 38 <= c_rsi <= 55

        vol_avg   = volume5.rolling(20).mean()
        vol_surge = volume5.iloc[-1] > (vol_avg.iloc[-1] * 1.3)
        vol_pct   = ((volume5.iloc[-1] / vol_avg.iloc[-1]) - 1) * 100

        tr        = pd.concat([high5 - low5, (high5 - close5.shift()).abs(), (low5 - close5.shift()).abs()], axis=1).max(axis=1)
        atr14     = tr.rolling(14).mean()
        atr_active = atr14.iloc[-1] > atr14.rolling(10).mean().iloc[-1]

        last_body  = abs(close5.iloc[-1] - df5['Open'].iloc[-1])
        last_range = high5.iloc[-1] - low5.iloc[-1]
        conviction = (last_range > 0) and (last_body / last_range > 0.50)
        body_pct   = (last_body / last_range * 100) if last_range > 0 else 0

        c_atr   = atr14.iloc[-1]
        c_price = close5.iloc[-1]
        tp_dist = c_atr * 2.0
        sl_dist = c_atr * 1.0

        long_signal  = htf_bullish and struct_bull and macd_bull and rsi_bull and vol_surge and atr_active and conviction
        short_signal = htf_bearish and struct_bear and macd_bear and rsi_bear and vol_surge and atr_active and conviction

        if long_signal:
            reason = (
                f"✅ 1H: Price above 50 EMA\n"
                f"✅ 5m: 9 EMA above 21 EMA\n"
                f"✅ MACD: Histogram positive + expanding\n"
                f"✅ RSI: {c_rsi:.1f} — mid zone\n"
                f"✅ Volume: +{vol_pct:.0f}% above avg\n"
                f"✅ Conviction candle: {body_pct:.0f}% body"
            )
            return "🟢 STRONG BUY", c_price, c_price + tp_dist, c_price - sl_dist, reason
        elif short_signal:
            reason = (
                f"✅ 1H: Price below 50 EMA\n"
                f"✅ 5m: 9 EMA below 21 EMA\n"
                f"✅ MACD: Histogram negative + expanding\n"
                f"✅ RSI: {c_rsi:.1f} — mid zone\n"
                f"✅ Volume: +{vol_pct:.0f}% above avg\n"
                f"✅ Conviction candle: {body_pct:.0f}% body"
            )
            return "🔴 SELL", c_price, c_price - tp_dist, c_price + sl_dist, reason
        else:
            missing = []
            if not vol_surge:  missing.append(f"volume {vol_pct:.0f}% above avg (need +30%)")
            if not atr_active: missing.append("ATR flat — market ranging")
            if not conviction: missing.append(f"weak candle — body {body_pct:.0f}% (need >50%)")
            if not (macd_bull or macd_bear): missing.append("MACD histogram not expanding")
            if not rsi_bull and not rsi_bear: missing.append(f"RSI {c_rsi:.1f} outside zone")
            reason = ("Waiting: " + " | ".join(missing)) if missing else "Not all 7 layers confirmed"
            return "⚪ WAITING", c_price, 0.0, 0.0, reason
    except Exception:
        return "⚪ WAITING", 0.0, 0.0, 0.0, ""


def get_scalp_signal(ticker_symbol):
    if ticker_symbol in FOREX_TICKERS:
        return _forex_signal(ticker_symbol)
    else:
        return _commodity_index_signal(ticker_symbol)


# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND TELEGRAM MONITOR — Confluence Day Template
# Scans the allowlist in strategy_config.yaml every 5 min during Mon–Fri
# 07:00–17:00 UTC. Emits at most daily_max_signals trade alerts (default 6),
# with sticky zone-key dedupe, cooldowns, and correlation filters.
# Telegram noise: trade alerts + one session-open + one daily summary only.
# ══════════════════════════════════════════════════════════════════════════════
_STATE_FILE = "monitor_state.json"
_data_errors_sent: set = set()   # "symbol|interval|YYYY-MM-DD" — once per day


def _read_state() -> dict:
    return _engine_load_state(_STATE_FILE)


def _write_state_raw(state: dict):
    _engine_save_state(state, _STATE_FILE)


def _build_tg_message(display_name, sig, entry, tp, sl, reason, session_name):
    """Legacy signature kept for any stray callers; prefer engine formatter."""
    rr = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0
    direction = "🟢 BUY" if "BUY" in str(sig) else "🔴 SELL"
    return (
        f"🚨 <b>ALPHAEDGE SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Asset:</b> {_tg_escape(display_name)}\n"
        f"📈 <b>Signal:</b> {direction}\n"
        f"⏰ <b>Time (UTC):</b> {datetime.now(timezone.utc).strftime('%H:%M  %d/%m/%Y')}\n"
        f"🏦 <b>Session:</b> {_tg_escape(session_name)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Entry:</b>  {entry}\n"
        f"🎯 <b>TP:</b>     {tp}\n"
        f"🛑 <b>SL:</b>     {sl}\n"
        f"📐 <b>R:R:</b>    1 : {rr:.1f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 <b>Why this trade:</b>\n{_tg_escape(reason)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
    )


def _track_outcomes(state: dict, cfg: dict, now) -> dict:
    """Resolve open trades (TP / SL / expiry) and send each follow-up once.
    Runs every loop, in and out of session, while markets trade. Only on the
    service that actually has Telegram credentials (the Render worker)."""
    ocfg = _outcomes.outcome_cfg(cfg)
    if not ocfg.get("enabled", True) or not (_TG_TOKEN and _TG_CHAT_ID):
        return state
    newly = _outcomes.check_open_trades(state, cfg, now)
    pending = _outcomes.pending_notifications(state, cfg)
    if not newly and not pending:
        return state
    _write_state_raw(state)          # persist "closed" BEFORE sending → never double-closes
    for rec in pending:
        rec["notify_attempts"] = int(rec.get("notify_attempts", 0)) + 1
        rec["notified"] = _send_telegram(_outcomes.format_outcome_message(
            rec, escape=_tg_escape, max_open_hours=ocfg.get("max_open_hours")))
        print(f"[outcomes] {rec['id']} {rec['status']} {rec.get('r')}R "
              f"notified={rec['notified']}", flush=True)
    _write_state_raw(state)
    return state


def _monitor_loop():
    """Background thread — one per process. State is date-keyed so a wiped
    monitor_state.json (Render free disk is ephemeral) just starts a fresh day
    and never re-fires yesterday's alerts. The trade-outcome book
    (state["trades"]) is carried across days."""
    import pandas as pd
    while True:
        loop_t0 = time.time()
        try:
            cfg = _load_strategy_config()          # hot-reload every loop
            now = pd.Timestamp.now(tz="UTC")
            state = _read_state()
            in_kz, session_name = _engine_session_info(now, cfg)
            prev = state.get("in_session", None)
            tg = cfg.get("telegram", {})

            # Trade outcomes first, so a session-close summary includes them
            try:
                state = _track_outcomes(state, cfg, now)
            except Exception as e:
                print(f"[outcomes] tracking error: {e!r}", flush=True)

            # First ever observation today — record silently
            if prev is None:
                state["in_session"] = in_kz
                _write_state_raw(state)

            # Session OPEN edge
            elif in_kz and prev is False:
                if tg.get("session_open", True):
                    _send_telegram(
                        f"🟢 <b>SESSION OPEN — {_tg_escape(session_name)}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                        f"📡 Confluence Day Template armed\n"
                        f"🎯 Daily budget: {cfg.get('risk', {}).get('daily_max_signals', 6)} alerts\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
                    )
                state["in_session"] = True
                state["summary_sent"] = False
                _write_state_raw(state)

            # Session CLOSE edge → one daily summary, then stop scanning
            elif (not in_kz) and prev is True:
                if tg.get("daily_summary", True) and not state.get("summary_sent"):
                    if _send_telegram(_engine_format_summary(state, session_name)):
                        _outcomes.mark_summarized(state)   # each result in one summary only
                    state["summary_sent"] = True
                state["in_session"] = False
                _write_state_raw(state)

            else:
                state["in_session"] = in_kz
                _write_state_raw(state)

            # always_on: no session-close edge — fire daily summary once near configured UTC hour
            _sess_cfg = cfg.get("session", {}) or {}
            if (
                _sess_cfg.get("always_on")
                and tg.get("daily_summary", True)
                and not state.get("summary_sent")
            ):
                _sum_hhmm = str(_sess_cfg.get("daily_summary_utc") or "21:00")
                try:
                    _sh, _sm = [int(x) for x in _sum_hhmm.split(":")[:2]]
                except Exception:
                    _sh, _sm = 21, 0
                if (now.hour, now.minute) >= (_sh, _sm):
                    if _send_telegram(_engine_format_summary(state, session_name)):
                        _outcomes.mark_summarized(state)
                    state["summary_sent"] = True
                    _write_state_raw(state)

            # Signal scan
            if in_kz:
                result = _engine_scan_once(now=now, cfg=cfg, state=state)
                # data errors — at most once per symbol/interval/day
                if tg.get("data_errors", True):
                    day = now.strftime("%Y-%m-%d")
                    for sym, interval, reason in result["data_errors"]:
                        key = f"{sym}|{interval}|{day}"
                        if key not in _data_errors_sent:
                            _data_errors_sent.add(key)
                            _send_telegram(
                                f"⚠️ <b>DATA ERROR</b>\n"
                                f"Symbol: {_tg_escape(sym)} | Interval: {_tg_escape(interval)}\n"
                                f"Reason: {_tg_escape(reason)}"
                            )

                accepted = result["accepted"]
                if accepted and tg.get("trade_alerts", True):
                    delivered = [c for c in accepted
                                 if _send_telegram(_engine_format_trade(c, session_name))]
                    state = _engine_record_emits(state, accepted, now)
                    # Track TP/SL only for alerts that actually reached Telegram
                    if _outcomes.outcome_cfg(cfg).get("enabled", True):
                        for c in delivered:
                            rec = _outcomes.add_open_trade(state, c, cfg, now)
                            print(f"[outcomes] tracking {rec['id']}", flush=True)

                state["scan_count"] = int(state.get("scan_count", 0)) + 1
                state["in_session"] = True
                _write_state_raw(state)

                # Optional scan updates — OFF by default in strategy_config.yaml
                if tg.get("scan_updates", False) and state["scan_count"] % 6 == 0:
                    status = (
                        "✅ " + ", ".join(f"{c.symbol} {c.side}" for c in accepted)
                        if accepted else "⏳ No A-tier setups — watching"
                    )
                    _send_telegram(
                        f"🔍 <b>SCAN UPDATE</b> — {_tg_escape(session_name)}\n"
                        f"{_tg_escape(status)}"
                    )

        except Exception as e:
            print(f"[monitor] loop error: {e!r}", flush=True)
        # 5-minute cadence measured from loop start (scan time no longer adds drift)
        time.sleep(max(30.0, 300.0 - (time.time() - loop_t0)))


def start_monitor():
    for thread in threading.enumerate():
        if thread.name == "alphaedge_monitor":
            return  # already running
    # Do NOT wipe monitor_state.json — date-keyed state is restart-safe.
    # A missing/stale file simply starts a fresh day budget.
    t = threading.Thread(target=_monitor_loop, name="alphaedge_monitor", daemon=True)
    t.start()

_RUN_IN_APP = os.environ.get("MONITOR_MODE", "app") == "app"
if _RUN_IN_APP:
    start_monitor()

# ── STARTUP PING — once per deploy (flag file). ──────────────────────────────
_STARTUP_FLAG = "startup_ping.flag"
if os.environ.get("MONITOR_MODE", "app") != "off" and not os.path.exists(_STARTUP_FLAG):
    try:
        _cfg0 = _load_strategy_config()
        _nsym = len(_cfg0.get("symbols", []))
        _cap = _cfg0.get("risk", {}).get("daily_max_signals", 6)
    except Exception:
        _nsym, _cap = "?", "?"
    _ok = _send_telegram(
        f"🚀 <b>ALPHAEDGE BOT ONLINE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
        f"✅ Confluence Day Template loaded\n"
        f"✅ Allowlist: {_nsym} symbols · daily cap {_cap}\n"
        f"✅ Sessions: Mon–Fri 07–17 UTC\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Trade alerts only — no scan spam</i>"
    )
    if _ok:
        try:
            with open(_STARTUP_FLAG, "w") as _f:
                _f.write("1")
        except Exception:
            pass


# --- TRADINGVIEW POP-UP ---
@st.dialog("📈 ADVANCED TRADINGVIEW CHART", width="large")
def show_popup_chart(ticker):
    tv_link = "https://www.tradingview.com/?aff_id=163585"
    if os.path.exists("static/tv_banner.jpg"):
        try:
            enc = base64.b64encode(open("static/tv_banner.jpg","rb").read()).decode()
            st.markdown(f'<a href="{tv_link}" target="_blank"><img src="data:image/jpeg;base64,{enc}" width="100%" style="border-radius:10px;margin-bottom:15px;"></a>', unsafe_allow_html=True)
        except Exception: pass
    else:
        st.info("⚠️ 'tv_banner.jpg' not found in 'static' folder.")
    st.markdown(f'<a href="{tv_link}" target="_blank"><button style="width:100%;background-color:#2962FF;color:white;border:none;padding:12px;border-radius:5px;font-weight:bold;cursor:pointer;margin-bottom:15px;">🚀 UPGRADE TO TRADINGVIEW PRO ➤</button></a>', unsafe_allow_html=True)
    tv_symbol = TV_MAP.get(ticker, "FX:EURUSD")
    st.iframe(popup_chart_html(tv_symbol, height=640), height=650)
    st.markdown(f'<a href="{tv_chart_url(tv_symbol)}" target="_blank">Open {ticker} on TradingView ↗</a> — drawings made there save to your TradingView account.', unsafe_allow_html=True)
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if os.path.exists("static/tv_promo_1.mp4"): st.caption("📺 Pro Features"); st.video("static/tv_promo_1.mp4", start_time=0)
    with c2:
        if os.path.exists("static/tv_promo_2.mp4"): st.caption("📺 Advanced Charting"); st.video("static/tv_promo_2.mp4", start_time=0)


# --- CHAT DB ---
DB_FILE  = "chat.db"
_db_lock = threading.Lock()

def init_db():
    with _db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, ts REAL NOT NULL)")
        conn.commit(); conn.close()

init_db()

def load_chat(limit=100):
    with _db_lock:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute("SELECT text, ts FROM messages ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
    return [{"text": r[0], "ts": r[1]} for r in reversed(rows)]

def save_message(text: str):
    clean = html.escape(text.strip())
    if not clean: return
    with _db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT INTO messages (text, ts) VALUES (?, ?)", (clean, time.time()))
        conn.commit(); conn.close()


# ================= 3. SIDEBAR =================
with st.sidebar:
    logo_file = "logo.gif" if os.path.exists("logo.gif") else "logo.png" if os.path.exists("logo.png") else None
    if logo_file:
        try:
            with open(logo_file,"rb") as f: enc = base64.b64encode(f.read()).decode()
            mime = "image/gif" if logo_file.endswith(".gif") else "image/png"
            st.markdown(f'<div style="text-align:center;margin-bottom:20px;"><img src="data:{mime};base64,{enc}" width="100%"></div>', unsafe_allow_html=True)
        except Exception: pass
    else:
        st.markdown('<div style="text-align:center;"><h1>🅰️</h1><h2>AlphaEdge</h2></div>', unsafe_allow_html=True)

    st.markdown('<div style="text-align:center;margin-bottom:20px;"><p style="font-size:10px;color:#888;">TRADING INTELLIGENCE REDEFINED</p></div><hr style="border-top:1px solid #333;">', unsafe_allow_html=True)

    # ── Paid gate: auth + seat status (sidebar) ─────────────────────────────
    _access = render_auth_sidebar()
    _user_paid = bool(_access.get("paid"))
    st.session_state["ae_access"] = _access
    if _access.get("paywall_enabled") and _access.get("authenticated") and not _user_paid:
        render_paywall(_access.get("user"))
    elif _access.get("paywall_enabled") and not _access.get("authenticated"):
        st.caption("Sign in to subscribe · teaser dashboard is free")
    # When paywall is OFF: no status caption / seat chrome for visitors (clean free site).
    st.markdown("---")

    with st.expander("🔴 LIVE MEDIA", expanded=True):
        st.subheader("📺 LIVE FINANCIAL TV")
        tv_channel = st.selectbox(
            "Select Channel:",
            list(TV_CHANNELS.keys()),
            label_visibility="collapsed",
            key="tv_sel",
        )
        # Same-origin player: YouTube live_stream embed + radio/Twitch fallbacks.
        # st.iframe(url) (not components.html/srcdoc) so YouTube gets a real Referer.
        st.iframe(tv_static_url(tv_channel), height=340)
        # Direct YouTube embed as a second path if the static player is blocked.
        with st.expander("Direct YouTube embed", expanded=False):
            st.iframe(tv_youtube_embed_url(tv_channel), height=220)
        _tv_meta = TV_CHANNELS.get(tv_channel) or {}
        st.caption(
            f"In-page Live TV · muted autoplay · Radio/Twitch tabs inside player"
            + (f" · [channel streams]({_tv_meta['streams_url']})" if _tv_meta.get("streams_url") else "")
        )

        st.subheader("🎵 TRADING STATION")
        station = st.selectbox("Select Audio:", list(STATIONS.keys()), label_visibility="collapsed")
        _stn = STATIONS[station]
        st.iframe(
            station_html(_stn["radio"], youtube_url=_stn.get("youtube"), height=210),
            height=210,
        )
        st.caption(
            f"In-page radio · [station page]({station_static_url(_stn['radio'], _stn.get('youtube'))})"
            + (f" · [Open on YouTube]({_stn['youtube']})" if _stn.get("youtube") else "")
        )

    st.markdown("---")
    st.markdown('<p style="text-align:center;color:#D4AF37;font-size:11px;font-weight:bold;letter-spacing:2px;">🏆 FEATURED PARTNERS</p>', unsafe_allow_html=True)

    if os.path.exists("static/exness_logo.png"): st.image("static/exness_logo.png", width="stretch")
    if os.path.exists("static/exness.mp4"):      st.video("static/exness.mp4", start_time=0)
    st.markdown('<a href="https://one.exnessonelink.com/a/9wwklqzfxb" target="_blank"><button style="width:100%;background-color:#D4AF37;color:#000;border:none;padding:12px;border-radius:5px;font-weight:bold;cursor:pointer;margin-top:6px;font-size:13px;">🚀 TRADE WITH 0 SPREADS ➤</button></a>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if os.path.exists("static/goat_logo.png"): st.image("static/goat_logo.png", width="stretch")
    if os.path.exists("static/goat.mp4"):      st.video("static/goat.mp4", start_time=0)
    st.markdown('<a href="https://checkout.goatfundedtrader.com/aff/Sherwet/" target="_blank"><button style="width:100%;background-color:#00E676;color:#000;border:none;padding:12px;border-radius:5px;font-weight:bold;cursor:pointer;margin-top:6px;font-size:13px;">🐐 GET FUNDED TODAY ➤</button></a>', unsafe_allow_html=True)

    st.divider()
    focus_ticker = st.selectbox("ACTIVE CHART ASSET:", list(TICKER_MAP.keys()), index=0)
    if st.button("GET YOUR TRADING VIEW ADVANCE CHART HERE", width="stretch"):
        show_popup_chart(focus_ticker)


# ================= 4. TABS =================
in_kz, session_name = get_session_info()
now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")

tab_dash, tab_cot, tab_sent, tab_ind, tab_fx, tab_news, tab_cal, tab_chat = st.tabs([
    "  📊 DASHBOARD  ", "  📊 COT DATA  ", "  📈 SENTIMENT  ",
    "  🏙️ INDICES  ", "  💱 CURRENCY MATRIX  ", "  📰 LIVE NEWS  ",
    "  📅 CALENDAR  ", "  💬 COMMUNITY  "
])



def _pro_only_tab(title: str) -> bool:
    """If user is not paid, show lock UI and return True (caller should skip body)."""
    acc = st.session_state.get("ae_access") or require_access()
    if acc.get("paid"):
        return False
    st.title(title)
    render_teaser_banner()
    render_paywall(acc.get("user"))
    st.info("This tab is included with AlphaEdge Pro.")
    return True


# ================= TAB 1: DASHBOARD =================
with tab_dash:
    # Keep the chart in its own container at a fixed position in the tab so its
    # iframe is never re-created on reruns (that would wipe drawings).
    _dash_top = st.container()
    _dash_chart = st.container()
    _access = st.session_state.get("ae_access") or require_access()
    _user_paid = bool(_access.get("paid"))
    with _dash_top:
        st.title("📊 ALPHAEDGE COMMAND CENTRE")
        if not _user_paid:
            render_teaser_banner()
            render_paywall(_access.get("user"))

        if in_kz:
            st.markdown(f'<div style="background:#0a1a0a;border:1px solid #00ff88;border-radius:6px;padding:10px 16px;margin-bottom:12px;"><span style="color:#00ff88;font-weight:bold;font-size:13px;">🟢 ACTIVE SESSION</span><span class="kill-zone-badge">{session_name}</span><span style="float:right;color:#888;font-size:12px;">{now_utc}</span></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="background:#1a0a0a;border:1px solid #ff4b4b;border-radius:6px;padding:10px 16px;margin-bottom:12px;"><span style="color:#888;font-weight:bold;font-size:13px;">⏸️ OFF SESSION</span><span class="dead-zone-badge">{session_name}</span><span style="float:right;color:#888;font-size:12px;">{now_utc}</span></div>', unsafe_allow_html=True)

        st.write("⏳ *Analyzing Live Market Structure...*")
        data = get_dashboard_data()

        errors = st.session_state.get("data_errors", [])
        if errors:
            with st.expander(f"⚠️ {len(errors)} asset(s) failed to load", expanded=False):
                for e in errors: st.caption(e)
            st.session_state["data_errors"] = []

        rows_html = ""
        if data:
            _items = list(data.items())
            if not _user_paid:
                _items = _items[:5]
            for name, row in _items:
                bias  = row.get("bias",  "—")
                price = row.get("price", 0)
                score = row.get("score", 0)
                trend = row.get("trend", "—")
                tech  = row.get("tech",  "—")
                css   = "bullish" if "BULL" in str(bias) else "bearish" if "BEAR" in str(bias) else ""
                try:
                    price_str = _fmt_price(float(price)) if price else "—"
                except Exception:
                    price_str = str(price)
                rows_html += (
                    f'<tr><td><b>{name}</b></td>'
                    f'<td class="{css}">{bias}</td>'
                    f'<td class="{css}">{score}</td>'
                    f'<td>{trend}</td><td>{tech}</td>'
                    f'<td style="color:#D4AF37;font-weight:bold;">{price_str}</td>'
                    f'<td><span class="live-tag">{"⚡ FUTURES ~10m" if str(TICKER_MAP.get(name, "")).endswith("=F") else "⚡ LIVE"}</span></td></tr>'
                )
        else:
            rows_html = "<tr><td colspan='7'>Loading Data...</td></tr>"

        st.markdown(f'<table class="heatmap-table"><thead><tr><th>SYMBOL</th><th>BIAS</th><th>SCORE</th><th>TREND</th><th>TECH</th><th>PRICE</th><th>SOURCE</th></tr></thead><tbody>{rows_html}</tbody></table>', unsafe_allow_html=True)
        if not _user_paid:
            st.caption("Teaser shows 5 symbols — Pro unlocks the full heatmap + live signals.")
        st.markdown("---")

        st.markdown("""
        <div style="background:linear-gradient(90deg,#0a0a0a,#111);border:1px solid #D4AF37;border-left:4px solid #D4AF37;border-radius:6px;padding:14px 18px;margin-bottom:10px;">
            <h3 style="margin:0;color:#D4AF37;font-size:18px;letter-spacing:2px;">📊 ALPHAEDGE LIVE SIGNALS</h3>
            <p style="margin:6px 0 0 0;color:#aaa;font-size:12px;">Confluence Day Template • Sweep+BOS (+ PD) / morning VWAP • Mon–Fri 07–17 UTC • daily cap 4 • 2.0R • Pro gated</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background-color:#0d1117;border:1px solid #FF6B35;border-radius:6px;padding:12px 16px;margin-bottom:14px;">
            <p style="margin:0;color:#FF6B35;font-size:11px;font-weight:bold;letter-spacing:1px;">⚠️ RISK DISCLAIMER — NOT FINANCIAL ADVICE</p>
            <p style="margin:6px 0 0 0;color:#888;font-size:11px;line-height:1.6;">
                Signals are generated algorithmically for <b style="color:#ccc;">educational and informational purposes only</b>.
                Trading leveraged products carries a <b style="color:#ccc;">high level of risk</b>.
                Past performance is not indicative of future results.
            </p>
            <p style="margin:8px 0 0 0;color:#D4AF37;font-size:11px;">📌 <b>Change ACTIVE CHART ASSET in the sidebar to switch instruments.</b></p>
        </div>
        """, unsafe_allow_html=True)

        if not _user_paid:
            st.markdown("""
            <div style="background:#0d1117;border:1px dashed #D4AF37;border-radius:8px;padding:20px;text-align:center;margin:12px 0;">
              <div style="font-size:28px;">🔒</div>
              <div style="color:#D4AF37;font-weight:700;margin-top:6px;">LIVE SIGNALS — PRO ONLY</div>
              <div style="color:#888;font-size:12px;margin-top:8px;">Subscribe (R149/mo or R35/wk) to unlock entries, SL/TP and checklist detail.</div>
            </div>
            """, unsafe_allow_html=True)
            sig, ent, tp, sl, reason = "🔒 PRO", 0.0, 0.0, 0.0, "Unlock AlphaEdge Pro to view live signals."
        else:
            sig, ent, tp, sl, reason = _signal_engine(focus_ticker)

        c1, c2, c3 = st.columns(3)
        c1.metric("📐 SIGNAL", sig)
        st.caption(f"📌 Analysing: **{focus_ticker}**")

        if sig not in ("⚪ WAITING", "WAIT", "WAITING"):
            c2.metric("⚡ LIVE ENTRY", _fmt_price(ent))
            c3.metric("🎯 TARGETS",    f"TP: {_fmt_price(tp, ent)} | SL: {_fmt_price(sl, ent)}")
            box_class    = "reason-box" if "BUY" in sig else "reason-box-sell"
            reason_lines = reason.replace("\n", "<br>")
            st.markdown(f'<div class="{box_class}"><p style="margin:0 0 6px 0;font-weight:bold;color:#ccc;font-size:12px;">📋 WHY THIS TRADE:</p><p style="margin:0;">{reason_lines}</p></div>', unsafe_allow_html=True)
        else:
            c2.metric("⚡ LIVE ENTRY", "Searching...")
            c3.metric("🎯 TARGETS",    "Awaiting Confluence")
            if reason:
                reason_lines = reason.replace("\n", "<br>")
                st.markdown(f'<div style="background:#0a0a0f;border:1px solid #333;border-left:3px solid #888;border-radius:4px;padding:10px 14px;margin-top:10px;font-size:12px;color:#666;"><p style="margin:0 0 4px 0;color:#888;font-weight:bold;">⏳ WAITING — CONDITIONS NOT YET MET:</p><p style="margin:0;">{reason_lines}</p></div>', unsafe_allow_html=True)

    with _dash_chart:
        st.markdown('<p style="margin:14px 0 4px 0;color:#D4AF37;font-size:12px;font-weight:bold;letter-spacing:1px;">📈 LIVE CHART · drawings, indicators, symbol search & fullscreen · switch pairs in the sidebar — drawings stay per pair until you refresh</p>', unsafe_allow_html=True)
        # Constant HTML → Streamlit never re-creates this iframe; one TradingView chart per
        # visited symbol lives inside it and is only shown/hidden (see ui_widgets.py).
        st.iframe(_CHART_HTML, height=CHART_HEIGHT)
        st.iframe(chart_bridge_html(TV_MAP.get(focus_ticker, "FX:EURUSD")), height=1)
        st.markdown(f'<a href="{tv_chart_url(TV_MAP.get(focus_ticker, "FX:EURUSD"))}" target="_blank" style="font-size:11px;color:#787b86;">Want drawings saved permanently? Open {focus_ticker} on TradingView ↗ (saves to your TradingView account)</a>', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # NOVA & INK · ETSY PRINTABLES SHOP
    # ══════════════════════════════════════════════════════════════════════════
    _ETSY_SHOP_URL = "https://novaandinkbycharl.etsy.com"
    _ETSY_PRODUCTS = [
        {
            "title": "Power Outage Checklist",
            "blurb": "Printable before/during/after blackout checklist.",
            "url": "https://www.etsy.com/listing/4580438621/power-outage-checklist-printable",
            "img": "static/etsy/01_power_outage_checklist.jpg",
        },
        {
            "title": "Before You Leave Home Checklist",
            "blurb": "Security walkthrough before travel.",
            "url": "https://www.etsy.com/listing/4572540421/before-you-leave-home-checklist-security",
            "img": "static/etsy/02_before_you_leave_home.jpg",
        },
        {
            "title": "Home Maintenance Checklist",
            "blurb": "Monthly systems checklist.",
            "url": "https://www.etsy.com/listing/4574337895/home-maintenance-checklist-monthly",
            "img": "static/etsy/03_home_maintenance_checklist.jpg",
        },
        {
            "title": "Fridge Food Safety (Keep or Toss)",
            "blurb": "Power-outage fridge rules.",
            "url": "https://www.etsy.com/listing/4582432373/fridge-food-safety-printable-power",
            "img": "static/etsy/04_fridge_food_safety.jpg",
        },
        {
            "title": "Home Shut-Off Guide",
            "blurb": "Water/gas/electric mains.",
            "url": "https://www.etsy.com/listing/4577212387/home-shut-off-guide-printable-utility",
            "img": "static/etsy/05_home_shut_off_guide.jpg",
        },
        {
            "title": "Building Contacts (Apartment)",
            "blurb": "Neighbour/caretaker/utility numbers.",
            "url": "https://www.etsy.com/listing/4584957634/building-contacts-printable-apartment",
            "img": "static/etsy/06_building_contacts.jpg",
        },
        {
            "title": "Services Contact Sheet",
            "blurb": "Electrician/plumber/locksmith.",
            "url": "https://www.etsy.com/listing/4574340653/services-contact-sheet-household",
            "img": "static/etsy/07_services_contact_sheet.jpg",
        },
        {
            "title": "Emergency Grab Bag Checklist",
            "blurb": "Go-bag packing list.",
            "url": "https://www.etsy.com/listing/4572701211/emergency-grab-bag-checklist-emergency",
            "img": "static/etsy/08_emergency_grab_bag.jpg",
        },
        {
            "title": "Family Emergency Plan",
            "blurb": "Meeting points/contacts/roles.",
            "url": "https://www.etsy.com/listing/4572030290/family-emergency-plan-printable",
            "img": "static/etsy/09_family_emergency_plan.jpg",
        },
        {
            "title": "Home Emergency Numbers",
            "blurb": "Fridge-ready numbers.",
            "url": "https://www.etsy.com/listing/4574968184/home-emergency-numbers-printable",
            "img": "static/etsy/10_home_emergency_numbers.jpg",
        },
        {
            "title": "Travel Emergency Card",
            "blurb": "Wallet travel ICE card.",
            "url": "https://www.etsy.com/listing/4567948436/travel-emergency-card-printable-travel",
            "img": "static/etsy/11_travel_emergency_card.jpg",
        },
        {
            "title": "Vehicle Emergency Card",
            "blurb": "Car roadside contacts.",
            "url": "https://www.etsy.com/listing/4568749183/vehicle-emergency-card-printable-car",
            "img": "static/etsy/12_vehicle_emergency_card.jpg",
        },
        {
            "title": "Medical Alert Wallet Card",
            "blurb": "Medical + contacts.",
            "url": "https://www.etsy.com/listing/4571277814/medical-alert-wallet-card-printable",
            "img": "static/etsy/13_medical_alert_wallet_card.jpg",
        },
        {
            "title": "Family ICE Card",
            "blurb": "Family ICE wallet card.",
            "url": "https://www.etsy.com/listing/4570620103/family-ice-card-printable-in-case-of",
            "img": "static/etsy/14_family_ice_card.jpg",
        },
        {
            "title": "Home Fire Escape Plan",
            "blurb": "Family fire escape map.",
            "url": "https://www.etsy.com/listing/4574960682/home-fire-escape-plan-family-fire-safety",
            "img": "static/etsy/15_home_fire_escape_plan.jpg",
        },
    ]

    def _etsy_img_data_uri(path):
        """Inline local product image so the scroller does not depend on CDN hotlinking."""
        try:
            with open(path, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        except OSError:
            return ""

    def _build_etsy_cards(products):
        cards = []
        for p in products:
            src = _etsy_img_data_uri(p["img"]) if os.path.exists(p["img"]) else ""
            img = (
                f'<img src="{src}" alt="{html.escape(p["title"])}" '
                'style="width:100%;height:140px;object-fit:cover;border-radius:6px;'
                'display:block;background:#1a1a1a;margin-bottom:8px;">'
                if src else
                '<div style="height:140px;border-radius:6px;background:#1a1a1a;margin-bottom:8px;"></div>'
            )
            cards.append(
                '<div class="etsy-card">'
                + img
                + '<div style="color:#D4AF37;font-weight:700;font-size:12px;line-height:1.35;'
                + 'margin-bottom:4px;min-height:32px;">' + html.escape(p["title"]) + "</div>"
                + '<div style="color:#888;font-size:10px;line-height:1.4;min-height:36px;'
                + 'margin-bottom:8px;">' + html.escape(p["blurb"]) + "</div>"
                + '<div style="display:flex;align-items:center;justify-content:space-between;gap:6px;">'
                + '<span style="color:#fff;font-weight:700;font-size:13px;">R30</span>'
                + '<a href="' + html.escape(p["url"]) + '" target="_blank" rel="noopener" '
                + 'style="background:#D4AF37;color:#000;text-decoration:none;font-size:10px;'
                + 'font-weight:700;padding:5px 8px;border-radius:4px;white-space:nowrap;">'
                + "View on Etsy ↗</a></div></div>"
            )
        return "".join(cards)

    _etsy_cards_html = _build_etsy_cards(_ETSY_PRODUCTS)

    st.iframe(f"""
    <style>
    html, body {{
        margin: 0; padding: 0; background: #0a0a0a;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    .etsy-track {{
        display: flex;
        gap: 14px;
        width: max-content;
        align-items: stretch;
        will-change: transform;
    }}
    .etsy-card {{
        background: #111;
        border: 1px solid #222;
        border-radius: 10px;
        padding: 10px;
        width: 190px;
        flex-shrink: 0;
        box-sizing: border-box;
        transition: border-color 0.25s;
    }}
    .etsy-card:hover {{ border-color: #D4AF37; }}
    #etsy-wrapper {{
        overflow: hidden;
        width: 100%;
        background: #0a0a0a;
        border-top: 1px solid #D4AF37;
        border-bottom: 1px solid #1a1a1a;
        padding: 12px 0;
    }}
    #etsy-header {{
        padding: 4px 4px 10px 4px;
    }}
    #etsy-title {{
        color: #D4AF37;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 1.5px;
    }}
    #etsy-header a {{
        color: #aaa;
        font-size: 11px;
        text-decoration: none;
        border-bottom: 1px solid #444;
        margin-left: 12px;
    }}
    #etsy-sub {{
        color: #666;
        font-size: 11px;
        margin-top: 6px;
    }}
    </style>
    <div id="etsy-header">
      <span id="etsy-title">NOVA &amp; INK · Printables from our shop</span>
      <a href="{_ETSY_SHOP_URL}" target="_blank" rel="noopener">novaandinkbycharl.etsy.com ↗</a>
      <div id="etsy-sub">Emergency &amp; home printables · R30 each · instant download on Etsy · hover to pause</div>
    </div>
    <div id="etsy-wrapper">
        <div class="etsy-track" id="etsy-track">
            {_etsy_cards_html}
            {_etsy_cards_html}
        </div>
    </div>
    <script>
    (function() {{
        const track   = document.getElementById('etsy-track');
        const wrapper = document.getElementById('etsy-wrapper');
        let pos    = 0;
        let paused = false;
        const speed = 0.45;

        function halfWidth() {{ return track.scrollWidth / 2; }}

        function step() {{
            if (!paused) {{
                pos += speed;
                if (pos >= halfWidth()) pos = 0;
                track.style.transform = 'translateX(-' + pos + 'px)';
            }}
            requestAnimationFrame(step);
        }}

        wrapper.addEventListener('mouseenter', function() {{ paused = true; }});
        wrapper.addEventListener('mouseleave', function() {{ paused = false; }});
        // Pause while interacting with links
        track.addEventListener('mousedown', function() {{ paused = true; }});

        requestAnimationFrame(step);
    }})();
    </script>
    """, height=320)


# ================= TAB 2: COT DATA =================
with tab_cot:
    if _pro_only_tab('📊 INSTITUTIONAL POSITIONING'):
        pass
    else:
        st.title("📊 INSTITUTIONAL POSITIONING")
        col_ctrl, _ = st.columns([1, 2])
        with col_ctrl:
            if st.button("🔄 REFRESH DATA"):
                try:
                    import cot_fetcher
                    if cot_fetcher.update_cot_data():
                        st.success("Updated!"); time.sleep(1); st.rerun()
                    else:
                        st.error("⚠️ COT refresh returned no data. The CFTC site may be down, try again later.")
                except ModuleNotFoundError:
                    st.error("⚠️ cot_fetcher module not found.")
                except Exception as e:
                    st.error(f"⚠️ COT refresh failed: {e}")

        def make_row(row):
            l_pct = row.get('long_pct', 0); s_pct = row.get('short_pct', 0)
            l_cls = "bull-strong" if l_pct > 60 else "bull-med" if l_pct > 50 else ""
            s_cls = "bear-strong" if s_pct > 60 else "bear-med" if s_pct > 50 else ""
            nc    = "#2962FF" if row.get('net_pos', 0) > 0 else "#D50000"
            return f"""<tr><td class="symbol-col">{row['Symbol']}</td><td>{int(row['long_pos']):,}</td><td>{int(row['short_pos']):,}</td><td style="color:{'#00E676' if row['change_long']>0 else '#FF5252'}">{int(row['change_long']):+,}</td><td style="color:{'#00E676' if row['change_short']>0 else '#FF5252'}">{int(row['change_short']):+,}</td><td class="{l_cls}">{l_pct:.1f}%</td><td class="{s_cls}">{s_pct:.1f}%</td><td>{row['net_pct']:.2f}%</td><td style="font-weight:bold;background-color:{nc};color:white;">{int(row.get('net_pos',0)):,}</td><td>{int(row['open_int']):,}</td><td>{int(row['change_oi']):+,}</td></tr>"""

        if os.path.exists("cot_live.json"):
            try:
                with open("cot_live.json","r") as f: cot_data = json.load(f)
                table_rows = "".join([make_row(dict(v, Symbol=k)) for k,v in cot_data.items()])
                _dates = sorted({v.get("report_date") for v in cot_data.values() if v.get("report_date")})
                if _dates:
                    st.caption(f"CFTC report date: {', '.join(_dates)} · Commodities = Managed Money (Disaggregated), Financials = Leveraged Funds (TFF)")
                st.markdown(f'<table class="heatmap-table" style="width:100%;text-align:center;"><thead><tr style="background:#111;color:#D4AF37;"><th>Symbol</th><th>Longs</th><th>Shorts</th><th>Δ Long</th><th>Δ Short</th><th>Long %</th><th>Short %</th><th>Net %</th><th>Net Pos</th><th>OI</th><th>Δ OI</th></tr></thead><tbody>{table_rows}</tbody></table>', unsafe_allow_html=True)
            except (json.JSONDecodeError, KeyError) as e:
                st.error(f"⚠️ Failed to parse COT data: {e}. Try refreshing.")
        else:
            st.info("ℹ️ No data found. Click Refresh.")


    # ================= TAB 3: SENTIMENT =================
with tab_sent:
    if _pro_only_tab('📈 TECHNICAL SENTIMENT'):
        pass
    else:
        st.title("📈 TECHNICAL SENTIMENT")
        gauge_asset = st.selectbox("Select Asset to Analyze:", list(TICKER_MAP.keys()), key="gauge_sel")
        tv_gauge    = TV_MAP.get(gauge_asset, "FX:EURUSD")
        st.write(f"Displaying Sentiment for: **{gauge_asset}**")
        c1, c2 = st.columns(2)
        with c1: st.caption("1 Hour Interval"); st.iframe(f'<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>{{"interval":"1h","width":"100%","isTransparent":true,"height":450,"symbol":"{tv_gauge}","showIntervalTabs":false,"displayMode":"single","locale":"en","colorTheme":"dark"}}</script></div>', height=460)
        with c2: st.caption("4 Hour Interval"); st.iframe(f'<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>{{"interval":"4h","width":"100%","isTransparent":true,"height":450,"symbol":"{tv_gauge}","showIntervalTabs":false,"displayMode":"single","locale":"en","colorTheme":"dark"}}</script></div>', height=460)


    # ================= TAB 4: INDICES =================
with tab_ind:
    if _pro_only_tab('🏙️ GLOBAL INDICES HEATMAP'):
        pass
    else:
        st.title("🏙️ GLOBAL INDICES HEATMAP")
        st.iframe('<iframe src="https://www.tradingview-widget.com/embed-widget/stock-heatmap/?theme=dark&market=america" height="800" width="100%"></iframe>', height=820)


    # ================= TAB 5: FOREX =================
with tab_fx:
    if _pro_only_tab('💱 GLOBAL CURRENCY MATRIX'):
        pass
    else:
        st.title("💱 GLOBAL CURRENCY MATRIX")
        st.iframe('<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-forex-heat-map.js" async>{"width":"100%","height":800,"currencies":["EUR","USD","JPY","GBP","CHF","AUD","CAD","NZD","ZAR"],"isTransparent":false,"colorTheme":"dark","locale":"en"}</script></div>', height=820)


    # ================= TAB 6: NEWS =================
with tab_news:
    if _pro_only_tab('📰 LIVE MARKET NEWS'):
        pass
    else:
        st.title("📰 LIVE MARKET NEWS")
        st.iframe('<iframe src="https://www.tradingview-widget.com/embed-widget/timeline/?feedMode=all_symbols&theme=dark" height="800" width="100%"></iframe>', height=820)


    # ================= TAB 7: CALENDAR =================
with tab_cal:
    if _pro_only_tab('📅 ECONOMIC CALENDAR'):
        pass
    else:
        st.title("📅 ECONOMIC CALENDAR")
        st.iframe('<iframe src="https://www.tradingview-widget.com/embed-widget/events/?theme=dark&importance=high" height="800" width="100%"></iframe>', height=820)


    # ================= TAB 8: COMMUNITY CHAT =================
with tab_chat:
    if _pro_only_tab('💬 TRADERS LOUNGE'):
        pass
    else:
        st.title("💬 TRADERS LOUNGE")
        st.write("Share setups, ideas, and market news with the AlphaEdge community.")
        col_info, col_btn = st.columns([3, 1])
        with col_info:
            st.info("🔄 **Note:** Click refresh to see the latest messages from other traders.")
        with col_btn:
            if st.button("🔄 REFRESH CHAT", width="stretch"):
                st.rerun()
        st.markdown("---")
        chat_history   = load_chat()
        chat_container = st.container(height=500)
        with chat_container:
            if not chat_history:
                st.info("Welcome to the AlphaEdge Traders Lounge. Be the first to drop a setup!")
            else:
                for msg in chat_history:
                    with st.chat_message("user"):
                        ts = datetime.fromtimestamp(msg['ts']).strftime("%H:%M")
                        st.markdown(f"**Anonymous Trader** · *{ts}*")
                        st.write(msg['text'])
        if prompt := st.chat_input("Drop a trading idea or setup..."):
            save_message(prompt)
            st.rerun()


    # ================= FIXED FOOTER =================
    _footer_url = (
        "https://www.tradingview-widget.com/embed-widget/ticker-tape/?theme=dark"
        "#%7B%22symbols%22%3A%5B%7B%22proName%22%3A%22FOREXCOM%3ASPXUSD%22%2C%22title%22%3A%22S%26P%20500%22%7D"
        "%2C%7B%22proName%22%3A%22FOREXCOM%3ANSXUSD%22%2C%22title%22%3A%22Nasdaq%20100%22%7D"
        "%2C%7B%22proName%22%3A%22FX_IDC%3AEURUSD%22%2C%22title%22%3A%22EUR%2FUSD%22%7D"
        "%2C%7B%22proName%22%3A%22OANDA%3AXAUUSD%22%2C%22title%22%3A%22GOLD%22%7D%5D"
        "%2C%22showSymbolLogo%22%3Atrue%2C%22colorTheme%22%3A%22dark%22"
        "%2C%22isTransparent%22%3Atrue%2C%22displayMode%22%3A%22adaptive%22%2C%22locale%22%3A%22en%22%7D"
    )
    st.markdown(
        f'<div class="ticker-footer"><iframe src="{_footer_url}" width="100%" height="40" frameborder="0" scrolling="no" style="margin-top:-10px;"></iframe></div>',
        unsafe_allow_html=True
    )
