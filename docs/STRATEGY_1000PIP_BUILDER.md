# "1000 Pip Builder" — experimental setup (DISABLED by default)

**Status: research only. Not enabled, not a proven system. Backtest is NEGATIVE — do not swap it in.**
`setups.pip_builder.enabled: false` in `strategy_config.yaml`. The old `smc_sweep` setup is untouched.

## Rules implemented (`strategy/setups/pip_builder.py`)
Forex only. Parameters marked *(assumed)* were not published by the method's author — they are guesses.
1. **Trend**: Daily AND 4H structure agree (confirmed swing HH+HL = up, LH+LL = down); otherwise skip.
2. **Location (1H)**: S/R *zone* = cluster (≥2 swing points) of 1H pivots, width 0.3×ATR(14) *(assumed)*, or 1H Bollinger (SMA20, 2σ) touch; buys only at support/lower band in uptrend, sells at resistance/upper band in downtrend; broken-zone **retest** counts.
3. **Trigger (5m/15m)**, only at the location: double bottom/top (entry = neckline break) or engulfing (close beyond previous high/low).
4. **Entry**: close of the trigger bar.
5. **SL**: pattern extreme ± 1.5 pips *(assumed)*; reject if > 0.5×1H ATR or < 3 pips.
6. **TP**: nearest prior 1H swing / opposite zone edge / opposite band; skip if < 10 pips or R:R < 1.0 *(assumed)*. Optional `tp1_pips`.
7. **Filters**: ±30 min news blackout; ATR sanity TP ≤ 2.5×1H ATR *(assumed)*.
8. **Pairs**: NZD/USD, GBP/USD, USD/CAD, EUR/USD, EUR/JPY, GBP/JPY (+USD/JPY, where old signals clustered).

**News**: no free historical calendar exists. The backtest and live fallback use a *static rule* (US NFP = first Friday 08:30 New York, DST-aware) plus optional `news.events_utc` and an optional live feed (`news.use_feed`). CPI/GDP/central-bank events are **not** blocked in the backtest.

## Also shipped
* `risk_per_trade` config (account size, risk %, lot size from SL pips; shown in Telegram alerts and the log) — `enabled: false` until the owner sets numbers. JPY-cross pip value uses `usdjpy_ref` (approximation).
* `signal_log.csv` (`strategy/signal_log.py`): every alert + TP/SL/expiry result, viewable/downloadable in the Dashboard tab ("🧾 SIGNAL LOG"). Render's free disk is ephemeral → resets on redeploy.
* "Not financial advice" notice at the bottom of the app and in the log panel (Telegram alerts already carried it).
* Engine: per-candidate `min_rr` / `keep_target` / risk limits (so a structural TP isn't overwritten by the 1.5R reprice); symbols with no enabled setup are no longer fetched; `1d` frame added.

## Backtest (`scripts/backtest_pip_builder.py`, data `scripts/fetch_histdata.py`)
* **Data**: HistData.com free 1-minute BID bars, 2023-01 → 2026-09 (≈3.7 years, 7 pairs). yfinance was not used (60-day 5m limit); Dukascopy rate-limited. HistData stamps are New York local time (verified via week-open 17:00 and NFP 08:30). 5m/15m/1H/4H/Daily derived from 1m with the live code.
* **Method**: every closed 5m bar, closed candles only, live setup code; entry 5 minutes after the trigger close (live scan latency) with live drift/risk checks; exits walked on 1-minute bars; SL+TP in the same bar = loss; SELL stops/targets on ask; spread per pair assumed (EURUSD 0.8, GBPUSD 1.0, USDJPY 1.0, NZDUSD 1.4, USDCAD 1.4, EURJPY 1.8, GBPJPY 2.5 pips); trades still open after 48h are closed at market.
* "Raw" = one open position per pair, no caps. "Gated" = live engine gates (daily cap 6, 2/symbol, cooldowns, correlation, dedupe).

### Result — spec defaults (all 7 pairs, 3.7 yrs)
| | Trades | /day (cal / weekday) | Win rate | Avg R | Net R | Net pips | Max DD (R) | PF | Avg R 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| Raw | 845 | 0.63 / 0.89 | 20.5% (BE 27.9%) | −0.26 | −220 | −1434 | 238 | 0.67 | −0.37…−0.15 |
| Gated (live rules) | 330 | 0.25 / 0.35 | 19.4% | −0.29 | −96 | −442 | 100 | 0.64 | −0.46…−0.13 |
| Old smc_sweep, same data/costs, raw | 544 | 0.41 | 30.0% (BE 33.8%) | −0.11 | −58 | −1357 | 102 | 0.85 | −0.22…+0.01 |
| Old smc_sweep, gated | 418 | 0.31 | 27.8% | −0.18 | −74 | −1284 | 105 | 0.75 | −0.31…−0.05 |

Half split (raw): first half 392 trades, 23.2% WR, −0.18R (−70R); second half 453 trades, 18.1% WR, −0.33R (−151R). By year (avg R): 2023 −0.09, 2024 −0.31, 2025 −0.29, 2026 −0.36. Worse in the more recent data.

Per pair (raw): EURJPY n184 −0.25R · GBPJPY n192 −0.18R · USDJPY n172 −0.14R · GBPUSD n120 −0.13R · USDCAD n63 −0.48R · EURUSD n78 −0.56R · NZDUSD n36 −0.78R. **Every pair is negative**; the best gated pair (GBPJPY, +0.20R, n55, CI −0.26…+0.69) is noise-sized.

Cost sensitivity: **zero spread → −0.006R (breakeven)**; 1× spread → −0.26R; 2× → −0.37R. The method has no edge before costs, and its 5–8 pip stops make costs ≈ 15–25% of risk.

Trigger mix: 827 of 845 trades are engulfing candles; double top/bottom patterns are rare (16 trades) — too few to judge (double top +0.64R on n=7 is not evidence).

### Variants (one factor at a time; raw; avg R all / H1 / H2; zero-cost avg R)
All 16 are negative net of costs in both halves; none is robust. Best: `min_touches_1` −0.14R (n1276), `sl_buffer 2.0p` −0.20R, `zone_width 0.5` −0.20R, London/NY hours only −0.20R (n442), `tp_max_atr 4` worst −0.31R, 15m-only −0.38R, TP1@10p half-size −0.26R (WR 28% but same expectancy). Full table: `reports/backtest_pip_builder_variants.json`, trades: `reports/backtest_pip_builder_trades_spec_default_*.csv`, old-strategy comparison: `reports/backtest_pip_builder_old_confluence.json`.
Because everything is negative, no variant is "selected"; picking the least-bad one would be overfitting.

## Caveats
Spreads are assumed typical retail values; no slippage/swap; BID-only bars; HistData minute bars have gaps; static news rule only; trigger/zone definitions are one reasonable reading of an informal method; entry latency modelled as 5 min; the old strategy's earlier "+4R over 51 days" (13 markets incl. indices/gold, yfinance) is not comparable to this FX-only 3.7-year run, where it is also negative (−0.11R raw).

## Recommendation
**Do not swap it in.** Net of realistic costs it loses ≈0.26R per trade with no pair, half or year in profit (zero-cost it's just breakeven). Keep it disabled. If the owner wants to keep exploring: lower-cost execution (raw-spread account), wider-stop higher-timeframe variants, or a proper news calendar are the next honest experiments. Enable only by setting `setups.pip_builder.enabled: true`.
