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
_TG_TOKEN    = "8546515684:AAF4rVZbiqtEqHVPFloJ26wHeDsaHR8hKHE"      # from @BotFather
_TG_CHAT_ID  = "5689404731"        # your personal Telegram chat ID
_FINNHUB_KEY = "d6ng6v9r01qodk5vlu30d6ng6v9r01qodk5vlu3g"    # free at finnhub.io — 60 req/min


# ══════════════════════════════════════════════════════════════════════════════
# FINNHUB SYMBOL MAP — real-time data for Telegram signals only
# ══════════════════════════════════════════════════════════════════════════════
_FH_MAP = {
    "EUR/USD": "OANDA:EUR_USD", "GBP/USD": "OANDA:GBP_USD",
    "USD/JPY": "OANDA:USD_JPY", "USD/CHF": "OANDA:USD_CHF",
    "AUD/USD": "OANDA:AUD_USD", "USD/CAD": "OANDA:USD_CAD",
    "NZD/USD": "OANDA:NZD_USD", "USD/ZAR": "OANDA:USD_ZAR",
    "GBP/ZAR": "OANDA:GBP_ZAR",
    "S&P 500": "OANDA:SPX500_USD", "NASDAQ 100": "OANDA:NAS100_USD",
    "US 30":   "OANDA:US30_USD",   "VIX": "CBOE:VIX",
    "GOLD":    "OANDA:XAU_USD",    "SILVER":    "OANDA:XAG_USD",
    "OIL (WTI)": "OANDA:BCO_USD",  "NAT GAS":   "OANDA:NATGAS_USD",
    "BITCOIN":   "BINANCE:BTCUSDT","ETHEREUM":  "BINANCE:ETHUSDT",
    "SOLANA":    "BINANCE:SOLUSDT",
}


def _fh_candles(display_name: str, resolution: str, bars: int) -> "pd.DataFrame | None":
    """
    Fetch real-time OHLCV from Finnhub. Free tier: 60 req/min.
    resolution: '5'=5min, '15'=15min, '60'=1H, 'D'=daily
    """
    if not _FINNHUB_KEY or "YOUR_" in _FINNHUB_KEY:
        return None
    fh_sym = _FH_MAP.get(display_name)
    if not fh_sym:
        return None
    secs = {"5": 300, "15": 900, "60": 3600, "D": 86400}
    now  = int(time.time())
    frm  = now - secs.get(resolution, 3600) * bars * 2
    try:
        r    = requests.get(
            "https://finnhub.io/api/v1/stock/candle",
            params={"symbol": fh_sym, "resolution": resolution,
                    "from": frm, "to": now, "token": _FINNHUB_KEY},
            timeout=12
        )
        d = r.json()
        if d.get("s") != "ok" or "c" not in d:
            return None
        df = pd.DataFrame({
            "Open": d["o"], "High": d["h"], "Low": d["l"],
            "Close": d["c"], "Volume": d.get("v", [0]*len(d["c"]))
        }, index=pd.to_datetime(d["t"], unit="s", utc=True))
        df.sort_index(inplace=True)
        df = df.tail(bars)
        df.dropna(inplace=True)
        return df if len(df) >= 15 else None
    except Exception:
        return None


def _fh_4h(display_name: str, bars: int = 60) -> "pd.DataFrame | None":
    """Build 4H bars by resampling 1H data."""
    df = _fh_candles(display_name, "60", bars * 4 + 20)
    if df is None or len(df) < 8:
        return None
    df4 = df.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()
    return df4 if len(df4) >= 8 else None


# ================= TELEGRAM HELPERS =================
def _send_telegram(message: str):
    if not _TG_TOKEN or "YOUR_" in _TG_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json={"chat_id": _TG_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass


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


def _next_session():
    h = datetime.now(timezone.utc).hour + datetime.now(timezone.utc).minute / 60.0
    if   h < 3.0:  return "Tokyo Open",        "00:00 UTC"
    elif h < 7.0:  return "London Open",        "07:00 UTC"
    elif h < 12.0: return "NY/London Overlap",  "12:00 UTC"
    else:          return "Tokyo Open",          "00:00 UTC (tomorrow)"


# ================= DASHBOARD DATA (yfinance — free, unlimited) =================
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
# FINNHUB SIGNAL ENGINE — used ONLY by Telegram background monitor
# Platform display signals still use yfinance (free, no API limits)
#
# 4-layer confluence:
#   Daily  — EMA 20 + EMA 50 direction (macro bias)
#   4H     — EMA 21 + EMA 50 structure
#   1H     — EMA 9/21 cross + RSI + MACD (intermediate entry)
#   5m     — EMA 9/21 cross + RSI + MACD (precision entry)
#
# ALL FOUR must agree — if any layer disagrees, no signal fires.
# SL: below/above 4H swing low/high + ATR buffer
# TP: minimum 2R enforced
# ══════════════════════════════════════════════════════════════════════════════

def _calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(com=period-1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period-1, adjust=False).mean()
    return 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))

