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

## Telegram
Trade alerts (setup, score, checklist, entry/SL/TP, R:R) + one SESSION OPEN + one daily summary at close. Startup ping once per deploy. Scan updates off (`telegram.scan_updates`). Data errors at most once per symbol/interval/day.

## State
`monitor_state.json` is keyed by UTC date. Missing, old-format or yesterday's file → fresh day budget (never re-fires old alerts). Old setups can't re-alert after a restart because signals must come from a candle that closed within the last 20 minutes.

## Backtest
```
python scripts/backtest_confluence.py --days 30 --live --out reports/my_run
python scripts/backtest_confluence.py --set risk.tp_rr=1.5 --set setups.orb_open.enabled=true
```
