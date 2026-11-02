# 04 — Data Models

Conventions (apply to every model unless noted):

- `id` — UUIDv7 primary key (time-ordered → good index locality, not enumerable).
- `created_at`, `updated_at` — `timestamptz`, auto.
- *(T)* = tenant-scoped: `business_id` FK (non-null, indexed, `on_delete=PROTECT`) and manager method `for_business()`.
- **Money** = `BigIntegerField` in the currency's minor unit (IQD exponent 0 → `12500` = 12,500 IQD; USD exponent 2 → `1250` = $12.50). Never floats. A `Money` value object handles arithmetic and formatting.
- **Translatable text** = paired fields `name_ar`, `name_en` (simple, indexable, searchable; only two languages are required).
- Soft delete only where history needs it (products, categories): `is_archived`; orders keep snapshots so hard references are not required.
- Django app owning each model in brackets.

## accounts

**User** [accounts] — custom user model (`AUTH_USER_MODEL`)
| Field | Type | Notes |
|-------|------|-------|
| email | citext, unique, nullable | at least one of email/phone required (check constraint) |
| phone | varchar(16), unique, nullable | E.164 |
| password | Django hash | Argon2 hasher |
| full_name | varchar(150) | |
| language | enum `ar`,`en` | default `ar` |
| is_platform_admin | bool | platform super-admin |
| totp_secret_encrypted | bytea, nullable | 2FA |
| is_active, last_login, date_joined | | |

**TelegramAccount** [accounts] — links a dashboard user to Telegram (staff notifications/actions)
| telegram_user_id | bigint, unique |
| user | O2O → User |
| username, first_name | varchar |
| linked_at | timestamptz |

**TelegramLinkCode** [accounts] — one-time code (hashed), user FK, expires_at (10 min), used_at.

## businesses

**Business** [businesses]
| Field | Type | Notes |
|-------|------|-------|
| slug | varchar(50), unique | used in shared-bot deep links and Mini App URL |
| name_ar, name_en | varchar(120) | |
| description_ar, description_en | text | |
| business_type | enum | restaurant, cafe, bakery, grocery, pharmacy, retail, other |
| logo, cover | image (S3 key) | |
| phone, whatsapp | E.164 | |
| currency | char(3) | `IQD` default, `USD` |
| default_language | enum | `ar` |
| timezone | varchar | `Asia/Baghdad` |
| status | enum | `active`, `inactive`, `suspended` |
| suspended_reason | text | |
| owner | FK → User | billing owner (also has Owner membership) |

**Branch** (T) — name_ar/en, governorate FK, address, location (lat/lng decimals), phone, is_default (partial unique per business), is_active, is_temporarily_closed, accepts_delivery, accepts_pickup, accepts_dine_in (table-QR orders, default off).

**WorkingHours** (T) — branch FK, weekday (0–6), opens_at (time), closes_at (time; `closes_at <= opens_at` means crosses midnight). Multiple rows per weekday allowed.

**Closure** (T) — branch FK, starts_at, ends_at, reason.

**BusinessSettings** (T, O2O Business)
| min_order_amount | money |
| customer_cancel_window_min | int, default 5 |
| auto_reject_after_min | int, nullable |
| allow_order_notes | bool |
| loyalty_enabled, loyalty_spend_per_point (1000), loyalty_point_value (25), loyalty_min_redeem (100) | bool + minor units | 1 point per `spend` paid on delivered orders; a point is worth `value` at checkout |
| require_verified_phone | bool, default true | checkout needs a verified phone (only while a WhatsApp sender is configured) |
| payment_methods | array enum (`cash_on_delivery`, `pay_at_pickup`) |
| ai_enabled | bool |
| ai_persona_note | text (owner-written tone/rules, ≤ 1000 chars) |
| welcome_message_ar/en | text |
| notification_chat_ids | array bigint (groups/channels) |

**TelegramBot** (T, O2O Business; or null when using the shared bot)
| bot_telegram_id | bigint, unique |
| username | varchar |
| token_encrypted | bytea | Fernet (MultiFernet for key rotation) |
| webhook_secret | varchar(64) | random, `secrets.token_urlsafe` |
| webhook_status | enum `pending`,`active`,`error` + last_error |
| is_shared_platform_bot | bool | exactly one row platform-wide may be true (partial unique) |

