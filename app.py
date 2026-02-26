import streamlit as st
import time
import os
import json
import html
import sqlite3
import threading
import pandas as pd
import yfinance as yf
import streamlit.components.v1 as components
import base64
from datetime import datetime

# ================= 1. PAGE CONFIG & BRANDING =================
st.set_page_config(page_title="AlphaEdge | Trading Intelligence", page_icon="🅰️", layout="wide", initial_sidebar_state="expanded")

# --- EXPANDED ASSET LIST (FUTURES UPDATE) ---
TICKER_MAP = {
    # Forex
    "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X", 
    "USD/CHF": "USDCHF=X", "AUD/USD": "AUDUSD=X", "USD/CAD": "USDCAD=X",
    "NZD/USD": "NZDUSD=X", "USD/ZAR": "USDZAR=X", "GBP/ZAR": "GBPZAR=X",
    # Indices (FUTURES - Reliable Live Data)
    "S&P 500": "ES=F", "NASDAQ 100": "NQ=F", "US 30": "YM=F", "VIX": "^VIX", 
    # Commodities
    "GOLD": "GC=F", "SILVER": "SI=F", "OIL (WTI)": "CL=F", "NAT GAS": "NG=F",
    # Crypto
    "BITCOIN": "BTC-USD", "ETHEREUM": "ETH-USD", "SOLANA": "SOL-USD"
}

# --- TRADINGVIEW SYMBOL MAPPING (FIXED FOR EMBEDS) ---
TV_MAP = {
    "EUR/USD": "FX:EURUSD", "GBP/USD": "FX:GBPUSD", "USD/JPY": "FX:USDJPY",
    "USD/CHF": "FX:USDCHF", "AUD/USD": "FX:AUDUSD", "USD/CAD": "FX:USDCAD",
    "NZD/USD": "FX:NZDUSD", "USD/ZAR": "FX:USDZAR", "GBP/ZAR": "FX:GBPZAR",
    "S&P 500": "CME_MINI:ES1!", "NASDAQ 100": "CME_MINI:NQ1!", "US 30": "CBOT_MINI:YM1!",
    "VIX": "TVC:VIX", "DAX 40": "INDEX:DE40",
    "GOLD": "OANDA:XAUUSD", "SILVER": "TVC:SILVER", "OIL (WTI)": "NYMEX:CL1!",
    "BITCOIN": "BINANCE:BTCUSDT", "ETHEREUM": "BINANCE:ETHUSDT", "SOLANA": "BINANCE:SOLUSDT"
}

# --- PIP SIZE LOOKUP per asset type (IMPROVED: replaces broken c_price * 0.0001 catch-all) ---
PIP_MAP = {
    "USDJPY=X": 0.01, "GBPJPY=X": 0.01,
    "EURUSD=X": 0.0001, "GBPUSD=X": 0.0001, "USDCHF=X": 0.0001,
    "AUDUSD=X": 0.0001, "USDCAD=X": 0.0001, "NZDUSD=X": 0.0001,
    "USDZAR=X": 0.0001, "GBPZAR=X": 0.0001,
    "GC=F": 0.10,      # Gold: 10 cents
    "SI=F": 0.005,     # Silver
    "CL=F": 0.01,      # Oil
    "NG=F": 0.001,     # Nat Gas
    "ES=F": 0.25,      # S&P 500 futures tick
    "NQ=F": 0.25,
    "YM=F": 1.0,
    "^VIX": 0.01,
    "BTC-USD": 10.0,   # Bitcoin: $10 per unit
    "ETH-USD": 1.0,
    "SOL-USD": 0.05,
}

