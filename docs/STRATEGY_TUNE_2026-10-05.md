# Strategy tune — 2026-10-05 (Africa/Johannesburg)

## Research summary (no BL Tech Telegram)
Sources reviewed: VWAP morning-window studies (QQQ public write-ups: ~62% WR 09:45–11:30 ET vs losing midday),
EMA9/21 “bone zone” + VWAP confluence practitioner notes, ICT kill-zone / Silver Bullet selectivity,
prior AlphaEdge CDT audit (`docs/STRATEGY_RECOMMENDATION.md`).

**Takeaway:** time-of-day + HTF + premium/discount filters raise *selectivity*; published 65–80% WR
figures are conditional and **not** reproduced on yfinance 5m replay here.

## What we changed
| Item | Change |
|---|---|
| `risk.tp_rr` / `min_rr` | 2.5 → **2.0** (higher achievable WR vs distance) |
| `risk.daily_max_signals` | 6 → **4** (few/day ceiling) |
| SMC `premium_discount` | **required: true** (was optional) |
| VWAP `avoid_ny` | lunch through close (`11:30–16:00`) — morning-only intent |
| New setup `ema_vwap_kz` | Morning EMA+VWAP confluence coded; **disabled by default** after 0/5 isolate |
| `orb_open` | Still disabled |

## Honest 30-session replay (closed 5m, same gates as live)

Window: **2026-08-25 → 2026-10-05**, 8 symbols, TP-before-SL; same-bar SL+TP = loss.

| Variant | Alerts | Alerts/day | Win % | BE % @ RR | Exp. R |
|---|---|---|---|---|---|
| **Shipped (PD required, 2.0R, no EMA)** | 5 | 0.17 | **40.0** | 33.3 | **+0.20** |
| PD optional, 2.0R | 17 | 0.57 | 29.4 | 33.3 | −0.12 |
| Prior-like 2.5R, PD optional | 17 | 0.57 | 23.5 | 28.6 | −0.18 |
| EMA+VWAP only (loosened) | 5 | 0.17 | 0.0 | 33.3 | −1.00 |

### Shipped trades
| Day | UTC | Symbol | Side | Score | Outcome |
|---|---|---|---|---|---|
| 2026-08-25 | 14:30 | GBP/USD | BUY | 6/6 | win |
| 2026-09-18 | 09:15 | US 30 | SELL | 6/6 | win |
| 2026-09-21 | 12:30 | GOLD | BUY | 6/6 | loss |
| 2026-09-28 | 07:00 | GBP/USD | SELL | 6/6 | loss |
| 2026-09-30 | 12:30 | S&P 500 | SELL | 6/6 | loss |

## Honesty notes
- **n=5 is tiny** — 95% CI on 40% WR is wide; this is *not* a proven edge.
- We did **not** hit ~few quality alerts/day with positive expectancy on this feed: every looser
  variant that approached ~0.6/day went negative. Spam caps remain; the binding constraint is
  pattern+PD rarity, not the daily max of 4.
- No spread/slippage/commission; yfinance delay ignored in replay.
- **Do not integrate third-party Telegram signal channels** (including BL Tech) — AlphaEdge stays on
  its own confluence engine.

## Ops
- Tune live via `strategy_config.yaml` (hot-reloaded each monitor loop).
- Artefacts: `reports/backtest_2026-10-05_shipped.json`, `reports/backtest_2026-10-05_variants.json`.