**Governorate** (reference, global) — code, name_ar, name_en. Seeded with 18 governorates.

## staff

**Permission catalog** — Python constant, synced to table `staff_permission(codename, group, description)` by migration. Examples:
`orders.view`, `orders.receive_notifications`, `orders.transition.confirmed`, `orders.transition.rejected`,
`orders.transition.preparing`, `orders.transition.ready`, `orders.transition.out_for_delivery`,
`orders.transition.delivered`, `orders.cancel`, `orders.assign_driver`, `catalog.view`, `catalog.edit`,
`catalog.edit_prices`, `customers.view`, `customers.view_pii`, `staff.manage`, `delivery.manage`,
`reports.view`, `reports.export`, `settings.edit`, `telegram.edit`, `billing.manage`.

**Role** (T) — name, is_owner (bool, one per business, protected), is_system (seeded default), permissions M2M → Permission. Unique (business, name).

**Membership** (T) — user FK, role FK (same business), branch scope (nullable M2M: restrict to branches), is_active, invited_by. Unique (business, user).

**StaffInvitation** (T) — email/phone, role FK, token_hash, expires_at, accepted_at.

Default role permissions:

| Permission group | Owner | Manager | Cashier | Kitchen | Delivery |
|------------------|:-----:|:-------:|:-------:|:-------:|:--------:|
| orders view/notify | ✔ | ✔ | ✔ | ✔ | own assigned |
| confirm / reject | ✔ | ✔ | ✔ | | |
| preparing / ready | ✔ | ✔ | ✔ | ✔ | |
| out_for_delivery / delivered | ✔ | ✔ | ✔ | | ✔ |
| cancel | ✔ | ✔ | | | |
| catalog edit / prices | ✔ | ✔ | | | |
| customers PII | ✔ | ✔ | ✔ | | assigned order only |
| staff, telegram, billing | ✔ | staff only | | | |
| reports / export | ✔ | ✔ | | | |

## categories / products

**Category** (T) — name_ar/en, image, parent FK (self, nullable, depth ≤ 1 enforced in service), sort_order, is_active, is_archived. Index (business, is_active, sort_order).

**Product** (T)
| Field | Type | Notes |
|-------|------|-------|
| category | FK → Category (same business) | PROTECT |
| name_ar, name_en | varchar(150) | |
| description_ar, description_en | text | |
| sku | varchar(64), nullable | unique per business when set |
| price | money, ≥ 0 | base price |
| compare_at_price | money, nullable | must be > price when set (check constraint) — shows discount |
| availability | enum | `available`, `out_of_stock`, `hidden` |
| track_stock | bool | |
| stock_quantity | int ≥ 0, nullable | required when track_stock |
| prep_time_min | int, nullable | |
| tags | array varchar | `spicy`, `vegetarian`, `new`, `best_seller`… |
| sort_order | int | |
| is_archived | bool | archived products disappear from catalog but keep order history |
| search_vector | tsvector (generated) | from normalised Arabic + English text, GIN index |
| search_text_normalised | text | Arabic-normalised name/desc for trigram (`pg_trgm`) search |

**ProductImage** (T) — product FK, image key, thumbnail key, width, height, sort_order, alt_ar/en.

**OptionGroup** (T) — product FK, name_ar/en, selection_type (`single`, `multiple`), is_required, min_select, max_select (check: 0 ≤ min ≤ max; single ⇒ max = 1), sort_order.

**Option** (T) — group FK, name_ar/en, price_delta (money, may be 0, ≥ 0), is_available, is_default, sort_order.

**ProductBranchAvailability** (T) — product FK, branch FK, availability override, stock override. (Multi-branch phase.)

## customers

**Customer** (T) — one row per (business, telegram user).
| telegram_user_id | bigint | unique (business, telegram_user_id) |
| telegram_username, first_name, last_name | | from Telegram, refreshed |
| full_name | varchar | as given at checkout |
| phone | E.164, nullable | last confirmed phone |
| phone_verified_at | timestamp, nullable | set only when `phone` was proven (WhatsApp code or own Telegram contact); cleared when the phone changes |
| language | `ar`/`en` | |
| is_blocked | bool + reason | business can block abusive customers |
| first_order_at, last_order_at, orders_count, total_spent | denormalised stats | updated in order service |

