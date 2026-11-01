# 01 — Software Requirements Specification

## 1. Purpose and scope

The platform lets independent businesses ("tenants": restaurants, cafés, shops) sell to customers
through Telegram. Each tenant gets its own Telegram bot, Mini App storefront, dashboard, staff
accounts and settings. The platform operator sells monthly subscription plans to tenants.

Primary market: Iraq. Arabic (RTL) is the default language; English is fully supported.

Out of scope for v1: online card payments (only cash on delivery / pay at pickup — see §6),
native mobile apps, marketplaces that aggregate several businesses into one storefront.

## 2. Actors

| Actor | Description | Interface |
|-------|-------------|-----------|
| Customer | End user ordering from a business | Telegram bot, Mini App |
| Owner | Owns one or more businesses; full control within them | Dashboard, Telegram (notifications) |
| Manager | Runs daily operations | Dashboard, Telegram |
| Cashier | Accepts/rejects orders, handles customers | Dashboard, Telegram |
| Kitchen staff | Moves orders through preparation | Dashboard (kitchen view), Telegram |
| Delivery staff | Takes and delivers orders | Telegram, Dashboard (mobile) |
| Platform admin | Operates the SaaS: tenants, plans, support | Platform admin console |
| AI assistant | System actor; proposes orders, never commits them | Bot conversations |

Roles are per business: a single user may be Owner of business A and Cashier at business B.

## 3. Functional requirements

IDs are referenced by tests and the roadmap.

### 3.1 Accounts and authentication (ACC)
- **ACC-1** Dashboard users register/login with email or Iraqi phone + password; password reset via email.
- **ACC-2** Optional TOTP two-factor authentication; mandatory for platform admins.
- **ACC-3** A dashboard user can link their Telegram account (one-time code sent through the bot) to receive staff notifications and act on order buttons.
- **ACC-4** Customers are identified only through Telegram (bot updates or validated Mini App initData). Customers never have passwords.
- **ACC-5** Sessions can be listed and revoked; password change revokes all refresh tokens.

### 3.2 Businesses (BUS)
- **BUS-1** Business profile: name (ar/en), slug, logo, cover, description, type (restaurant, café, bakery, grocery, pharmacy, retail, other), phone(s), address, governorate, GPS location, currency, default language, timezone (default `Asia/Baghdad`).
- **BUS-2** Working hours per weekday with multiple intervals (e.g. 12:00–16:00, 18:00–02:00 crossing midnight), plus holiday/closure overrides and a manual "temporarily closed" switch.
- **BUS-3** Ordering rules: accept delivery / pickup / dine-in flags, minimum order amount, customer cancellation window (minutes after placement, only while `pending`), auto-reject after N minutes without acceptance (optional), order notes allowed.
- **BUS-4** Telegram configuration: bot token (write-only, encrypted at rest), bot username (read from Telegram), Mini App URL, notification group/chat IDs, welcome message (ar/en).
- **BUS-5** Status: `active`, `suspended` (by platform), `inactive` (by owner). Suspended/inactive businesses cannot receive orders; their bot replies with a closure message.
- **BUS-6** Multi-branch (designed now, UI in a later phase): a business has ≥1 branch; orders, stock and delivery zones belong to a branch.

### 3.3 Catalog (CAT)
- **CAT-1** Categories: name (ar/en), image, sort order, active flag, optional parent (one level of nesting).
- **CAT-2** Products: name/description (ar/en), multiple ordered images, base price, compare-at price/discount, category, active flag, availability (`available`, `out_of_stock`, `hidden`), optional stock tracking with quantity, preparation time, tags, sort order, SKU.
- **CAT-3** Option groups per product: single-select (variations such as size) or multi-select (add-ons/extras), required flag, min/max selections; each option has a price delta (may be 0), availability and sort order.
- **CAT-4** Product search across name/description in Arabic and English, tolerant of Arabic letter variants (أ/إ/آ/ا, ة/ه, ى/ي) and diacritics.
- **CAT-5** Image uploads validated (type, size, dimensions), re-encoded to WebP, thumbnails generated.
- **CAT-6** Plan limits apply (e.g. max products, max images per product).

### 3.4 Cart (CRT)
- **CRT-1** One active cart per (customer, business, branch). Shared by Bot and Mini App — adding in one is visible in the other.
- **CRT-2** Cart lines: product + selected options + quantity + note. Identical product/option combinations merge.
- **CRT-3** Cart totals are always computed by the server from current prices; the cart shows warnings when an item became unavailable or its price changed.
- **CRT-4** Carts expire after a configurable inactivity period (default 7 days).

