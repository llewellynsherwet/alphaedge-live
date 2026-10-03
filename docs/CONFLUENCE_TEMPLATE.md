# Confluence Day Template — how it works

## Files
| File | Purpose |
|------|---------|
| `strategy_config.yaml` | **All tunables.** Re-read every monitor loop (~5 min) — edit and the next scan uses it. Bad YAML → last good config keeps running (error in logs). |
| `strategy/engine.py` | Session gate (Mon–Fri 07–17 UTC), scan, ranking, gates (daily cap, per-symbol cap, cooldowns, dedupe, correlation), date-keyed state, Telegram formatting |
| `strategy/setups/smc_sweep.py` | Core: liquidity sweep → BOS with displacement → first retest of a fresh FVG (or strict OB) |
| `strategy/setups/orb_open.py` | NY Opening Range Breakout (pluggable; **disabled by default**) |
| `strategy/setups/vwap_pullback.py` | Session VWAP pullback on trend days (futures only — needs volume) |
| `strategy/checklist.py` | Per-setup 6-factor checklist scoring (weights / required flags from config) |
| `strategy/data.py` | yfinance fetch, **closed candles only**, 15m/4h resampling, backtest slicer |
| `scripts/backtest_confluence.py` | Replay backtest using the same setup + gate code as live |

## Strict definitions
- **Sweep**: wick through the most recent confirmed swing high/low, candle closes back inside; the swept extreme must hold afterwards.
- **BOS**: close beyond the most recent confirmed opposite swing after the sweep, with a displacement candle (body ≥ `displacement_atr` × ATR) in that leg.
- **FVG**: 3-candle imbalance inside the displacement leg, gap ≥ `min_fvg_atr` × ATR.
- **OB** (fallback): last opposite-colour candle in the leg **whose next candle closes beyond it**. Not "any opposite candle".
- Entry only on the **first** retest of the zone, on a closed candle; SL beyond the sweep extreme; TP = `tp_rr` × risk.

## Alert gates (live and backtest)
`min_rr` · setup `min_score` + `required` factors · signal age ≤ `max_signal_age_minutes` · dedupe `symbol|side|setup|zone` (kept for the day) · `daily_max_signals` · `per_symbol_max` · `cooldown_minutes` (also means one alert per scan at most) · `symbol_cooldown_minutes` · `correlation_groups`.
If several qualify at once they are ranked by score → R:R → symbol priority.

## Execution checks (live price at alert time) — `execution:` + per-symbol `quote:`
Why: Yahoo futures (YM=F, NQ=F, ES=F, GC=F) are ~10 min delayed and trade at a basis to the cash/CFD
price you actually execute (US30 ≈ −340 pts, NAS100 ≈ −270, SPX500 ≈ −60, XAUUSD ≈ −$30 vs futures),
and the old entry was the close of a 15m trigger candle that could already be 10–25 min old.

At alert time (`strategy/pricing.py`) every candidate is validated **before** the alert gates:
1. Fresh 1m data for the signal ticker + the live quote source (`quote.source: yf` e.g. `^DJI`, or
   `gold_api` for spot XAU). Reject if the feed is older than `max_data_age_minutes` or the live
   price older than `max_price_age_minutes`.
2. Reject if TP or SL already traded on 1m bars since the trigger candle closed (`reject_if_tp_sl_hit`),
   or the live price is already beyond SL/TP.
3. Reject if price moved toward TP by more than `max_drift_atr` × ATR or `max_drift_tp_frac` of the TP distance.
4. `entry_mode: market` → entry = live price; structural SL kept; `tp_on_reprice: keep_rr` re-places TP at
   `risk.tp_rr` × new risk (`keep_target` keeps the original TP). `min_rr` re-checked. `entry_mode: limit`
   keeps the zone entry and labels it LIMIT.
5. Levels are converted to the quote (cash/CFD) space by subtracting the measured basis; the Telegram
   message and dashboard show feed age, live price age, candle age and the basis used.

Note: the backtest does not apply these live checks, so live will emit somewhat fewer alerts than the
backtest. Your broker's CFD can still differ from the cash index by a few points (fair value/spread).

## Telegram
Trade alerts (setup, score, checklist, entry/SL/TP in cash/CFD price, R:R, data age) + TP/SL/expiry follow-ups + one SESSION OPEN + one daily summary at close. Startup ping once per deploy. Scan updates off (`telegram.scan_updates`). Data errors at most once per symbol/interval/day.

## Trade outcomes (TP / SL follow-ups) — `outcomes:` · `strategy/outcomes.py`
- Every trade alert that Telegram accepted is stored as an open trade (id, symbol, side, setup, entry/SL/TP,
  quote source + basis, sent time) under `trades.open` in `monitor_state.json`.
- Every monitor loop (5-min cadence, in and out of session) while markets trade (Sun 17:00 → Fri 17:00 New York),
  1m candles (5m fallback) since the alert are fetched in the **same price space as the alert**:
  spot FX → the yf ticker; `quote.source: yf` → the cash ticker (e.g. `^DJI`), with signal futures − stored basis
  filling minutes when the cash market is shut (that is how the entry was derived then);
  `quote.source: gold_api` → `GC=F` − stored basis plus the live gold-api spot print (gold-api has no candles).
- Candles are walked in order from the first bar starting at/after the alert; highs/lows count (wicks).
  TP and SL in the same candle → **SL** (conservative), and the message says so.
- No hit after `max_open_hours` (default 48 h wall-clock) → `⌛ EXPIRED` notice, marked at the last price before
  the deadline; tracking stops. Expired R is shown but not counted in the net R.
- A trade is moved to `trades.closed` and saved **before** the Telegram follow-up is sent, so it can only close once;
  an undelivered follow-up is retried on later loops (max 3 attempts).
- The session-close summary adds `Outcomes today: W / L / expired · net R · win rate` for results that closed today
  plus any not yet reported (e.g. overnight/weekend hits), and the count still open.
- Only runs where `TG_TOKEN`/`TG_CHAT_ID` are set (the Render worker). `outcomes.enabled: false` turns it off.

## State
`monitor_state.json` is keyed by UTC date. Missing, old-format or yesterday's file → fresh day budget (never re-fires old alerts). Old setups can't re-alert after a restart because signals must come from a candle that closed within the last 20 minutes.
The `trades` book (open trades + 14 days of results) is carried across the daily reset; it is lost only if the file itself is wiped (e.g. Render free-disk redeploy).

## Backtest
```
python scripts/backtest_confluence.py --days 30 --live --out reports/my_run
python scripts/backtest_confluence.py --set risk.tp_rr=1.5 --set setups.orb_open.enabled=true
```
