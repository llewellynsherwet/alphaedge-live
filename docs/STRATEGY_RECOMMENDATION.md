# AlphaEdge Strategy Upgrade — Audit, Research & Recommendation

**Repo:** llewellynsherwet/alphaedge-live  
**HEAD:** 7f6f6ee  
**Date:** 2026-09-28 (Africa/Johannesburg)  
**Status:** Recommendation only — no code push/merge

---

## 1) Code audit — how signals fire today

### Architecture
| Piece | Role |
|--------|------|
| `monitor_worker.py` | Boots on Render; `exec`s `app.py` above `# --- TRADINGVIEW POP-UP ---`; starts monitor |
| `render.yaml` | `python monitor_worker.py & MONITOR_MODE=off streamlit run app.py`; wipes `monitor_state.json` + `startup_ping.flag` on each start |
| `app.py` `_monitor_loop` | Every **300s**, if in session: scan **all** `TICKER_MAP` keys via `_signal_engine` |
| `_signal_engine` | Session gate 07–17 UTC → `US 30` → `_us30_open_strategy`; else → `_smc_4h_strategy` |
| Legacy (UI-unused for TG) | `_forex_signal`, `_commodity_index_signal`, `get_scalp_signal` — **not** called by the Telegram monitor |

### Instruments scanned (~20)
FX: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD, USD/ZAR, GBP/ZAR  
Indices: S&P 500 (`ES=F`), NASDAQ 100 (`NQ=F`), US 30 (`YM=F`), VIX  
Commodities: GOLD, SILVER, OIL, NAT GAS  
Crypto: BTC, ETH, SOL

### Strategies in live path

**A. US30 Open (`_us30_open_strategy`) — only `"US 30"`**
- Window: **07:30–10:30 America/New_York**, weekdays only
- Layers (need **≥3 same-direction** biases): L1 pre-market box (08:30–09:30 NY on 5m), L2 DOW stock EMA21 bias, L3 DXY inverse, L4 double top/bottom 30m, L5 4H HH/HL or LH/LL + EMA21
- Pre-open: WAIT with bias text; post-open: BUY/SELL with ATR-based SL/TP, target ~**2.5R**
- Timeframes: 5m, 1h (DOW/DXY), 30m, 4h

**B. SMC 4H (`_smc_4h_strategy`) — every other symbol**
- Closed candles only on 4h + 1h (forming bar stripped)
- Need **score ≥ 4/5**: L1 structure (HH+HL / LH+LL; *partial* still sets direction), L2 last opposing 4h candle as “order block”, L3 1H EMA9/21 align, L4 RSI zone (40–65 long / 35–60 short), L5 MACD hist rising **or** >0 (long) / falling **or** <0 (short)
- SL: OB edge ± 0.3 ATR; reject if risk > 7% of price; TP `max(2.5R, 3×ATR)`

### Session / trading hours (`get_session_info`)
| UTC window | Label | `in_kz` |
|------------|--------|--------|
| 07:00–10:00 | London Open | True |
| 10:00–12:00 | London Continuation | True |
| 12:00–16:00 | NY / London Overlap | True |
| 16:00–17:00 | New York Close | True |
| else | OFF-SESSION | False |

**Gaps:** no weekday/weekend check on the global session gate (US30 has its own weekday check); crypto/FX can still be marked “in session” on Saturday/Sunday 07–17 UTC.

### Telegram send sites (all spam-relevant)
1. **Trade signals** — `_monitor_loop` when `sig` not WAIT and `sig != prev_sig`
2. **SCAN UPDATE** — every 6th in-session loop (~every 30 min)
3. **SESSION OPEN / CLOSED** — on `in_kz` edge
4. **STARTUP** — once per process (`startup_ping.flag`)
5. **DATA ERROR** — once per symbol/interval per process (`_log_data_error`)

### Dedupe / cooldown / caps (current)
| Control | Present? |
|---------|----------|
| Per-symbol last-signal string | Yes (`monitor_state.json` `last_signals`) |
| Cooldown (minutes) after alert | **No** |
| Daily max signals | **No** |
| Min R:R hard gate before send | Soft only (strategies *aim* for 2.5R; no reject if computed RR low) |
| Symbol allowlist for alerts | **No** — all ~20 |
| Confluence score in monitor | Only inside strategies; monitor does not re-check |
| Prevent WAIT→BUY→WAIT→BUY re-fire | **No** — WAIT clears `last_signals`, same BUY can re-alert |
| Survive redeploy without re-spam | **No** — startCommand deletes state; `start_monitor` also removes state file |

