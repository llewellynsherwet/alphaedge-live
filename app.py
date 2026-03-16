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
# CREDENTIALS — Telegram only (no other API keys needed)
# Set these as Environment Variables on Render dashboard
# OR replace the placeholder strings below with your actual values
# ══════════════════════════════════════════════════════════════════════════════
_TG_TOKEN   = os.environ.get("TG_TOKEN",   "8546515684:AAF4rVZbiqtEqHVPFloJ26wHeDsaHR8hKHE")   # from @BotFather
_TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "5689404731")     # your Telegram chat ID

# NOTE: No Finnhub key needed. No other API keys needed.
# Signal engine uses yfinance — free, no key, works on Render.


def _send_telegram(message: str):
    """Send a message to the Telegram bot. Silently skips if credentials not set."""
    if not _TG_TOKEN or "YOUR_" in _TG_TOKEN:
        return
    if not _TG_CHAT_ID or "YOUR_" in _TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json={"chat_id": _TG_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass


def get_session_info():
    """Returns (in_session, session_name) based on current UTC time."""
    now = datetime.now(timezone.utc)
    h   = now.hour + now.minute / 60.0
    if   7.0  <= h < 10.0: return True,  "🇬🇧 LONDON OPEN"
    elif 10.0 <= h < 12.0: return True,  "🇬🇧🇺🇸 LONDON CONTINUATION"
    elif 12.0 <= h < 16.0: return True,  "🇺🇸 NY / LONDON OVERLAP"
    elif 16.0 <= h < 17.0: return True,  "🇺🇸 NEW YORK CLOSE"
    else:                   return False, "🔴 OFF-SESSION"


def _next_session():
    """Returns (name, time_str) of the next upcoming session."""
    now  = datetime.now(timezone.utc)
    h    = now.hour + now.minute / 60.0
    if h < 7.0:
        mins = int((7.0 - h) * 60)
        return "🇬🇧 London Open", f"{7 - (now.hour if now.hour > 7 else 0):02d}:00 UTC"
    elif h < 12.0:
        return "🇺🇸 NY / London Overlap", "12:00 UTC"
    else:
        return "🇬🇧 London Open (tomorrow)", "07:00 UTC"


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
                f"Symbol: {symbol} | Interval: {interval}\n"
                f"Reason: {reason}\n"
                f"<i>Check yfinance / network on Render</i>"
            )
        except Exception:
            pass