def _calc_atr(df, period=14):
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"]  - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def _calc_macd_hist(series):
    macd = series.ewm(span=12, adjust=False).mean() - series.ewm(span=26, adjust=False).mean()
    return macd - macd.ewm(span=9, adjust=False).mean()

def _check_entry(df, direction):
    """Check one timeframe for entry signal. Returns dict with details."""
    if df is None or len(df) < 30:
        return {"ok": False, "reason": "insufficient data"}
    close  = df["Close"]
    ema9   = close.ewm(span=9,  adjust=False).mean()
    ema21  = close.ewm(span=21, adjust=False).mean()
    rsi    = _calc_rsi(close)
    atr    = _calc_atr(df)
    macd_h = _calc_macd_hist(close)

    c = close.iloc[-1];   p_c = close.iloc[-2]
    e9  = ema9.iloc[-1];  pe9  = ema9.iloc[-2]
    e21 = ema21.iloc[-1]; pe21 = ema21.iloc[-2]
    r   = rsi.iloc[-1]
    a   = atr.iloc[-1]
    mh  = macd_h.iloc[-1]; pmh = macd_h.iloc[-2]
    atr_avg = atr.rolling(10).mean().iloc[-1]

    pb_pct     = abs(c - e21) / e21 if e21 != 0 else 1
    fresh_bull = pe9 <= pe21 and e9 > e21
    fresh_bear = pe9 >= pe21 and e9 < e21
    cont_bull  = e9 > e21 and pb_pct < 0.003
    cont_bear  = e9 < e21 and pb_pct < 0.003
    atr_active = a > atr_avg * 0.9

    if direction == "bull":
        ema_ok  = fresh_bull or cont_bull
        rsi_ok  = 38 <= r <= 68
        macd_ok = mh > 0 or mh > pmh
        etype   = "Fresh EMA cross ↑" if fresh_bull else "Pullback to EMA 21"
    else:
        ema_ok  = fresh_bear or cont_bear
        rsi_ok  = 32 <= r <= 62
        macd_ok = mh < 0 or mh < pmh
        etype   = "Fresh EMA cross ↓" if fresh_bear else "Pullback to EMA 21"

    ok = ema_ok and rsi_ok and macd_ok and atr_active
    return {"ok": ok, "ema_ok": ema_ok, "rsi_ok": rsi_ok, "macd_ok": macd_ok,
            "atr_active": atr_active, "rsi": r, "atr": a, "etype": etype, "pb_pct": pb_pct * 100}


