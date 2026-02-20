import streamlit as st
import time
import os
import json
import pandas as pd
import yfinance as yf
import streamlit.components.v1 as components
import base64

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
    # Fixed Indices to use CME Futures (100% supported by Sentiment Widget)
    "S&P 500": "CME_MINI:ES1!", "NASDAQ 100": "CME_MINI:NQ1!", "US 30": "CBOT_MINI:YM1!",
    "VIX": "TVC:VIX", "DAX 40": "INDEX:DE40",
    "GOLD": "OANDA:XAUUSD", "SILVER": "TVC:SILVER", "OIL (WTI)": "NYMEX:CL1!",
    "BITCOIN": "BINANCE:BTCUSDT", "ETHEREUM": "BINANCE:ETHUSDT", "SOLANA": "BINANCE:SOLUSDT"
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
@st.cache_data(ttl=60)
def get_dashboard_data():
    results = []
    for symbol, y_sym in TICKER_MAP.items():
        try:
            ticker = yf.Ticker(y_sym)
            df = ticker.history(period="1d", interval="5m")
            if df.empty: df = ticker.history(period="5d", interval="1h")
            
            if not df.empty:
                current_price = df['Close'].iloc[-1]
                sma_20 = df['Close'].rolling(window=20).mean().iloc[-1]
                if pd.isna(sma_20): sma_20 = current_price
                bias = "BULLISH" if current_price > sma_20 else "BEARISH"
                open_price = df['Open'].iloc[0] if df['Open'].iloc[0] > 0 else current_price
                pct_change = ((current_price - open_price) / open_price) * 100
                score = int(min(max(abs(pct_change) * 50, 1), 10))
                if bias == "BEARISH": score = -score
                tech = "Overbought" if score >= 8 else "Oversold" if score <= -8 else "Neutral"
                
                results.append({
                    "Symbol": symbol, "Bias": bias, "Score": score, 
                    "Trend": "Upward" if bias=="BULLISH" else "Downward",
                    "Tech": tech, "Price": current_price
                })
        except: continue
    return results

# --- NEW SMART SENTIMENT FUNCTION ---
def get_smart_sentiment(ticker_symbol):
    """Calculates sentiment based on 14-day momentum"""
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="14d") 
        if len(hist) < 14:
            return "Neutral 😐"
        start_price = hist['Close'].iloc[0]
        end_price = hist['Close'].iloc[-1]
        change = ((end_price - start_price) / start_price) * 100
        if change > 5: return "Strong Buy 🚀"
        elif change > 1: return "Bullish 📈"
        elif change < -5: return "Strong Sell 🔻"
        elif change < -1: return "Bearish 📉"
        else: return "Neutral ⚖️"
    except Exception:
        return "Neutral ⚖️"

# --- TRADINGVIEW AFFILIATE POP-UP DIALOG ---
@st.dialog("📈 ADVANCED TRADINGVIEW CHART", width="large")
def show_popup_chart(ticker):
    tv_link = "https://www.tradingview.com/?aff_id=163585"
    
    # 1. Clickable Affiliate Banner
    banner_path = "static/tv_banner.jpg"
    if os.path.exists(banner_path):
        try:
            # We encode the local image so it loads flawlessly inside the pop-up link
            encoded_img = base64.b64encode(open(banner_path, "rb").read()).decode()
            st.markdown(f"""
            <a href="{tv_link}" target="_blank">
                <img src="data:image/jpeg;base64,{encoded_img}" width="100%" style="border-radius:10px; margin-bottom:15px;">
            </a>
            """, unsafe_allow_html=True)
        except Exception as e:
            pass
    else:
        st.info("⚠️ 'tv_banner.jpg' not found in 'static' folder.")

    # 2. Main Affiliate Button
    st.markdown(f"""
    <a href="{tv_link}" target="_blank">
        <button style="width: 100%; background-color: #2962FF; color: white; border: none; padding: 12px; border-radius: 5px; font-weight: bold; cursor: pointer; margin-bottom: 15px;">
            🚀 UPGRADE TO TRADINGVIEW PRO ➤
        </button>
    </a>
    """, unsafe_allow_html=True)

    # 3. The Live Chart
    tv_symbol = TV_MAP.get(ticker, "FX:EURUSD")
    components.html(f"""<div id="tv_chart_popup" style="height:500px;"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize": true, "symbol": "{tv_symbol}", "interval": "H1", "theme": "dark", "style": "1", "locale": "en", "toolbar_bg": "#f1f3f6", "enable_publishing": false, "hide_side_toolbar": false, "allow_symbol_change": true, "container_id": "tv_chart_popup"}});</script>""", height=510)

    # 4. Promotional Videos (Side-by-Side)
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


