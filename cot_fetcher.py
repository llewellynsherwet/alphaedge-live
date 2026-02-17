import pandas as pd
import requests
import io
import json
import datetime

# --- ASSET CONFIGURATION ---
ASSET_CONFIG = {
    # FINANCIALS (Currencies, Indices, Crypto)
    "CAD": ["CANADIAN", "DOLLAR"],
    "AUD": ["AUSTRALIAN", "DOLLAR"],
    "USD": ["USD", "INDEX"],
    "ZAR": ["SOUTH", "AFRICAN", "RAND"],
    "EUR": ["EURO", "FX"],
    "NZD": ["NZ", "DOLLAR"],
    "JPY": ["JAPANESE", "YEN"],
    "GBP": ["BRITISH", "POUND"],
    "CHF": ["SWISS", "FRANC"],
    "BTC": ["BITCOIN"],
    "NIKKEI": ["NIKKEI", "STOCK"],
    "DOW": ["DJIA"],
    "RUSSELL": ["RUSSELL", "2000"],
    "SPX": ["S&P", "500"],
    "NASDAQ": ["NASDAQ", "100"],
    "US10T": ["10-YEAR", "TREASURY"],
    
    # COMMODITIES (Metals, Energy)
    "SILVER": ["SILVER"],
    "Gold": ["GOLD"],
    "PLATINUM": ["PLATINUM"],
    "COPPER": ["COPPER"],
    "USOil": ["CRUDE", "OIL", "LIGHT"],
}

def fetch_and_process(url, report_type):
    print(f"⏳ Downloading {report_type} (No Headers Mode)...")
    headers = {"User-Agent": "Mozilla/5.0"}
    extracted = {}
    
    try:
        r = requests.get(url, headers=headers, timeout=30)
        
        # Read without header (header=None) so the first row is data, not names
        df = pd.read_csv(io.StringIO(r.text), header=None, low_memory=False, on_bad_lines='skip')
        
        # --- COLUMN MAPPING (Based on your Debug Output) ---
        # 0: Name, 2: Date, 7: Open Interest, 24: Change in OI
        
        idx_name = 0
        idx_date = 2
        idx_oi = 7
        idx_doi = 24
        
        if report_type == "Commodities":
            # Disaggregated Report (Wheat Example)
            # 12: Managed Money Long, 13: Managed Money Short
            idx_long = 12
            idx_short = 13
            # Calculated Offsets for Change (Indices 29/30 based on +17 shift pattern)
            idx_dlong = 29
            idx_dshort = 30
            
        else: # Financials
            # TFF Report (CAD Example)
            # 14: Leveraged Funds Long, 15: Leveraged Funds Short
            idx_long = 14
            idx_short = 15
            # Calculated Offsets for Change
            idx_dlong = 31
            idx_dshort = 32

        # Filter for Latest Date
        df[idx_date] = pd.to_datetime(df[idx_date], errors='coerce')
        latest_date = df[idx_date].max()
        print(f"   📅 {report_type} Date: {latest_date.date()}")
        df = df[df[idx_date] == latest_date]
        
        # Convert Name to Uppercase
        df[idx_name] = df[idx_name].astype(str).str.upper()
        
        print(f"   🔍 Scanning {report_type}...")

        for symbol, keywords in ASSET_CONFIG.items():
            # Check keywords against Column 0 (Name)
            mask = df[idx_name].apply(lambda x: all(k in x for k in keywords))
            row = df[mask]
            
            if not row.empty:
                r = row.iloc[0]
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
                        "open_int": oi, "change_oi": d_oi
                    }
                except: pass
        
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
    else:
        print("❌ Fatal: No assets found.")

if __name__ == "__main__":
    update_cot_data()