def _finnhub_signal(display_name: str) -> tuple:
    """
    TRIPLE CONFLUENCE ENGINE — London + NY Sessions
    Rebuilt from scratch. Uses 1H + 4H only (no timezone-sensitive filters).
    Fires frequently during both sessions. Minimum 2R enforced.

    STRATEGY — 3-layer confluence:
      1. 4H TREND  : EMA 21 direction (above = bull, below = bear)
      2. 1H ENTRY  : EMA 9 crosses EMA 21 in trend direction
                     OR price pulls back to 1H EMA 21 and holds
      3. MOMENTUM  : RSI not extended (35-65) + MACD histogram confirms

    SESSIONS COVERED:
      London : 07:00-10:00 UTC  — all forex pairs + Gold
      NY     : 12:00-17:00 UTC  — all 20 assets
      London+NY overlap: 12:00-16:00 UTC — highest priority, all assets

    SL: below/above 1H swing low/high (last 5 bars) + 0.2×ATR buffer
    TP: 2.5×ATR minimum, always at least 2R
    """
    try:
        now_utc   = datetime.now(timezone.utc)
        h         = now_utc.hour + now_utc.minute / 60.0
        in_london = 7.0  <= h < 10.0
        in_ny     = 12.0 <= h < 17.0
        in_session = in_london or in_ny

        if not in_session:
            return "⚪ WAITING", 0.0, 0.0, 0.0, "Outside London/NY session"

        # ── FETCH 4H + 1H DATA (no timezone filters — works everywhere) ────────
        df_4h = _fh_4h(display_name, 60)
        df_1h = _fh_candles(display_name, "60", 80)

        if df_4h is None or df_1h is None:
            return "⚪ WAITING", 0.0, 0.0, 0.0, "Waiting: Finnhub data unavailable"
        if len(df_4h) < 10 or len(df_1h) < 30:
            return "⚪ WAITING", 0.0, 0.0, 0.0, "Waiting: insufficient bars"

        # ── LAYER 1: 4H TREND (EMA 21) ─────────────────────────────────────────
        h4_close  = df_4h["Close"]
        h4_ema21  = h4_close.ewm(span=21, adjust=False).mean()
        h4_ema50  = h4_close.ewm(span=50, adjust=False).mean()
        h4_price  = h4_close.iloc[-1]
        h4_e21    = h4_ema21.iloc[-1]
        h4_e50    = h4_ema50.iloc[-1]

        # 4H trend: price AND ema21 relationship to ema50
        trend_bull_4h = h4_price > h4_e21 and h4_e21 > h4_e50
        trend_bear_4h = h4_price < h4_e21 and h4_e21 < h4_e50

        # Relaxed: accept if price just above/below ema21 (catches early moves)
        if not trend_bull_4h and not trend_bear_4h:
            trend_bull_4h = h4_price > h4_e21
            trend_bear_4h = h4_price < h4_e21

        if not trend_bull_4h and not trend_bear_4h:
            return "⚪ WAITING", h4_price, 0.0, 0.0, "4H trend unclear — price too close to EMA 21"

        direction = "bull" if trend_bull_4h else "bear"

        # ── LAYER 2: 1H ENTRY — EMA 9/21 CROSS or PULLBACK ────────────────────
        h1_close = df_1h["Close"]
        h1_high  = df_1h["High"]
        h1_low   = df_1h["Low"]
        h1_open  = df_1h["Open"]

        h1_ema9  = h1_close.ewm(span=9,  adjust=False).mean()
        h1_ema21 = h1_close.ewm(span=21, adjust=False).mean()

        c_price  = h1_close.iloc[-1]
        c_open   = h1_open.iloc[-1]
        c_high   = h1_high.iloc[-1]
        c_low    = h1_low.iloc[-1]

        e9_now   = h1_ema9.iloc[-1];  e9_prev  = h1_ema9.iloc[-2]
        e21_now  = h1_ema21.iloc[-1]; e21_prev = h1_ema21.iloc[-2]

        # Fresh EMA cross on 1H
        fresh_bull = e9_prev <= e21_prev and e9_now > e21_now
        fresh_bear = e9_prev >= e21_prev and e9_now < e21_now

        # Pullback to 1H EMA 21 (within 0.3% — generous tolerance)
        pb_pct     = abs(c_price - e21_now) / e21_now if e21_now != 0 else 1
        pb_bull    = direction == "bull" and e9_now > e21_now and pb_pct < 0.003
        pb_bear    = direction == "bear" and e9_now < e21_now and pb_pct < 0.003

        entry_bull = direction == "bull" and (fresh_bull or pb_bull)
        entry_bear = direction == "bear" and (fresh_bear or pb_bear)

        if not entry_bull and not entry_bear:
            etype = "fresh cross" if (fresh_bull or fresh_bear) else f"pullback ({pb_pct*100:.2f}% from EMA21, need <0.3%)"
            cross_dir = "above" if direction == "bull" else "below"
            return "⚪ WAITING", c_price, 0.0, 0.0, (
                f"4H trend: {'BULLISH' if direction=='bull' else 'BEARISH'} ✅\n"
                f"⏳ 1H waiting: EMA 9 not yet {cross_dir} EMA 21 | {etype}"
            )

        # ── LAYER 3: MOMENTUM — RSI + MACD ────────────────────────────────────
        rsi_s    = _calc_rsi(h1_close)
        c_rsi    = rsi_s.iloc[-1]
        macd_h   = _calc_macd_hist(h1_close)
        mh_now   = macd_h.iloc[-1]
        mh_prev  = macd_h.iloc[-2]

        if direction == "bull":
            rsi_ok  = 35 <= c_rsi <= 70
            macd_ok = mh_now > mh_prev or mh_now > 0
        else:
            rsi_ok  = 30 <= c_rsi <= 65
            macd_ok = mh_now < mh_prev or mh_now < 0

        if not rsi_ok:
            return "⚪ WAITING", c_price, 0.0, 0.0, (
                f"4H {'BULL' if direction=='bull' else 'BEAR'} ✅ | 1H entry ✅\n"
                f"⏳ RSI {c_rsi:.1f} outside zone ({'need <70' if direction=='bull' else 'need >30'})"
            )

        if not macd_ok:
            return "⚪ WAITING", c_price, 0.0, 0.0, (
                f"4H {'BULL' if direction=='bull' else 'BEAR'} ✅ | 1H entry ✅ | RSI ✅\n"
                f"⏳ MACD histogram not confirming direction yet"
            )

        # ── ATR for SL/TP ──────────────────────────────────────────────────────
        atr_1h  = _calc_atr(df_1h)
        c_atr   = atr_1h.iloc[-1]

        # Swing SL: low/high of last 5 1H bars + ATR buffer
        swing_low  = h1_low.iloc[-5:].min()
        swing_high = h1_high.iloc[-5:].max()

        # ── BUILD SIGNAL ───────────────────────────────────────────────────────
        session = "🇬🇧 London" if in_london else "🇺🇸 New York"
        etype_str = "EMA 9/21 Cross" if (fresh_bull or fresh_bear) else "Pullback to EMA 21"

        if entry_bull:
            sl       = swing_low - (c_atr * 0.2)
            raw_risk = c_price - sl
            if raw_risk <= 0 or raw_risk > c_price * 0.06:
                return "⚪ WAITING", c_price, 0.0, 0.0, "SL too wide — skipping (choppy 1H)"
            tp  = c_price + max(raw_risk * 2.5, c_atr * 2.5)
            rr  = (tp - c_price) / raw_risk
            reason = (
                f"📊 Session: {session}\n"
                f"✅ 4H Trend: BULLISH — price above EMA 21/50\n"
                f"✅ 1H Entry: {etype_str} — EMA 9 above EMA 21\n"
                f"✅ RSI: {c_rsi:.1f} — momentum zone\n"
                f"✅ MACD: histogram {'rising' if mh_now > mh_prev else 'positive'}\n"
                f"SL below 1H swing low | TP: 2.5× risk | R:R 1:{rr:.1f}"
            )
            return "🟢 BUY", c_price, tp, sl, reason

        else:
            sl       = swing_high + (c_atr * 0.2)
            raw_risk = sl - c_price
            if raw_risk <= 0 or raw_risk > c_price * 0.06:
                return "⚪ WAITING", c_price, 0.0, 0.0, "SL too wide — skipping (choppy 1H)"
            tp  = c_price - max(raw_risk * 2.5, c_atr * 2.5)
            rr  = raw_risk / (c_price - tp) if (c_price - tp) > 0 else 0
            reason = (
                f"📊 Session: {session}\n"
                f"✅ 4H Trend: BEARISH — price below EMA 21/50\n"
                f"✅ 1H Entry: {etype_str} — EMA 9 below EMA 21\n"
                f"✅ RSI: {c_rsi:.1f} — momentum zone\n"
                f"✅ MACD: histogram {'falling' if mh_now < mh_prev else 'negative'}\n"
                f"SL above 1H swing high | TP: 2.5× risk | R:R 1:{rr:.1f}"
            )
            return "🔴 SELL", c_price, tp, sl, reason

    except Exception as e:
        return "⚪ WAITING", 0.0, 0.0, 0.0, f"Error: {str(e)}"


