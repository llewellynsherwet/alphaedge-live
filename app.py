import streamlit as st
import time
import os
import json
import html
import sqlite3
import threading
import requests
import pandas as pd
import yfinance as yf
import streamlit.components.v1 as components
import base64
from datetime import datetime, timezone

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
    "S&P 500": "CME_MINI:ES1!", "NASDAQ 100": "CME_MINI:NQ1!", "US 30": "CBOT_MINI:YM1!",
    "VIX": "TVC:VIX", "DAX 40": "INDEX:DE40",
    "GOLD": "OANDA:XAUUSD", "SILVER": "TVC:SILVER", "OIL (WTI)": "NYMEX:CL1!",
    "BITCOIN": "BINANCE:BTCUSDT", "ETHEREUM": "BINANCE:ETHUSDT", "SOLANA": "BINANCE:SOLUSDT"
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
    "</style>"
)
st.markdown(_css, unsafe_allow_html=True)


# ================= TELEGRAM HELPERS =================
def get_telegram_creds():
    """Returns hardcoded credentials — safe for background thread use."""
    return _TG_TOKEN, _TG_CHAT_ID

def send_telegram(message: str):
    token, chat_id = get_telegram_creds()
    if not token or not chat_id:
        return False, "No credentials set"
    try:
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        if resp.status_code == 200:
            return True, ""
        return False, resp.text
    except Exception as e:
        return False, str(e)

def test_telegram():
    msg = (
        "✅ <b>AlphaEdge — Connection Successful!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 Your Telegram bot is now linked to AlphaEdge.\n"
        "📡 Live signals will be delivered here automatically.\n\n"
        "⚠️ <i>Not financial advice. Trade responsibly.</i>"
    )
    return send_telegram(msg)


# ================= SESSION / KILL ZONE FILTER =================
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


# ================= DASHBOARD DATA =================
@st.cache_data(ttl=60, show_spinner=False)
def get_dashboard_data():
    results = []
    for symbol, y_sym in TICKER_MAP.items():
        try:
            ticker = yf.Ticker(y_sym)
            df = ticker.history(period="2d", interval="5m")
            if df.empty: df = ticker.history(period="5d", interval="1h")
            if not df.empty and len(df) >= 20:
                current_price = df['Close'].iloc[-1]
                sma_20 = df['Close'].rolling(window=20).mean().iloc[-1]
                if pd.isna(sma_20): continue
                bias = "BULLISH" if current_price > sma_20 else "BEARISH"
                open_price = df['Open'].iloc[0]
                if open_price == 0 or pd.isna(open_price): open_price = current_price
                pct_change = ((current_price - open_price) / open_price) * 100
                score = int(min(max(abs(pct_change) * 50, 1), 10))
                if bias == "BEARISH": score = -score
                tech = "Overbought" if score >= 8 else "Oversold" if score <= -8 else "Neutral"
                results.append({"Symbol": symbol, "Bias": bias, "Score": score,
                    "Trend": "Upward" if bias=="BULLISH" else "Downward", "Tech": tech, "Price": current_price})
        except Exception as e:
            st.session_state.setdefault("data_errors", []).append(f"{symbol}: {str(e)}")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# VETERAN FOREX SIGNAL ENGINE — 6-Layer Confluence System
