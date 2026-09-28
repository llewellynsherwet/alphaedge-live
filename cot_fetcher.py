import pandas as pd
import requests
import io
import json
import datetime

# --- ASSET CONFIGURATION ---
# Exact CFTC market-name prefixes (upper case). Matching by prefix avoids picking up
# MICRO / ICE / spread contracts that merely contain the same words.
ASSET_CONFIG = {
    # FINANCIALS (Currencies, Indices, Crypto) - TFF report, Leveraged Funds
    "CAD": ["CANADIAN DOLLAR - "],
    "AUD": ["AUSTRALIAN DOLLAR - "],
    "USD": ["USD INDEX - "],
    "ZAR": ["SO AFRICAN RAND - ", "SOUTH AFRICAN RAND - "],
    "EUR": ["EURO FX - "],
    "NZD": ["NZ DOLLAR - "],
    "JPY": ["JAPANESE YEN - "],
    "GBP": ["BRITISH POUND - "],
    "CHF": ["SWISS FRANC - "],
    "BTC": ["BITCOIN - "],
    "NIKKEI": ["NIKKEI STOCK AVERAGE YEN DENOM", "NIKKEI STOCK AVERAGE - "],
    "DOW": ["DJIA CONSOLIDATED", "DJIA X $5"],
    "RUSSELL": ["RUSSELL E-MINI"],
    "SPX": ["S&P 500 CONSOLIDATED", "E-MINI S&P 500 - "],
    "NASDAQ": ["NASDAQ-100 CONSOLIDATED", "NASDAQ MINI"],
    "US10T": ["UST 10Y NOTE"],

    # COMMODITIES (Metals, Energy) - Disaggregated report, Managed Money
    "SILVER": ["SILVER - "],
    "Gold": ["GOLD - "],
    "PLATINUM": ["PLATINUM - "],
    "COPPER": ["COPPER- #1", "COPPER #1"],
    "USOil": ["WTI-PHYSICAL - ", "CRUDE OIL, LIGHT SWEET - NEW YORK"],
}

# Column indices (0-based) verified against the CFTC header files
# fut_disagg_txt_YYYY.zip / fut_fin_txt_YYYY.zip.
COLUMNS = {
    # Disaggregated: 13 M_Money_Positions_Long_All, 14 M_Money_Positions_Short_All,
    # 55 Change_in_Open_Interest_All, 61/62 Change_in_M_Money_Long/Short_All
    "Commodities": dict(oi=7, doi=55, long=13, short=14, dlong=61, dshort=62),
    # TFF: 14/15 Lev_Money_Positions_Long/Short_All, 24 Change_in_Open_Interest_All,
    # 31/32 Change_in_Lev_Money_Long/Short_All
    "Financials": dict(oi=7, doi=24, long=14, short=15, dlong=31, dshort=32),
}


def _find_row(df, prefixes, idx_name=0):
    for p in prefixes:
        m = df[df[idx_name].str.startswith(p)]
        if not m.empty:
            return m.iloc[0]
    return None


def fetch_and_process(url, report_type):
    print(f"⏳ Downloading {report_type} (No Headers Mode)...")
    headers = {"User-Agent": "Mozilla/5.0"}
    extracted = {}
    
    try:
        r = requests.get(url, headers=headers, timeout=30)
        
        # Read without header (header=None) so the first row is data, not names
        df = pd.read_csv(io.StringIO(r.text), header=None, low_memory=False, on_bad_lines='skip')
        
        idx_name = 0
        idx_date = 2
        c = COLUMNS[report_type]
        idx_oi, idx_doi = c["oi"], c["doi"]
        idx_long, idx_short = c["long"], c["short"]
        idx_dlong, idx_dshort = c["dlong"], c["dshort"]

        # Filter for Latest Date
        df[idx_date] = pd.to_datetime(df[idx_date], errors='coerce')
        latest_date = df[idx_date].max()
        print(f"   📅 {report_type} Date: {latest_date.date()}")
        df = df[df[idx_date] == latest_date]
        
        # Convert Name to Uppercase
        df[idx_name] = df[idx_name].astype(str).str.upper().str.strip()
        
        print(f"   🔍 Scanning {report_type}...")

        for symbol, prefixes in ASSET_CONFIG.items():
            r = _find_row(df, prefixes, idx_name)
            if r is not None:
                try:
                    # EXTRACT BY INTEGER INDEX
                    longs = float(r.iloc[idx_long])
                    shorts = float(r.iloc[idx_short])
                    d_long = float(r.iloc[idx_dlong])
                    d_short = float(r.iloc[idx_dshort])
                    oi = float(r.iloc[idx_oi])
                    d_oi = float(r.iloc[idx_doi])

                    # Math
                    net = longs - shorts
                    total = longs + shorts
                    l_pct = (longs / total * 100) if total > 0 else 0
                    s_pct = (shorts / total * 100) if total > 0 else 0
                    net_chg = (net / oi * 100) if oi > 0 else 0

                    extracted[symbol] = {
                        "long_pos": longs, "short_pos": shorts,
                        "change_long": d_long, "change_short": d_short,
                        "long_pct": l_pct, "short_pct": s_pct,
                        "net_pct": net_chg, "net_pos": net,
                        "open_int": oi, "change_oi": d_oi,
                        "report_date": str(latest_date.date()),
                    }
                except (ValueError, TypeError, IndexError):
                    pass
        
        print(f"   ✅ Found {len(extracted)} assets in {report_type}")
        return extracted

    except Exception as e:
        print(f"   ❌ Error in {report_type}: {e}")
        return {}

def update_cot_data():
    all_data = {}
    
    # 1. COMMODITIES
    c_data = fetch_and_process("https://www.cftc.gov/dea/newcot/f_disagg.txt", "Commodities")
    all_data.update(c_data)
    
    # 2. FINANCIALS
    f_data = fetch_and_process("https://www.cftc.gov/dea/newcot/FinFutWk.txt", "Financials")
    all_data.update(f_data)

    if all_data:
        with open("cot_live.json", "w") as f:
            json.dump(all_data, f)
        print(f"✅ SUCCESS! Saved {len(all_data)} assets.")
        return True
    print("❌ Fatal: No assets found.")
    return False

if __name__ == "__main__":
    update_cot_data()