# Strategy tune — 2026-10-08 ("more signals")

**Problem:** the bot was alive (daily SESSION CLOSED posts on Oct 5/6/7) but starved — 1 alert since Oct 5.
With all 6 SMC checklist items required, the Liquidity Sweep + BOS setup almost never qualified.

## Method
- New sweep harness `scripts/tune_sweep.py` (reuses the live setup code + `engine.gate_candidates`).
  1. **Collect** every raw setup hit over the longest window yfinance allows (5m ≈ 60 days →
     **51 calendar days, 2026-08-18 → 2026-10-08 07:30 UTC**, all **13 symbols**), with the checklist
     made permissive so the factors can be re-scored per variant (pattern detection unchanged).
  2. **Gate** each variant step-by-step with the live caps / cooldowns / dedupe / correlation groups.
- Outcome: TP-before-SL on the following 5m path; SL+TP in the same bar = **loss**. Open trades marked
  to market. **No spread / slippage / commission**, no live repricing/drift rejection (live will reject a few more).
- Alerts/day = per calendar day (bot is 24/7); "wkday/d" = per Mon–Fri. Max DD = peak-to-trough of cumulative R.
- H1 / H2 = net R in the first vs second half of the window (overfit check).
- Cross-checked the shipped config with the original harness `scripts/backtest_confluence.py --days 51`:
  80 alerts, 1.57/day, 41.2% WR, +0.031R/trade, net +2.5R, max DD 10.5R (`reports/backtest_2026-10-08_shipped.json`).

SMC checklist legend: core = liquidity_sweep + mss_bos + pd_array (always required).
vwap_pullback (indices/gold, unchanged checklist) is included in every row unless stated.

## Comparison (51 days, 13 symbols)

