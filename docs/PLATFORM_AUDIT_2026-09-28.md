# Platform audit — 2026-09-28 (~18:00 SAST)

Method: `streamlit run app.py` headless (MONITOR_MODE=off, Telegram vars unset) + Playwright/Chrome
screenshots of every tab and sidebar section, browser console/page errors and failed requests;
same audit against https://alphaedge-live-1.onrender.com (HTTP 200, `/_stcore/health` = ok).
Streamlit AppTest: 0 exceptions on all 8 tabs. Screenshots: `audit_screens/` (`local_*`, `render_*`).

| Section | Status | Notes |
|---|---|---|
| Dashboard heatmap | working → improved | 39 rows live. Prices now use sensible decimals (was 4 dp on indices); futures rows tagged "FUTURES ~10m". |
| Engine signal metrics | working → improved | Entry/TP/SL formatted per instrument; reason shows data age + basis. |
| TradingView main chart | **fixed** | `interval:"H1"` is invalid → widget fell back to 1D; now `"60"`. Indices now OANDA CFD (US30USD/NAS100USD/SPX500USD) to match repriced alerts. |
| TradingView popup | **fixed** | Same interval fix; `tv_promo_2.mp4` was HEVC (Chrome "Video source error", MEDIA_ERR_SRC_NOT_SUPPORTED) → re-encoded H.264. |
| Trade Station (sidebar audio) | working | Lofi + Chillout Jazz YouTube embeds load; Pop Radio (181.fm) and Hip Hop (cdnstream) `<audio>` readyState 4 and playing. |
| Live Financial TV | working | YouTube live embed loads (shows fallback text when a channel isn't live). |
| Partner videos (Exness/GOAT) | working | H.264, play. |
| COT tab | **fixed** | Commodities columns were off by one block: "Longs" = Swap spread, "Shorts" = Managed-Money long, "Δ Long" = MM long (old-crop). Now MM long/short (13/14), ΔMM (61/62), ΔOI (55), verified against CFTC header files. Exact market-name prefixes (no MICRO/ICE mismatches: WTI now NYMEX WTI-Physical; ZAR and US10T now found). Report date shown. |
| Sentiment (TA gauges) | working on Render | Locally shows "No data here yet" only because TradingView's scanner rejects a localhost origin (CORS); not an app bug. |
| Indices / Currency matrix / News / Calendar | working | TradingView widgets render. |
| Community chat | working | sqlite chat loads. |
| Footer ticker tape | working | |