def _us30_open_strategy(ticker_symbol):
    try:
        now_utc    = datetime.now(timezone.utc)
        h          = now_utc.hour + now_utc.minute / 60.0
        in_preopen = 13.0 <= h < 14.5
        at_open    = 14.5 <= h < 15.5
        if not (in_preopen or at_open):
            return "WAIT", 0.0, 0.0, 0.0, "US30: waiting for pre-open window (13:00-15:30 UTC)"

        score = 0
        layers = []
        box_bias = stock_bias = dxy_bias = pattern_bias = smc_bias = "neutral"

        # L1: Pre-market box
        df_5m = _yf_candles(ticker_symbol, "5m", 100)
        box_high = box_low = 0.0
        if df_5m is not None and len(df_5m) >= 20:
            pm = df_5m.iloc[-20:-10]
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
            layers.append("L1 SKIP: 5M data unavailable")

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
        df_4h = _yf_candles(ticker_symbol, "4h", 20)
        if df_4h is not None and len(df_4h) >= 8:
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
                + "WAIT for 14:30 UTC open candle to close\n"
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
                rr = risk / (price - tp) if (price - tp) > 0 else 0
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
    try:
        df_4h = _yf_candles(ticker_symbol, "4h", 30)
        df_1h = _yf_candles(ticker_symbol, "1h", 50)
        if df_4h is None or df_1h is None:
            return "WAIT", 0.0, 0.0, 0.0, "SMC 4H: data unavailable"
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
        for i in range(len(df_4h) - 2, max(len(df_4h) - 8, 0), -1):
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
        price = h1c.iloc[-1]
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
            rr = risk / (price - tp) if (price - tp) > 0 else 0
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
    """
    ALPHAEDGE SIGNAL ENGINE
    US30  -> US30 Open Strategy (5 layers: pre-market box, DOW stocks, DXY, double top/bottom, 4H SMC)
    Other -> SMC 4H Strategy   (5 layers: structure, order block, 1H EMA, RSI, MACD)
    """
    try:
        now_utc    = datetime.now(timezone.utc)
        h          = now_utc.hour + now_utc.minute / 60.0
        if not (7.0 <= h < 17.0):
            return "WAIT", 0.0, 0.0, 0.0, "Outside session (07-17 UTC)"
        ticker_symbol = TICKER_MAP.get(display_name)
        if not ticker_symbol:
            return "WAIT", 0.0, 0.0, 0.0, "Unknown asset"
        if display_name == "US 30":
            return _us30_open_strategy(ticker_symbol)
        return _smc_4h_strategy(display_name, ticker_symbol)
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
            data = json.load(f)
            # Ensure scan_count key always exists
            data.setdefault("scan_count", 0)
            return data
    except Exception:
        return {"in_kz": None, "last_signals": {}, "scan_count": 0}

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
                signals_found = []
                for display_name in TICKER_MAP.keys():
                    try:
                        sig, entry, tp, sl, reason = _signal_engine(display_name)
                        prev_sig = last_signals.get(display_name, "⚪ WAITING")
                        if sig not in ("⚪ WAITING", "WAIT", "WAITING") and sig != prev_sig:
                            msg = _build_tg_message(display_name, sig, entry, tp, sl, reason, session_name)
                            _send_telegram(msg)
                            last_signals[display_name] = sig
                            signals_found.append(f"{display_name}: {sig}")
                            _write_state(in_kz, last_signals)
                        elif sig in ("⚪ WAITING","WAIT","WAITING") and prev_sig not in ("⚪ WAITING","WAIT","WAITING"):
                            last_signals[display_name] = "⚪ WAITING"
                            _write_state(in_kz, last_signals)
                        time.sleep(1)
                    except Exception:
                        continue
                # Send scan summary every 30 min (6 loops × 5 min) so you know bot is alive
                scan_count = state.get("scan_count", 0) + 1
                # Write scan_count separately — don't mix into last_signals
                try:
                    sc_data = {"in_kz": in_kz, "last_signals": last_signals, "scan_count": scan_count}
                    with open(_STATE_FILE, "w") as _f:
                        json.dump(sc_data, _f)
                except Exception:
                    pass
                if scan_count % 6 == 0:
                    status = "✅ " + ", ".join(signals_found) if signals_found else "⏳ No setups yet — watching"
                    _send_telegram(
                        f"🔍 <b>SCAN UPDATE</b> — {session_name}\n"
                        f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                        f"📊 Scanned 20 markets\n"
                        f"{status}\n"
                        f"<i>Next scan in 5 min</i>"
                    )

        except Exception:
            pass
        time.sleep(300)


# ── MONITOR SINGLETON — survives Streamlit reruns on Render ─────────────────
# threading.enumerate() checks if our named thread is already alive.
# This works across all Streamlit reruns because threads live at the OS level,
# not the Python module level. No file locks, no race conditions.

def start_monitor():
    # Check if monitor thread is already running by name
    for thread in threading.enumerate():
        if thread.name == "alphaedge_monitor":
            return  # Already running — do nothing
    # Fresh start — wipe stale state so old last_signals don't block new signals
    try:
        if os.path.exists(_STATE_FILE):
            os.remove(_STATE_FILE)
    except Exception:
        pass
    # Not running — start it
    t = threading.Thread(target=_monitor_loop, name="alphaedge_monitor", daemon=True)
    t.start()

start_monitor()