# ================= 3. SIDEBAR =================
with st.sidebar:
    # --- LOGO ---
    logo_file = "logo.gif" if os.path.exists("logo.gif") else "logo.png" if os.path.exists("logo.png") else None
    
    if logo_file:
        try:
            with open(logo_file, "rb") as f: encoded = base64.b64encode(f.read()).decode()
            mime = "image/gif" if logo_file.endswith(".gif") else "image/png"
            st.markdown(f'<div style="text-align:center;margin-bottom:20px;"><img src="data:{mime};base64,{encoded}" width="100%"></div>', unsafe_allow_html=True)
        except: pass
    else:
        st.markdown('<div style="text-align:center;"><h1>🅰️</h1><h2>AlphaEdge</h2></div>', unsafe_allow_html=True)

    st.markdown('<div style="text-align:center;margin-bottom:20px;"><p style="font-size:10px;color:#888;">TRADING INTELLIGENCE REDEFINED</p></div><hr style="border-top:1px solid #333;">', unsafe_allow_html=True)

    # --- MEDIA ---
    with st.expander("🔴 LIVE MEDIA", expanded=True):
        st.subheader("📺 BLOOMBERG TV")
        # Fixed: Permanent Live Channel Feed without auto-mute so audio works on click
        components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/live_stream?channel=UCIALMKvObZNtJ6AmdCLP7Lg" frameborder="0" allowfullscreen></iframe>', height=160)
        
        st.subheader("🎵 TRADING STATION")
        # Fixed: Radio Selector is BACK
        station = st.selectbox("Select Audio:", ["NYC Power 105.1", "Lofi Trading Beats", "Chillout Jazz"], label_visibility="collapsed")
        
        if station == "NYC Power 105.1":
            # Fixed iHeart widget (No pop-ups)
            components.html('<iframe allow="autoplay" width="100%" height="150" src="https://www.iheart.com/live/power-1051-1473/?embed=true" frameborder="0"></iframe>', height=160)
        elif station == "Lofi Trading Beats":
            components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/jfKfPfyJRdk?autoplay=1" frameborder="0" allowfullscreen></iframe>', height=160)
        elif station == "Chillout Jazz":
            components.html('<iframe width="100%" height="150" src="https://www.youtube.com/embed/Dx5qFachd3A?autoplay=1" frameborder="0" allowfullscreen></iframe>', height=160)

    # --- 💎 ROTATING AFFILIATE PARTNERS ---
    st.markdown("---")
    st.caption("🏆 FEATURED PARTNER")
    
    # Get the current minute to alternate ads seamlessly
    current_minute = int(time.time() / 60)
    
    # Toggle between Exness and Goat Funded Trader based on the minute
    if current_minute % 2 == 0:
        # --- EXNESS ---
        p_logo = "static/exness_logo.png"
        p_video = "static/exness.mp4"
        p_link = "https://one.exnessonelink.com/a/9wwklqzfxb"
        p_color = "#D4AF37" # Gold
        p_text = "🚀 TRADE WITH 0 SPREADS ➤"
    else:
        # --- GOAT FUNDED TRADER ---
        p_logo = "static/goat_logo.png"
        p_video = "static/goat.mp4"
        p_link = "https://checkout.goatfundedtrader.com/aff/Sherwet/"
        p_color = "#00E676" # Green to stand out differently
        p_text = "🐐 GET FUNDED TODAY ➤"

    if os.path.exists(p_logo):
        st.image(p_logo, use_container_width=True)
    else:
        st.error(f"⚠️ '{p_logo}' not found in 'static' folder")

    if os.path.exists(p_video):
        st.video(p_video, start_time=0)
    else:
        st.info(f"⚠️ '{p_video}' not found in 'static' folder")

    # The Clickable Button
    st.markdown(f"""
    <a href="{p_link}" target="_blank">
        <button style="
            width: 100%; 
            background-color: {p_color}; 
            color: black; 
            border: none; 
            padding: 12px; 
            border-radius: 5px; 
            font-weight: bold; 
            cursor: pointer;
            margin-top: 10px;
        ">
            {p_text}
        </button>
    </a>
    """, unsafe_allow_html=True)

    st.divider()
    focus_ticker = st.selectbox("ACTIVE CHART ASSET:", list(TICKER_MAP.keys()), index=0)

    # --- NEW: TRIGGER FOR TRADINGVIEW POP-UP ---
    if st.button("GET YOUR TRADING VIEW ADVANCE CHART HERE", use_container_width=True):
        show_popup_chart(focus_ticker)

