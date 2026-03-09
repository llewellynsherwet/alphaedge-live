import streamlit as st
import time
import os
import html
import sqlite3
import threading
import requests
import pandas as pd
import streamlit.components.v1 as components
import base64
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="AlphaEdge | Trading Intelligence",
    page_icon="🅰️", layout="wide",
    initial_sidebar_state="collapsed"
)

# ═══════════════════════════════════════════════════════════════════════
# ASSET MAPS
# ═══════════════════════════════════════════════════════════════════════
TICKER_MAP = {
    "EUR/USD": "EUR/USD", "GBP/USD": "GBP/USD", "USD/JPY": "USD/JPY",
    "USD/CHF": "USD/CHF", "AUD/USD": "AUD/USD", "USD/CAD": "USD/CAD",
    "NZD/USD": "NZD/USD", "USD/ZAR": "USD/ZAR", "GBP/ZAR": "GBP/ZAR",
    "S&P 500": "SPX",     "NASDAQ 100": "NDX",   "US 30":   "DJI",
    "VIX":     "VIX",
    "GOLD":    "XAU/USD", "SILVER":  "XAG/USD",  "OIL (WTI)": "WTI/USD",
    "NAT GAS": "NATURAL_GAS/USD",
    "BITCOIN": "BTC/USD", "ETHEREUM": "ETH/USD", "SOLANA": "SOL/USD",
}

TV_MAP = {
    "EUR/USD": "FX:EURUSD",    "GBP/USD": "FX:GBPUSD",    "USD/JPY": "FX:USDJPY",
    "USD/CHF": "FX:USDCHF",    "AUD/USD": "FX:AUDUSD",    "USD/CAD": "FX:USDCAD",
    "NZD/USD": "FX:NZDUSD",    "USD/ZAR": "FX:USDZAR",    "GBP/ZAR": "FX:GBPZAR",
    "S&P 500": "CME_MINI:ES1!", "NASDAQ 100": "CME_MINI:NQ1!", "US 30": "CBOT_MINI:YM1!",
    "VIX":     "TVC:VIX",
    "GOLD":    "OANDA:XAUUSD", "SILVER":  "TVC:SILVER",   "OIL (WTI)": "NYMEX:CL1!",
    "NAT GAS": "NYMEX:NG1!",
    "BITCOIN": "BINANCE:BTCUSDT", "ETHEREUM": "BINANCE:ETHUSDT", "SOLANA": "BINANCE:SOLUSDT",
}

