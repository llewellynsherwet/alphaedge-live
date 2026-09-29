# Live chart & Trading Station

## Immersive chart (Dashboard tab)
TradingView Advanced Chart widget, 820 px tall, full width: top toolbar, drawing tools (left
toolbar), indicators, symbol search (`allow_symbol_change`), date ranges, details/hotlist/calendar
side panel, save-image, dark theme, 1h default, UTC. Bar above the chart: current symbol,
**⛶ Fullscreen** (fullscreens the chart iframe; CSS overlay fallback) and **Open full chart on
TradingView ↗** (affiliate link; drawings made there save to the user's TradingView account).

## Why drawings used to vanish
Streamlit re-created the chart iframe every time its HTML changed (the symbol was baked into the
HTML), so switching pairs destroyed the chart and everything drawn on it.

## How it works now (`ui_widgets.py`)
- `persistent_chart_html()` is a **constant** HTML string rendered in its own `st.container()` at a
  fixed position, so Streamlit never re-creates that iframe on reruns.
- Inside it, one TradingView chart per visited symbol (max 10, least-recently-used evicted), stacked
  and shown/hidden, never destroyed on switch.
- The sidebar selection reaches it through a hidden "bridge" iframe (`chart_bridge_html`) that calls
  `AE_CHART.show(symbol)` in the chart frame (same origin) and writes `sessionStorage` as a fallback.

| Action | Drawings / indicators / interval / zoom |
|---|---|
| Switch pair in sidebar and come back | **kept** (same chart instance, verified with Playwright) |
| Switch Streamlit tabs and come back | **kept** |
| Any other rerun (button, chat, refresh data) | **kept** |
| Fullscreen on/off | **kept** |
| Page refresh / new tab / redeploy / Render restart | **lost** (the free embed has no storage) |
| More than 10 different pairs in one session | oldest unused pair's chart is dropped |
| Changing symbol with the widget's own search box | stays in that pair's chart instance; use the sidebar to keep per-pair drawings |

For permanent drawings use **Open full chart on TradingView ↗** (saved to the user's TradingView account).

## Trading Station
`station_html()` plays YouTube with an ordered fallback list (on player error or a stream that never
starts while visible → next source), then a plain radio stream. **Next ▶** skips/retries.
- Lofi: `rFZHOHl-L8A` (Lofi Girl "lofi hip hop radio 📚", new since Sep 2026), `JD-kMIpDfnY`,
  `CwPCy1GLS38`, `1Tl2FtV06qo` → radio `https://stream.laut.fm/lofi`
- Jazz: `Dx5qFachd3A`, `E2vONfzoyRI`, `A8jDx9TLMQc` → radio Jazz Radio (infomaniak)
The old lofi ID `jfKfPfyJRdk` ended ("This live stream recording is not available", YouTube error 150).
Update IDs in `STATIONS_YT` in `app.py` if Lofi Girl restarts a stream again.