**PhoneVerification** (T) — customer FK, phone (E.164), code_hash (HMAC-SHA256 of the 6-digit code;
the code itself is never stored), expires_at (10 min), attempts (max 5), verified_at. A new code
expires the previous ones.

**LoyaltyEntry** (T) — append-only points ledger: customer, order (nullable), delta, reason
(`earn` on delivery, `redeem` at checkout, `refund` on cancel/reject, `adjust` by staff with a
note), balance_after. `Customer.points_balance` is its running sum, changed only together with an
entry under a row lock; unique (order, reason) makes earn/redeem/refund idempotent. Orders keep
`points_redeemed` and `points_discount` (included in `discount_total`).

**CustomerAddress** (T) — customer FK, label (home/work/other), zone FK, area, street, landmark, building/floor, location lat/lng, is_default.

## orders

**Cart** (T) — customer FK, branch FK, status (`active`, `converted`, `abandoned`), expires_at. Partial unique (customer, branch) where status = active.

**CartItem** (T) — cart FK, product FK, quantity (1–99), note, `options_fingerprint` (sorted option IDs hash; unique (cart, product, fingerprint) → merging).

**CartItemOption** — cart_item FK, option FK.

**OrderCounter** (T, PK = business) — `last_number`; incremented under `SELECT … FOR UPDATE` inside the order transaction.

**Order** (T)
| Field | Type | Notes |
|-------|------|-------|
| number | int | unique (business, number) |
| branch | FK | |
| customer | FK | PROTECT |
| channel | enum | `bot`, `mini_app`, `ai`, `dashboard` |
| status | enum | `pending`, `confirmed`, `preparing`, `ready`, `out_for_delivery`, `delivered`, `cancelled`, `rejected` |
| version | int | optimistic concurrency for transitions |
| fulfilment | enum | `delivery`, `pickup`, `dine_in` (from a table QR: no phone, no address, `ready → delivered` = served) |
| table_label | varchar(10) | dine-in table number `[A-Za-z0-9]{1,10}` |
| idempotency_key | uuid | unique (business, customer, idempotency_key) |
| customer_name, customer_phone | snapshot | |
| delivery_zone | FK nullable (SET NULL) + `zone_name_snapshot` | |
| address_text, landmark, location lat/lng | snapshot | |
| notes | text ≤ 500 | |
| payment_method, payment_status | enum | `unpaid`, `paid`, `refunded` |
| currency | char(3) | snapshot of business currency |
| subtotal, delivery_fee, discount_total, total | money | check: total = subtotal + delivery_fee − discount_total ≥ 0 |
| assigned_driver | FK Membership, nullable | |
| placed_at, confirmed_at, ready_at, delivered_at, cancelled_at | timestamptz | |
| cancel_reason / reject_reason | text | |

Indexes: (business, status, placed_at desc), (business, placed_at), (business, customer, placed_at desc).

**OrderItem** (T) — order FK, product FK (SET NULL), `product_name_ar/en_snapshot`, `unit_price_snapshot` (base + options), quantity, line_total, note.

**OrderItemOption** — order_item FK, option FK (SET NULL), `group_name_snapshot`, `option_name_snapshot`, `price_delta_snapshot`.

**OrderStatusEvent** (T) — order FK, from_status, to_status, actor_user (nullable), actor_customer (nullable), source (`dashboard`,`telegram`,`mini_app`,`system`,`customer`), reason, created_at. Append-only.

**OrderNotificationMessage** (T) — order FK, bot FK, chat_id, message_id, kind (`staff`, `customer`). Lets the system edit every copy of the order message on status change.

**Transition table** (code, not DB — the state machine is a domain rule, versioned with the code):

| From | To | Permission |
|------|----|-----------|
| pending | confirmed | orders.transition.confirmed |
| pending | rejected | orders.transition.rejected |
| pending | cancelled | customer within window, or orders.cancel |
| confirmed | preparing | orders.transition.preparing |
| preparing | ready | orders.transition.ready |
| ready | out_for_delivery | orders.transition.out_for_delivery (delivery orders only) |
| ready | delivered | orders.transition.delivered (pickup orders only) |
| out_for_delivery | delivered | orders.transition.delivered |
| confirmed / preparing / ready / out_for_delivery | cancelled | orders.cancel |