# ═══════════════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════════════
_css = (
    "<style>"
    ".stApp{background-color:#050505;color:#e0e0e0;}"
    "section[data-testid='stSidebar']{background-color:#000;border-right:1px solid #222;}"
    ".stTabs [data-baseweb='tab-list']{gap:8px;background-color:#080808;padding:10px;border-bottom:2px solid #D4AF37;}"
    ".stTabs [data-baseweb='tab']{height:50px;background-color:#111;color:#888;border:1px solid #333;padding-left:20px;padding-right:20px;}"
    ".stTabs [aria-selected='true']{background-color:#D4AF37 !important;color:#000 !important;font-weight:bold;}"
    "h1,h2,h3{color:#D4AF37 !important;text-transform:uppercase;font-family:'Helvetica Neue',sans-serif;}"
    ".heatmap-table{width:100%;border-collapse:collapse;font-family:'Inter',sans-serif;font-size:13px;background-color:#080808;border:1px solid #333;}"
    ".heatmap-table th{background-color:#111;color:#D4AF37;padding:12px;text-align:left;border-bottom:2px solid #D4AF37;}"
    ".heatmap-table td{padding:10px;border-bottom:1px solid #222;color:#ccc;}"
    ".bullish{color:#00ff88 !important;font-weight:bold;}"
    ".bearish{color:#ff4b4b !important;font-weight:bold;}"
    ".live-tag{color:#00ff88;border:1px solid #00ff88;padding:2px 5px;font-size:10px;border-radius:3px;}"
    ".kill-zone-badge{display:inline-block;background:#00ff88;color:#000;font-size:10px;font-weight:bold;padding:2px 8px;border-radius:3px;margin-left:8px;}"
    ".dead-zone-badge{display:inline-block;background:#ff4b4b;color:#fff;font-size:10px;font-weight:bold;padding:2px 8px;border-radius:3px;margin-left:8px;}"
    ".reason-box{background:#0a0f0a;border:1px solid #1a3a1a;border-left:3px solid #00ff88;border-radius:4px;padding:10px 14px;margin-top:10px;font-size:12px;color:#aaa;line-height:1.7;}"
    ".reason-box-sell{background:#0f0a0a;border:1px solid #3a1a1a;border-left:3px solid #ff4b4b;border-radius:4px;padding:10px 14px;margin-top:10px;font-size:12px;color:#aaa;line-height:1.7;}"
    ".main .block-container{padding-bottom:60px;}"
    ".ticker-footer{position:fixed;bottom:0;left:0;width:100%;height:40px;background:#000;border-top:1px solid #D4AF37;z-index:999999;}"
    "</style>"
)
st.markdown(_css, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════
# CREDENTIALS  ← EDIT THESE TWO LINES
# ═══════════════════════════════════════════════════════════════════════
_FINNHUB_KEY = "d6ng6v9r01qodk5vlu30d6ng6v9r01qodk5vlu3g"   # free at finnhub.io — 60 calls/min forever
_TG_TOKEN    = "8546515684:AAF4rVZbiqtEqHVPFloJ26wHeDsaHR8hKHE"
_TG_CHAT_ID  = "5689404731"

# ═══════════════════════════════════════════════════════════════════════
# FINNHUB — FREE REAL-TIME DATA LAYER
# 60 calls/min free forever. No credit limits. Sign up at finnhub.io
# ═══════════════════════════════════════════════════════════════════════

# Finnhub symbol map
_FH_MAP = {
    # Forex — Finnhub uses OANDA:EUR_USD format
    "EUR/USD": "OANDA:EUR_USD", "GBP/USD": "OANDA:GBP_USD",
    "USD/JPY": "OANDA:USD_JPY", "USD/CHF": "OANDA:USD_CHF",
    "AUD/USD": "OANDA:AUD_USD", "USD/CAD": "OANDA:USD_CAD",
    "NZD/USD": "OANDA:NZD_USD", "USD/ZAR": "OANDA:USD_ZAR",
    "GBP/ZAR": "OANDA:GBP_ZAR",
    # Indices
    "S&P 500":    "^GSPC",  "NASDAQ 100": "^NDX",
    "US 30":      "^DJI",   "VIX":        "^VIX",
    # Commodities
    "GOLD":       "OANDA:XAU_USD", "SILVER":    "OANDA:XAG_USD",
    "OIL (WTI)":  "NYMEX:CL1!",   "NAT GAS":   "NYMEX:NG1!",
    # Crypto — Finnhub uses BINANCE:BTCUSDT
    "BITCOIN":  "BINANCE:BTCUSDT",
    "ETHEREUM": "BINANCE:ETHUSDT",
    "SOLANA":   "BINANCE:SOLUSDT",
}

# Finnhub interval map: resolution codes
_FH_RES = {"5min": "5", "1h": "60", "4h": "D", "1day": "D"}
# Note: Finnhub free tier: 5m, 15m, 30m, 60m, D, W, M
# We use 5m, 60m (1H), D (daily) — 4H built by resampling 60m bars

import time as _time

def _fh_candles(display_name: str, resolution: str, bars: int) -> pd.DataFrame | None:
    """
    Fetch OHLCV candles from Finnhub (free, 60 req/min).
    resolution: '5' = 5min, '60' = 1H, 'D' = daily
    Returns DataFrame with Open/High/Low/Close/Volume columns, oldest first.
    """
    if not _FINNHUB_KEY or "YOUR_" in _FINNHUB_KEY:
        return None

    fh_sym = _FH_MAP.get(display_name)
    if not fh_sym:
        return None

    import time as _t
    now  = int(_t.time())
    # How many seconds back to request
    secs_per_bar = {"5": 300, "15": 900, "30": 1800, "60": 3600, "D": 86400}
    spb  = secs_per_bar.get(resolution, 3600)
    frm  = now - (spb * bars * 2)   # 2x buffer for weekends/gaps

    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/stock/candle",
            params={
                "symbol":     fh_sym,
                "resolution": resolution,
                "from":       frm,
                "to":         now,
                "token":      _FINNHUB_KEY,
            },
            timeout=12,
        )
        data = resp.json()

        if data.get("s") != "ok" or "c" not in data:
            return None

        df = pd.DataFrame({
            "Open":   data["o"],
            "High":   data["h"],
            "Low":    data["l"],
            "Close":  data["c"],
            "Volume": data.get("v", [0] * len(data["c"])),
        }, index=pd.to_datetime(data["t"], unit="s", utc=True))

        df = df.sort_index()          # oldest first
        df = df.tail(bars)            # keep only what we need
        df.dropna(inplace=True)
        return df if len(df) >= 15 else None

    except Exception:
        return None


def _fh_4h(display_name: str, bars: int = 60) -> pd.DataFrame | None:
    """Build 4H bars by resampling 1H data (Finnhub free tier has no 4H endpoint)."""
    df_1h = _fh_candles(display_name, "60", bars * 4 + 20)
    if df_1h is None or len(df_1h) < 8:
        return None
    df_4h = df_1h.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()
    return df_4h if len(df_4h) >= 8 else None