# ══════════════════════════════════════════════════════════════════════════════
# Layer 1 — Kill Zone:     Only trade London Open / NY session (institutional hours)
# Layer 2 — Daily Bias:    1D 20 EMA — only trade WITH the macro trend
# Layer 3 — 4H Structure:  Price must be on correct side of 4H 200 EMA
# Layer 4 — EMA Cross:     9/21 EMA crossover on 5m (original logic kept)
# Layer 5 — RSI Zone:      40-65 long / 35-60 short (original logic kept)
# Layer 6 — Pullback Entry: Price retraces to 21 EMA after cross (veteran entry)
# TP/SL: ATR-based dynamic targets — adapts to current volatility
# Returns: signal, entry, tp, sl, reason (full explanation string)
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=30, show_spinner=False)
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

        # Layer 1: Kill Zone
        in_kz, session_name = get_session_info()
        if not in_kz:
            return "⚪ WAITING", close5.iloc[-1], 0.0, 0.0, f"Outside kill zone — {session_name}. Veteran traders only trade London Open (07:00-10:00 UTC) and NY Session (12:00-16:00 UTC)."

        # Layer 2: Daily Bias
        daily_ema20   = df1d['Close'].ewm(span=20, adjust=False).mean()
        daily_bullish = df1d['Close'].iloc[-1] > daily_ema20.iloc[-1]
        daily_bearish = df1d['Close'].iloc[-1] < daily_ema20.iloc[-1]

        # Layer 3: 4H 200 EMA
        ema200_4h = df4h['Close'].ewm(span=200, adjust=False).mean()
        above_200 = df4h['Close'].iloc[-1] > ema200_4h.iloc[-1]
        below_200 = df4h['Close'].iloc[-1] < ema200_4h.iloc[-1]

        # Layer 4: 5m EMA cross
        ema9    = close5.ewm(span=9,  adjust=False).mean()
        ema21   = close5.ewm(span=21, adjust=False).mean()
        c_price = close5.iloc[-1]
        c_ema9  = ema9.iloc[-1]
        c_ema21 = ema21.iloc[-1]

        # Layer 5: RSI
        delta    = close5.diff()
        ema_gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
        ema_loss = (-1 * delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
        rsi      = 100 - (100 / (1 + ema_gain / ema_loss))
        c_rsi    = rsi.iloc[-1]

        # Layer 6: Pullback to 21 EMA (within 0.05%)
        pullback_pct = abs(c_price - c_ema21) / c_ema21
        on_pullback  = pullback_pct < 0.0005

        # ATR-based TP/SL
        tr    = pd.concat([high5 - low5, (high5 - close5.shift()).abs(), (low5 - close5.shift()).abs()], axis=1).max(axis=1)
        c_atr = tr.rolling(14).mean().iloc[-1]
        tp_dist = c_atr * 1.5
        sl_dist = c_atr * 1.0

        long_ok = daily_bullish and above_200 and c_ema9 > c_ema21 and c_price > c_ema9 and 40 <= c_rsi <= 65 and on_pullback
        short_ok = daily_bearish and below_200 and c_ema9 < c_ema21 and c_price < c_ema9 and 35 <= c_rsi <= 60 and on_pullback

        if long_ok:
            reason = (
                f"✅ Session: {session_name} — institutional volume active\n"
                f"✅ Daily bias: BULLISH — price trading above 1D EMA20, macro trend is up\n"
                f"✅ 4H structure: Price above 200 EMA — confirmed uptrend on higher timeframe\n"
                f"✅ 5m EMA: 9 EMA crossed above 21 EMA — short-term momentum turned bullish\n"
                f"✅ RSI: {c_rsi:.1f} — mid-range zone, not overbought, momentum has room to extend\n"
                f"✅ Pullback entry: Price retraced {pullback_pct*100:.3f}% from 21 EMA — veteran entry, not chasing the cross"
            )
            return "🟢 STRONG BUY", c_price, c_price + tp_dist, c_price - sl_dist, reason

        elif short_ok:
            reason = (
                f"✅ Session: {session_name} — institutional volume active\n"
                f"✅ Daily bias: BEARISH — price trading below 1D EMA20, macro trend is down\n"
                f"✅ 4H structure: Price below 200 EMA — confirmed downtrend on higher timeframe\n"
                f"✅ 5m EMA: 9 EMA crossed below 21 EMA — short-term momentum turned bearish\n"
                f"✅ RSI: {c_rsi:.1f} — mid-range zone, not oversold, momentum has room to extend\n"
                f"✅ Pullback entry: Price retraced {pullback_pct*100:.3f}% from 21 EMA — veteran entry, not chasing the cross"
            )
            return "🔴 SELL", c_price, c_price - tp_dist, c_price + sl_dist, reason

        else:
            missing = []
            if not on_pullback: missing.append(f"price is {pullback_pct*100:.3f}% from 21 EMA — waiting for pullback (need <0.05%)")
            if not (daily_bullish or daily_bearish): missing.append("daily trend unclear")
            if daily_bullish and not above_200: missing.append("price below 4H 200 EMA — counter-trend buy rejected")
            if daily_bearish and not below_200: missing.append("price above 4H 200 EMA — counter-trend sell rejected")
            if not (40 <= c_rsi <= 65 or 35 <= c_rsi <= 60): missing.append(f"RSI {c_rsi:.1f} outside the acceptable zone")
            reason = ("Waiting: " + " | ".join(missing)) if missing else "No confluence — all 6 layers must align simultaneously"
            return "⚪ WAITING", c_price, 0.0, 0.0, reason

    except Exception:
        return "⚪ WAITING", 0.0, 0.0, 0.0, ""


# ══════════════════════════════════════════════════════════════════════════════
# HIGH-CONVICTION ENGINE — Commodities, Indices & Crypto
# 7-Layer: HTF Trend | Structure | MACD | RSI | Volume | ATR | Conviction Candle
# ══════════════════════════════════════════════════════════════════════════════
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

        # Layer 1: HTF 1h 50 EMA
        ema50_1h    = df1h['Close'].ewm(span=50, adjust=False).mean()
        htf_bullish = df1h['Close'].iloc[-1] > ema50_1h.iloc[-1]
        htf_bearish = df1h['Close'].iloc[-1] < ema50_1h.iloc[-1]

        # Layer 2: 5m structure
        ema21_5m   = close5.ewm(span=21, adjust=False).mean()
        ema9_5m    = close5.ewm(span=9,  adjust=False).mean()
        struct_bull = ema9_5m.iloc[-1] > ema21_5m.iloc[-1] and close5.iloc[-1] > ema21_5m.iloc[-1]
        struct_bear = ema9_5m.iloc[-1] < ema21_5m.iloc[-1] and close5.iloc[-1] < ema21_5m.iloc[-1]

        # Layer 3: MACD histogram expanding
        macd_line  = close5.ewm(span=12, adjust=False).mean() - close5.ewm(span=26, adjust=False).mean()
        histogram  = macd_line - macd_line.ewm(span=9, adjust=False).mean()
        macd_bull  = histogram.iloc[-1] > 0 and histogram.iloc[-1] > histogram.iloc[-2]
        macd_bear  = histogram.iloc[-1] < 0 and histogram.iloc[-1] < histogram.iloc[-2]

        # Layer 4: RSI tight zone
        delta5   = close5.diff()
        avg_gain = delta5.clip(lower=0).ewm(com=13, adjust=False).mean()
        avg_loss = (-1 * delta5.clip(upper=0)).ewm(com=13, adjust=False).mean()
        c_rsi    = (100 - (100 / (1 + avg_gain / avg_loss))).iloc[-1]
        rsi_bull = 45 <= c_rsi <= 62
        rsi_bear = 38 <= c_rsi <= 55

        # Layer 5: Volume surge
        vol_avg   = volume5.rolling(20).mean()
        vol_surge = volume5.iloc[-1] > (vol_avg.iloc[-1] * 1.3)
        vol_pct   = ((volume5.iloc[-1] / vol_avg.iloc[-1]) - 1) * 100

        # Layer 6: ATR active
        tr        = pd.concat([high5 - low5, (high5 - close5.shift()).abs(), (low5 - close5.shift()).abs()], axis=1).max(axis=1)
        atr14     = tr.rolling(14).mean()
        atr_active = atr14.iloc[-1] > atr14.rolling(10).mean().iloc[-1]

        # Layer 7: Conviction candle
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
                f"✅ 1H macro trend: Price above 50 EMA — institutions are positioned long\n"
                f"✅ 5m structure: 9 EMA above 21 EMA, price above both — local trend bullish\n"
                f"✅ MACD: Histogram positive AND expanding vs previous bar — momentum accelerating\n"
                f"✅ RSI: {c_rsi:.1f} — mid-range zone, not overbought, trade has room to move\n"
                f"✅ Volume: +{vol_pct:.0f}% above 20-bar average — institutional participation confirmed\n"
                f"✅ ATR: Volatility is above its own average — market is trending, not ranging\n"
                f"✅ Conviction candle: Body is {body_pct:.0f}% of range — strong directional bar, not a doji"
            )
            return "🟢 STRONG BUY", c_price, c_price + tp_dist, c_price - sl_dist, reason

        elif short_signal:
            reason = (
                f"✅ 1H macro trend: Price below 50 EMA — institutions are positioned short\n"
                f"✅ 5m structure: 9 EMA below 21 EMA, price below both — local trend bearish\n"
                f"✅ MACD: Histogram negative AND expanding vs previous bar — bearish momentum accelerating\n"
                f"✅ RSI: {c_rsi:.1f} — mid-range zone, not oversold, trade has room to drop\n"
                f"✅ Volume: +{vol_pct:.0f}% above 20-bar average — institutional participation confirmed\n"
                f"✅ ATR: Volatility is above its own average — market is trending, not ranging\n"
                f"✅ Conviction candle: Body is {body_pct:.0f}% of range — strong directional bar, not a doji"
            )
            return "🔴 SELL", c_price, c_price - tp_dist, c_price + sl_dist, reason

        else:
            missing = []
            if not vol_surge:   missing.append(f"volume only {vol_pct:.0f}% above avg (need +30%)")
            if not atr_active:  missing.append("ATR flat — market is ranging, no trend")
            if not conviction:  missing.append(f"weak candle — body only {body_pct:.0f}% of range (need >50%)")
            if not (macd_bull or macd_bear): missing.append("MACD histogram not expanding")
            if not rsi_bull and not rsi_bear: missing.append(f"RSI {c_rsi:.1f} outside acceptable zone")
            reason = ("Waiting: " + " | ".join(missing)) if missing else "Not all 7 layers confirmed — patience is the strategy"
            return "⚪ WAITING", c_price, 0.0, 0.0, reason

    except Exception:
        return "⚪ WAITING", 0.0, 0.0, 0.0, ""


