# AlphaEdge Pro — paid gate MVP

## Paywall toggle (default OFF)

The paywall is **not deleted** — it is a switch:

| Setting | Effect |
|---|---|
| **OFF (default)** | Full dashboard / Pro for everyone — no sign-in or Paystack checkout required |
| **ON** | Unpaid visitors see teaser; paid subscribers get full Pro |

Control:
1. **Env** `PAYWALL_ENABLED` — unset or `false`/`0`/`off` → OFF; `true`/`1`/`on` → ON
2. **Owner sidebar** — unlock with `OWNER_PIN` (env) via `?owner_pin=<pin>` or `?owner=1` + PIN form, then use the "Require Pro subscription" toggle (`paywall_override.json`). Visitors never see this panel.

`render.yaml` ships `PAYWALL_ENABLED=false`. Set `OWNER_PIN` in the Render dashboard (sync: false).

### Clean free-open site (paywall OFF)
Visitors do **not** see: paywall toggle, "Dev: simulate Telegram login", teaser banners, seat counters, or checkout chrome. Owner unlocks the ops panel with the PIN.

## Pricing (ZAR, Paystack) — only when paywall ON
| Plan | Price | Notes |
|---|---|---|
| Weekly | **R35** | ~R5/day |
| Monthly | **R149** | Preferred (lower fee drag vs weekly) |

Hard cap: **300** concurrent active paid seats.

## Auth
- **Email magic link** — token in DB; emailed when `SMTP_*` set; otherwise link shown in UI (demo).
- **Telegram Login Widget** — verify HMAC with `TELEGRAM_LOGIN_BOT_TOKEN`; set `TELEGRAM_LOGIN_BOT_USERNAME`.
- Dev helper: simulate Telegram login when bot username unset — **owner session only**.

## Paystack
Env (never commit secrets):
- `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_SECRET_KEY`
- `APP_BASE_URL` (callback base)
- Optional: `MAGIC_LINK_SECRET`, `TELEGRAM_LOGIN_BOT_*`, `SMTP_*`
- `PAYWALL_ENABLED` (default false)
- `OWNER_PIN` (owner unlock; never commit)

Without Paystack keys the app runs a **demo checkout** that activates a subscription on return
(`?ae_pay_ref=…&ae_pay_demo=1`) so the gate can be tested end-to-end when the paywall is ON.

## Teaser vs Pro (only when paywall ON)
| | Teaser (free) | Pro (paid) |
|---|---|---|
| Live Media (TV open-on-YT + radio station) | ✅ | ✅ |
| Heatmap | 5 symbols | Full |
| Live signals / SL-TP | 🔒 | ✅ |
| Chart | ✅ (teaser) | ✅ |
| COT / Sentiment / Indices / FX / News / Calendar / Chat | 🔒 | ✅ |

When paywall is **OFF**, every visitor gets the Pro column with no checkout.

## Files
`billing/` — `db.py`, `auth.py`, `paystack.py`, `gate.py`, `ui.py`, `plans.py`  
SQLite: `billing.db` (gitignored).  
Override: `paywall_override.json` (gitignored).