### 3.5 Orders (ORD)
- **ORD-1** Checkout collects: fulfilment type (delivery / pickup), customer name, phone (Iraqi format validated), delivery zone + address details (district, street, nearest landmark — "أقرب نقطة دالة"), optional GPS location, notes, payment method.
- **ORD-2** Order creation is a single DB transaction: re-price every line from DB, validate availability/stock/options/minimum/working hours/zone, compute delivery fee & discounts, snapshot names and prices into order items, decrement stock, clear cart.
- **ORD-3** Idempotency: each checkout carries a client-generated idempotency key; repeating the request returns the original order instead of creating a duplicate.
- **ORD-4** Human-readable order number per business (e.g. `#1042`), plus a global UUID.
- **ORD-5** Status machine:

  ```
  pending ──► confirmed ──► preparing ──► ready ──► out_for_delivery ──► delivered
     │            │             │           │               │
     ├─► rejected └──────── cancelled ◄─────┴───────────────┘
     └─► cancelled (by customer, within window)
  ```
  `ready → delivered` is allowed for pickup orders (skip `out_for_delivery`). Terminal: `delivered`, `cancelled`, `rejected`.
- **ORD-6** Each transition records actor, source (dashboard / telegram / system / customer), reason and timestamp. Rejection and cancellation require a reason.
- **ORD-7** Transitions are permission-checked per role and are idempotent: a repeated or stale request (e.g. a second press of an old Telegram button) never applies twice and reports the current status.
- **ORD-8** Customers can see order history and live status in bot and Mini App, and cancel within the business's window.
- **ORD-9** Optional delivery assignment to a delivery staff member.

### 3.6 Delivery (DLV)
- **DLV-1** Delivery zones per branch: name (ar/en), governorate, list of districts/areas, fee, minimum order, estimated time, active flag, optional free-delivery threshold.
- **DLV-2** Reference data: the 18 Iraqi governorates (seeded); districts are free text per zone in v1.
- **DLV-3** Pickup supported without zone.

### 3.7 Discounts (DSC)
- **DSC-1** Product-level discount (compare-at price) in v1.
- **DSC-2** Coupons (percentage / fixed, min order, usage limits, validity window) — Phase 5.

### 3.8 Notifications (NTF)
- **NTF-1** New order → message to the business's configured notification chats and linked staff with permission `orders.receive_notifications`, with action buttons valid for the current status only.
- **NTF-2** Order message is edited in place as status changes (no chat spam); all staff messages for the same order stay in sync.
- **NTF-3** Every status change → message to the customer in their language.
- **NTF-4** Delivery is asynchronous (Celery) with retries and respect for Telegram rate limits; failures never roll back the order.
- **NTF-5** Dashboard receives real-time order events over WebSocket; new-order sound alert.

### 3.9 Staff and roles (STF)
- **STF-1** Default roles seeded per business: Owner, Manager, Cashier, Kitchen, Delivery.
- **STF-2** Roles are editable sets of permissions from a fixed permission catalog; custom roles allowed.
- **STF-3** Owner role cannot be deleted or stripped; a business always has ≥1 owner.
- **STF-4** Invite staff by email/phone or one-time invitation link; staff count limited by plan.

### 3.10 Analytics (ANL)
- **ANL-1** Overview: total orders, today's orders, pending, completed, total sales, revenue trend (day/week/month), best-selling products, recent customers, average order value.
- **ANL-2** Reports by date range and branch; export CSV/XLSX.
- **ANL-3** All figures computed in the business timezone and only from `delivered` orders for revenue (configurable to include `confirmed+`).

### 3.11 Subscriptions and entitlements (SUB)
- **SUB-1** Plans (Free, Basic, Professional, Enterprise, and any new one) are data, not code: each defines entitlements (feature flags and numeric limits).
- **SUB-2** Entitlement keys (initial): `max_products`, `max_categories`, `max_staff`, `max_branches`, `max_orders_per_month`, `max_images_per_product`, `ai_assistant` (bool), `ai_messages_per_month`, `analytics_export` (bool), `custom_bot` (bool), `coupons` (bool), `remove_branding` (bool).
- **SUB-3** Per-business overrides of any entitlement (for deals/support).
- **SUB-4** Subscription lifecycle: `trialing`, `active`, `past_due`, `cancelled`, `expired`; grace period configurable. Payment is recorded manually by platform admins in v1 (Iraq: cash/ZainCash/bank transfer outside the system).
- **SUB-5** Limits enforced server-side in the service layer; the dashboard shows usage vs limit.