def get_scalp_signal(ticker_symbol):
    if ticker_symbol in FOREX_TICKERS:
        return _forex_signal(ticker_symbol)
    else:
        return _commodity_index_signal(ticker_symbol)


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM BACKGROUND MONITOR
# Scans all pairs every 5 min — sends alert only when signal CHANGES state
# ══════════════════════════════════════════════════════════════════════════════
_last_signals: dict = {}

# ── TELEGRAM CREDENTIALS (hardcoded — never shown to users) ─────────────────
# Replace the values below with your actual token and chat ID
# These are only visible in your code, not on the platform
_TG_TOKEN:   str = "8546515684:AAF4rVZbiqtEqHVPFloJ26wHeDsaHR8hKHE"
_TG_CHAT_ID: str = "5689404731"

def _build_telegram_message(display_name, sig, entry, tp, sl, reason, session_name):
    rr = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0
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
        f"🔍 <b>Why this trade:</b>\n{reason}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
    )

def _monitor_loop():
    global _last_signals
    while True:
        try:
            in_kz, session_name = get_session_info()
            token, chat_id = get_telegram_creds()
            if token and chat_id:
                for display_name, ticker in TICKER_MAP.items():
                    try:
                        sig, entry, tp, sl, reason = get_scalp_signal(ticker)
                        prev = _last_signals.get(ticker, "⚪ WAITING")
                        if sig != "⚪ WAITING" and sig != prev:
                            msg = _build_telegram_message(display_name, sig, entry, tp, sl, reason, session_name)
                            send_telegram(msg)
                            _last_signals[ticker] = sig
                        elif sig == "⚪ WAITING" and prev != "⚪ WAITING":
                            _last_signals[ticker] = "⚪ WAITING"
                        time.sleep(1)
                    except Exception:
                        continue
        except Exception:
            pass
        time.sleep(300)