# ═══════════════════════════════════════════════════════════════════════
# MAIN SIGNAL ENGINE — 4 TIMEFRAME CONFLUENCE
# ═══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def get_signal(display_name: str):
    """
    4-Timeframe Multi-Confluence Signal Engine (Twelve Data real-time)

    DAILY  → macro bias (EMA 20 + EMA 50 direction)
    4H     → structural trend (EMA 21 + EMA 50, price alignment)
    1H     → intermediate entry (EMA 9/21, RSI, MACD, ATR)
    5m     → precision entry  (EMA 9/21, RSI, MACD, ATR)

    BOT DECISION:
      ⭐⭐⭐ STRONG  → Daily + 4H + 1H + 5m all agree  → SEND
      ⭐⭐   GOOD   → Daily + 4H + 1H agree, 5m aligning → SEND with note
      ⏳    WEAK   → Daily + 4H agree but entry TFs not ready → WAIT
      ❌    NONE   → Daily or 4H conflict → WAIT

    SL: structure-based — below/above last 8-bar 4H swing low/high
    TP: minimum 2R enforced (or 2.5× 1H ATR, whichever is larger)
    """
    try:
        df_1d = _fh_candles(display_name, "D",  90)
        df_4h = _fh_4h(display_name, 60)
        df_1h = _fh_candles(display_name, "60", 80)
        df_5m = _fh_candles(display_name, "5",  100)

        if df_1d is None or df_4h is None or df_1h is None:
            return "⚪ WAITING", 0.0, 0.0, 0.0, (
                "⚠️ No data from Twelve Data.\n"
                "Check your _FINNHUB_KEY is set in app.py.\n"
                "Free key at finnhub.io — no credit limits"
            )

        c_price = df_1h["Close"].iloc[-1]

        # ── Layer 1: Daily Bias ───────────────────────────────────────
        ema20_d = df_1d["Close"].ewm(span=20, adjust=False).mean()
        ema50_d = df_1d["Close"].ewm(span=50, adjust=False).mean()
        d_close = df_1d["Close"].iloc[-1]
        daily_bull = d_close > ema50_d.iloc[-1] and ema20_d.iloc[-1] > ema50_d.iloc[-1]
        daily_bear = d_close < ema50_d.iloc[-1] and ema20_d.iloc[-1] < ema50_d.iloc[-1]

        if not daily_bull and not daily_bear:
            return "⚪ WAITING", c_price, 0.0, 0.0, (
                "Daily EMA 20 and EMA 50 are overlapping — no clear macro bias.\n"
                "Waiting for daily trend to establish direction."
            )

        bias = "bull" if daily_bull else "bear"

        # ── Layer 2: 4H Structure ─────────────────────────────────────
        ema21_4h = df_4h["Close"].ewm(span=21, adjust=False).mean()
        ema50_4h = df_4h["Close"].ewm(span=50, adjust=False).mean()
        h4_close = df_4h["Close"].iloc[-1]
        struct_bull = h4_close > ema21_4h.iloc[-1] and ema21_4h.iloc[-1] > ema50_4h.iloc[-1]
        struct_bear = h4_close < ema21_4h.iloc[-1] and ema21_4h.iloc[-1] < ema50_4h.iloc[-1]
        struct_ok   = (bias == "bull" and struct_bull) or (bias == "bear" and struct_bear)

        if not struct_ok:
            d_label = "BULLISH" if bias == "bull" else "BEARISH"
            return "⚪ WAITING", c_price, 0.0, 0.0, (
                f"Daily is {d_label} but 4H structure not aligned yet.\n"
                "Waiting for 4H EMAs to confirm the daily direction."
            )

        # 4H swing for SL
        swing_low  = df_4h["Low"].iloc[-8:].min()
        swing_high = df_4h["High"].iloc[-8:].max()

        # ── Layers 3 + 4: 1H and 5m Entry Checks ─────────────────────
        h1 = _check_entry(df_1h, bias)
        m5 = _check_entry(df_5m, bias) if df_5m is not None else None

        h1_ok = h1["signal"]
        m5_ok = m5["signal"] if m5 else False

        # ── Bot Decision ──────────────────────────────────────────────
        if not h1_ok and not m5_ok:
            reasons = []
            if not h1["ema_entry"]:
                reasons.append("1H: No EMA cross and price not near EMA 21")
            if not h1["rsi_ok"]:
                reasons.append(f"1H RSI {h1['rsi']:.1f} — outside entry zone")
            if not h1["macd_ok"]:
                reasons.append("1H MACD not confirming direction")
            if not h1["atr_active"]:
                reasons.append("1H ATR flat — market has no momentum")
            if m5 and not m5["ema_entry"]:
                reasons.append("5m: No EMA cross and price not near EMA 21")
            return "⚪ WAITING", c_price, 0.0, 0.0, (
                "Daily ✅  |  4H ✅  |  Entry pending:\n" +
                "\n".join(f"⏳ {r}" for r in reasons)
            )

        # ── TP / SL ───────────────────────────────────────────────────
        atr_1h = h1["atr"]

        if bias == "bull":
            sl       = swing_low  - (atr_1h * 0.3)
            raw_risk = c_price - sl
            if raw_risk <= 0 or raw_risk > c_price * 0.06:
                return "⚪ WAITING", c_price, 0.0, 0.0, "SL too wide vs current price — skipping trade"
            tp  = c_price + max(raw_risk * 2.0, atr_1h * 2.5)
            sig = "🟢 BUY"
        else:
            sl       = swing_high + (atr_1h * 0.3)
            raw_risk = sl - c_price
            if raw_risk <= 0 or raw_risk > c_price * 0.06:
                return "⚪ WAITING", c_price, 0.0, 0.0, "SL too wide vs current price — skipping trade"
            tp  = c_price - max(raw_risk * 2.0, atr_1h * 2.5)
            sig = "🔴 SELL"

        rr = abs(tp - c_price) / raw_risk

        # ── Confidence Label ──────────────────────────────────────────
        if h1_ok and m5_ok:
            confidence = "⭐⭐⭐ HIGH CONFIDENCE — 1H + 5m both confirmed"
        else:
            confidence = "⭐⭐ GOOD ENTRY — 1H confirmed, 5m aligning"

        d_arrow  = ">" if bias == "bull" else "<"
        sl_label = "below 4H swing low" if bias == "bull" else "above 4H swing high"
        m5_note  = h1["cross_type"] if not m5 else (m5["cross_type"] + f" | RSI {m5['rsi']:.1f}" if m5_ok else "Aligning...")

        reason = (
            f"{confidence}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Daily: {'BULLISH ↑' if bias == 'bull' else 'BEARISH ↓'} "
            f"— EMA 20 {d_arrow} EMA 50 (macro confirmed)\n"
            f"📊 4H structure: ALIGNED ✅ — EMAs sloping "
            f"{'up' if bias == 'bull' else 'down'}, "
            f"price {'above' if bias == 'bull' else 'below'} both EMAs\n"
            f"⏰ 1H entry: {h1['cross_type']} | RSI {h1['rsi']:.1f}\n"
            f"⚡ 5m entry: {m5_note}\n"
            f"📐 R:R = 1:{rr:.1f} ({'excellent' if rr >= 2.5 else 'acceptable'})\n"
            f"🛑 SL {sl_label} + 0.3× ATR buffer\n"
            f"⚠️ Not financial advice. Manage your risk."
        )

        return sig, c_price, tp, sl, reason

    except Exception as e:
        return "⚪ WAITING", 0.0, 0.0, 0.0, f"Engine error: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD HEATMAP DATA (Twelve Data)