# --- ALPHAEDGE CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    section[data-testid="stSidebar"] { background-color: #000000; border-right: 1px solid #222; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #080808; padding: 10px; border-bottom: 2px solid #D4AF37; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #111; color: #888; border: 1px solid #333; border-bottom: none; padding-left: 20px; padding-right: 20px; }
    .stTabs [aria-selected="true"] { background-color: #D4AF37 !important; color: #000 !important; font-weight: bold; }
    h1, h2, h3 { color: #D4AF37 !important; text-transform: uppercase; font-family: 'Helvetica Neue', sans-serif; }
    .heatmap-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 13px; background-color: #080808; border: 1px solid #333; }
    .heatmap-table th { background-color: #111; color: #D4AF37; padding: 12px; text-align: left; border-bottom: 2px solid #D4AF37; }
    .heatmap-table td { padding: 10px; border-bottom: 1px solid #222; color: #ccc; }
    .bullish { color: #00ff88 !important; font-weight: bold; }
    .bearish { color: #ff4b4b !important; font-weight: bold; }
    .live-tag { color: #00ff88; border: 1px solid #00ff88; padding: 2px 5px; font-size: 10px; border-radius: 3px; }
    .ticker-footer { position: fixed; bottom: 0; left: 0; width: 100%; height: 40px; background: #000; border-top: 1px solid #D4AF37; z-index: 999999; }
    .main .block-container { padding-bottom: 60px; }
    .symbol-col { background-color: #304FFE; color: white !important; font-weight: bold; }
    .bull-strong { background-color: #2962FF; color: white; } 
    .bull-med { background-color: #448AFF; color: white; }    
    .bear-strong { background-color: #D50000; color: white; } 
    .bear-med { background-color: #FF5252; color: white; }    
    </style>
""", unsafe_allow_html=True)

# ================= 2. CACHED DATA FUNCTIONS =================
@st.cache_data(ttl=60, show_spinner=False)
def get_dashboard_data():
    results = []
    for symbol, y_sym in TICKER_MAP.items():
        try:
            ticker = yf.Ticker(y_sym)
            df = ticker.history(period="2d", interval="5m")  # FIX: use 2d so SMA-20 has enough candles
            if df.empty:
                df = ticker.history(period="5d", interval="1h")
            
            if not df.empty and len(df) >= 20:
                current_price = df['Close'].iloc[-1]
                sma_20 = df['Close'].rolling(window=20).mean().iloc[-1]
                # FIX: only fallback if genuinely NaN, log a warning
                if pd.isna(sma_20):
                    continue  # skip rather than show a meaningless signal
                bias = "BULLISH" if current_price > sma_20 else "BEARISH"
                open_price = df['Open'].iloc[0]
                if open_price == 0 or pd.isna(open_price):
                    open_price = current_price
                pct_change = ((current_price - open_price) / open_price) * 100
                score = int(min(max(abs(pct_change) * 50, 1), 10))
                if bias == "BEARISH":
                    score = -score
                tech = "Overbought" if score >= 8 else "Oversold" if score <= -8 else "Neutral"
                
                results.append({
                    "Symbol": symbol, "Bias": bias, "Score": score, 
                    "Trend": "Upward" if bias == "BULLISH" else "Downward",
                    "Tech": tech, "Price": current_price
                })
        except Exception as e:
            # FIX: log the error instead of silently swallowing it
            st.session_state.setdefault("data_errors", []).append(f"{symbol}: {str(e)}")
            continue
    return results


# --- EMA SCALPER (renamed from "AI" to be accurate) ---
@st.cache_data(ttl=30, show_spinner=False)  # FIX: was uncached, hammered yfinance on every rerender
def get_scalp_signal(ticker_symbol):
    """Calculates live 5m scalping signals using 9/21 EMA + RSI"""
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="5d", interval="5m") 
        if len(hist) < 25:
            return "⚪ WAITING", 0.0, 0.0, 0.0
            
        close = hist['Close']
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -1 * delta.clip(upper=0)
        ema_gain = gain.ewm(com=13, adjust=False).mean()
        ema_loss = loss.ewm(com=13, adjust=False).mean()
        rs = ema_gain / ema_loss
        rsi = 100 - (100 / (1 + rs))
        
        c_price = close.iloc[-1]
        c_ema9 = ema9.iloc[-1]
        c_ema21 = ema21.iloc[-1]
        c_rsi = rsi.iloc[-1]
        
        # FIX: use proper pip lookup table instead of c_price * 0.0001
        pip = PIP_MAP.get(ticker_symbol, 0.0001)
        tp_dist = 15 * pip
        sl_dist = 10 * pip
        
        if c_ema9 > c_ema21 and c_price > c_ema9 and 40 <= c_rsi <= 65:
            return "🟢 STRONG BUY", c_price, c_price + tp_dist, c_price - sl_dist
        elif c_ema9 < c_ema21 and c_price < c_ema9 and 35 <= c_rsi <= 60:
            return "🔴 SELL", c_price, c_price - tp_dist, c_price + sl_dist
        else:
            return "⚪ WAITING", c_price, 0.0, 0.0
    except Exception:
        return "⚪ WAITING", 0.0, 0.0, 0.0


# --- TRADINGVIEW AFFILIATE POP-UP DIALOG ---
@st.dialog("📈 ADVANCED TRADINGVIEW CHART", width="large")
def show_popup_chart(ticker):
    tv_link = "https://www.tradingview.com/?aff_id=163585"
    
    banner_path = "static/tv_banner.jpg"
    if os.path.exists(banner_path):
        try:
            encoded_img = base64.b64encode(open(banner_path, "rb").read()).decode()
            st.markdown(f"""
            <a href="{tv_link}" target="_blank">
                <img src="data:image/jpeg;base64,{encoded_img}" width="100%" style="border-radius:10px; margin-bottom:15px;">
            </a>
            """, unsafe_allow_html=True)
        except Exception:
            pass
    else:
        st.info("⚠️ 'tv_banner.jpg' not found in 'static' folder.")

    st.markdown(f"""
    <a href="{tv_link}" target="_blank">
        <button style="width: 100%; background-color: #2962FF; color: white; border: none; padding: 12px; border-radius: 5px; font-weight: bold; cursor: pointer; margin-bottom: 15px;">
            🚀 UPGRADE TO TRADINGVIEW PRO ➤
        </button>
    </a>
    """, unsafe_allow_html=True)

    tv_symbol = TV_MAP.get(ticker, "FX:EURUSD")
    components.html(f"""<div id="tv_chart_popup" style="height:500px;"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize": true, "symbol": "{tv_symbol}", "interval": "H1", "theme": "dark", "style": "1", "locale": "en", "toolbar_bg": "#f1f3f6", "enable_publishing": false, "hide_side_toolbar": false, "allow_symbol_change": true, "container_id": "tv_chart_popup"}});</script>""", height=510)

    st.markdown("---")
    c1, c2 = st.columns(2)
    video1_path = "static/tv_promo_1.mp4"
    video2_path = "static/tv_promo_2.mp4"
    
    with c1:
        if os.path.exists(video1_path):
            st.caption("📺 Pro Features Overview")
            st.video(video1_path, start_time=0)
    with c2:
        if os.path.exists(video2_path):
            st.caption("📺 Advanced Charting Tools")
            st.video(video2_path, start_time=0)


# ================= CHAT: SQLite backend (replaces flat JSON with race-condition risk) =================
DB_FILE = "chat.db"
_db_lock = threading.Lock()

def init_db():
    with _db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                ts REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()

init_db()

def load_chat(limit=100):
    with _db_lock:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(
            "SELECT text, ts FROM messages ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    # Return oldest-first for display
    return [{"text": r[0], "ts": r[1]} for r in reversed(rows)]

def save_message(text: str):
    # FIX: sanitize input before storing to prevent XSS
    clean_text = html.escape(text.strip())
    if not clean_text:
        return
    with _db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT INTO messages (text, ts) VALUES (?, ?)", (clean_text, time.time()))
        conn.commit()
        conn.close()


# ================= 3. SIDEBAR =================
with st.sidebar:
    logo_file = "logo.gif" if os.path.exists("logo.gif") else "logo.png" if os.path.exists("logo.png") else None
    
    if logo_file:
        try:
            with open(logo_file, "rb") as f:
                encoded = base64.b64encode(f.read()).decode()
            mime = "image/gif" if logo_file.endswith(".gif") else "image/png"
            st.markdown(f'<div style="text-align:center;margin-bottom:20px;"><img src="data:{mime};base64,{encoded}" width="100%"></div>', unsafe_allow_html=True)
        except Exception:
            pass
    else:
        st.markdown('<div style="text-align:center;"><h1>🅰️</h1><h2>AlphaEdge</h2></div>', unsafe_allow_html=True)

    st.markdown('<div style="text-align:center;margin-bottom:20px;"><p style="font-size:10px;color:#888;">TRADING INTELLIGENCE REDEFINED</p></div><hr style="border-top:1px solid #333;">', unsafe_allow_html=True)

    with st.expander("🔴 LIVE MEDIA", expanded=True):
        st.subheader("📺 BLOOMBERG TV")
        components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/live_stream?channel=UCIALMKvObZNtJ6AmdCLP7Lg" frameborder="0" allowfullscreen></iframe>', height=160)
        
        st.subheader("🎵 TRADING STATION")
        station = st.selectbox("Select Audio:", ["NYC Power 105.1", "Lofi Trading Beats", "Chillout Jazz"], label_visibility="collapsed")
        
        if station == "NYC Power 105.1":
            components.html('<iframe allow="autoplay" width="100%" height="150" src="https://www.iheart.com/live/power-1051-1473/?embed=true" frameborder="0"></iframe>', height=160)
        elif station == "Lofi Trading Beats":
            components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/jfKfPfyJRdk?autoplay=1" frameborder="0" allowfullscreen></iframe>', height=160)
        elif station == "Chillout Jazz":
            components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/Dx5qFachd3A?autoplay=1" frameborder="0" allowfullscreen></iframe>', height=160)

    # --- BOTH AFFILIATE PARTNERS ALWAYS VISIBLE ---
    st.markdown("---")
    st.markdown('<p style="text-align:center; color:#D4AF37; font-size:11px; font-weight:bold; letter-spacing:2px;">🏆 FEATURED PARTNERS</p>', unsafe_allow_html=True)

    # --- PARTNER 1: EXNESS ---
    if os.path.exists("static/exness_logo.png"):
        st.image("static/exness_logo.png", use_container_width=True)
    if os.path.exists("static/exness.mp4"):
        st.video("static/exness.mp4", start_time=0)
    st.markdown("""
    <a href="https://one.exnessonelink.com/a/9wwklqzfxb" target="_blank">
        <button style="width:100%; background-color:#D4AF37; color:#000; border:none; padding:12px; border-radius:5px; font-weight:bold; cursor:pointer; margin-top:6px; font-size:13px;">
            🚀 TRADE WITH 0 SPREADS ➤
        </button>
    </a>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- PARTNER 2: GOAT FUNDED TRADER ---
    if os.path.exists("static/goat_logo.png"):
        st.image("static/goat_logo.png", use_container_width=True)
    if os.path.exists("static/goat.mp4"):
        st.video("static/goat.mp4", start_time=0)
    st.markdown("""
    <a href="https://checkout.goatfundedtrader.com/aff/Sherwet/" target="_blank">
        <button style="width:100%; background-color:#00E676; color:#000; border:none; padding:12px; border-radius:5px; font-weight:bold; cursor:pointer; margin-top:6px; font-size:13px;">
            🐐 GET FUNDED TODAY ➤
        </button>
    </a>
    """, unsafe_allow_html=True)

    st.divider()
    focus_ticker = st.selectbox("ACTIVE CHART ASSET:", list(TICKER_MAP.keys()), index=0)

    if st.button("GET YOUR TRADING VIEW ADVANCE CHART HERE", use_container_width=True):
        show_popup_chart(focus_ticker)

# ================= 4. MAIN NAVIGATION =================
tab_dash, tab_cot, tab_sent, tab_ind, tab_fx, tab_news, tab_cal, tab_chat = st.tabs([
    "  📊 DASHBOARD  ", "  📊 COT DATA  ", "  📈 SENTIMENT  ", 
    "  🏙️ INDICES  ", "  💱 CURRENCY MATRIX  ", "  📰 LIVE NEWS  ", "  📅 CALENDAR  ", "  💬 COMMUNITY  "
])

# ================= TAB 1: DASHBOARD =================
with tab_dash:
    st.title("📊 ALPHAEDGE COMMAND CENTRE")
    st.write("⏳ *Analyzing Live Market Structure...*")
    
    data = get_dashboard_data()

    # FIX: show data errors in an expander so they're visible but not intrusive
    errors = st.session_state.get("data_errors", [])
    if errors:
        with st.expander(f"⚠️ {len(errors)} asset(s) failed to load", expanded=False):
            for e in errors:
                st.caption(e)
        st.session_state["data_errors"] = []  # reset after display

    rows_html = ""
    if data:
        for row in data:
            css_class = "bullish" if row['Bias'] == "BULLISH" else "bearish"
            # FIX: removed dangling empty NOTES column — header had 8 cols, rows only had 7
            rows_html += f"""<tr>
                <td><b>{row['Symbol']}</b></td>
                <td class="{css_class}">{row['Bias']}</td>
                <td class="{css_class}">{row['Score']:+}</td>
                <td>{row['Trend']}</td>
                <td>{row['Tech']}</td>
                <td style="color:#D4AF37; font-weight:bold;">{row['Price']:,.4f}</td>
                <td><span class="live-tag">⚡ LIVE</span></td>
            </tr>"""
    else:
        rows_html = "<tr><td colspan='7'>Loading Data...</td></tr>"

    # FIX: header columns now match row columns (7 cols, NOTES removed)
    st.markdown(f"""<table class="heatmap-table"><thead><tr>
        <th>SYMBOL</th><th>BIAS</th><th>SCORE</th><th>TREND</th><th>TECH</th><th>PRICE</th><th>SOURCE</th>
    </tr></thead><tbody>{rows_html}</tbody></table>""", unsafe_allow_html=True)

    st.markdown("---")

    # --- AI EMA SIGNAL HEADING ---
    st.markdown("""
    <div style="background: linear-gradient(90deg, #0a0a0a, #111); border: 1px solid #D4AF37; border-left: 4px solid #D4AF37; border-radius: 6px; padding: 14px 18px; margin-bottom: 10px;">
        <h3 style="margin:0; color:#D4AF37; font-size:18px; letter-spacing:2px;">🤖 AI EMA SCALPER SIGNALS</h3>
        <p style="margin:6px 0 0 0; color:#aaa; font-size:12px;">Real-time 9/21 EMA crossover with RSI confirmation on 5-minute bars</p>
    </div>
    """, unsafe_allow_html=True)

    # --- DISCLAIMER BANNER ---
    st.markdown(f"""
    <div style="background-color:#0d1117; border:1px solid #FF6B35; border-radius:6px; padding:12px 16px; margin-bottom:14px;">
        <p style="margin:0; color:#FF6B35; font-size:11px; font-weight:bold; letter-spacing:1px;">⚠️ RISK DISCLAIMER — NOT FINANCIAL ADVICE</p>
        <p style="margin:6px 0 0 0; color:#888; font-size:11px; line-height:1.6;">
            The signals displayed on this platform are generated algorithmically for <b style="color:#ccc;">educational and informational purposes only</b>. 
            They do not constitute financial advice, investment recommendations, or a solicitation to buy or sell any financial instrument. 
            Trading leveraged products such as Forex, Indices, Commodities, and Cryptocurrencies carries a <b style="color:#ccc;">high level of risk</b> and may not be suitable for all investors. 
            You could lose more than your initial deposit. Past signal performance is not indicative of future results. 
            Always conduct your own due diligence and consult a qualified financial advisor before making any trading decisions.
        </p>
        <p style="margin:8px 0 0 0; color:#D4AF37; font-size:11px;">
            📌 <b>These signals are generated for the asset selected in the sidebar dropdown only.</b> 
            Change the <b>ACTIVE CHART ASSET</b> in the left sidebar to generate signals for a different instrument.
        </p>
    </div>
    """, unsafe_allow_html=True)

    y_sym = TICKER_MAP.get(focus_ticker, "EURUSD=X")
    sig, ent, tp, sl = get_scalp_signal(y_sym)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("📐 EMA SIGNAL", sig)
    
    st.caption(f"📌 Analysing: **{focus_ticker}** — change asset in the sidebar dropdown to update signals")

    if sig != "⚪ WAITING":
        c2.metric("⚡ LIVE ENTRY", f"{ent:.4f}")
        c3.metric("🎯 TARGETS", f"TP: {tp:.4f} | SL: {sl:.4f}")
    else:
        c2.metric("⚡ LIVE ENTRY", "Searching...")
        c3.metric("🎯 TARGETS", "Awaiting Pullback")

    tv_symbol = TV_MAP.get(focus_ticker, "FX:EURUSD")
    components.html(f"""<div id="tv_chart_main" style="height:600px;"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize": true, "symbol": "{tv_symbol}", "interval": "H1", "theme": "dark", "style": "1", "locale": "en", "toolbar_bg": "#f1f3f6", "enable_publishing": false, "hide_side_toolbar": false, "allow_symbol_change": true, "container_id": "tv_chart_main"}});</script>""", height=610)

# ================= TAB 2: COT DATA =================
with tab_cot:
    st.title("📊 INSTITUTIONAL POSITIONING")
    col_ctrl, col_info = st.columns([1, 2])
    with col_ctrl:
        if st.button("🔄 REFRESH DATA"):
            try:
                import cot_fetcher
                if cot_fetcher.update_cot_data():
                    st.success("Updated!"); time.sleep(1); st.rerun()
            except ModuleNotFoundError:
                st.error("⚠️ cot_fetcher module not found. Please ensure cot_fetcher.py is in the project directory.")
            except Exception as e:
                st.error(f"⚠️ COT refresh failed: {e}")

    def make_row(row):
        l_pct = row.get('long_pct', 0); s_pct = row.get('short_pct', 0)
        l_cls = "bull-strong" if l_pct > 60 else "bull-med" if l_pct > 50 else ""
        s_cls = "bear-strong" if s_pct > 60 else "bear-med" if s_pct > 50 else ""
        net_color = "#2962FF" if row.get('net_pos', 0) > 0 else "#D50000"

        return f"""<tr><td class="symbol-col">{row['Symbol']}</td><td>{int(row['long_pos']):,}</td><td>{int(row['short_pos']):,}</td><td style="color:{'#00E676' if row['change_long']>0 else '#FF5252'}">{int(row['change_long']):+,}</td><td style="color:{'#00E676' if row['change_short']>0 else '#FF5252'}">{int(row['change_short']):+,}</td><td class="{l_cls}">{l_pct:.1f}%</td><td class="{s_cls}">{s_pct:.1f}%</td><td>{row['net_pct']:.2f}%</td><td style="font-weight:bold; background-color:{net_color}; color:white;">{int(row.get('net_pos', 0)):,}</td><td>{int(row['open_int']):,}</td><td>{int(row['change_oi']):+,}</td></tr>"""

    if os.path.exists("cot_live.json"):
        try:
            with open("cot_live.json", "r") as f:
                cot_data = json.load(f)
            rows_list = [dict(v, Symbol=k) for k, v in cot_data.items()]
            table_rows = "".join([make_row(row) for row in rows_list])
            st.markdown(f"""<table class="heatmap-table" style="width:100%; text-align:center;"><thead><tr style="background:#111; color:#D4AF37;"><th>Symbol</th><th>Longs</th><th>Shorts</th><th>Δ Long</th><th>Δ Short</th><th>Long %</th><th>Short %</th><th>Net %</th><th>Net Pos</th><th>OI</th><th>Δ OI</th></tr></thead><tbody>{table_rows}</tbody></table>""", unsafe_allow_html=True)
        except (json.JSONDecodeError, KeyError) as e:
            st.error(f"⚠️ Failed to parse COT data: {e}. Try refreshing.")
    else:
        st.info("ℹ️ No data found. Click Refresh.")

# ================= TAB 3: SENTIMENT =================
with tab_sent:
    st.title("📈 TECHNICAL SENTIMENT")
    gauge_asset = st.selectbox("Select Asset to Analyze:", list(TICKER_MAP.keys()), key="gauge_sel")
    tv_gauge = TV_MAP.get(gauge_asset, "FX:EURUSD")
    st.write(f"Displaying Sentiment for: **{gauge_asset}**")
    c1, c2 = st.columns(2)
    with c1: st.caption("1 Hour Interval"); components.html(f"""<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>{{"interval": "1h", "width": "100%", "isTransparent": true, "height": 450, "symbol": "{tv_gauge}", "showIntervalTabs": false, "displayMode": "single", "locale": "en", "colorTheme": "dark"}}</script></div>""", height=460)
    with c2: st.caption("4 Hour Interval"); components.html(f"""<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>{{"interval": "4h", "width": "100%", "isTransparent": true, "height": 450, "symbol": "{tv_gauge}", "showIntervalTabs": false, "displayMode": "single", "locale": "en", "colorTheme": "dark"}}</script></div>""", height=460)

# ================= TAB 4: INDICES =================
with tab_ind:
    st.title("🏙️ GLOBAL INDICES HEATMAP")
    components.html("""<iframe src="https://www.tradingview-widget.com/embed-widget/stock-heatmap/?theme=dark&market=america" height="800" width="100%"></iframe>""", height=820)

# ================= TAB 5: FOREX =================
with tab_fx:
    st.title("💱 GLOBAL CURRENCY MATRIX")
    components.html("""<div class="tradingview-widget-container"><script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-forex-heat-map.js" async>{"width": "100%", "height": 800, "currencies": ["EUR","USD","JPY","GBP","CHF","AUD","CAD","NZD","ZAR"], "isTransparent": false, "colorTheme": "dark", "locale": "en"}</script></div>""", height=820)

# ================= TAB 6: NEWS =================
with tab_news:
    st.title("📰 LIVE MARKET NEWS")
    components.html("""<iframe src="https://www.tradingview-widget.com/embed-widget/timeline/?feedMode=all_symbols&theme=dark" height="800" width="100%"></iframe>""", height=820)

# ================= TAB 7: CALENDAR =================
with tab_cal:
    st.title("📅 ECONOMIC CALENDAR")
    components.html("""<iframe src="https://www.tradingview-widget.com/embed-widget/events/?theme=dark&importance=high" height="800" width="100%"></iframe>""", height=820)

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
    
    chat_history = load_chat()
    
    chat_container = st.container(height=500)
    with chat_container:
        if not chat_history:
            st.info("Welcome to the AlphaEdge Traders Lounge. Be the first to drop a setup!")
        else:
            for msg in chat_history:
                with st.chat_message("user"):
                    # FIX: text is pre-sanitized via html.escape() on save, safe to display
                    ts = datetime.fromtimestamp(msg['ts']).strftime("%H:%M")
                    st.markdown(f"**Anonymous Trader** · *{ts}*")
                    st.write(msg['text'])  # use st.write (not markdown) to avoid any residual injection risk
    
    if prompt := st.chat_input("Drop a trading idea or setup..."):
        save_message(prompt)  # FIX: sanitizes and writes to SQLite atomically
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
    f'<div class="ticker-footer">'
    f'<iframe src="{_footer_url}" width="100%" height="40" frameborder="0" scrolling="no" style="margin-top:-10px;"></iframe>'
    f'</div>',
    unsafe_allow_html=True
)