Observed `monitor_state.json` already held many concurrent directions (EUR/USD SELL, GBP/USD BUY, …) — consistent with multi-asset firing in one session.

---

## 2) WHY it spams Telegram

1. **Universe too wide:** ~20 assets × every 5 minutes during a 10-hour session ≈ **~2,400 strategy evaluations/day**. Even a modest hit-rate floods chat.
2. **Weak SMC filters:** 4/5 is easy — OB almost always found in last 8 bars; RSI bands are wide; MACD accepts “positive OR rising”; partial structure still chooses a side. Many symbols can qualify together.
3. **State machine allows re-entry spam:** `BUY` → later `WAIT` resets key → same `BUY` fires again when layers flicker (4h/1h closed-bar changes, yfinance noise).
4. **No daily cap / no cooldown:** nothing stops 15+ alerts in one London–NY day.
5. **Noise messages:** 30-min SCAN UPDATE + open/close + startup + data errors compete with real trades.
6. **Restart amnesia:** wiping `monitor_state.json` on deploy re-opens every “new” signal.
7. **Dual-direction portfolio:** no “one bias / correlated pairs” rule — EURUSD BUY and USDCHF BUY (etc.) can both alert.
8. **Legacy comment mismatch:** monitor comment still says “Finnhub / 4 layers”; live path is yfinance + 5-layer SMC — filters feel stricter in comments than they are in code.

---

## 3) Research — 5 selective day-trade candidates

Sources consulted (reputable / practitioner + research-style): TradeAlgo ORB guides, ORB Setups backtests, Concretum/SFI ORB paper, DayTradingToolkit VWAP, AffordableIndicators VWAP futures, LiquidityScan / ICT confluence, Backtrex SMC entries, EMA 9/21 practitioner guides, confluence scoring literature.

**Caveat:** published “65–80% win rate” claims are **conditional on heavy selectivity** (3–4 independent confluences, session filters, daily caps). Raw ORB/EMA alone often sits ~50–60%. Treat 65–80% as a **design target via filters**, not a guarantee.

### Candidate 1 — Opening Range Breakout (ORB)
- **Rules:** Build OR from first 15–30 min after cash open (or London open for FX). Enter on **closed** break of OR high/low with volume ≥1.5× OR avg; SL mid-range or opposite side; TP 1.5–2× range height; optional gap-direction-only.
- **Quality filters:** VIX/vol regime, relative volume, one trade per symbol/session, skip if OR too wide vs ATR.
- **Why selective WR can be high:** Volume + regime filters cut false breaks; 15–30m OR reduces noise vs 5m.
- **Bot fit:** Natural upgrade of existing US30 pre-market box; config: `orb_minutes`, `session_anchor`, `min_rel_vol`.

### Candidate 2 — Session VWAP pullback (trend day)
- **Rules:** After clear separation above/below session VWAP, wait first (or confirmed) pullback to VWAP on **declining** volume; enter on close reclaiming VWAP; SL beyond VWAP/swing; TP prior extreme or ≥2R.
- **Quality filters:** Trade only trend days (price held one side of VWAP N bars); avoid midday lull; require VWAP slope + optional 9 EMA confluence.
- **Why selective WR can be high:** Institutional benchmark + volume signature; few setups/day per symbol.
- **Bot fit:** yfinance OHLCV can approximate session VWAP for futures/indices; FX tick-volume is weaker — prefer indices/commodities or session-anchored VWAP.

### Candidate 3 — Liquidity sweep + BOS/MSS (ICT/SMC A-tier) ★ recommended core
- **Rules (independent stack):** (1) HTF bias 4H/D, (2) premium/discount vs dealing range, (3) sweep of equal highs/lows or prior swing, (4) MSS/BOS on 15m/5m, (5) entry on OB **or** FVG (count as **one** PD-array), (6) kill-zone only.
- **Quality filters:** Require **≥4 independent** checklist points; kill-zone only; min R:R 1:2.5; no double-count OB+FVG from same candle.
- **Why selective WR can be high:** Confluence literature: 4-signal thresholds often map to much higher observed WR than 1–2 signals, with far fewer trades.
- **Bot fit:** Closest to current SMC code; replace loose layers with real sweep/MSS + config checklist. Reuses session windows already in app.

