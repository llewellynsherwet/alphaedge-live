#!/usr/bin/env python3
"""Download free 1-minute FX bars from HistData.com (generic ASCII M1, BID quotes,
timestamps are America/New_York local time (verified: week open 17:00, NFP 08:30)) and cache one parquet per pair (UTC index).

  pip install histdata
  python scripts/fetch_histdata.py --from-year 2023 --to 2026-09 [--pairs EURUSD,...]

Complete years are fetched as one yearly zip, the current year month-by-month.
Network only; never touches Telegram. Output: /workspace/bt_data/<PAIR>_1m.parquet
"""
import argparse, io, sys, time, zipfile
from pathlib import Path

import pandas as pd

OUT = Path("/workspace/bt_data")
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "USDCAD", "EURJPY", "GBPJPY"]


def _get(pair, year, month):
    from histdata import download_hist_data as dl
    from histdata.api import Platform, TimeFrame
    d = OUT / "hd"; d.mkdir(parents=True, exist_ok=True)
    kw = dict(year=str(year), pair=pair.lower(), platform=Platform.GENERIC_ASCII,
              time_frame=TimeFrame.ONE_MINUTE, output_directory=str(d))
    if month:
        kw["month"] = str(month)
    tag = f"{year}{int(month):02d}" if month else f"{year}"
    f = d / f"DAT_ASCII_{pair}_M1_{tag}.zip"
    for k in range(4):
        if f.exists():
            break
        try:
            dl(**kw)
        except Exception as e:
            print(f"  retry {pair} {tag}: {e!r}", file=sys.stderr); time.sleep(3 + 3 * k)
    return f


def _parse(f):
    with zipfile.ZipFile(f) as z:
        name = [n for n in z.namelist() if n.endswith(".csv")][0]
        df = pd.read_csv(z.open(name), sep=";", header=None, names=["ts", "Open", "High", "Low", "Close", "Volume"])
    idx = pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S")
    # HistData says "EST, no DST", but empirically (week open always 17:00, NFP spike always 08:30
    # in the raw stamps, all year) the stamps are New York LOCAL time incl. DST.
    df.index = idx.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    return df[df.index.notna()].drop(columns="ts")


def run(pair, y0, y1, m1):
    parts = []
    for y in range(y0, y1 + 1):
        if y < y1:
            f = _get(pair, y, None)
            if f.exists(): parts.append(_parse(f))
        else:
            for m in range(1, m1 + 1):
                f = _get(pair, y, m)
                if f.exists(): parts.append(_parse(f))
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.to_parquet(OUT / f"{pair}_1m.parquet")
    print(f"{pair}: {len(df)} 1m bars {df.index[0]} → {df.index[-1]}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2023)
    ap.add_argument("--to", default="2026-09", help="YYYY-MM last month to include")
    ap.add_argument("--pairs", default=",".join(PAIRS))
    a = ap.parse_args()
    y1, m1 = map(int, a.to.split("-"))
    OUT.mkdir(parents=True, exist_ok=True)
    for p in a.pairs.split(","):
        run(p, a.from_year, y1, m1)
