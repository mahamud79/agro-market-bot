# Agro Market Bot 🌱

A WhatsApp-based agricultural marketplace for Sierra Leone. Farmers, input
sellers, buyers, and delivery riders interact entirely through WhatsApp chat,
while payments are collected and held in escrow through
[Monime](https://monime.io) (Orange Money / Mobile Money). A web-based admin
dashboard provides oversight of users, transactions, and market prices.

The entire application is a single FastAPI service (`main.py`) backed by a
PostgreSQL database (Supabase).

---

## Table of contents

- [Overview](#overview)
- [Key features](#key-features)
- [Tech stack](#tech-stack)
- [How it works](#how-it-works)
- [User roles](#user-roles)
- [Conversation flow & state machine](#conversation-flow--state-machine)
- [Order & escrow lifecycle](#order--escrow-lifecycle)
- [Project structure](#project-structure)
- [Database schema](#database-schema)
- [Environment variables](#environment-variables)
- [Local setup](#local-setup)
- [Deployment (Render)](#deployment-render)
- [External service configuration](#external-service-configuration)
- [HTTP endpoints](#http-endpoints)
- [Admin dashboard](#admin-dashboard)
- [Testing payments without spending money](#testing-payments-without-spending-money)
- [Known limitations & security notes](#known-limitations--security-notes)
- [Credits](#credits)

---

## Overview

Agro Market Bot lets people in Sierra Leone trade agricultural produce and farm
inputs over WhatsApp without needing a smartphone app. A buyer messages the bot,
searches for produce, places an order, and pays via a Monime checkout link. The
money is held in escrow until the buyer confirms delivery, at which point it is
released to the seller. Delivery can be self-pickup or fulfilled by a registered
rider who sets their own fee.

## Key features

- **WhatsApp-native UX** — the whole marketplace runs in chat via the WhatsApp
  Cloud API; no separate app to install.
- **Four user roles** — Farmer, Input Seller, Buyer, and Driver/Rider, each with
  its own menu and flows.
- **Guided onboarding & registration** — collects name, Mobile Money number,
  vehicle details (drivers), and location.
- **Admin approval** — farmers, input sellers, and drivers require admin approval
  before they can transact; buyers are auto-approved.
- **Product listings with photos** — sellers add produce/inputs with a name,
  quantity, price, and an image.
- **Location-aware marketplace search** — results prioritise listings near the
  buyer's location.
- **Escrow payments via Monime** — orders generate a hosted Monime checkout
  link; funds are held until delivery is confirmed.
- **Receipts** — on successful payment, both buyer and seller receive a formatted
  WhatsApp receipt (with names, phone numbers, amount, transaction ID, and
  date/time).
- **Delivery management** — riders browse available jobs, claim them, set a fee,
  and mark deliveries complete; buyers then confirm receipt to release escrow.
- **Market price board** — admins publish reference crop prices that all users
  can view.
- **Admin web dashboard** — manage user approvals, view transaction ledgers
  (successful / pending / disputed), and maintain market prices.
- **Bilingual scaffolding** — English and Krio message templates are defined
  (see [Known limitations](#known-limitations--security-notes)).

## Tech stack

| Layer | Technology |
| --- | --- |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) |
| ASGI server | [Uvicorn](https://www.uvicorn.org/) |
| Database | PostgreSQL (hosted on [Supabase](https://supabase.com/)) |
| DB driver | `psycopg2` |
| Messaging | [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api) (Meta Graph API v18.0) |
| Payments | [Monime](https://monime.io) Checkout Sessions + webhooks |
| Hosting | [Render](https://render.com/) |
| Language | Python 3 |

Dependencies are pinned in [`requirements.txt`](./requirements.txt):

```text
fastapi==0.104.1
uvicorn==0.24.0
requests==2.31.0
psycopg2-binary==2.9.9
python-dotenv==1.0.0
python-multipart==0.0.6
```

## How it works

```
   WhatsApp user                Meta WhatsApp Cloud API
        │                                 │
        │  chat message                   │  POST /webhook
        ▼                                 ▼
   ┌─────────────────────────────────────────────────┐
   │                Agro Market Bot                    │
   │                 (FastAPI, main.py)                │
   │                                                   │
   │   conversation state machine ── PostgreSQL ───────┼──► Supabase
   │   checkout link creation ─────────────────────────┼──► Monime API
   │   admin dashboard (HTML)                           │
   └─────────────────────────────────────────────────┘
        ▲                                 ▲
        │  POST /webhook/monime           │  outbound receipts /
        │  (payment completed)            │  notifications
   Monime payment events            WhatsApp Cloud API
```

1. A user sends a WhatsApp message. Meta forwards it to `POST /webhook`.
2. The bot loads the user's session (current flow + step) from the database and
   responds based on a state machine.
3. When a buyer checks out, the bot calls the Monime API to create a hosted
   checkout session and sends the payment link to the buyer.
4. When the buyer pays, Monime calls `POST /webhook/monime`. The bot marks the
   order `paid`, holds funds in escrow, and sends receipts to both parties.
5. After delivery, the buyer replies to confirm; escrow is released to the seller.

## User roles

| Role | Internal key | Approval | Capabilities |
| --- | --- | --- | --- |
| Farmer | `role_farmer` | Admin required | Add produce, view inventory, manage orders, buy supplies, view prices |
| Input Seller | `role_input` | Admin required | Add supplies/tools, view inventory, manage orders, view prices |
| Buyer | `role_buyer` | Auto-approved | Buy produce, buy inputs, view orders, view prices |
| Driver / Rider | `role_driver` | Admin required | Find deliveries, claim jobs & set fee, complete deliveries |

## Conversation flow & state machine

Each user has a session row holding a `current_flow` and `current_step`. The
text handler in `process_webhook_payload` routes messages based on these values.
Temporary data between steps (search results, selected product, cart quantity,
etc.) is stored as JSON in `user_sessions.temp_data`.

Primary flows:

- `onboarding` — role selection (and language, where applicable).
- `registration` — name, vehicle (drivers), Mobile Money number, location.
- `pending_approval` — holding state until an admin approves the account.
- `main_menu` — role-specific dashboard menus.
- `add_produce` / `add_input` — multi-step listing creation ending with a photo.
- `buyer_search` / `farmer_search` — search → view item → buy decision.
- `buyer_checkout` — quantity → delivery method → (address) → order created.
- `manage_order` — seller accepts/rejects, chooses delivery handling and fee.
- `driver_flow` — browse/accept jobs, set fee, complete deliveries.

Global shortcuts available at any time: `hi` / `hello` / `menu` (return to
dashboard), `A` / `B` (confirm or dispute delivery), and `accept <id>` /
`reject <id>` (seller order actions).

## Order & escrow lifecycle

```
pending ─► (seller accepts)
              ├─ pickup  ──────────────► AWAITING_PAYMENT
              └─ delivery ─► (rider/seller fee) ─► AWAITING_PAYMENT / AWAITING_DRIVER
AWAITING_PAYMENT ─► (buyer pays via Monime) ─► paid          [wallet_status: held]
paid ─► (rider marks delivered) ─► DELIVERED
DELIVERED/paid ─► (buyer confirms "A") ─► Successful          [wallet_status: released]
              └─ (buyer disputes "B") ─► Unsuccessful          [escrow held for review]
(seller rejects) ─► DECLINED
```

- `status` tracks the order stage.
- `wallet_status` tracks escrow: `held` while funds are secured, `released` once
  delivery is confirmed.
- Every order also carries `subtotal`, `delivery_fee`, a SLE 5 platform fee, and
  the computed `total_amount`.

## Project structure

```
agro-market-bot/
├── main.py            # The entire application: routes, DB helpers,
│                      # WhatsApp + Monime integration, conversation
│                      # state machine, and the admin dashboard HTML.
├── requirements.txt   # Pinned Python dependencies.
└── README.md          # This file.
```

> The project is intentionally a single-file FastAPI app. Functions are grouped
> by concern: messaging helpers, database helpers, receipt/checkout helpers,
> admin routes, the Monime webhook, and the WhatsApp message handler.

## Database schema

The app expects the following PostgreSQL tables (Supabase). Column lists are
derived from the queries in `main.py`; on startup the app runs a few idempotent
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migrations for newer columns.

**`users`**

| Column | Notes |
| --- | --- |
| `phone` | Primary key (WhatsApp number, no `+`) |
| `name` | Full name |
| `role` | `role_farmer` / `role_input` / `role_buyer` / `role_driver` |
| `language` | `english` / `krio` |
| `location` | District/city or shared location |
| `momo_number` | Mobile Money payout number |
| `vehicle_number` | Driver vehicle plate |
| `vehicle_image_id` | WhatsApp media id of vehicle photo |
| `is_approved` | Boolean admin approval |
| `nin_status` | National ID status (reserved) |
| `created_at` | Timestamp |

**`user_sessions`**

| Column | Notes |
| --- | --- |
| `phone` | Primary key |
| `current_flow` | Active conversation flow |
| `current_step` | Active step within the flow |
| `temp_data` | JSON scratch space between steps |

**`products`**

| Column | Notes |
| --- | --- |
| `id` | Primary key |
| `farmer_phone` | Seller's phone |
| `product_name`, `price`, `quantity` | Listing details |
| `image_id` | WhatsApp media id of product photo |
| `category` | `produce` / `input` |
| `created_at` | Timestamp |

**`orders`**

| Column | Notes |
| --- | --- |
| `id` | Primary key |
| `buyer_phone`, `farmer_phone`, `driver_phone` | Parties |
| `product_id`, `product_name`, `order_qty` | What was ordered |
| `status` | Order lifecycle stage |
| `wallet_status` | `held` / `released` (escrow) |
| `delivery_preference` | `delivery` / `pickup` |
| `payment_method` | e.g. `Monime Escrow Hold` |
| `subtotal`, `delivery_fee`, `total_amount` | Money (SLE) |
| `receipt_number`, `transaction_id` | Receipt + payment references |
| `created_at` | Timestamp |

**`market_prices`** — `id`, `crop_name`, `location`, `price`.

**`admin_auth`** — `phone`, `password_hash` (SHA-256), `session_token`.

## Environment variables

Set these in a `.env` file locally (loaded via `python-dotenv`) or as service
environment variables on Render:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string (Supabase) |
| `WHATSAPP_TOKEN` | WhatsApp Cloud API access token |
| `PHONE_NUMBER_ID` | WhatsApp Cloud API phone number ID |
| `ADMIN_PHONE` | Admin's phone number (dashboard owner & alerts) |
| `MONIME_SECRET_KEY` | Monime access token (needs **Checkout Session** create permission) |
| `MONIME_SPACE_ID` | Monime Space ID (`spc-...`) |

> A webhook verify token is currently hardcoded in `main.py` as `VERIFY_TOKEN`.
> Consider moving it to an environment variable (see
> [Known limitations](#known-limitations--security-notes)).

## Local setup

Prerequisites: Python 3.10+ and access to a PostgreSQL database.

```bash
# 1. Clone
git clone https://github.com/mahamud79/agro-market-bot.git
cd agro-market-bot

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env (see Environment variables above)
#    DATABASE_URL=...
#    WHATSAPP_TOKEN=...
#    PHONE_NUMBER_ID=...
#    ADMIN_PHONE=...
#    MONIME_SECRET_KEY=...
#    MONIME_SPACE_ID=...

# 5. Run
uvicorn main:app --host 0.0.0.0 --port 10000 --reload
```

The service exposes the admin dashboard at `http://localhost:10000/admin`.
WhatsApp and Monime require a publicly reachable HTTPS URL, so for end-to-end
testing use the deployed Render URL or a tunnel (e.g. ngrok).

On startup the app verifies the database connection and applies the
`ADD COLUMN IF NOT EXISTS` migrations; check the logs for
`✅ Successfully connected to Supabase & Tables Verified!`.

## Deployment (Render)

The app is deployed as a Render Web Service at
`https://agro-market-bot.onrender.com`.

- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment:** set all variables from the table above.
- Render redeploys automatically on each push to the connected branch. Confirm
  the latest deploy shows "Live" before testing.

## External service configuration

### WhatsApp Cloud API
- Configure the webhook callback URL to `https://<your-domain>/webhook` and set
  the verify token to match `VERIFY_TOKEN` in `main.py`.
- Subscribe to the `messages` field.
- Note Meta's **24-hour customer service window**: free-form messages (including
  receipts) can only be sent within 24 hours of the user's last message;
  otherwise an approved message template is required.

### Monime
- Use a **live** access token (starts with `mon_`, not `mon_test_`) that has the
  **Checkout Session** create permission, and put it in `MONIME_SECRET_KEY`.
- Register a webhook pointing to `https://<your-domain>/webhook/monime`
  subscribed to `checkout_session.completed` (the app also accepts
  `payment_code.completed`). Webhooks are created via the Monime API
  (`POST https://api.monime.io/v1/webhooks`).
- Ensure your Monime Space has the desired payment methods enabled (e.g. Mobile
  Money). Card payments must be enabled by Monime for your Space.

## HTTP endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/webhook` | WhatsApp webhook verification (hub challenge) |
| POST | `/webhook` | Inbound WhatsApp messages (processed in the background) |
| POST | `/webhook/monime` | Monime payment events → marks paid, sends receipts |
| GET | `/checkout/pay/{order_id}` | Fallback checkout page (used if Monime API call fails) |
| POST | `/admin/api/simulate-webhook-trigger/{order_id}` | Simulates a successful payment (testing) |
| GET | `/admin/login` | Admin login page |
| POST | `/admin/process-login` | Authenticates the admin and sets a session cookie |
| GET | `/admin/logout` | Clears the admin session |
| GET | `/admin` | Admin dashboard |
| POST | `/admin/user/toggle/{phone}` | Approve/revoke a user |
| POST | `/admin/price/add` | Add a market price |
| POST | `/admin/price/delete/{price_id}` | Delete a market price |
| POST | `/admin/order/delete/{order_id}` | Delete an order |

## Admin dashboard

Visit `/admin/login` and sign in with the admin password (compared against the
SHA-256 `password_hash` stored in `admin_auth` for `ADMIN_PHONE`). The dashboard
provides:

- **User management** — approve/revoke farmers, input sellers, drivers, and
  buyers.
- **Transaction ledgers** — Successful, Pending, and Unsuccessful/Disputed
  tables showing the order ID, date & time, seller and buyer (name + phone),
  product, amount, order status, escrow state, and receipt code.
- **Market price management** — add and remove reference crop prices.

## Testing payments without spending money

You can exercise the full receipt path without a real Monime payment by sending
a simulated `checkout_session.completed` event to the webhook (replace `48` with
a real order ID that is awaiting payment):

```bash
curl -X POST https://<your-domain>/webhook/monime \
  -H "Content-Type: application/json" \
  -d '{
        "event": {"name": "checkout_session.completed"},
        "data": {"status": "completed", "reference": "48", "metadata": {"order_id": "48"}}
      }'
```

The order should flip to `paid`, and both the buyer and seller should receive a
receipt on WhatsApp (subject to the 24-hour messaging window).

## Known limitations & security notes

These are documented for transparency and future hardening:

- **`/admin/api/simulate-webhook-trigger/{order_id}` is unauthenticated.** It can
  mark any order as paid and trigger receipts. It should be protected by admin
  auth or disabled in production.
- **No webhook signature verification.** `/webhook/monime` does not validate the
  Monime HMAC signature, so forged payment events are possible. Adding HMAC
  verification is recommended.
- **Escrow payout to sellers is not fully wired** to Monime's real payout API in
  `process_confirm_delivery`; orders are marked released regardless of the API
  result. Verify against Monime's payout documentation before relying on
  automatic disbursement.
- **Krio menus are defined but not rendered** — menu helpers currently default to
  English, and onboarding does not prompt for language.
- **Hardcoded webhook verify token** (`VERIFY_TOKEN`) should be moved to an
  environment variable.
- **No connection pooling** — each database helper opens and closes its own
  connection. Introducing pooling would improve performance and stability under
  load.
- Many database helpers swallow exceptions silently; richer logging would aid
  debugging.

## Credits

**Developed by [Mahamud Hasan](https://github.com/mahamud79)** — design,
architecture, and full implementation of the platform.

Commissioned by / operated for **Salgro Limited** (client), the business that
runs the Agro Market service.

Business contact (Salgro Limited):

- 📞 +232 99166746
- 📧 info@agromarketbot.com