### Candidate 4 — EMA trend pullback (9/21 + HTF)
- **Rules:** HTF (1H/4H) trend via EMA50/200; on 5m/15m wait pullback into 9–21 EMA zone; confirmation candle; SL beyond swing/21; min 2R.
- **Quality filters:** VWAP side filter; ATR expansion; no trade if EMAs flat; session hours only.
- **Why selective WR can be high:** Practitioner reports ~55–62% with VWAP filter and ~2–3 signals/session/symbol — raise threshold further for 5–6/day **portfolio** total.
- **Bot fit:** Easy to code; already partially present in legacy `_forex_signal` — but alone it **overtrades** unless capped hard.

### Candidate 5 — Hybrid “template” (ORB morning + SMC/VWAP continuation)
- **Rules:** Morning: one ORB attempt per index; rest of day: only A-tier sweep+BOS or VWAP pullback with HTF align.
- **Quality filters:** Global daily max 5–6; per-symbol max 1–2; cooldown; correlated-pair mutex.
- **Bot fit:** Best operational match for “flexible live template” — one engine, multiple setup types as config plugins.

---

## 4) Recommended PRIMARY design — **Confluence Day Template (CDT)**

**Name:** Confluence Day Template  
**Primary setup family:** Liquidity sweep + BOS/MSS with HTF bias (Candidate 3), with optional plugin slots for ORB (US30 morning) and VWAP pullback.  
**Goal:** ~**5–6 Telegram trade alerts/day** during existing London–NY hours, high-selectivity checklist aiming at **65–80% quality band** (validate live; do not promise).

### Design principles (“live and flexible”)
- **Config-driven:** symbols, sessions, checklist weights, min score, daily max, cooldown, min R:R live in `strategy_config.yaml` (or JSON) — **no core rewrite** to retune.
- **Strategy plugins:** each setup implements `evaluate(symbol, bars, cfg) -> Signal|None`.
- **Engine owns:** session gate, weekday, ranking, dedupe, cooldown, daily budget, Telegram formatting.
- **Checklist is data:** toggle/require factors without changing Python if only thresholds change.

### Concrete quality gates (expected ~5–6/day)

| Gate | Default |
|------|---------|
| Session | Keep 07–17 UTC; add **Mon–Fri only**; optional NY kill-zone tighten for indices (13:30–16:00 UTC summer / DST-aware NY) |
| Alert universe | Start with **6–8** symbols e.g. US30, ES, NQ, EURUSD, GBPUSD, XAU, BTC (config list) |
| Min independent confluence | **≥ 4 / 6** checklist points (config) |
| Checklist (SMC core) | HTF bias · premium/discount · liquidity sweep · MSS/BOS · PD-array (OB **or** FVG) · kill-zone |
| Min R:R | **≥ 2.5** or discard |
| Per-symbol max / day | **1** (ORB morning exception: +1 continuation later = 2 max) |
| Global daily max | **6** trade alerts |
| Cooldown | **45–60 min** global between trade alerts; **120 min** same symbol |
| Dedupe key | `(symbol, side, setup_id, entry_zone_rounded)` sticky until TP/SL invalidation or session end — **do not clear on WAIT flicker** |
| Correlated mutex | Block second alert if highly correlated pair already alerted same side (e.g. EURUSD+GBPUSD) |
| Rank if many qualify | Prefer higher score, then better R:R, then priority symbol list — take top until daily budget filled |
| Noise Telegram | Disable SCAN UPDATE by default; keep one session open + one close; rate-limit DATA ERROR |

### Illustrative config sketch

```yaml
# strategy_config.yaml
session:
  timezone_display: "UTC"
  windows:
    - {start: "07:00", end: "17:00", name: "LONDON_NY"}
  weekdays_only: true

symbols:
  - {id: "US 30", yf: "YM=F", priority: 1, setups: ["orb_open", "smc_sweep"]}
  - {id: "S&P 500", yf: "ES=F", priority: 2, setups: ["smc_sweep", "vwap_pb"]}
  - {id: "EUR/USD", yf: "EURUSD=X", priority: 3, setups: ["smc_sweep"]}
  # ...

risk:
  min_rr: 2.5
  daily_max_signals: 6
  per_symbol_max: 1
  cooldown_minutes: 45
  symbol_cooldown_minutes: 120

confluence:
  min_score: 4
  factors:
    htf_bias: {required: true, weight: 1}
    premium_discount: {required: true, weight: 1}
    liquidity_sweep: {required: true, weight: 1}
    mss_bos: {required: true, weight: 1}
    pd_array: {required: false, weight: 1}   # OB or FVG, not both
    kill_zone: {required: true, weight: 1}

telegram:
  trade_alerts: true
  session_open_close: true
  scan_updates: false
  startup_ping: true
  data_errors: true
```