### 3.12 AI assistant (AI)
- **AI-1** Optional per business (entitlement + owner toggle).
- **AI-2** Understands Iraqi Arabic, MSA and English free text; extracts products, quantities, options, fulfilment hints.
- **AI-3** Answers questions using only business data (hours, zones, fees, menu, policies FAQ written by owner).
- **AI-4** Produces a structured order *proposal*; backend validates it; customer must confirm; creation goes through the normal order service (ORD-2).
- **AI-5** Never invents products, prices, discounts, availability, fees or policies; unknown → asks or hands over.
- **AI-6** Handover to human: customer request or low confidence → staff notified, AI paused for that chat.
- **AI-7** Timeouts, token/usage limits per plan, full logging (with PII minimisation), and automatic fallback to the button-based flow.

### 3.13 Platform administration (PLT)
- **PLT-1** List/search/filter all businesses; view details and usage.
- **PLT-2** Create business with owner invitation; suspend/activate with reason (audited).
- **PLT-3** Manage plans and entitlements; assign/extend subscriptions; record payments.
- **PLT-4** Platform-wide statistics (businesses, active, orders, GMV, AI usage).
- **PLT-5** Support tickets from owners (and escalated customer issues).
- **PLT-6** System health page (DB, Redis, Celery queues, bot webhooks status, error rate).
- **PLT-7** Impersonation is **not** provided; admins act via audited admin endpoints only.

## 4. Iraq-specific requirements

- **Currency:** IQD default, stored as integer amounts (no fractional dinars in practice). USD supported per business (2 minor units). Display: `12,500 د.ع` / `IQD 12,500`.
- **Phone numbers:** Normalised to E.164 `+9647XXXXXXXXX`. Accept inputs like `0770 123 4567`, `7701234567`, `+964 770…`, `00964…`, and Arabic-Indic digits (٠١٢…). Mobile prefixes 75x/77x/78x/79x validated with `phonenumbers` (region `IQ`).
- **Addresses:** Governorate → zone → free-text area + street + nearest landmark (most Iraqi deliveries rely on landmarks). Optional Telegram location share.
- **Digits:** Inputs accept both Arabic-Indic and Latin digits everywhere.
- **Time:** `Asia/Baghdad` (UTC+3, no DST). Working hours that cross midnight are common.
- **Language:** Arabic default; bot copy in a friendly Iraqi tone ("هلا بيك", "تدلل"), dashboard in clear MSA.

## 5. Non-functional requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | API latency (p95, read) | < 200 ms |
| NFR-2 | Order creation (p95) | < 500 ms |
| NFR-3 | Bot response to a button press | < 1 s (excluding AI) |
| NFR-4 | Capacity, v1 | 500 businesses, 50k orders/day on a single 4 vCPU / 8 GB host; horizontal scaling path documented |
| NFR-5 | Availability | 99.5 % monthly |
| NFR-6 | Data durability | Daily full backup + continuous WAL archiving, RPO ≤ 15 min, RTO ≤ 2 h |
| NFR-7 | Security | OWASP ASVS L2 targets; zero cross-tenant reads in tests |
| NFR-8 | Accessibility | WCAG 2.1 AA for dashboard and Mini App |
| NFR-9 | i18n | Every user-facing string translatable; RTL/LTR layout switching |
| NFR-10 | Observability | Structured logs with request/tenant IDs, Sentry, health endpoints, metrics |
| NFR-11 | Maintainability | Type-checked Python & TS, ≥ 85 % coverage on services, lint-clean CI |
| NFR-12 | Privacy | Customer PII only visible to their business; data export/delete on request |

## 6. Assumptions and constraints

- Payments: cash on delivery and pay at pickup in v1. The `payment_method` and `Payment` model are designed so local gateways (ZainCash, FastPay, Qi Card) can be added when official APIs and merchant agreements are available.
- Each business either connects its **own** bot (token from BotFather) or uses the platform's shared bot via deep link `t.me/<platform_bot>?start=<business_slug>` (lower plans).
- Telegram Bot API limits apply (~30 msgs/s per bot globally, ~1 msg/s per chat, 20 msgs/min per group).
