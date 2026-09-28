# Backtest — shipped config (2026-09-28)

Session days: 30 (2026-08-18 → 2026-09-28), 8 symbols, 5-minute replay on closed candles, same gates as live.

| Metric | Value |
|---|---|
| Alerts | 16 |
| Alerts/day mean · median · max | 0.53 · 0.0 · 2 |
| Days with 0 / 1 / 2 alerts | 18 / 8 / 4 |
| Win / loss | 5 / 11 |
| Win rate (TP 2.5R before SL) | 31.2% |
| Break-even win rate at 2.5R | 28.6% |
| Expectancy | 0.094 R/trade |

## Variants tested (same data)

| Variant | Alerts/day | Win % | Break-even % | Exp. R |
|---|---|---|---|---|
| **Shipped**: 2.5R, SMC+VWAP, HTF+kill-zone required, score ≥5 | 0.53 | 31.2 | 28.6 | +0.09 |
| + ORB enabled | 0.77 | 26.1 (ORB 1/7) | 28.6 | −0.09 |
| Loose: score ≥4, HTF/KZ optional | 1.2 | 27.8 | 28.6 | −0.03 |
| First tuning pass (10 symbols, score ≥4, ORB on) | 2.3 | 20.6 | 28.6 | −0.28 |
| Shipped filters, TP 1.5R | 0.53 | 43.8 | 40.0 | +0.09 |
| Shipped filters, TP 1.0R | 0.53 | 50.0 | 50.0 | 0.00 |

## Caveats

- 16 trades is a small sample: a 95% interval on 31% runs from roughly 11% to 59%. **This does not show a proven edge.**
- yfinance 5m OHLC; if SL and TP fall in the same bar it counts as a loss. No spread, slippage or commission. Real yfinance data arrives about 5–15 minutes late; the replay assumes no delay.
- 65–80% win rates were not reached by any variant. Win rate mostly depends on TP distance, as expected.
- ~5–6 quality alerts/day did not appear on this data: every variant loose enough to get there had negative expectancy, so the daily cap of 6 is a ceiling, not a target.

## Trades

| Day | UTC | Symbol | Setup | Side | Score | Outcome |
|---|---|---|---|---|---|---|
| 2026-08-24 | 07:45 | GOLD | smc_sweep | BUY | 5/6 | win |
| 2026-08-24 | 15:45 | S&P 500 | smc_sweep | SELL | 5/6 | loss |
| 2026-08-25 | 13:45 | US 30 | smc_sweep | BUY | 5/6 | loss |
| 2026-08-25 | 14:30 | GBP/USD | smc_sweep | BUY | 6/6 | loss |
| 2026-08-26 | 09:30 | US 30 | smc_sweep | BUY | 5/6 | loss |
| 2026-08-27 | 08:45 | AUD/USD | smc_sweep | BUY | 5/6 | loss |
| 2026-08-27 | 12:30 | USD/JPY | smc_sweep | BUY | 5/6 | loss |
| 2026-08-28 | 12:45 | NASDAQ 100 | smc_sweep | BUY | 5/6 | loss |
| 2026-08-28 | 13:30 | AUD/USD | smc_sweep | BUY | 5/6 | loss |
| 2026-08-31 | 13:00 | GBP/USD | smc_sweep | SELL | 5/6 | loss |
| 2026-09-04 | 13:15 | USD/JPY | smc_sweep | SELL | 5/6 | win |
| 2026-09-08 | 15:15 | S&P 500 | smc_sweep | SELL | 5/6 | win |
| 2026-09-15 | 07:15 | USD/JPY | smc_sweep | BUY | 5/6 | win |
| 2026-09-18 | 09:15 | US 30 | smc_sweep | SELL | 6/6 | win |
| 2026-09-21 | 12:30 | GOLD | smc_sweep | BUY | 6/6 | loss |
| 2026-09-28 | 07:00 | GBP/USD | smc_sweep | SELL | 6/6 | loss |