# ── STARTUP PING — fires once when Render starts the app ─────────────────────
# Sends one message to Telegram so you know the bot is live and credentials work
_STARTUP_FLAG = "startup_ping.flag"
if not os.path.exists(_STARTUP_FLAG):
    try:
        with open(_STARTUP_FLAG, "w") as _f:
            _f.write("1")
        _send_telegram(
            f"🚀 <b>ALPHAEDGE BOT ONLINE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
            f"✅ Credentials loaded\n"
            f"✅ Monitor thread started\n"
            f"✅ Scanning: London 07-17 UTC\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Bot will scan every 5 min during sessions</i>"
        )
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
            components.html('<iframe width="100%" height="200" src="https://www.youtube.com/embed/iEpJwprxDdk?autoplay=1&mute=0" frameborder="0" allow="autoplay; encrypted-media" allowfullscreen></iframe>', height=210)
        elif tv_channel == "CNBC Live":
            st.video("https://www.youtube.com/watch?v=9NyxcX3rhQs")
        elif tv_channel == "Reuters TV":
            st.video("https://www.youtube.com/watch?v=H6hY8Y9n4c0")

        st.subheader("🎵 TRADING STATION")
        station = st.selectbox("Select Audio:", [
            "Lofi Trading Beats", "Chillout Jazz", "Pop Radio", "Hip Hop Radio"
        ], label_visibility="collapsed")
        if station == "Lofi Trading Beats":
            components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/jfKfPfyJRdk?autoplay=1" frameborder="0" allowfullscreen></iframe>', height=160)
        elif station == "Chillout Jazz":
            components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/Dx5qFachd3A?autoplay=1" frameborder="0" allowfullscreen></iframe>', height=160)
        elif station == "Pop Radio":
            st.audio("https://listen.181fm.com/181-themix_128k.mp3")
        elif station == "Hip Hop Radio":
            st.audio("https://pureplay.cdnstream1.com/6045_128.mp3")

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
        for name, row in data.items():
            bias  = row.get("bias",  "—")
            price = row.get("price", 0)
            score = row.get("score", 0)
            trend = row.get("trend", "—")
            tech  = row.get("tech",  "—")
            css   = "bullish" if "BULL" in str(bias) else "bearish" if "BEAR" in str(bias) else ""
            try:
                price_str = f"{price:,.4f}" if price else "—"
            except Exception:
                price_str = str(price)
            rows_html += (
                f'<tr><td><b>{name}</b></td>'
                f'<td class="{css}">{bias}</td>'
                f'<td class="{css}">{score}</td>'
                f'<td>{trend}</td><td>{tech}</td>'
                f'<td style="color:#D4AF37;font-weight:bold;">{price_str}</td>'
                f'<td><span class="live-tag">⚡ LIVE</span></td></tr>'
            )
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

    sig, ent, tp, sl, reason = _signal_engine(focus_ticker)

    c1, c2, c3 = st.columns(3)
    c1.metric("📐 EMA SIGNAL", sig)
    st.caption(f"📌 Analysing: **{focus_ticker}**")

    if sig not in ("⚪ WAITING", "WAIT", "WAITING"):
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


    # ── AMAZON AFFILIATE SCROLLER — below live chart ──────────────────────────
    # ══════════════════════════════════════════════════════════════════════
    # AFFILIATE PRODUCTS — update URLs with your real Amazon affiliate links
    # Get your links at: affiliate-program.amazon.com → search product → Get Link
    # Format: {"name": "Product Name", "tag": "Short description",
    #           "url": "https://amzn.to/YOURCODE", "emoji": "🖥️"}
    # ══════════════════════════════════════════════════════════════════════
    amazon_products = [
        {"name": "Logitech MX Master 3 Mouse",         "tag": "Best for multi-screen trading setups",         "url": "https://amzn.to/3trading1",  "emoji": "🖱️"},
        {"name": "Dell 27-inch 4K Monitor",                "tag": "Ultra-sharp charting display",                 "url": "https://amzn.to/3trading2",  "emoji": "🖥️"},
        {"name": "Autonomous SmartDesk Pro",            "tag": "Stand-up trading desk",                        "url": "https://amzn.to/3trading3",  "emoji": "🪑"},
        {"name": "Blue Yeti USB Microphone",            "tag": "For trading livestreams & YouTube",            "url": "https://amzn.to/3trading4",  "emoji": "🎙️"},
        {"name": "Elgato Stream Deck",                  "tag": "One-click order shortcuts for traders",        "url": "https://amzn.to/3trading5",  "emoji": "⌨️"},
        {"name": "Trading in the Zone — Mark Douglas",  "tag": "The #1 trading psychology book",               "url": "https://amzn.to/3trading6",  "emoji": "📘"},
        {"name": "Reminiscences of a Stock Operator",   "tag": "Jesse Livermore — timeless trading bible",     "url": "https://amzn.to/3trading7",  "emoji": "📗"},
        {"name": "Bose QuietComfort 45 Headphones",     "tag": "Stay focused during volatile sessions",        "url": "https://amzn.to/3trading8",  "emoji": "🎧"},
        {"name": "LG 34-inch UltraWide Monitor",           "tag": "See more charts on one screen",                "url": "https://amzn.to/3trading9",  "emoji": "🖥️"},
        {"name": "Ergonomic Lumbar Support Chair",      "tag": "Long session comfort essential",               "url": "https://amzn.to/3trading10", "emoji": "💺"},
        {"name": "Mechanical Trading Journal Notebook", "tag": "Track every trade by hand",                    "url": "https://amzn.to/3trading11", "emoji": "📓"},
        {"name": "Ring Light 18-inch for Traders",         "tag": "Look professional on video calls & streams",   "url": "https://amzn.to/3trading12", "emoji": "💡"},
    ]

    cards_html = "".join([
        f'''<a href="{p["url"]}" target="_blank" style="text-decoration:none;">
        <div class="amz-card">
            <span style="font-size:28px;">{p["emoji"]}</span>
            <div style="margin-top:6px;font-weight:bold;color:#D4AF37;font-size:12px;">{p["name"]}</div>
            <div style="color:#aaa;font-size:10px;margin-top:3px;">{p["tag"]}</div>
            <div style="margin-top:6px;background:#FF9900;color:#000;border-radius:3px;
                        padding:3px 8px;font-size:10px;font-weight:bold;display:inline-block;">
                🛒 View on Amazon
            </div>
        </div></a>'''
        for p in amazon_products
    ])

    components.html(f"""
    <style>
    .amz-track {{
        display: flex;
        gap: 16px;
        width: max-content;
    }}
    .amz-card {{
        background: #111;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 12px;
        width: 160px;
        text-align: center;
        flex-shrink: 0;
        transition: border-color 0.3s;
        cursor: pointer;
    }}
    .amz-card:hover {{ border-color: #FF9900; }}
    #amz-wrapper {{
        overflow: hidden;
        width: 100%;
        background: #0a0a0a;
        border-top: 1px solid #D4AF37;
        border-bottom: 1px solid #D4AF37;
        padding: 12px 0;
        position: relative;
    }}
    #amz-label {{
        color: #FF9900;
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 2px;
        padding: 0 0 6px 4px;
        font-family: monospace;
    }}
    </style>
    <div id="amz-label">🛒 RECOMMENDED TRADING GEAR — AMAZON</div>
    <div id="amz-wrapper">
        <div class="amz-track" id="amz-track">
            {cards_html}
            {cards_html}
        </div>
    </div>
    <script>
    (function() {{
        const track   = document.getElementById('amz-track');
        const wrapper = document.getElementById('amz-wrapper');
        let pos       = 0;
        let paused    = false;
        let pauseTimer = null;
        const speed   = 0.6;  // px per frame — adjust for faster/slower

        function getHalfWidth() {{
            return track.scrollWidth / 2;
        }}

        function step() {{
            if (!paused) {{
                pos += speed;
                // No auto-pause — scrolls continuously unless hovered
                // Reset when one full copy has scrolled past
                if (pos >= getHalfWidth()) {{
                    pos = 0;
                    track.dataset.paused = "";
                }}
                track.style.transform = 'translateX(-' + pos + 'px)';
            }}
            requestAnimationFrame(step);
        }}
        requestAnimationFrame(step);

        // Pause on hover only — resume immediately when cursor leaves
        wrapper.addEventListener('mouseenter', function() {{ paused = true; }});
        wrapper.addEventListener('mouseleave', function() {{ paused = false; }});
    }})();
    </script>
    """, height=220)



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