def start_monitor():
    if not st.session_state.get("monitor_started", False):
        t = threading.Thread(target=_monitor_loop, daemon=True)
        t.start()
        st.session_state["monitor_started"] = True

start_monitor()


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
    components.html(f"""<div id="tv_chart_popup" style="height:500px;"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize":true,"symbol":"{tv_symbol}","interval":"H1","theme":"dark","style":"1","locale":"en","toolbar_bg":"#f1f3f6","enable_publishing":false,"hide_side_toolbar":false,"allow_symbol_change":true,"container_id":"tv_chart_popup"}});</script>""", height=510)
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

    with st.expander("🔴 LIVE MEDIA", expanded=True):
        st.subheader("📺 BLOOMBERG TV")
        components.html('<iframe width="100%" height="150" src="https://www.youtube-nocookie.com/embed/live_stream?channel=UCIALMKvObZNtJ6AmdCLP7Lg&rel=0&modestbranding=1" frameborder="0" allowfullscreen referrerpolicy="no-referrer"></iframe>', height=160)
        st.subheader("🎵 TRADING STATION")
        station = st.selectbox("Select Audio:", ["NYC Power 105.1", "Lofi Trading Beats", "Chillout Jazz"], label_visibility="collapsed")
        if station == "NYC Power 105.1":
            components.html('<iframe allow="autoplay" width="100%" height="150" src="https://www.iheart.com/live/power-1051-1473/?embed=true" frameborder="0"></iframe>', height=160)
        elif station == "Lofi Trading Beats":
            components.html('<iframe width="100%" height="150" src="https://www.youtube-nocookie.com/embed/jfKfPfyJRdk?autoplay=1&rel=0&modestbranding=1" frameborder="0" allowfullscreen referrerpolicy="no-referrer"></iframe>', height=160)
        elif station == "Chillout Jazz":
            components.html('<iframe width="100%" height="150" src="https://www.youtube-nocookie.com/embed/Dx5qFachd3A?autoplay=1&rel=0&modestbranding=1" frameborder="0" allowfullscreen referrerpolicy="no-referrer"></iframe>', height=160)

    st.markdown("---")
    st.markdown('<p style="text-align:center;color:#D4AF37;font-size:11px;font-weight:bold;letter-spacing:2px;">🏆 FEATURED PARTNERS</p>', unsafe_allow_html=True)

    if os.path.exists("static/exness_logo.png"): st.image("static/exness_logo.png", use_container_width=True)
    if os.path.exists("static/exness.mp4"):      st.video("static/exness.mp4", start_time=0)
    st.markdown('<a href="https://one.exnessonelink.com/a/9wwklqzfxb" target="_blank"><button style="width:100%;background-color:#D4AF37;color:#000;border:none;padding:12px;border-radius:5px;font-weight:bold;cursor:pointer;margin-top:6px;font-size:13px;">🚀 TRADE WITH 0 SPREADS ➤</button></a>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if os.path.exists("static/goat_logo.png"): st.image("static/goat_logo.png", use_container_width=True)
    if os.path.exists("static/goat.mp4"):      st.video("static/goat.mp4", start_time=0)
    st.markdown('<a href="https://checkout.goatfundedtrader.com/aff/Sherwet/" target="_blank"><button style="width:100%;background-color:#00E676;color:#000;border:none;padding:12px;border-radius:5px;font-weight:bold;cursor:pointer;margin-top:6px;font-size:13px;">🐐 GET FUNDED TODAY ➤</button></a>', unsafe_allow_html=True)

    st.divider()
    focus_ticker = st.selectbox("ACTIVE CHART ASSET:", list(TICKER_MAP.keys()), index=0)
    if st.button("GET YOUR TRADING VIEW ADVANCE CHART HERE", use_container_width=True):
        show_popup_chart(focus_ticker)


# ================= SESSION INFO — called once at top level =================
in_kz, session_name = get_session_info()
now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")

# ================= 4. TABS =================
tab_dash, tab_cot, tab_sent, tab_ind, tab_fx, tab_news, tab_cal, tab_chat = st.tabs([
    "  📊 DASHBOARD  ", "  📊 COT DATA  ", "  📈 SENTIMENT  ",
    "  🏙️ INDICES  ", "  💱 CURRENCY MATRIX  ", "  📰 LIVE NEWS  ",
    "  📅 CALENDAR  ", "  💬 COMMUNITY  "
])


# ================= TAB 1: DASHBOARD =================
with tab_dash:
    st.title("📊 ALPHAEDGE COMMAND CENTRE")

    if in_kz:
        st.markdown(f'<div style="background:#0a1a0a;border:1px solid #00ff88;border-radius:6px;padding:10px 16px;margin-bottom:12px;"><span style="color:#00ff88;font-weight:bold;font-size:13px;">🟢 ACTIVE KILL ZONE</span><span class="kill-zone-badge">{session_name}</span><span style="float:right;color:#888;font-size:12px;">{now_utc}</span></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="background:#1a0a0a;border:1px solid #ff4b4b;border-radius:6px;padding:10px 16px;margin-bottom:12px;"><span style="color:#ff4b4b;font-weight:bold;font-size:13px;">🔴 OFF SESSION</span><span class="dead-zone-badge">{session_name}</span><span style="float:right;color:#888;font-size:12px;">{now_utc}</span></div>', unsafe_allow_html=True)

    st.write("⏳ *Analyzing Live Market Structure...*")
    data = get_dashboard_data()

    errors = st.session_state.get("data_errors", [])
    if errors:
        with st.expander(f"⚠️ {len(errors)} asset(s) failed to load", expanded=False):
            for e in errors: st.caption(e)
        st.session_state["data_errors"] = []

    rows_html = ""
    if data:
        for row in data:
            css = "bullish" if row['Bias'] == "BULLISH" else "bearish"
            rows_html += f'<tr><td><b>{row["Symbol"]}</b></td><td class="{css}">{row["Bias"]}</td><td class="{css}">{row["Score"]:+}</td><td>{row["Trend"]}</td><td>{row["Tech"]}</td><td style="color:#D4AF37;font-weight:bold;">{row["Price"]:,.4f}</td><td><span class="live-tag">⚡ LIVE</span></td></tr>'
    else:
        rows_html = "<tr><td colspan='7'>Loading Data...</td></tr>"

    st.markdown(f'<table class="heatmap-table"><thead><tr><th>SYMBOL</th><th>BIAS</th><th>SCORE</th><th>TREND</th><th>TECH</th><th>PRICE</th><th>SOURCE</th></tr></thead><tbody>{rows_html}</tbody></table>', unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("""
    <div style="background:linear-gradient(90deg,#0a0a0a,#111);border:1px solid #D4AF37;border-left:4px solid #D4AF37;border-radius:6px;padding:14px 18px;margin-bottom:10px;">
        <h3 style="margin:0;color:#D4AF37;font-size:18px;letter-spacing:2px;">🤖 AI EMA SCALPER SIGNALS</h3>
        <p style="margin:6px 0 0 0;color:#aaa;font-size:12px;">Veteran-grade 6-layer confluence system • Kill zone filter • Daily bias • 4H structure • Pullback entry • ATR targets</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background-color:#0d1117;border:1px solid #FF6B35;border-radius:6px;padding:12px 16px;margin-bottom:14px;">
        <p style="margin:0;color:#FF6B35;font-size:11px;font-weight:bold;letter-spacing:1px;">⚠️ RISK DISCLAIMER — NOT FINANCIAL ADVICE</p>
        <p style="margin:6px 0 0 0;color:#888;font-size:11px;line-height:1.6;">
            Signals are generated algorithmically for <b style="color:#ccc;">educational and informational purposes only</b>.
            They do not constitute financial advice or investment recommendations.
            Trading leveraged products carries a <b style="color:#ccc;">high level of risk</b> — you could lose more than your deposit.
            Past performance is not indicative of future results. Always consult a qualified financial advisor.
        </p>
        <p style="margin:8px 0 0 0;color:#D4AF37;font-size:11px;">📌 <b>Signals apply to the asset selected in the sidebar dropdown only.</b> Change <b>ACTIVE CHART ASSET</b> to switch instruments.</p>
    </div>
    """, unsafe_allow_html=True)

    y_sym = TICKER_MAP.get(focus_ticker, "EURUSD=X")
    sig, ent, tp, sl, reason = get_scalp_signal(y_sym)

    c1, c2, c3 = st.columns(3)
    c1.metric("📐 EMA SIGNAL", sig)
    st.caption(f"📌 Analysing: **{focus_ticker}** — change asset in the sidebar dropdown to update signals")

    if sig != "⚪ WAITING":
        c2.metric("⚡ LIVE ENTRY", f"{ent:.4f}")
        c3.metric("🎯 TARGETS",    f"TP: {tp:.4f} | SL: {sl:.4f}")
        box_class    = "reason-box" if "BUY" in sig else "reason-box-sell"
        reason_lines = reason.replace("\n", "<br>")
        st.markdown(f'<div class="{box_class}"><p style="margin:0 0 6px 0;font-weight:bold;color:#ccc;font-size:12px;">📋 WHY THIS TRADE WAS TAKEN:</p><p style="margin:0;">{reason_lines}</p></div>', unsafe_allow_html=True)
    else:
        c2.metric("⚡ LIVE ENTRY", "Searching...")
        c3.metric("🎯 TARGETS",    "Awaiting Confluence")
        if reason:
            reason_lines = reason.replace("\n", "<br>")
            st.markdown(f'<div style="background:#0a0a0f;border:1px solid #333;border-left:3px solid #888;border-radius:4px;padding:10px 14px;margin-top:10px;font-size:12px;color:#666;"><p style="margin:0 0 4px 0;color:#888;font-weight:bold;">⏳ WAITING — CONDITIONS NOT YET MET:</p><p style="margin:0;">{reason_lines}</p></div>', unsafe_allow_html=True)

    tv_symbol = TV_MAP.get(focus_ticker, "FX:EURUSD")
    components.html(f"""<div id="tv_chart_main" style="height:600px;"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize":true,"symbol":"{tv_symbol}","interval":"H1","theme":"dark","style":"1","locale":"en","toolbar_bg":"#f1f3f6","enable_publishing":false,"hide_side_toolbar":false,"allow_symbol_change":true,"container_id":"tv_chart_main"}});</script>""", height=610)


# ================= TAB 2: COT DATA =================
with tab_cot:
    st.title("📊 INSTITUTIONAL POSITIONING")
    col_ctrl, _ = st.columns([1, 2])
    with col_ctrl:
        if st.button("🔄 REFRESH DATA"):
            try:
                import cot_fetcher
                if cot_fetcher.update_cot_data():
                    st.success("Updated!"); time.sleep(1); st.rerun()
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
            st.markdown(f'<table class="heatmap-table" style="width:100%;text-align:center;"><thead><tr style="background:#111;color:#D4AF37;"><th>Symbol</th><th>Longs</th><th>Shorts</th><th>Δ Long</th><th>Δ Short</th><th>Long %</th><th>Short %</th><th>Net %</th><th>Net Pos</th><th>OI</th><th>Δ OI</th></tr></thead><tbody>{table_rows}</tbody></table>', unsafe_allow_html=True)
        except (json.JSONDecodeError, KeyError) as e:
            st.error(f"⚠️ Failed to parse COT data: {e}. Try refreshing.")
    else:
        st.info("ℹ️ No data found. Click Refresh.")


# ================= TAB 3: SENTIMENT =================
with tab_sent:
    st.title("📈 TECHNICAL SENTIMENT")
    gauge_asset = st.selectbox("Select Asset to Analyze:", list(TICKER_MAP.keys()), key="gauge_sel")
    tv_gauge    = TV_MAP.get(gauge_asset, "FX:EURUSD")
    st.write(f"Displaying Sentiment for: **{gauge_asset}**")
    c1, c2 = st.columns(2)
    with c1: st.caption("1 Hour Interval"); components.html(f'<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>{{"interval":"1h","width":"100%","isTransparent":true,"height":450,"symbol":"{tv_gauge}","showIntervalTabs":false,"displayMode":"single","locale":"en","colorTheme":"dark"}}</script></div>', height=460)
    with c2: st.caption("4 Hour Interval"); components.html(f'<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>{{"interval":"4h","width":"100%","isTransparent":true,"height":450,"symbol":"{tv_gauge}","showIntervalTabs":false,"displayMode":"single","locale":"en","colorTheme":"dark"}}</script></div>', height=460)


# ================= TAB 4: INDICES =================
with tab_ind:
    st.title("🏙️ GLOBAL INDICES HEATMAP")
    components.html('<iframe src="https://www.tradingview-widget.com/embed-widget/stock-heatmap/?theme=dark&market=america" height="800" width="100%"></iframe>', height=820)


# ================= TAB 5: FOREX =================
with tab_fx:
    st.title("💱 GLOBAL CURRENCY MATRIX")
    components.html('<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-forex-heat-map.js" async>{"width":"100%","height":800,"currencies":["EUR","USD","JPY","GBP","CHF","AUD","CAD","NZD","ZAR"],"isTransparent":false,"colorTheme":"dark","locale":"en"}</script></div>', height=820)


# ================= TAB 6: NEWS =================
with tab_news:
    st.title("📰 LIVE MARKET NEWS")
    components.html('<iframe src="https://www.tradingview-widget.com/embed-widget/timeline/?feedMode=all_symbols&theme=dark" height="800" width="100%"></iframe>', height=820)


# ================= TAB 7: CALENDAR =================
with tab_cal:
    st.title("📅 ECONOMIC CALENDAR")
    components.html('<iframe src="https://www.tradingview-widget.com/embed-widget/events/?theme=dark&importance=high" height="800" width="100%"></iframe>', height=820)


# ================= TAB 9: COMMUNITY CHAT =================
with tab_chat:
    st.title("💬 TRADERS LOUNGE")
    st.write("Share setups, ideas, and market news with the AlphaEdge community.")
    col_info, col_btn = st.columns([3, 1])
    with col_info:
        st.info("🔄 **Note:** Click refresh to see the latest messages from other traders.")
    with col_btn:
        if st.button("🔄 REFRESH CHAT", use_container_width=True):
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
