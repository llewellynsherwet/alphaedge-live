# AlphaEdge Pro — paid gate MVP

## Pricing (ZAR, Paystack)
| Plan | Price | Notes |
|---|---|---|
| Weekly | **R35** | ~R5/day |
| Monthly | **R149** | Preferred (lower fee drag vs weekly) |

Hard cap: **300** concurrent active paid seats.

## Auth
- **Email magic link** — token in DB; emailed when `SMTP_*` set; otherwise link shown in UI (demo).
- **Telegram Login Widget** — verify HMAC with `TELEGRAM_LOGIN_BOT_TOKEN`; set `TELEGRAM_LOGIN_BOT_USERNAME`.
- Dev helper: simulate Telegram login when bot username unset.

## Paystack
Env (never commit secrets):
- `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_SECRET_KEY`
- `APP_BASE_URL` (callback base)
- Optional: `MAGIC_LINK_SECRET`, `TELEGRAM_LOGIN_BOT_*`, `SMTP_*`

Without Paystack keys the app runs a **demo checkout** that activates a subscription on return
(`?ae_pay_ref=…&ae_pay_demo=1`) so the gate can be tested end-to-end.

## Teaser vs Pro
| | Teaser (free) | Pro (paid) |
|---|---|---|
| Live Media (TV open-on-YT + radio station) | ✅ | ✅ |
| Heatmap | 5 symbols | Full |
| Live signals / SL-TP | 🔒 | ✅ |
| Chart | ✅ (teaser) | ✅ |
| COT / Sentiment / Indices / FX / News / Calendar / Chat | 🔒 | ✅ |

## Files
`billing/` — `db.py`, `auth.py`, `paystack.py`, `gate.py`, `ui.py`, `plans.py`  
SQLite: `billing.db` (gitignored).