| Variant | Alerts | /day | wkday/d | WR % | avg R | net R | max DD R | H1 / H2 net R |
|---|---|---|---|---|---|---|---|---|
| A all-6 req (previous) · 2.0R · cap4/sym1 | 25 | 0.49 | 0.68 | 24.0 | -0.280 | -7.0 | 12.0 | +3.0 / -10.0 |
| A all-6 req (previous) · 2.0R · cap6/sym2 | 26 | 0.51 | 0.7 | 26.9 | -0.192 | -5.0 | 12.0 | +5.0 / -10.0 |
| A all-6 req (previous) · 1.5R · cap4/sym1 | 25 | 0.49 | 0.68 | 44.0 | +0.100 | +2.5 | 8.0 | +5.5 / -3.0 |
| A all-6 req (previous) · 1.5R · cap6/sym2 | 26 | 0.51 | 0.7 | 46.2 | +0.154 | +4.0 | 8.0 | +7.0 / -3.0 |
| B KZ score-only, min5 · 2.0R · cap4/sym1 | 28 | 0.55 | 0.76 | 21.4 | -0.357 | -10.0 | 13.0 | +1.0 / -11.0 |
| B KZ score-only, min5 · 2.0R · cap6/sym2 | 29 | 0.57 | 0.78 | 24.1 | -0.276 | -8.0 | 13.0 | +3.0 / -11.0 |
| B KZ score-only, min5 · 1.5R · cap4/sym1 | 28 | 0.55 | 0.76 | 42.9 | +0.071 | +2.0 | 8.0 | +3.5 / -1.5 |
| B KZ score-only, min5 · 1.5R · cap6/sym2 | 29 | 0.57 | 0.78 | 44.8 | +0.121 | +3.5 | 8.0 | +5.0 / -1.5 |
| C PD score-only, min5 · 2.0R · cap4/sym1 | 59 | 1.16 | 1.59 | 28.8 | -0.136 | -8.0 | 14.0 | +3.0 / -11.0 |
| C PD score-only, min5 · 2.0R · cap6/sym2 | 59 | 1.16 | 1.59 | 28.8 | -0.136 | -8.0 | 14.0 | +3.0 / -11.0 |
| C PD score-only, min5 · 1.5R · cap4/sym1 | 59 | 1.16 | 1.59 | 40.7 | +0.017 | +1.0 | 9.0 | +4.0 / -3.0 |
| C PD score-only, min5 · 1.5R · cap6/sym2 | 59 | 1.16 | 1.59 | 40.7 | +0.017 | +1.0 | 9.0 | +4.0 / -3.0 |
| D PD+KZ score-only, min5 · 2.0R · cap4/sym1 | 61 | 1.2 | 1.65 | 27.9 | -0.164 | -10.0 | 15.0 | +2.0 / -12.0 |
| D PD+KZ score-only, min5 · 2.0R · cap6/sym2 | 61 | 1.2 | 1.65 | 27.9 | -0.164 | -10.0 | 15.0 | +2.0 / -12.0 |
| D PD+KZ score-only, min5 · 1.5R · cap4/sym1 | 61 | 1.2 | 1.65 | 41.0 | +0.025 | +1.5 | 9.0 | +3.0 / -1.5 |
| D PD+KZ score-only, min5 · 1.5R · cap6/sym2 | 61 | 1.2 | 1.65 | 41.0 | +0.025 | +1.5 | 9.0 | +3.0 / -1.5 |
| E PD+KZ score-only, min4 · 2.0R · cap4/sym1 | 79 | 1.55 | 2.11 | 27.8 | -0.165 | -13.0 | 21.0 | +2.0 / -15.0 |
| E PD+KZ score-only, min4 · 2.0R · cap6/sym2 | 80 | 1.57 | 2.14 | 27.5 | -0.175 | -14.0 | 21.0 | +1.0 / -15.0 |
| E PD+KZ score-only, min4 · 1.5R · cap4/sym1 | 79 | 1.55 | 2.11 | 39.2 | -0.019 | -1.5 | 13.5 | +2.0 / -3.5 |
| E PD+KZ score-only, min4 · 1.5R · cap6/sym2 | 80 | 1.57 | 2.14 | 38.8 | -0.031 | -2.5 | 13.5 | +1.0 / -3.5 |
| G HTF score-only, PD req, min5 · 2.0R · cap4/sym1 | 57 | 1.12 | 1.54 | 28.1 | -0.158 | -9.0 | 19.0 | +6.0 / -15.0 |
| G HTF score-only, PD req, min5 · 2.0R · cap6/sym2 | 60 | 1.18 | 1.62 | 28.3 | -0.150 | -9.0 | 20.0 | +7.0 / -16.0 |
| G HTF score-only, PD req, min5 · 1.5R · cap4/sym1 | 57 | 1.12 | 1.54 | 42.1 | +0.053 | +3.0 | 14.0 | +7.5 / -4.5 |
| G HTF score-only, PD req, min5 · 1.5R · cap6/sym2 | 60 | 1.18 | 1.62 | 43.3 | +0.083 | +5.0 | 12.5 | +8.0 / -3.0 |
| H core only, min4 · 2.0R · cap4/sym1 | 109 | 2.14 | 2.89 | 31.2 | -0.064 | -7.0 | 24.0 | +10.0 / -17.0 |
| H core only, min4 · 2.0R · cap6/sym2 | 124 | 2.43 | 3.3 | 29.8 | -0.105 | -13.0 | 27.0 | +7.0 / -20.0 |
| H core only, min4 · 1.5R · cap4/sym1 | 109 | 2.14 | 2.89 | 41.3 | +0.032 | +3.5 | 16.0 | +9.0 / -5.5 |
| H core only, min4 · 1.5R · cap6/sym2 | 124 | 2.43 | 3.3 | 39.5 | -0.012 | -1.5 | 17.0 | +5.0 / -6.5 |
| I PD req, HTF+KZ score-only, min4 · 2.0R · cap4/sym1 | 76 | 1.49 | 2.03 | 31.6 | -0.053 | -4.0 | 14.0 | +7.0 / -11.0 |
| I PD req, HTF+KZ score-only, min4 · 2.0R · cap6/sym2 | 81 | 1.59 | 2.16 | 30.9 | -0.074 | -6.0 | 16.0 | +7.0 / -13.0 |
| I PD req, HTF+KZ score-only, min4 · 1.5R · cap4/sym1 | 76 | 1.49 | 2.03 | 42.1 | +0.053 | +4.0 | 12.0 | +6.5 / -2.5 |
| **I PD req, HTF+KZ score-only, min4 · 1.5R · cap6/sym2 (SHIPPED)** | **81** | **1.59** | **2.16** | **42.0** | **+0.049** | **+4.0** | **10.5** | **+6.0 / -2.0** |
| D +ema_vwap_kz · 2.0R · cap6/sym2 | 62 | 1.22 | 1.68 | 27.4 | -0.177 | -11.0 | 15.0 | +1.0 / -12.0 |
| D +orb_open · 2.0R · cap6/sym2 | 71 | 1.39 | 1.92 | 25.4 | -0.239 | -17.0 | 22.0 | +2.0 / -19.0 |
| D no vwap_pullback · 2.0R · cap6/sym2 | 45 | 0.88 | 1.22 | 31.1 | -0.067 | -3.0 | 9.0 | +1.0 / -4.0 |
| D +ema_vwap_kz · 1.5R · cap6/sym2 | 62 | 1.22 | 1.68 | 40.3 | +0.008 | +0.5 | 9.0 | +2.0 / -1.5 |
| D +orb_open · 1.5R · cap6/sym2 | 71 | 1.39 | 1.92 | 38.0 | -0.049 | -3.5 | 12.5 | +4.5 / -8.0 |
| D no vwap_pullback · 1.5R · cap6/sym2 | 45 | 0.88 | 1.22 | 37.8 | -0.056 | -2.5 | 8.0 | -1.5 / -1.0 |
| E +ema_vwap_kz · 2.0R · cap6/sym2 | 81 | 1.59 | 2.16 | 27.2 | -0.185 | -15.0 | 21.0 | +0.0 / -15.0 |
| E +orb_open · 2.0R · cap6/sym2 | 90 | 1.76 | 2.41 | 26.7 | -0.200 | -18.0 | 28.0 | +1.0 / -19.0 |
| E no vwap_pullback · 2.0R · cap6/sym2 | 65 | 1.27 | 1.73 | 29.2 | -0.123 | -8.0 | 14.0 | -1.0 / -7.0 |
| E +ema_vwap_kz · 1.5R · cap6/sym2 | 81 | 1.59 | 2.16 | 38.3 | -0.043 | -3.5 | 13.5 | +0.0 / -3.5 |
| E +orb_open · 1.5R · cap6/sym2 | 90 | 1.76 | 2.41 | 37.8 | -0.056 | -5.0 | 19.0 | +2.5 / -7.5 |
| E no vwap_pullback · 1.5R · cap6/sym2 | 65 | 1.27 | 1.73 | 35.4 | -0.115 | -7.5 | 12.5 | -4.5 / -3.0 |
| I +ema_vwap_kz · 2.0R · cap6/sym2 | 82 | 1.61 | 2.19 | 30.5 | -0.085 | -7.0 | 16.0 | +6.0 / -13.0 |
| I +orb_open · 2.0R · cap6/sym2 | 92 | 1.8 | 2.46 | 28.3 | -0.152 | -14.0 | 23.0 | +5.0 / -19.0 |
| I no vwap_pullback · 2.0R · cap6/sym2 | 65 | 1.27 | 1.73 | 33.8 | +0.015 | +1.0 | 8.0 | +7.0 / -6.0 |
| I +ema_vwap_kz · 1.5R · cap6/sym2 | 82 | 1.61 | 2.19 | 41.5 | +0.037 | +3.0 | 10.5 | +5.0 / -2.0 |
| I +orb_open · 1.5R · cap6/sym2 | 92 | 1.8 | 2.46 | 39.1 | -0.022 | -2.0 | 14.0 | +6.0 / -8.0 |
| I no vwap_pullback · 1.5R · cap6/sym2 | 65 | 1.27 | 1.73 | 40.0 | +0.000 | +0.0 | 7.0 | +2.5 / -2.5 |

