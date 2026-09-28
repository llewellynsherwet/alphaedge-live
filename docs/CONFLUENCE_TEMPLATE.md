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
Trade alerts (setup, score, checklist, entry/SL/TP in cash/CFD price, R:R, data age) + one SESSION OPEN + one daily summary at close. Startup ping once per deploy. Scan updates off (`telegram.scan_updates`). Data errors at most once per symbol/interval/day.

## State
`monitor_state.json` is keyed by UTC date. Missing, old-format or yesterday's file → fresh day budget (never re-fires old alerts). Old setups can't re-alert after a restart because signals must come from a candle that closed within the last 20 minutes.

## Backtest
```
python scripts/backtest_confluence.py --days 30 --live --out reports/my_run
python scripts/backtest_confluence.py --set risk.tp_rr=1.5 --set setups.orb_open.enabled=true
```