Cancelling or rejecting restores stock for tracked products.

**OrderReview** (T) — order (1:1), customer, rating 1–5 (check constraint), comment ≤500, reply ≤500,
replied_at, replied_by. Only the order's customer, only for a `delivered` order, editable for 7 days
after delivery. Shop average and count are public in the storefront info (`rating_avg`, `rating_count`).

## delivery

**DeliveryZone** (T) — branch FK, name_ar/en, governorate FK, areas (array text, normalised for matching), fee, min_order (nullable), free_delivery_threshold (nullable), eta_min/eta_max (minutes), is_active, sort_order.

## notifications

**NotificationOutbox** — event type, payload JSON, dedup_key (unique), status, attempts, next_attempt_at, last_error. Written in the same transaction as the domain change (transactional outbox), drained by Celery → no lost or duplicated notifications even if the worker crashes. The drain leases due rows in a short transaction (`next_attempt_at` = lease expiry), sends with no transaction open, and writes each result back only while it still holds the lease. One drain runs at a time (cache lock), and a business whose bot is rate-limited, unreachable or rejected (401/404) is paused for the rest of the run.

## subscriptions

**Feature** (global) — key (PK, e.g. `max_products`), value_type (`bool`, `int`), default_value, is_metered (bool), reset_period (`none`, `month`), description.

**Plan** (global) — code (`free`, `basic`, `pro`, `enterprise`, …), name_ar/en, monthly_price (money, currency), is_public, is_active, sort_order, trial_days.

**PlanEntitlement** — plan FK, feature FK, value (JSON: `true`/`false`/int; `null` = unlimited). Unique (plan, feature).

**Subscription** (T) — plan FK, status (`trialing`, `active`, `past_due`, `cancelled`, `expired`), current_period_start/end, grace_until, cancel_at_period_end. Partial unique: one non-terminal subscription per business.

**SubscriptionPayment** (T) — subscription FK, amount, currency, method (`cash`, `zaincash`, `bank_transfer`, `other`), reference, recorded_by (platform admin), paid_at.

**EntitlementOverride** (T) — feature FK, value, reason, expires_at, created_by.

**UsageCounter** (T) — feature FK, period_start, used. Unique (business, feature, period_start). Incremented atomically (`F('used') + 1`) with limit check in the same statement.

**Entitlement resolution:** override (if not expired) → active subscription's plan entitlement → feature default. Cached in Redis per business, invalidated on change. API: `entitlements.check(business, "max_products", increment=1)` raises `PlanLimitExceeded`.

## chatbot (AI)

**KnowledgeEntry** (T) — question/topic, answer_ar/en, is_active (owner-written FAQ, policies).

**AIConversation** (T) — customer FK, status (`active`, `handed_over`, `closed`), handed_over_to (Membership), last_activity_at.

**AIMessage** (T) — conversation FK, role (`user`, `assistant`, `tool`), content (PII-masked copy), tool_name, tokens_in, tokens_out, latency_ms, provider, model, error.

**AIProposal** (T) — conversation FK, raw_intent JSON, validated_lines JSON, status (`proposed`, `confirmed`, `rejected`, `expired`), order FK (nullable).

## analytics

**DailyBusinessStats** (T) — date (business TZ), branch FK nullable, orders_count, delivered_count, cancelled_count, gross_sales, delivery_fees, new_customers. Unique (business, branch, date). Rebuilt nightly + updated incrementally on order delivery.

**ProductDailyStats** (T) — date, product FK, quantity_sold, revenue.

## platform

**SupportTicket** — business FK, opened_by (User), subject, status (`open`, `pending`, `resolved`, `closed`), priority. **SupportMessage** — ticket FK, author, body, attachments.

**AuditLog** — actor (User), business (nullable), action, target_type, target_id, changes JSON, ip, user_agent, created_at. Append-only; written for security-relevant actions (role/permission changes, suspensions, token changes, price changes, exports).