# ═══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def get_dashboard_data():
    """Uses yfinance — free, unlimited, fine for display purposes."""
    results = []
    for display_name, yf_sym in TICKER_MAP.items():
        try:
            df = yf.Ticker(yf_sym).history(period="2d", interval="1h")
            if df is None or len(df) < 20:
                df = yf.Ticker(yf_sym).history(period="5d", interval="1h")
            if df is None or len(df) < 10:
                continue
            price = float(df["Close"].iloc[-1])
            sma20 = df["Close"].rolling(20).mean().iloc[-1]
            ema50 = df["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
            if pd.isna(sma20) or price == 0:
                continue
            bias  = "BULLISH" if price > ema50 else "BEARISH"
            pct   = ((df["Close"].iloc[-1] - df["Close"].iloc[0]) / df["Close"].iloc[0]) * 100
            score = int(min(max(abs(pct) * 30, 1), 10))
            if bias == "BEARISH": score = -score
            tech  = "Overbought" if score >= 7 else "Oversold" if score <= -7 else "Neutral"
            results.append({
                "Symbol": display_name, "Bias": bias, "Score": score,
                "Trend": "Upward" if bias == "BULLISH" else "Downward",
                "Tech": tech, "Price": price,
            })
        except Exception as e:
            st.session_state.setdefault("data_errors", []).append(f"{display_name}: {str(e)}")
    return results

# ═══════════════════════════════════════════════════════════════════════
# SESSION / KILL ZONE
# ═══════════════════════════════════════════════════════════════════════
def get_session_info():
    now = datetime.now(timezone.utc)
    h   = now.hour + now.minute / 60.0
    if   7.0  <= h < 10.0: return True,  "🇬🇧 LONDON OPEN"
    elif 12.0 <= h < 16.0: return True,  "🇺🇸 NY / LONDON OVERLAP"
    elif 0.0  <= h <  3.0: return True,  "🌏 TOKYO OPEN"
    elif 18.0 <= h < 20.0: return False, "🌙 SYDNEY OPEN (low volume)"
    elif 10.0 <= h < 12.0: return False, "😴 LONDON DEAD ZONE"
    elif 16.0 <= h < 18.0: return False, "😴 NY AFTERNOON (fading)"
    else:                   return False, "🔴 OFF-SESSION (avoid)"

def _next_session():
    now = datetime.now(timezone.utc)
    h   = now.hour + now.minute / 60.0
    if   h < 0.0:  return "Tokyo Open",        "00:00 UTC"
    elif h < 7.0:  return "London Open",        "07:00 UTC"
    elif h < 12.0: return "NY/London Overlap",  "12:00 UTC"
    else:           return "Tokyo Open",         "00:00 UTC (tomorrow)"

# ═══════════════════════════════════════════════════════════════════════
# TELEGRAM HELPERS
# ═══════════════════════════════════════════════════════════════════════
def get_telegram_creds():
    return _TG_TOKEN, _TG_CHAT_ID

def send_telegram(message: str):
    token, chat_id = get_telegram_creds()
    if not token or not chat_id or "YOUR_" in token:
        return False, "Credentials not set"
    try:
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
        return (True, "") if resp.status_code == 200 else (False, resp.text)
    except Exception as e:
        return False, str(e)

def _build_signal_message(display_name, sig, entry, tp, sl, reason, session_name):
    rr        = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0
    direction = "🟢 BUY" if "BUY" in sig else "🔴 SELL"
    return (
        f"🚨 <b>ALPHAEDGE SIGNAL ALERT</b> 🚨\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Asset:</b> {display_name}\n"
        f"📈 <b>Signal:</b> {direction}\n"
        f"⏰ <b>Time (UTC):</b> {datetime.now(timezone.utc).strftime('%H:%M  %d/%m/%Y')}\n"
        f"🏦 <b>Session:</b> {session_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Entry:</b>  {entry:.4f}\n"
        f"🎯 <b>TP:</b>     {tp:.4f}\n"
        f"🛑 <b>SL:</b>     {sl:.4f}\n"
        f"📐 <b>R:R:</b>    1 : {rr:.1f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 <b>Confluence:</b>\n{reason}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
    )

# ═══════════════════════════════════════════════════════════════════════
# BACKGROUND MONITOR — scans every 5 min, session-aware
# ═══════════════════════════════════════════════════════════════════════
_last_signals:      dict = {}
_last_session_state: bool = None

def _monitor_loop():
    global _last_signals, _last_session_state
    while True:
        try:
            in_kz, session_name = get_session_info()
            token, chat_id = get_telegram_creds()

            if token and chat_id and "YOUR_" not in token:

                # Session OPEN alert
                if in_kz and _last_session_state == False:
                    send_telegram(
                        f"🟢 <b>KILL ZONE OPEN — {session_name}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                        f"📡 AlphaEdge scanning all 20 markets\n"
                        f"👀 Watching for Daily + 4H + 1H + 5m confluence\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
                    )

                # Session CLOSE alert
                elif not in_kz and _last_session_state == True:
                    next_name, next_time = _next_session()
                    send_telegram(
                        f"🔴 <b>SESSION CLOSED — {session_name}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                        f"😴 Low volume period — no new signals\n"
                        f"⏭️ <b>Next session:</b> {next_name} at {next_time}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
                    )
                    _last_signals = {}   # fresh slate each session

                _last_session_state = in_kz

                # Signal scan — only during kill zones
                if in_kz:
                    for display_name in TICKER_MAP.keys():
                        try:
                            sig, entry, tp, sl, reason = get_signal(display_name)
                            prev = _last_signals.get(td_sym, "⚪ WAITING")
                            if sig != "⚪ WAITING" and sig != prev:
                                msg = _build_signal_message(
                                    display_name, sig, entry, tp, sl, reason, session_name
                                )
                                send_telegram(msg)
                                _last_signals[td_sym] = sig
                            elif sig == "⚪ WAITING" and prev != "⚪ WAITING":
                                _last_signals[td_sym] = "⚪ WAITING"
                            time.sleep(1)
                        except Exception:
                            continue

        except Exception:
            pass
        time.sleep(300)   # scan every 5 minutes

_monitor_started = False
def start_monitor():
    global _monitor_started
    if not _monitor_started:
        t = threading.Thread(target=_monitor_loop, daemon=True)
        t.start()
        _monitor_started = True

start_monitor()

# ═══════════════════════════════════════════════════════════════════════
# POPUP CHART
# ═══════════════════════════════════════════════════════════════════════
def show_popup_chart(ticker_name):
    tv_sym = TV_MAP.get(ticker_name, "FX:EURUSD")
    components.html(
        f'<div style="position:fixed;top:0;left:0;width:100%;height:100%;'
        f'background:rgba(0,0,0,0.9);z-index:9999;display:flex;'
        f'align-items:center;justify-content:center;">'
        f'<div style="width:90%;height:90%;background:#111;border:1px solid #D4AF37;border-radius:8px;">'
        f'<iframe src="https://www.tradingview.com/chart/?symbol={tv_sym}" '
        f'width="100%" height="100%" frameborder="0"></iframe></div></div>',
        height=700,
    )

# ═══════════════════════════════════════════════════════════════════════
# COMMUNITY CHAT DB
# ═══════════════════════════════════════════════════════════════════════
DB_FILE  = "chat.db"
_db_lock = threading.Lock()

def init_db():
    with _db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, ts REAL)"
        )
        conn.commit(); conn.close()