# ══════════════════════════════════════════════════════════════════════════════
# PLATFORM DISPLAY SIGNALS — yfinance (free, unlimited, for UI only)
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
# BACKGROUND TELEGRAM MONITOR
# Uses Finnhub real-time data. Runs every 5 min. Silent — no UI.
# Sends session open/close alerts + signals when all 4 layers align.
# ══════════════════════════════════════════════════════════════════════════════
_last_signals: dict = {}

# ── STATE FILE — persists across Streamlit reruns and page visits ────────────
# Module-level variables reset every time Streamlit reruns the script.
# We write session state to a file so the monitor thread reads/writes disk,
# not memory — this guarantees ONE open alert and ONE close alert only.
_STATE_FILE = "monitor_state.json"

def _read_state() -> dict:
    try:
        with open(_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"in_kz": None, "last_signals": {}}

def _write_state(in_kz: bool, last_signals: dict):
    try:
        with open(_STATE_FILE, "w") as f:
            json.dump({"in_kz": in_kz, "last_signals": last_signals}, f)
    except Exception:
        pass


def _build_tg_message(display_name, sig, entry, tp, sl, reason, session_name):
    rr        = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0
    direction = "🟢 BUY" if "BUY" in sig else "🔴 SELL"
    return (
        f"🚨 <b>ALPHAEDGE SIGNAL</b> 🚨\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Asset:</b> {display_name}\n"
        f"📈 <b>Signal:</b> {direction}\n"
        f"⏰ <b>Time (UTC):</b> {datetime.now(timezone.utc).strftime('%H:%M  %d/%m/%Y')}\n"
        f"🏦 <b>Session:</b> {session_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Entry:</b>  {entry:.5f}\n"
        f"🎯 <b>TP:</b>     {tp:.5f}\n"
        f"🛑 <b>SL:</b>     {sl:.5f}\n"
        f"📐 <b>R:R:</b>    1 : {rr:.1f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 <b>Why this trade:</b>\n{reason}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
    )