### Module sketch (files to add)

```
strategy/
  __init__.py
  engine.py          # session, rank, caps, cooldown, dedupe
  checklist.py       # score factors from cfg
  setups/
    smc_sweep.py     # primary
    orb_open.py      # US30 / indices morning
    vwap_pullback.py # optional
  config_loader.py
strategy_config.yaml
```

`app.py` keeps UI + Telegram transport; monitor calls `engine.scan()` instead of inlined `_smc_4h_strategy` / `_us30_open_strategy`.

---

## 5) Implementation plan (do not push yet)

### Phase A — Stop the spam (fast, low risk)
1. Alert allowlist (6–8 symbols) in config / env.
2. `daily_max_signals: 6` + persist count in `monitor_state.json` (date-keyed).
3. Cooldown + sticky dedupe key (stop WAIT flicker re-fire).
4. Turn off SCAN UPDATE (or make hourly / opt-in).
5. Weekday filter on `get_session_info`.
6. Stop deleting `last_signals` usefulness on every deploy *or* migrate dedupe to date+hash so restarts don’t re-blast.

**Touch:** `app.py` (`_monitor_loop`, `get_session_info`, `_write_state`), `render.yaml` (revisit state wipe), optionally `monitor_worker.py` (unchanged if engine stays in app).

### Phase B — Strategy template
1. Extract indicators (`_calc_rsi/atr/macd`, candle fetch) to shared helpers.
2. Implement `smc_sweep` with real sweep + MSS detection (replace loose OB/RSI/MACD stack as primary gate).
3. Port US30 box logic into `orb_open` with confluence + daily budget.
4. Wire `_signal_engine` → `engine.evaluate`.
5. Streamlit metrics: show checklist score + remaining daily budget.

### Phase C — Validate
1. Paper / log-only mode: write candidates to JSON without Telegram for 1–2 weeks.
2. Tune `min_score` / universe until median ~5–6 alerts/day.
3. Only then enable Telegram trade alerts.

### File / function change list

| File | Functions / areas | Change |
|------|-------------------|--------|
| `app.py` | `get_session_info`, `_next_session` | Weekdays; optional DST-aware labels |
| `app.py` | `_us30_open_strategy` | Move → `strategy/setups/orb_open.py` or thin wrapper |
| `app.py` | `_smc_4h_strategy` | Replace with / delegate to `smc_sweep` |
| `app.py` | `_signal_engine` | Call strategy engine + config |
| `app.py` | `_monitor_loop`, `_build_tg_message`, `_read/_write_state` | Caps, cooldown, sticky dedupe, quieter TG |
| `app.py` | `_forex_signal`, `_commodity_index_signal`, `get_scalp_signal` | Mark deprecated or remove from mental model (not TG path) |
| `monitor_worker.py` | `main` | Keep; ensure it loads new modules |
| `render.yaml` | `startCommand` | Avoid wiping signal budget mid-day; wipe only flags that must reset |
| **NEW** `strategy_config.yaml` | — | Tunables |
| **NEW** `strategy/engine.py` | `scan`, `can_emit`, `rank` | Core template |
| **NEW** `strategy/checklist.py` | `score` | Config checklist |
| **NEW** `strategy/setups/*.py` | `evaluate` | Plugins |

### Success criteria mapping
| Criterion | How we meet it |
|-----------|----------------|
| Audit of spam causes | §1–2 above |
| Researched options | §3 (5 candidates) |
| One concrete template | §4 CDT |
| ~5–6/day | daily_max + allowlist + min_score 4 + cooldowns |
| Flexible live | YAML checklist + plugin setups |
| No push/merge | This doc only |

---

## 6) Risks / honesty notes
- **65–80% win rate is aspirational** under A-tier confluence; require journaling to verify on this data feed (yfinance lag/gaps).
- FX “volume” on yfinance is tick-ish — prefer structure/session filters over volume for FX; volume gates better on YM/ES/NQ/GC.
- Reducing symbols reduces spam but also opportunity — start tight, expand only if under ~3 alerts/day for a week.