def load_chat(limit=100):
    try:
        with _db_lock:
            conn = sqlite3.connect(DB_FILE)
            rows = conn.execute(
                "SELECT text, ts FROM messages ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
        return list(reversed(rows))
    except Exception:
        return []

def save_message(text: str):
    clean = html.escape(text.strip())
    if not clean: return
    with _db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT INTO messages (text, ts) VALUES (?, ?)", (clean, time.time()))
        conn.commit(); conn.close()

init_db()

# ═══════════════════════════════════════════════════════════════════════
# SESSION INFO — resolved once, used everywhere
# ═══════════════════════════════════════════════════════════════════════
in_kz, session_name = get_session_info()
now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")

# ═══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════
with st.sidebar:
    logo_file = "logo.gif" if os.path.exists("logo.gif") else "logo.png" if os.path.exists("logo.png") else None
    if logo_file:
        try:
            with open(logo_file, "rb") as f:
                enc  = base64.b64encode(f.read()).decode()
                mime = "image/gif" if logo_file.endswith(".gif") else "image/png"
            st.markdown(
                f'<div style="text-align:center;margin-bottom:20px;">'
                f'<img src="data:{mime};base64,{enc}" width="100%"></div>',
                unsafe_allow_html=True,
            )
        except Exception:
            pass
    else:
        st.markdown('<div style="text-align:center;"><h1>🅰️</h1><h2>AlphaEdge</h2></div>', unsafe_allow_html=True)

    st.markdown(
        '<div style="text-align:center;margin-bottom:20px;">'
        '<p style="font-size:10px;color:#888;">TRADING INTELLIGENCE REDEFINED</p>'
        '</div><hr style="border-top:1px solid #333;">',
        unsafe_allow_html=True,
    )

    with st.expander("🔴 LIVE MEDIA", expanded=True):
        st.subheader("📺 LIVE FINANCIAL TV")
        tv_ch = st.selectbox(
            "Channel:", ["Bloomberg Markets", "CNBC Live", "Reuters TV"],
            label_visibility="collapsed", key="tv_sel"
        )
        if tv_ch == "Bloomberg Markets":
            components.html(
                '<iframe width="100%" height="150" '
                'src="https://www.youtube-nocookie.com/embed/live_stream?channel=UCIALMKvObZNtJ6AmdCLP7Lg" '
                'frameborder="0" allowfullscreen referrerpolicy="no-referrer"></iframe>',
                height=160,
            )
            st.markdown(
                '<p style="font-size:10px;color:#555;">Error? '
                '<a href="https://www.youtube.com/@BloombergMarkets/streams" target="_blank" '
                'style="color:#D4AF37;">Watch on YouTube ↗</a></p>',
                unsafe_allow_html=True,
            )
        elif tv_ch == "CNBC Live":
            components.html(
                '<iframe width="100%" height="150" '
                'src="https://www.youtube-nocookie.com/embed/live_stream?channel=UCrp_UI8XtuAWcp6g7utDLKQ" '
                'frameborder="0" allowfullscreen referrerpolicy="no-referrer"></iframe>',
                height=160,
            )
            st.markdown(
                '<p style="font-size:10px;color:#555;">Error? '
                '<a href="https://www.youtube.com/@CNBCtelevision/streams" target="_blank" '
                'style="color:#D4AF37;">Watch on YouTube ↗</a></p>',
                unsafe_allow_html=True,
            )
        else:
            components.html(
                '<iframe width="100%" height="150" '
                'src="https://www.youtube-nocookie.com/embed/live_stream?channel=UCwBOEANMhgSVTSGSAfS61Lg" '
                'frameborder="0" allowfullscreen referrerpolicy="no-referrer"></iframe>',
                height=160,
            )
            st.markdown(
                '<p style="font-size:10px;color:#555;">Error? '
                '<a href="https://www.youtube.com/@Reuters/streams" target="_blank" '
                'style="color:#D4AF37;">Watch on YouTube ↗</a></p>',
                unsafe_allow_html=True,
            )

        st.subheader("🎵 TRADING STATION")
        station = st.selectbox(
            "Audio:", ["NYC Power 105.1", "Lofi Trading Beats", "Chillout Jazz"],
            label_visibility="collapsed"
        )
        if station == "NYC Power 105.1":
            components.html(
                '<iframe allow="autoplay" width="100%" height="150" '
                'src="https://www.iheart.com/live/power-1051-1473/?embed=true" frameborder="0"></iframe>',
                height=160,
            )
        elif station == "Lofi Trading Beats":
            components.html(
                '<iframe width="100%" height="150" '
                'src="https://www.youtube-nocookie.com/embed/jfKfPfyJRdk?autoplay=1&rel=0" '
                'frameborder="0" allowfullscreen referrerpolicy="no-referrer"></iframe>',
                height=160,
            )
        else:
            components.html(
                '<iframe width="100%" height="150" '
                'src="https://www.youtube-nocookie.com/embed/Dx5qFachd3A?autoplay=1&rel=0" '
                'frameborder="0" allowfullscreen referrerpolicy="no-referrer"></iframe>',
                height=160,
            )

    st.markdown("---")
    st.markdown(
        '<p style="text-align:center;color:#D4AF37;font-size:11px;'
        'font-weight:bold;letter-spacing:2px;">🏆 FEATURED PARTNERS</p>',
        unsafe_allow_html=True,
    )

    if os.path.exists("static/exness_logo.png"): st.image("static/exness_logo.png", use_container_width=True)
    if os.path.exists("static/exness.mp4"):      st.video("static/exness.mp4", start_time=0)
    st.markdown(
        '<a href="https://one.exnessonelink.com/a/9wwklqzfxb" target="_blank">'
        '<button style="width:100%;background-color:#D4AF37;color:#000;border:none;'
        'padding:12px;border-radius:5px;font-weight:bold;cursor:pointer;'
        'margin-top:6px;font-size:13px;">🚀 TRADE WITH 0 SPREADS ➤</button></a>',
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    if os.path.exists("static/goat_logo.png"): st.image("static/goat_logo.png", use_container_width=True)
    if os.path.exists("static/goat.mp4"):      st.video("static/goat.mp4", start_time=0)
    st.markdown(
        '<a href="https://checkout.goatfundedtrader.com/aff/Sherwet/" target="_blank">'
        '<button style="width:100%;background-color:#00E676;color:#000;border:none;'
        'padding:12px;border-radius:5px;font-weight:bold;cursor:pointer;'
        'margin-top:6px;font-size:13px;">🐐 GET FUNDED TODAY ➤</button></a>',
        unsafe_allow_html=True,
    )

    st.divider()
    focus_ticker = st.selectbox("ACTIVE CHART ASSET:", list(TICKER_MAP.keys()), index=0)
    if st.button("GET YOUR TRADINGVIEW ADVANCED CHART HERE", use_container_width=True):
        show_popup_chart(focus_ticker)

# ═══════════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════════
tab_dash, tab_cot, tab_sent, tab_ind, tab_fx, tab_news, tab_cal, tab_chat = st.tabs([
    "  📊 DASHBOARD  ", "  📊 COT DATA  ", "  📈 SENTIMENT  ",
    "  🏙️ INDICES  ",  "  💱 CURRENCY MATRIX  ", "  📰 LIVE NEWS  ",
    "  📅 CALENDAR  ", "  💬 COMMUNITY  ",
])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════
with tab_dash:
    st.title("📊 ALPHAEDGE COMMAND CENTRE")

    # Session banner
    if in_kz:
        st.markdown(
            f'<div style="background:#0a1a0a;border:1px solid #00ff88;border-radius:6px;'
            f'padding:10px 16px;margin-bottom:12px;">'
            f'<span style="color:#00ff88;font-weight:bold;font-size:13px;">🟢 ACTIVE KILL ZONE</span>'
            f'<span class="kill-zone-badge">{session_name}</span>'
            f'<span style="float:right;color:#888;font-size:12px;">{now_utc}</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="background:#1a0a0a;border:1px solid #ff4b4b;border-radius:6px;'
            f'padding:10px 16px;margin-bottom:12px;">'
            f'<span style="color:#ff4b4b;font-weight:bold;font-size:13px;">🔴 OFF SESSION</span>'
            f'<span class="dead-zone-badge">{session_name}</span>'
            f'<span style="float:right;color:#888;font-size:12px;">{now_utc}</span></div>',
            unsafe_allow_html=True,
        )

    # API key warning
    if "YOUR_" in _FINNHUB_KEY:
        st.warning(
            "⚠️ **Twelve Data API key not set.** "
            "Get a free key at [twelvedata.com](https://twelvedata.com) "
            "and paste it into `_FINNHUB_KEY` in app.py. "
            "Without it no live data or signals will work."
        )

    st.write("⏳ *Fetching live market data from Twelve Data...*")
    data = get_dashboard_data()

    rows_html = ""
    if data:
        for row in data:
            css = "bullish" if row["Bias"] == "BULLISH" else "bearish"
            rows_html += (
                f'<tr><td><b>{row["Symbol"]}</b></td>'
                f'<td class="{css}">{row["Bias"]}</td>'
                f'<td class="{css}">{row["Score"]:+}</td>'
                f'<td>{row["Trend"]}</td>'
                f'<td>{row["Tech"]}</td>'
                f'<td style="color:#D4AF37;font-weight:bold;">{row["Price"]:,.4f}</td>'
                f'<td><span class="live-tag">⚡ LIVE</span></td></tr>'
            )
    else:
        rows_html = "<tr><td colspan='7' style='color:#888;'>Loading data — set your Twelve Data API key</td></tr>"

    st.markdown(
        f'<table class="heatmap-table"><thead><tr>'
        f'<th>SYMBOL</th><th>BIAS</th><th>SCORE</th>'
        f'<th>TREND</th><th>TECH</th><th>PRICE</th><th>SOURCE</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown(
        '<h3 style="border-bottom:2px solid #D4AF37;padding-bottom:6px;">'
        '⚡ AI EMA SCALPER — LIVE SIGNAL</h3>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="background:#0a0800;border:1px solid #D4AF37;border-radius:4px;'
        'padding:8px 14px;margin-bottom:12px;font-size:11px;color:#D4AF37;">'
        '⚠️ <b>RISK DISCLAIMER:</b> Signals are for educational purposes only. '
        'Past performance does not guarantee future results. '
        'Never risk more than you can afford to lose.</div>',
        unsafe_allow_html=True,
    )

    # Signal for selected asset
    if "YOUR_" not in _FINNHUB_KEY:
        sig, entry, tp, sl, reason = get_signal(focus_ticker)

        c1, c2, c3 = st.columns(3)
        with c1:
            color = "#00ff88" if "BUY" in sig else "#ff4b4b" if "SELL" in sig else "#888"
            st.markdown(
                f'<div style="background:#111;border:1px solid {color};border-radius:6px;'
                f'padding:14px;text-align:center;">'
                f'<div style="font-size:11px;color:#888;">SIGNAL</div>'
                f'<div style="font-size:20px;font-weight:bold;color:{color};">{sig}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f'<div style="background:#111;border:1px solid #333;border-radius:6px;'
                f'padding:14px;text-align:center;">'
                f'<div style="font-size:11px;color:#888;">ENTRY</div>'
                f'<div style="font-size:18px;font-weight:bold;color:#D4AF37;">'
                f'{entry:.4f if entry else "—"}</div></div>',
                unsafe_allow_html=True,
            )
        with c3:
            rr_val = abs(tp - entry) / abs(sl - entry) if entry and sl and abs(sl - entry) > 0 else 0
            st.markdown(
                f'<div style="background:#111;border:1px solid #333;border-radius:6px;'
                f'padding:14px;text-align:center;">'
                f'<div style="font-size:11px;color:#888;">R:R RATIO</div>'
                f'<div style="font-size:18px;font-weight:bold;color:#D4AF37;">'
                f'{"1 : " + f"{rr_val:.1f}" if rr_val else "—"}</div></div>',
                unsafe_allow_html=True,
            )

        if "BUY" in sig:
            box_class = "reason-box"
        elif "SELL" in sig:
            box_class = "reason-box-sell"
        else:
            box_class = "reason-box"

        reason_html = reason.replace("\n", "<br>")
        st.markdown(
            f'<div class="{box_class}">'
            f'<b>🤖 BOT ANALYSIS — {focus_ticker}</b><br><br>{reason_html}</div>',
            unsafe_allow_html=True,
        )

        if entry and tp and sl:
            c4, c5, c6 = st.columns(3)
            with c4:
                st.metric("TP", f"{tp:.4f}")
            with c5:
                st.metric("SL", f"{sl:.4f}")
            with c6:
                st.metric("Entry", f"{entry:.4f}")
    else:
        st.info("Set your Twelve Data API key in app.py to see live signals.")

    # TradingView chart
    tv_sym = TV_MAP.get(focus_ticker, "FX:EURUSD")
    st.markdown("---")
    components.html(
        f'<div class="tradingview-widget-container">'
        f'<div id="tradingview_chart"></div>'
        f'<script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>'
        f'<script type="text/javascript">new TradingView.widget({{'
        f'"autosize": true, "symbol": "{tv_sym}", "interval": "60",'
        f'"timezone": "Etc/UTC", "theme": "dark", "style": "1",'
        f'"locale": "en", "toolbar_bg": "#111", "enable_publishing": false,'
        f'"container_id": "tradingview_chart"}})</script></div>',
        height=500,
    )

# ═══════════════════════════════════════════════════════════════════════
# TAB 2: COT DATA
# ═══════════════════════════════════════════════════════════════════════
with tab_cot:
    st.title("📊 COT DATA — COMMITMENT OF TRADERS")
    try:
        import cot_fetcher
        cot_fetcher.render()
    except ImportError:
        st.info("COT fetcher module not found. Add cot_fetcher.py to your project root.")
    except Exception as e:
        st.error(f"COT data error: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 3: SENTIMENT
# ═══════════════════════════════════════════════════════════════════════
with tab_sent:
    st.title("📈 MARKET SENTIMENT")
    st.info("Sentiment data coming soon. Integration with Fear & Greed index and retail positioning.")

# ═══════════════════════════════════════════════════════════════════════
# TAB 4: INDICES
# ═══════════════════════════════════════════════════════════════════════
with tab_ind:
    st.title("🏙️ GLOBAL INDICES")
    indices = ["S&P 500", "NASDAQ 100", "US 30", "VIX"]
    for name in indices:
        td_sym = TICKER_MAP.get(name)
        if td_sym:
            price = _td_price(td_sym)
            if price:
                st.metric(name, f"{price:,.2f}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 5: CURRENCY MATRIX
# ═══════════════════════════════════════════════════════════════════════
with tab_fx:
    st.title("💱 CURRENCY STRENGTH MATRIX")
    fx_pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
                "AUD/USD", "USD/CAD", "NZD/USD", "USD/ZAR", "GBP/ZAR"]
    fx_data = []
    for name in fx_pairs:
        yf_sym = TICKER_MAP.get(name)
        if yf_sym:
            try:
                df = yf.Ticker(yf_sym).history(period="2d", interval="1h")
                if df is not None and len(df) >= 10:
                    price = float(df["Close"].iloc[-1])
                    sma20 = df["Close"].rolling(20).mean().iloc[-1]
                    ema50 = df["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
                    bias  = "BULLISH" if price > ema50 else "BEARISH"
                    chg   = ((df["Close"].iloc[-1] - df["Close"].iloc[-8]) / df["Close"].iloc[-8]) * 100 if len(df) >= 8 else 0
                    fx_data.append({
                        "Pair": name,
                        "Price": f"{price:.5f}",
                        "Bias": bias,
                        "8H Change": f"{chg:+.2f}%"
                    })
            except Exception:
                continue
    if fx_data:
        df_fx = pd.DataFrame(fx_data)
        st.dataframe(df_fx, use_container_width=True, hide_index=True)
    else:
        st.info("Loading currency data...")

# ═══════════════════════════════════════════════════════════════════════
# TAB 6: NEWS
# ═══════════════════════════════════════════════════════════════════════
with tab_news:
    st.title("📰 LIVE MARKET NEWS")
    components.html(
        '<script src="https://s3.tradingview.com/external-embedding/embed-widget-timeline.js" async>'
        '{"feedMode":"all_symbols","colorTheme":"dark","isTransparent":false,'
        '"displayMode":"regular","width":"100%","height":600,"locale":"en"}</script>',
        height=620,
    )

# ═══════════════════════════════════════════════════════════════════════
# TAB 7: CALENDAR
# ═══════════════════════════════════════════════════════════════════════
with tab_cal:
    st.title("📅 ECONOMIC CALENDAR")
    components.html(
        '<iframe src="https://sslecal2.investing.com?columns=exc_flags,exc_currency,'
        'exc_importance,exc_actual,exc_forecast,exc_previous&features=datepicker,'
        'timezone&countries=25,32,6,37,72,22,17,39,14,10,35,43,56&calType=day'
        '&timeZone=8&lang=1" width="100%" height="600" frameborder="0"></iframe>',
        height=620,
    )

# ═══════════════════════════════════════════════════════════════════════
# TAB 8: COMMUNITY CHAT
# ═══════════════════════════════════════════════════════════════════════
with tab_chat:
    st.title("💬 COMMUNITY CHAT")
    st.caption("Live chat for AlphaEdge members. Be respectful.")

    chat_input = st.text_input("Your message:", key="chat_input", max_chars=300)
    if st.button("Send", key="chat_send") and chat_input.strip():
        save_message(chat_input.strip())
        st.rerun()

    messages = load_chat(100)
    if messages:
        for text, ts in messages:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M")
            st.write(f"[{dt}] {text}")
    else:
        st.info("No messages yet. Be the first to say hello!")

# ═══════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="ticker-footer">'
    '<marquee style="color:#D4AF37;font-size:11px;line-height:40px;font-weight:bold;">'
    '⚡ AlphaEdge Trading Intelligence &nbsp;|&nbsp; '
    'Real-time signals powered by Twelve Data &nbsp;|&nbsp; '
    'Daily + 4H + 1H + 5m Confluence Engine &nbsp;|&nbsp; '
    '⚠️ Not financial advice &nbsp;|&nbsp; '
    'Trade responsibly &nbsp;|&nbsp; '
    'Session: ' + session_name +
    '</marquee></div>',
    unsafe_allow_html=True,
)