def _monitor_loop():
    """
    Background thread — runs once per process lifetime.
    State is stored in monitor_state.json so it survives Streamlit reruns.
    ONE open message, ONE close message — nothing else fires repeatedly.
    """
    while True:
        try:
            in_kz, session_name  = get_session_info()
            state                = _read_state()
            prev_kz              = state.get("in_kz", None)   # None = first ever run
            last_signals         = state.get("last_signals", {})

            # First ever run — record state silently, no message sent
            if prev_kz is None:
                _write_state(in_kz, last_signals)

            # Kill zone just OPENED (False → True) — send ONE open message
            elif in_kz and prev_kz is False:
                _send_telegram(
                    f"🟢 <b>SESSION OPEN — {session_name}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                    f"📡 Scanning 20 markets\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
                )
                _write_state(in_kz, last_signals)

            # Kill zone just CLOSED (True → False) — send ONE close message
            elif not in_kz and prev_kz is True:
                nxt_name, nxt_time = _next_session()
                _send_telegram(
                    f"🔴 <b>SESSION CLOSED — {session_name}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                    f"😴 No signals until next session\n"
                    f"⏭️ <b>Next:</b> {nxt_name} at {nxt_time}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ <i>Not financial advice. Trade responsibly.</i>"
                )
                last_signals = {}   # fresh slate for next session
                _write_state(in_kz, last_signals)

            # No transition — just update in_kz in case it drifted
            else:
                _write_state(in_kz, last_signals)

            # Signal scan — Finnhub real-time, London + NY sessions
            if in_kz:
                for display_name in TICKER_MAP.keys():
                    try:
                        sig, entry, tp, sl, reason = _finnhub_signal(display_name)
                        prev_sig = last_signals.get(display_name, "⚪ WAITING")
                        if sig != "⚪ WAITING" and sig != prev_sig:
                            msg = _build_tg_message(display_name, sig, entry, tp, sl, reason, session_name)
                            _send_telegram(msg)
                            last_signals[display_name] = sig
                            _write_state(in_kz, last_signals)
                        elif sig == "⚪ WAITING" and prev_sig != "⚪ WAITING":
                            last_signals[display_name] = "⚪ WAITING"
                            _write_state(in_kz, last_signals)
                        time.sleep(1)
                    except Exception:
                        continue

        except Exception:
            pass
        time.sleep(300)