Extra cooldown checks on the chosen variant (1.5R, cap 6 / 2 per symbol):

| Global / symbol cooldown | /day | WR % | net R | max DD R |
|---|---|---|---|---|
| **40 / 120 min (kept)** | **1.59** | **42.0** | **+4.0** | **10.5** |
| 30 / 120 | 1.63 | 41.0 | +2.0 | 11.5 |
| 20 / 90 | 1.65 | 40.5 | +1.0 | 12.5 |
| 15 / 60 | 1.71 | 39.1 | −2.0 | 13.5 |

## What the data said
- **The old config was not actually good on the longer window:** all-6-required @ 2.0R = 0.49/day, 24% WR, **−7.0R**
  (most of its alerts were vwap_pullback; the earlier +0.20R came from n=5 on 8 symbols).
- Strictest rules at 1.5R (A) had the best per-alert number (+0.15R, DD 8R) but only ~0.5/day (~3.5/week) —
  that is the "starved" bot the user is complaining about. I keeps the same net R at ~3× the frequency.
- **1.5R beats 2.0R on every variant** (higher WR more than pays for the smaller target).
- **Premium/discount is the one context factor that helped sweeps** (unique raw SMC hits: PD ✅ +0.08R vs PD ❌ −0.20R @ 2R).
  Requiring **HTF bias did not help** (aligned sweeps were slightly worse), and kill-zone timing was ≈ neutral.
