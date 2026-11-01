# 03 — Entity-Relationship Diagrams

Split by domain for readability. Field details are in [04-DATA-MODELS.md](04-DATA-MODELS.md).
Every entity marked *(T)* carries `business_id` and is tenant-scoped.

## 1. Identity, businesses, staff

```mermaid
erDiagram
    USER ||--o{ MEMBERSHIP : has
    BUSINESS ||--o{ MEMBERSHIP : employs
    ROLE ||--o{ MEMBERSHIP : grants
    BUSINESS ||--o{ ROLE : defines
    ROLE }o--o{ PERMISSION : includes
    USER ||--o| TELEGRAM_ACCOUNT : links
    BUSINESS ||--o{ BRANCH : has
    BUSINESS ||--|| BUSINESS_SETTINGS : configures
    BUSINESS ||--o| TELEGRAM_BOT : connects
    BRANCH ||--o{ WORKING_HOURS : opens
    BRANCH ||--o{ CLOSURE : closes
    BUSINESS ||--o{ STAFF_INVITATION : sends
    GOVERNORATE ||--o{ BRANCH : located_in

    USER {
        uuid id PK
        string email UK
        string phone UK
        bool is_platform_admin
    }
    BUSINESS {
        uuid id PK
        string slug UK
        string status
        char currency
    }
    MEMBERSHIP {
        uuid id PK
        uuid user_id FK
        uuid business_id FK
        uuid role_id FK
        bool is_active
    }
    ROLE {
        uuid id PK
        uuid business_id FK
        string name
        bool is_owner
    }
    TELEGRAM_BOT {
        uuid id PK
        uuid business_id FK
        bytes token_encrypted
        string webhook_secret
    }
```

## 2. Catalog

```mermaid
erDiagram
    BUSINESS ||--o{ CATEGORY : has
    CATEGORY ||--o{ CATEGORY : parent_of
    CATEGORY ||--o{ PRODUCT : groups
    PRODUCT ||--o{ PRODUCT_IMAGE : shows
    PRODUCT ||--o{ OPTION_GROUP : offers
    OPTION_GROUP ||--o{ OPTION : contains
    BRANCH ||--o{ PRODUCT_BRANCH_AVAILABILITY : overrides
    PRODUCT ||--o{ PRODUCT_BRANCH_AVAILABILITY : per_branch

    PRODUCT {
        uuid id PK
        uuid business_id FK
        uuid category_id FK
        bigint price
        bigint compare_at_price
        string availability
        bool track_stock
        int stock_quantity
    }
    OPTION_GROUP {
        uuid id PK
        uuid product_id FK
        string selection_type
        int min_select
        int max_select
    }
    OPTION {
        uuid id PK
        uuid group_id FK
        bigint price_delta
        bool is_available
    }
```

## 3. Customers, carts, orders, delivery

```mermaid
erDiagram
    BUSINESS ||--o{ CUSTOMER : serves
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : saves
    CUSTOMER ||--o{ CART : owns
    CART ||--o{ CART_ITEM : contains
    CART_ITEM }o--|| PRODUCT : references
    CART_ITEM ||--o{ CART_ITEM_OPTION : selects
    CUSTOMER ||--o{ ORDER : places
    BRANCH ||--o{ ORDER : fulfils
    ORDER ||--o{ ORDER_ITEM : contains
    ORDER_ITEM ||--o{ ORDER_ITEM_OPTION : snapshot
    ORDER ||--o{ ORDER_STATUS_EVENT : history
    ORDER ||--o{ ORDER_NOTIFICATION_MESSAGE : tracked_in
    ORDER }o--o| DELIVERY_ZONE : delivered_to
    ORDER }o--o| MEMBERSHIP : assigned_driver
    BRANCH ||--o{ DELIVERY_ZONE : covers
    BUSINESS ||--|| ORDER_COUNTER : numbers

    CUSTOMER {
        uuid id PK
        uuid business_id FK
        bigint telegram_user_id
        string phone
        string language
    }
    ORDER {
        uuid id PK
        uuid business_id FK
        int number
        string status
        int version
        string idempotency_key
        bigint subtotal
        bigint delivery_fee
        bigint discount_total
        bigint total
    }
    ORDER_ITEM {
        uuid id PK
        uuid order_id FK
        uuid product_id FK "nullable, SET NULL"
        string product_name_snapshot
        bigint unit_price_snapshot
        int quantity
        bigint line_total
    }
    DELIVERY_ZONE {
        uuid id PK
        uuid branch_id FK
        bigint fee
        bigint min_order
        bigint free_delivery_threshold
    }
```

## 4. Subscriptions, AI, platform

```mermaid
erDiagram
    PLAN ||--o{ PLAN_ENTITLEMENT : defines
    FEATURE ||--o{ PLAN_ENTITLEMENT : valued_in
    BUSINESS ||--o{ SUBSCRIPTION : subscribes
    PLAN ||--o{ SUBSCRIPTION : sold_as
    BUSINESS ||--o{ ENTITLEMENT_OVERRIDE : granted
    FEATURE ||--o{ ENTITLEMENT_OVERRIDE : overrides
    BUSINESS ||--o{ USAGE_COUNTER : consumes
    SUBSCRIPTION ||--o{ SUBSCRIPTION_PAYMENT : paid_by
    BUSINESS ||--o{ AI_CONVERSATION : chats
    CUSTOMER ||--o{ AI_CONVERSATION : participates
    AI_CONVERSATION ||--o{ AI_MESSAGE : contains
    BUSINESS ||--o{ KNOWLEDGE_ENTRY : answers_from
    BUSINESS ||--o{ SUPPORT_TICKET : opens
    SUPPORT_TICKET ||--o{ SUPPORT_MESSAGE : thread
    USER ||--o{ AUDIT_LOG : performs
    BUSINESS ||--o{ DAILY_BUSINESS_STATS : aggregates

    FEATURE {
        string key PK
        string value_type "bool|int"
    }
    PLAN_ENTITLEMENT {
        uuid plan_id FK
        string feature_key FK
        json value
    }
    SUBSCRIPTION {
        uuid id PK
        uuid business_id FK
        uuid plan_id FK
        string status
        datetime current_period_end
    }
    USAGE_COUNTER {
        uuid business_id FK
        string feature_key FK
        date period_start
        int used
    }
```
