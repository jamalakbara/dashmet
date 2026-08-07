# dashmet — Entity Relationship Diagram

> **Version:** 0.1
> **Status:** Draft
> **Scope:** Full ER model of the PostgreSQL schema in `backend/app/models/`.
> **Companion doc:** [`docs/internal-schema-spec.md`](./internal-schema-spec.md) — field-by-field prose reference, query patterns, action-type dictionary. §8 of that doc has a short ASCII sketch; this file is the full diagram it points to.

---

## Table of Contents

1. [How to read this](#1-how-to-read-this)
2. [Full schema overview](#2-full-schema-overview)
3. [Tenancy & access layer](#3-tenancy--access-layer)
4. [Platform & account layer](#4-platform--account-layer)
5. [Structural hierarchy](#5-structural-hierarchy)
6. [Metrics & sync layer](#6-metrics--sync-layer)
7. [Notes](#7-notes)

---

## 1. How to read this

- Diagrams are [Mermaid `erDiagram`](https://mermaid.js.org/syntax/entityRelationshipDiagram.html) blocks — they render inline on GitHub and most markdown viewers.
- `PK` = primary key, `FK` = foreign key, `UK` = part of a unique constraint. A column with none of these is a plain attribute.
- Relationship lines use standard crow's-foot notation: `||` = exactly one, `o{` = zero-or-many, `||--||` = exactly one-to-one.
- Every table also carries a surrogate `uuid id PK` (via `UUIDPrimaryKeyMixin`), shown in every entity block below.
- Three tables (`metrics_daily`, `metric_action_stats`, `metric_breakdowns`) key off a polymorphic `entity_type` + `entity_id` pair rather than a single foreign key — see [§7](#7-notes) for what that means for the diagram.

---

## 2. Full schema overview

Bird's-eye view — entity names and cardinality only. See §3–§6 for full attribute lists per layer.

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERSHIPS : "has"
    USERS ||--o{ ORGANIZATION_MEMBERSHIPS : "holds"
    USERS ||--o{ ORGANIZATION_MEMBERSHIPS : "invited (nullable)"
    ORGANIZATION_MEMBERSHIPS ||--o{ MEMBERSHIP_ACCOUNTS : "grants"
    ACCOUNTS ||--o{ MEMBERSHIP_ACCOUNTS : "scoped-by"

    ORGANIZATIONS ||--o{ PLATFORM_CONNECTIONS : "owns"
    PLATFORMS ||--o{ PLATFORM_CONNECTIONS : "type-of"
    USERS ||--o{ PLATFORM_CONNECTIONS : "connected-by (nullable)"

    ORGANIZATIONS ||--o{ ACCOUNTS : "owns"
    PLATFORM_CONNECTIONS ||--o{ ACCOUNTS : "sources"
    PLATFORMS ||--o{ ACCOUNTS : "type-of"
    ACCOUNTS ||--|| ACCOUNT_CONFIGS : "configures"

    ACCOUNTS ||--o{ CAMPAIGNS : "runs"
    CAMPAIGNS ||--o{ AD_GROUPS : "contains"
    AD_GROUPS ||--o{ ADS : "contains"
    ACCOUNTS ||--o{ CREATIVES : "owns"
    CREATIVES ||--o{ ADS : "renders-as (nullable)"

    ACCOUNTS ||--o{ METRICS_DAILY : "scoped-to"
    ACCOUNTS ||--o{ METRIC_ACTION_STATS : "scoped-to"
    ACCOUNTS ||--o{ METRIC_BREAKDOWNS : "scoped-to"
    ACCOUNTS ||--o{ SYNC_JOBS : "tracks"
```

---

## 3. Tenancy & access layer

Corresponds to `docs/internal-schema-spec.md` §2. Governs who can see which organization's data, and — since per-member account access shipped — which accounts within it.

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERSHIPS : "has"
    USERS ||--o{ ORGANIZATION_MEMBERSHIPS : "holds"
    ORGANIZATION_MEMBERSHIPS ||--o{ MEMBERSHIP_ACCOUNTS : "grants"
    ACCOUNTS ||--o{ MEMBERSHIP_ACCOUNTS : "scoped-by"

    ORGANIZATIONS {
        uuid id PK
        string name
        string slug UK
        timestamptz created_at
        timestamptz updated_at
    }

    USERS {
        uuid id PK
        string email UK
        string password_hash
        string name
        boolean email_verified
        string email_verify_token "nullable"
        string reset_password_token "nullable"
        timestamptz reset_password_expires_at "nullable"
        timestamptz last_login_at "nullable"
        timestamptz created_at
        timestamptz updated_at
    }

    ORGANIZATION_MEMBERSHIPS {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK "nullable — null until invite accepted"
        string role "owner | member"
        uuid invited_by_user_id FK "nullable, SET NULL on delete"
        string invite_email "nullable"
        string invite_token "nullable"
        timestamptz invite_expires_at "nullable"
        timestamptz accepted_at "nullable"
        timestamptz created_at
    }

    MEMBERSHIP_ACCOUNTS {
        uuid id PK
        uuid membership_id FK "CASCADE"
        uuid account_id FK "CASCADE"
        timestamptz created_at
    }
```

**Unique / partial-unique constraints:**
- `organizations`: `slug`
- `users`: `email`
- `organization_memberships`: `(organization_id, user_id)`; plus a **partial** unique index `(organization_id, invite_email) WHERE invite_email IS NOT NULL` — prevents duplicate pending invites to the same email before the invitee has a `user_id`.
- `membership_accounts`: `(membership_id, account_id)`

**Access model:** owners are unrestricted (implicit access to every org account, no `membership_accounts` rows needed). Members see only accounts explicitly granted via `membership_accounts` — no row means no access. Both FKs cascade, so removing a member or an account drops the grant automatically.

---

## 4. Platform & account layer

Corresponds to `docs/internal-schema-spec.md` §3 ("Platform & Account Layer").

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ PLATFORM_CONNECTIONS : "owns"
    PLATFORMS ||--o{ PLATFORM_CONNECTIONS : "type-of"
    USERS ||--o{ PLATFORM_CONNECTIONS : "connected-by (nullable)"
    ORGANIZATIONS ||--o{ ACCOUNTS : "owns"
    PLATFORM_CONNECTIONS ||--o{ ACCOUNTS : "sources (RESTRICT delete)"
    PLATFORMS ||--o{ ACCOUNTS : "type-of"
    ACCOUNTS ||--|| ACCOUNT_CONFIGS : "configures"

    PLATFORMS {
        string id PK "meta | tiktok | google_ads"
        string name
        string currency_field "nullable"
        string timezone_field "nullable"
    }

    PLATFORM_CONNECTIONS {
        uuid id PK
        uuid organization_id FK "CASCADE"
        string platform_id FK
        text access_token "encrypted at rest"
        string token_type "default 'system_user'"
        string_array scopes "nullable"
        uuid connected_by_user_id FK "nullable, SET NULL"
        boolean is_active "default true"
        text refresh_token "nullable"
        timestamptz token_expires_at "nullable"
        timestamptz last_used_at "nullable"
        timestamptz created_at
        timestamptz updated_at
    }

    ACCOUNTS {
        uuid id PK
        uuid organization_id FK "CASCADE"
        uuid platform_connection_id FK "RESTRICT"
        string platform_id FK
        string external_id "platform-native account id"
        string name
        string currency "default USD"
        string timezone "default UTC"
        string account_status "default 'active'; 'disabled' hides it"
        string account_type "default 'standard'; e.g. 'cpas'"
        string business_id "nullable"
        string business_name "nullable"
        timestamptz synced_at "nullable"
        timestamptz created_at
    }

    ACCOUNT_CONFIGS {
        uuid id PK
        uuid account_id FK "CASCADE, UK — one config per account"
        string primary_conversion_action "default 'purchase'"
        string attribution_window "default '7d_click_1d_view'"
        string roas_action_type "default 'purchase'"
        timestamptz updated_at
    }
```

**Unique constraints:** `accounts (organization_id, platform_id, external_id)`; `account_configs (account_id)`.

**Why `platform_connection_id → accounts` is `ON DELETE RESTRICT`, not `CASCADE`:** disconnecting a platform connection must not silently delete historical account/metrics data — the connection has to be explicitly handled first. Every other tenancy foreign key cascades; this one deliberately doesn't.

---

## 5. Structural hierarchy

Corresponds to `docs/internal-schema-spec.md` §3 ("Structural Hierarchy"). Platform-agnostic naming: Meta "Ad Sets," Google "Ad Groups," TikTok "Ad Groups" are all `ad_group` internally.

```mermaid
erDiagram
    ACCOUNTS ||--o{ CAMPAIGNS : "runs"
    CAMPAIGNS ||--o{ AD_GROUPS : "contains"
    ACCOUNTS ||--o{ AD_GROUPS : "runs (denormalized for query speed)"
    AD_GROUPS ||--o{ ADS : "contains"
    CAMPAIGNS ||--o{ ADS : "rolls up to (denormalized)"
    ACCOUNTS ||--o{ ADS : "runs (denormalized)"
    ACCOUNTS ||--o{ CREATIVES : "owns"
    CREATIVES ||--o{ ADS : "renders-as (nullable, SET NULL)"

    CAMPAIGNS {
        uuid id PK
        uuid account_id FK "CASCADE"
        string platform_id FK
        string platform_campaign_id UK "with account_id"
        string name
        string status "default 'active'"
        string effective_status "default 'active'"
        string objective "nullable — normalized"
        string platform_objective "nullable — raw, e.g. PRODUCT_SALES"
        numeric daily_budget "nullable"
        numeric lifetime_budget "nullable"
        string buying_type "nullable"
        date start_date "nullable"
        date end_date "nullable"
        timestamptz synced_at "nullable"
        timestamptz created_at "nullable"
        timestamptz updated_at "nullable"
    }

    AD_GROUPS {
        uuid id PK
        uuid campaign_id FK "CASCADE"
        uuid account_id FK "CASCADE"
        string platform_id FK
        string platform_adgroup_id UK "with account_id"
        string name
        string status "default 'active'"
        string effective_status "default 'active'"
        string optimization_goal "nullable"
        string billing_event "nullable"
        numeric bid_amount "nullable"
        numeric daily_budget "nullable"
        numeric lifetime_budget "nullable"
        jsonb targeting_summary "nullable"
        date start_date "nullable"
        date end_date "nullable"
        timestamptz synced_at "nullable"
        timestamptz created_at "nullable"
        timestamptz updated_at "nullable"
    }

    ADS {
        uuid id PK
        uuid ad_group_id FK "CASCADE"
        uuid campaign_id FK "CASCADE"
        uuid account_id FK "CASCADE"
        string platform_id FK
        string platform_ad_id UK "with account_id"
        string name
        string status "default 'active'"
        string effective_status "default 'active'"
        uuid creative_id FK "nullable, SET NULL"
        timestamptz synced_at "nullable"
        timestamptz created_at "nullable"
        timestamptz updated_at "nullable"
    }

    CREATIVES {
        uuid id PK
        string platform_id FK
        uuid account_id FK "CASCADE"
        string platform_creative_id UK "with account_id"
        string name "nullable"
        string format "nullable"
        text title "nullable"
        string body "nullable, max 5000 chars"
        string image_url "nullable"
        string thumbnail_url "nullable"
        string video_id "nullable"
        string cta_type "nullable"
        string destination_url "nullable"
        jsonb raw_spec "nullable — full platform payload"
        timestamptz synced_at "nullable"
    }
```

**Unique constraints:** `campaigns (account_id, platform_campaign_id)`; `ad_groups (account_id, platform_adgroup_id)`; `ads (account_id, platform_ad_id)`; `creatives (account_id, platform_creative_id)`.

**Note:** `account_id` on `ad_groups` and `ads` duplicates what's derivable by walking `campaign_id`/`ad_group_id` up the tree — intentional denormalization so any metrics/access query can filter on `account_id` directly at any level.

---

## 6. Metrics & sync layer

Corresponds to `docs/internal-schema-spec.md` §4–§5. This is where the polymorphic pattern lives: one metrics row can belong to an `account`, `campaign`, `ad_group`, or `ad`, discriminated by `entity_type` + `entity_id` rather than four separate nullable foreign-key columns.

```mermaid
erDiagram
    ACCOUNTS ||--o{ SYNC_JOBS : "tracks (real FK, CASCADE)"
    ACCOUNTS ||--o{ METRICS_DAILY : "scoped-to (see note)"
    ACCOUNTS ||--o{ METRIC_ACTION_STATS : "scoped-to (see note)"
    ACCOUNTS ||--o{ METRIC_BREAKDOWNS : "scoped-to (see note)"

    METRICS_DAILY {
        uuid id PK
        string entity_type "account | campaign | ad_group | ad"
        uuid entity_id "polymorphic"
        string platform_id
        uuid account_id
        date date
        bigint impressions "nullable"
        bigint reach "nullable — non-additive, never summed"
        numeric frequency "nullable"
        bigint clicks "nullable"
        numeric spend "nullable"
        numeric ctr "nullable"
        numeric cpm "nullable"
        numeric cpc "nullable"
        numeric cpp "nullable"
        bigint unique_clicks "nullable"
        bigint inline_link_clicks "nullable"
        bigint unique_inline_link_clicks "nullable"
        numeric inline_link_click_ctr "nullable"
        numeric unique_ctr "nullable"
        numeric cost_per_inline_link_click "nullable"
        numeric cost_per_unique_click "nullable"
        bigint inline_post_engagement "nullable"
        numeric cost_per_inline_post_engagement "nullable"
        numeric auction_bid "nullable"
        numeric auction_competitiveness "nullable"
        numeric auction_max_competitor_bid "nullable"
        bigint total_actions "nullable"
        bigint total_unique_actions "nullable"
        numeric result_rate "nullable"
        numeric estimated_ad_recall_rate "nullable"
        bigint estimated_ad_recallers "nullable"
        timestamptz fetched_at "nullable — freshness token source"
        boolean is_estimated "default false"
        string attribution_window "nullable — see §7"
    }

    METRIC_ACTION_STATS {
        uuid id PK
        string entity_type
        uuid entity_id "polymorphic"
        string platform_id
        uuid account_id
        date date
        string field_name "e.g. actions, action_values, page_events"
        string action_type "e.g. purchase, add_to_cart, engagement"
        numeric value
        timestamptz fetched_at "nullable"
    }

    METRIC_BREAKDOWNS {
        uuid id PK
        string entity_type
        uuid entity_id "polymorphic"
        string platform_id
        uuid account_id
        date date
        string breakdown_type "age | gender | placement | ..."
        string breakdown_value
        bigint impressions "nullable"
        bigint reach "nullable"
        bigint clicks "nullable"
        numeric spend "nullable"
        numeric conversions "nullable"
        numeric ctr "nullable"
        numeric cpm "nullable"
        numeric cpc "nullable"
        timestamptz fetched_at "nullable"
    }

    SYNC_JOBS {
        uuid id PK
        uuid account_id FK "CASCADE"
        string platform_id
        string job_type "structure | insights_daily | breakdown | creatives | async_submit"
        string entity_type "nullable"
        date date_start "nullable"
        date date_stop "nullable"
        string breakdown_type "nullable"
        string status "pending | running | completed | failed"
        string platform_job_id "nullable — async report_run_id"
        integer rows_written "nullable"
        text error_message "nullable"
        integer rate_limit_pct_at_start "nullable"
        timestamptz started_at "nullable"
        timestamptz completed_at "nullable"
        timestamptz created_at
    }
```

**Unique constraints:**
- `metrics_daily`: `(entity_type, entity_id, date)` — note this does not currently include `attribution_window`; see §7.
- `metric_action_stats`: `(entity_id, date, field_name, action_type)`
- `metric_breakdowns`: `(entity_id, date, breakdown_type, breakdown_value)`
- `sync_jobs`: no unique constraint (multiple rows per account/type/day are expected — one per sync attempt); indexed on `(account_id, job_type, status)` and `(job_type, status, platform_job_id)` for the async poll loop.

---

## 7. Notes

**Polymorphic association, not a modeled foreign key.** `metrics_daily`, `metric_action_stats`, and `metric_breakdowns` key off `entity_type` (a string discriminator: `account | campaign | ad_group | ad`) + `entity_id` (a bare `uuid`). A single column can't declare a foreign key to four different parent tables, so referential integrity here is enforced by application code and tests, not the database. Every query against these tables must filter by `account_id` values that belong to the requesting user's `organization_id` — never trust a client-supplied `account_id` alone.

**`account_id` and `platform_id` on the three metrics tables are plain columns, not foreign keys** — same reasoning as above (a metrics row's real anchor is the polymorphic `entity_id`; `account_id` is a denormalized convenience column for fast scoping). `sync_jobs.account_id` is the one exception in this layer — it references exactly one table, so it's a real foreign key with `ON DELETE CASCADE`.

**`attribution_window` is not part of `metrics_daily`'s unique constraint.** The column exists, but `uq_metrics_daily_entity_date` only covers `(entity_type, entity_id, date)`. In practice, this means an upsert keyed on that constraint could overwrite one attribution window's spend with another's if an account's window setting ever changes or a backfill runs under a different window than the original sync. Flagged in `docs/prd.md` §9 as a known gap.

**`platforms` is intentionally a tiny lookup table** (`id`, `name`, `currency_field`, `timezone_field`) for the three currently-integrated platforms (`meta`, `tiktok`, `google_ads`) — not a general config store.