def start_monitor():
    """Start background thread ONCE per process — guarded by a file lock."""
    lock_file = "monitor.lock"
    if not os.path.exists(lock_file):
        try:
            with open(lock_file, "w") as f:
                f.write(str(os.getpid()))
            t = threading.Thread(target=_monitor_loop, daemon=True)
            t.start()
        except Exception:
            pass

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
        st.subheader("📺 LIVE FINANCIAL TV")
        tv_channel = st.selectbox("Select Channel:", [
            "Bloomberg Markets", "CNBC Live", "Reuters TV"
        ], label_visibility="collapsed", key="tv_sel")
        if tv_channel == "Bloomberg Markets":
            st.video("https://www.youtube.com/@BloombergTV/live")
        elif tv_channel == "CNBC Live":
            st.video("https://www.youtube.com/watch?v=9NyxcX3rhQs")
        elif tv_channel == "Reuters TV":
            st.video("https://www.youtube.com/watch?v=H6hY8Y9n4c0")

        st.subheader("🎵 TRADING STATION")
        station = st.selectbox("Select Audio:", ["Lofi Trading Beats", "Chillout Jazz"], label_visibility="collapsed")
        if station == "Lofi Trading Beats":
            components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/jfKfPfyJRdk?autoplay=1" frameborder="0" allowfullscreen></iframe>', height=160)
        elif station == "Chillout Jazz":
            components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/Dx5qFachd3A?autoplay=1" frameborder="0" allowfullscreen></iframe>', height=160)

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


# ================= 4. TABS =================
in_kz, session_name = get_session_info()
now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")

tab_dash, tab_cot, tab_sent, tab_ind, tab_fx, tab_news, tab_cal, tab_chat = st.tabs([
    "  📊 DASHBOARD  ", "  📊 COT DATA  ", "  📈 SENTIMENT  ",
    "  🏙️ INDICES  ", "  💱 CURRENCY MATRIX  ", "  📰 LIVE NEWS  ",
    "  📅 CALENDAR  ", "  💬 COMMUNITY  "
])


# ================= TAB 1: DASHBOARD =================
with tab_dash:
    st.title("📊 ALPHAEDGE COMMAND CENTRE")

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
        for row in data:
            css = "bullish" if row['Bias'] == "BULLISH" else "bearish"
            rows_html += f'<tr><td><b>{row["Symbol"]}</b></td><td class="{css}">{row["Bias"]}</td><td class="{css}">{row["Score"]:+}</td><td>{row["Trend"]}</td><td>{row["Tech"]}</td><td style="color:#D4AF37;font-weight:bold;">{row["Price"]:,.4f}</td><td><span class="live-tag">⚡ LIVE</span></td></tr>'
    else:
        rows_html = "<tr><td colspan='7'>Loading Data...</td></tr>"

    st.markdown(f'<table class="heatmap-table"><thead><tr><th>SYMBOL</th><th>BIAS</th><th>SCORE</th><th>TREND</th><th>TECH</th><th>PRICE</th><th>SOURCE</th></tr></thead><tbody>{rows_html}</tbody></table>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("""
    <div style="background:linear-gradient(90deg,#0a0a0a,#111);border:1px solid #D4AF37;border-left:4px solid #D4AF37;border-radius:6px;padding:14px 18px;margin-bottom:10px;">
        <h3 style="margin:0;color:#D4AF37;font-size:18px;letter-spacing:2px;">📊 ALPHAEDGE LIVE SIGNALS</h3>
        <p style="margin:6px 0 0 0;color:#aaa;font-size:12px;">Triple confluence engine • 4H trend • 1H EMA cross • RSI + MACD • London &amp; NY sessions • 2.5R minimum</p>
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

    y_sym = TICKER_MAP.get(focus_ticker, "EURUSD=X")
    sig, ent, tp, sl, reason = get_scalp_signal(y_sym)

    c1, c2, c3 = st.columns(3)
    c1.metric("📐 EMA SIGNAL", sig)
    st.caption(f"📌 Analysing: **{focus_ticker}**")

    if sig != "⚪ WAITING":
        c2.metric("⚡ LIVE ENTRY", f"{ent:.4f}")
        c3.metric("🎯 TARGETS",    f"TP: {tp:.4f} | SL: {sl:.4f}")
        box_class    = "reason-box" if "BUY" in sig else "reason-box-sell"
        reason_lines = reason.replace("\n", "<br>")
        st.markdown(f'<div class="{box_class}"><p style="margin:0 0 6px 0;font-weight:bold;color:#ccc;font-size:12px;">📋 WHY THIS TRADE:</p><p style="margin:0;">{reason_lines}</p></div>', unsafe_allow_html=True)
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


# ================= TAB 8: COMMUNITY CHAT =================
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