# ================= 4. MAIN NAVIGATION =================
tab_dash, tab_cot, tab_sent, tab_ind, tab_fx, tab_news, tab_cal = st.tabs([
    "  📊 DASHBOARD  ", "  📊 COT DATA  ", "  📈 SENTIMENT  ", 
    "  🏙️ INDICES  ", "  💱 CURRENCY MATRIX  ", "  📰 LIVE NEWS  ", "  📅 CALENDAR  "
])

# ================= TAB 1: DASHBOARD =================
with tab_dash:
    st.title("📊 ALPHAEDGE COMMAND CENTRE")
    st.write("⏳ *Analyzing Live Market Structure...*")
    
    data = get_dashboard_data()
    rows_html = ""
    if data:
        for row in data:
            css_class = "bullish" if row['Bias'] == "BULLISH" else "bearish"
            rows_html += f"""<tr><td><b>{row['Symbol']}</b></td><td class="{css_class}">{row['Bias']}</td><td class="{css_class}">{row['Score']:+}</td><td>{row['Trend']}</td><td>{row['Tech']}</td><td style="color:#D4AF37; font-weight:bold;">{row['Price']:,.4f}</td><td><span class="live-tag">⚡ LIVE</span></td></tr>"""
    else:
        rows_html = "<tr><td colspan='7'>Loading Data...</td></tr>"

    st.markdown(f"""<table class="heatmap-table"><thead><tr><th>SYMBOL</th><th>BIAS</th><th>SCORE</th><th>TREND</th><th>TECH</th><th>PRICE</th><th>SOURCE</th><th>NOTES</th></tr></thead><tbody>{rows_html}</tbody></table>""", unsafe_allow_html=True)

    st.markdown("---")
    
    # --- SMART SENTIMENT INJECTED HERE ---
    col_title, col_metric = st.columns([3, 1])
    with col_title:
        st.subheader(f"📈 LIVE CHART: {focus_ticker}")
    with col_metric:
        y_sym = TICKER_MAP.get(focus_ticker, "EURUSD=X")
        current_sentiment = get_smart_sentiment(y_sym)
        st.metric(label="AI Momentum Sentiment", value=current_sentiment)

    tv_symbol = TV_MAP.get(focus_ticker, "FX:EURUSD")
    components.html(f"""<div id="tv_chart_main" style="height:600px;"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize": true, "symbol": "{tv_symbol}", "interval": "H1", "theme": "dark", "style": "1", "locale": "en", "toolbar_bg": "#f1f3f6", "enable_publishing": false, "hide_side_toolbar": false, "allow_symbol_change": true, "container_id": "tv_chart_main"}});</script>""", height=610)