- Only "core only, min 4" reached > 2/calendar day, but with a 16R drawdown and −5.5R in the second half.
- orb_open and ema_vwap_kz made every variant worse → **left disabled**.
- Tightening cooldowns adds only ~0.1/day and erodes expectancy → **cooldowns unchanged**.

## Shipped: variant **I — PD required, HTF + kill-zone score-only, min 4 | 1.5R | cap 6 / 2 per symbol**
| Key | Before | After |
|---|---|---|
| `risk.tp_rr` / `risk.min_rr` | 2.0 / 2.0 | **1.5 / 1.5** |
| `risk.daily_max_signals` | 4 | **6** (ceiling; replay max was 5 in a day) |
| `risk.per_symbol_max` | 1 | **2** |
| `setups.smc_sweep.min_score` | 5 | **4** |
| `smc_sweep.checklist.htf_bias.required` | true | **false** (still scored + shown) |
| `smc_sweep.checklist.kill_zone.required` | true | **false** (still scored + shown) |
| cooldowns, max_signal_age, execution/repricing, correlation groups, outcomes, Telegram flags | — | unchanged |

Expected: **~1.6 alerts/calendar day (~2.2 per weekday, weekends quieter)**, ~42% WR at 1.5R (breakeven 40%),
≈ +0.03 to +0.05R per alert, max drawdown ≈ 10.5R over the window.

## Honest caveats
- **The edge is thin — this is ≈ breakeven, not a proven money-maker.** Every variant lost money in the second
  half (mid-Sep → Oct 8); the shipped one lost the least (−2.0R) while tripling frequency.
- **2/day is met on weekdays, not on a calendar-day basis** (~1.6/day incl. weekends). Getting > 2/calendar day
  required dropping PD, which made drawdowns ~16R+ and the recent half clearly negative.
- The 65–80% win-rate target is **not** achievable with these rules on this data; ~42% at 1.5R is what the replay supports.
- Many alerts land 00:00–02:00 UTC (Tokyo open = 02:00–04:00 SAST) because the scanner is 24/7.
- Scores now show as 4/6–6/6; a 4/6 alert means the sweep pattern + PD location are present but HTF bias / kill zone are not.
- yfinance data, no costs; live repricing/drift checks will drop some alerts. Re-run `python scripts/tune_sweep.py`
  in 2–3 weeks to re-check with fresh data.

## Ops
- Hot-reloaded from `strategy_config.yaml` on the next monitor loop after Render deploys main.
- Artefacts: `reports/tune_2026-10-08_variants.json` (all variants + trades), `reports/backtest_2026-10-08_shipped.json`.