# ================= TAB 2: COT DATA =================
with tab_cot:
    st.title("📊 INSTITUTIONAL POSITIONING")
    
    col_ctrl, col_info = st.columns([1, 2])
    with col_ctrl:
        if st.button("🔄 REFRESH DATA"):
            import cot_fetcher
            if cot_fetcher.update_cot_data():
                st.success("Updated!"); time.sleep(1); st.rerun()

    def make_row(row):
        l_pct = row.get('long_pct', 0); s_pct = row.get('short_pct', 0)
        l_cls = "bull-strong" if l_pct > 60 else "bull-med" if l_pct > 50 else ""
        s_cls = "bear-strong" if s_pct > 60 else "bear-med" if s_pct > 50 else ""
        net_color = "#2962FF" if row.get('net_pos', 0) > 0 else "#D50000"

        return f"""<tr><td class="symbol-col">{row['Symbol']}</td><td>{int(row['long_pos']):,}</td><td>{int(row['short_pos']):,}</td><td style="color:{'#00E676' if row['change_long']>0 else '#FF5252'}">{int(row['change_long']):+,}</td><td style="color:{'#00E676' if row['change_short']>0 else '#FF5252'}">{int(row['change_short']):+,}</td><td class="{l_cls}">{l_pct:.1f}%</td><td class="{s_cls}">{s_pct:.1f}%</td><td>{row['net_pct']:.2f}%</td><td style="font-weight:bold; background-color:{net_color}; color:white;">{int(row.get('net_pos', 0)):,}</td><td>{int(row['open_int']):,}</td><td>{int(row['change_oi']):+,}</td></tr>"""

    if os.path.exists("cot_live.json"):
        with open("cot_live.json", "r") as f: data = json.load(f)
        rows_list = []
        for sym, vals in data.items():
            vals['Symbol'] = sym
            rows_list.append(vals)
        table_rows = "".join([make_row(row) for row in rows_list])
        st.markdown(f"""<table class="heatmap-table" style="width:100%; text-align:center;"><thead><tr style="background:#111; color:#D4AF37;"><th>Symbol</th><th>Longs</th><th>Shorts</th><th>Δ Long</th><th>Δ Short</th><th>Long %</th><th>Short %</th><th>Net %</th><th>Net Pos</th><th>OI</th><th>Δ OI</th></tr></thead><tbody>{table_rows}</tbody></table>""", unsafe_allow_html=True)
    else: st.info("ℹ️ No data found. Click Refresh.")

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

# ================= FIXED FOOTER =================
st.markdown("""<div class="ticker-footer"><iframe src="https://www.tradingview-widget.com/embed-widget/ticker-tape/?theme=dark#%7B%22symbols%22%3A%5B%7B%22proName%22%3A%22FOREXCOM%3ASPXUSD%22%2C%22title%22%3A%22S%26P%20500%22%7D%2C%7B%22proName%22%3A%22FOREXCOM%3ANSXUSD%22%2C%22title%22%3A%22Nasdaq%20100%22%7D%2C%7B%22proName%22%3A%22FX_IDC%3AEURUSD%22%2C%22title%22%3A%22EUR%2FUSD%22%7D%2C%7B%22proName%22%3A%22OANDA%3AXAUUSD%22%2C%22title%22%3A%22GOLD%22%7D%5D%2C%22showSymbolLogo%22%3Atrue%2C%22colorTheme%22%3A%22dark%22%2C%22isTransparent%22%3Atrue%2C%22displayMode%22%3A%22adaptive%22%2C%22locale%22%3A%22en%22%7D" width="100%" height="40" frameborder="0" scrolling="no" style="margin-top:-10px;"></iframe></div>""", unsafe_allow_html=True)