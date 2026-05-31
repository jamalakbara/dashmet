# DashMet — Internal Schema Specification

> **Version:** 0.1  
> **Status:** Draft  
> **Scope:** Platform-agnostic normalized schema covering Meta Ads (v1), with extension points for Google Ads, TikTok Ads, and Google Analytics.

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Platform & Account Layer](#2-platform--account-layer)
3. [Structural Hierarchy](#3-structural-hierarchy)
4. [Metrics Layer](#4-metrics-layer)
   - [4.1 metrics_daily — Scalar Metrics](#41-metrics_daily--scalar-metrics)
   - [4.2 metric_action_stats — Array Metrics](#42-metric_action_stats--array-metrics)
   - [4.3 metric_breakdowns — Breakdown Dimensions](#43-metric_breakdowns--breakdown-dimensions)
5. [Sync & Job Tracking](#5-sync--job-tracking)
6. [Platform Mapping Reference](#6-platform-mapping-reference)
7. [Action Types Reference](#7-action-types-reference)
8. [Schema Diagram](#8-schema-diagram)
9. [Query Patterns](#9-query-patterns)
10. [Extension Notes](#10-extension-notes)

---

## 1. Design Principles

**1. Normalize structure, denormalize for speed.**  
The entity hierarchy (account → campaign → ad_group → ad → creative) is normalized to avoid duplication. Metrics are stored flat per entity per day for fast read access.

**2. Separate scalar metrics from array metrics.**  
Meta returns many fields as `list<AdsActionStats>` — arrays of `{ action_type, value }` pairs. These cannot be stored in a flat row. A dedicated `metric_action_stats` table handles all array-typed fields, keyed by `(entity, date, field_name, action_type)`.

**3. Platform-agnostic entity names.**  
Meta calls them "Ad Sets", Google Ads calls them "Ad Groups", TikTok calls them "Ad Groups". Internally they are all `ad_group`. The `platform_entity_name` column records the platform's native name for reference.

**4. Store raw, compute derived.**  
Store raw fields from the API (impressions, clicks, spend, conversion_value). Compute derived metrics at query time (ROAS = conversion_value / spend, frequency = impressions / reach, CTR = clicks / impressions × 100). Exception: store pre-computed `ctr`, `cpm`, `cpc`, `cpp` when the platform returns them directly, as these may use platform-internal logic.

**5. Per-account conversion configuration.**  
Each ad account defines which `action_type` counts as its primary conversion (e.g. `purchase` for ecom, `lead` for B2B). This is stored in `account_configs` and used when surfacing "conversions" and "CPA" in the dashboard.

**6. Respect fetch boundaries.**  
Unique metrics (reach, unique_clicks, etc.) are slower to compute and should be fetched in a separate API call from non-unique metrics. The schema stores them together, but the sync layer must fetch them separately.

---

## 2. SaaS / Multi-tenancy Layer

### `organizations`

The top-level tenant. Every user belongs to one or more organizations. All ad account data is scoped to an organization.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `name` | varchar | Display name (e.g. "Acme Marketing") |
| `slug` | varchar UNIQUE | URL-safe identifier (e.g. `acme-marketing`) |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `email` | varchar UNIQUE | |
| `password_hash` | varchar | bcrypt |
| `name` | varchar | Display name |
| `email_verified` | boolean | Default `false` — must verify before access |
| `email_verify_token` | varchar | Null once verified |
| `reset_password_token` | varchar | Short-lived, null when not in use |
| `reset_password_expires_at` | timestamp | |
| `last_login_at` | timestamp | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

### `organization_memberships`

Links users to organizations with a role.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `organization_id` | uuid FK → organizations | |
| `user_id` | uuid FK → users | |
| `role` | varchar | `owner` \| `member` |
| `invited_by_user_id` | uuid FK → users | Null if self-registered |
| `invite_token` | varchar | Set when invite is pending, null once accepted |
| `invite_expires_at` | timestamp | |
| `accepted_at` | timestamp | Null until invite accepted |
| `created_at` | timestamp | |

**Role permissions:**

| Action | Owner | Member |
|---|---|---|
| View dashboard | ✅ | ✅ |
| Connect / disconnect ad accounts | ✅ | ❌ |
| Invite members | ✅ | ❌ |
| Remove members | ✅ | ❌ |
| Update org settings | ✅ | ❌ |
| Trigger manual sync | ✅ | ❌ |

### `platform_connections`

Stores the access token per org per platform. Replaces any notion of a global `META_ACCESS_TOKEN` env variable — each org connects their own ad accounts.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `organization_id` | uuid FK → organizations | |
| `platform_id` | varchar FK → platforms | |
| `access_token` | varchar | Encrypted at rest |
| `token_type` | varchar | `system_user` \| `user_token` |
| `scopes` | varchar[] | e.g. `["ads_read", "read_insights"]` |
| `connected_by_user_id` | uuid FK → users | Who connected this |
| `is_active` | boolean | False = disconnected |
| `last_used_at` | timestamp | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

> **Security:** `access_token` is encrypted at rest (e.g. AES-256 via a KMS key). It is never returned in any API response. The sync worker reads it directly from the DB at job execution time.

---

## 3. Platform & Account Layer

### `platforms`

Reference table. Populated at deploy time — not synced from any API.

| Column | Type | Notes |
|---|---|---|
| `id` | varchar PK | `meta` \| `google_ads` \| `tiktok` \| `google_analytics` |
| `name` | varchar | Display name (e.g. "Meta Ads") |
| `currency_field` | varchar | Field name used for currency in API response |
| `timezone_field` | varchar | Field name used for timezone in API response |

### `accounts`

One row per ad account per platform, scoped to an organization.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | Internal ID |
| `organization_id` | uuid FK → organizations | Tenant owner of this account |
| `platform_connection_id` | uuid FK → platform_connections | Which connection token to use for syncing |
| `platform_id` | varchar FK → platforms | |
| `external_id` | varchar | Platform's native ID (e.g. `act_1234567890` for Meta) |
| `name` | varchar | Account name |
| `currency` | varchar | ISO 4217 code (e.g. `USD`) |
| `timezone` | varchar | IANA timezone (e.g. `America/Los_Angeles`) |
| `account_status` | varchar | `active` \| `disabled` \| `pending_review` \| `closed` |
| `business_id` | varchar | Parent business ID (Meta: Business Manager ID) |
| `business_name` | varchar | |
| `synced_at` | timestamp | Last time this account record was updated |
| `created_at` | timestamp | |

### `account_configs`

Per-account configuration that affects how metrics are displayed.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `account_id` | uuid FK → accounts | |
| `primary_conversion_action` | varchar | Action type that = "a conversion" for this account (e.g. `purchase`, `lead`) |
| `attribution_window` | varchar | `7d_click` \| `1d_click` \| `7d_click_1d_view` — must match platform settings |
| `roas_action_type` | varchar | Action type used for ROAS calculation (usually `purchase`) |
| `updated_at` | timestamp | |

> **Why this matters:** Meta's Ads Manager uses a specific attribution window per account. If your API call doesn't match that window, conversion numbers will differ. Store the expected window here and always pass `action_attribution_windows` in insights requests.

---

## 3. Structural Hierarchy

### `campaigns`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | Internal ID |
| `account_id` | uuid FK → accounts | |
| `platform_id` | varchar FK → platforms | Denormalized for query convenience |
| `platform_campaign_id` | varchar | Platform's native ID |
| `name` | varchar | |
| `status` | varchar | `active` \| `paused` \| `deleted` \| `archived` |
| `effective_status` | varchar | Actual delivery state (accounts for parent/budget status) |
| `objective` | varchar | Normalized: `awareness` \| `traffic` \| `engagement` \| `leads` \| `app_promotion` \| `sales` |
| `platform_objective` | varchar | Raw platform value (e.g. `OUTCOME_SALES`) |
| `daily_budget` | numeric | In account currency units (not cents) |
| `lifetime_budget` | numeric | In account currency units |
| `buying_type` | varchar | `auction` \| `reserved` |
| `start_date` | date | |
| `end_date` | date | Null if ongoing |
| `synced_at` | timestamp | |
| `created_at` | timestamp | Platform-reported creation time |
| `updated_at` | timestamp | Platform-reported update time |

### `ad_groups`

Meta name: "Ad Set". Google Ads / TikTok name: "Ad Group".

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `campaign_id` | uuid FK → campaigns | |
| `account_id` | uuid FK → accounts | Denormalized |
| `platform_id` | varchar FK → platforms | Denormalized |
| `platform_adgroup_id` | varchar | |
| `name` | varchar | |
| `status` | varchar | `active` \| `paused` \| `deleted` \| `archived` |
| `effective_status` | varchar | |
| `optimization_goal` | varchar | `impressions` \| `reach` \| `link_clicks` \| `conversions` \| `leads` \| `app_installs` \| … |
| `billing_event` | varchar | `impressions` \| `link_clicks` \| `thruplay` |
| `bid_amount` | numeric | In account currency units |
| `daily_budget` | numeric | Null if inheriting from campaign |
| `lifetime_budget` | numeric | |
| `targeting_summary` | jsonb | Store raw targeting spec — used for display only |
| `start_date` | date | |
| `end_date` | date | |
| `synced_at` | timestamp | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

### `ads`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `ad_group_id` | uuid FK → ad_groups | |
| `campaign_id` | uuid FK → campaigns | Denormalized |
| `account_id` | uuid FK → accounts | Denormalized |
| `platform_id` | varchar FK → platforms | Denormalized |
| `platform_ad_id` | varchar | |
| `name` | varchar | |
| `status` | varchar | `active` \| `paused` \| `deleted` \| `archived` |
| `effective_status` | varchar | |
| `creative_id` | uuid FK → creatives | Null until creative is fetched |
| `synced_at` | timestamp | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

### `creatives`

Stores ad content — text, images, video. Fetched lazily (on first drill-in to an ad).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `platform_id` | varchar FK → platforms | |
| `account_id` | uuid FK → accounts | |
| `platform_creative_id` | varchar | |
| `name` | varchar | |
| `format` | varchar | `image` \| `video` \| `carousel` \| `collection` \| `instant_experience` \| `text` |
| `title` | varchar | Headline text |
| `body` | text | Primary body / description text |
| `image_url` | varchar | Direct image URL |
| `thumbnail_url` | varchar | Video thumbnail URL |
| `video_id` | varchar | Platform video asset ID |
| `cta_type` | varchar | `shop_now` \| `learn_more` \| `sign_up` \| `book_now` \| `download` \| … |
| `destination_url` | varchar | Final destination URL |
| `raw_spec` | jsonb | Full platform-native creative spec (e.g. `object_story_spec`, `asset_feed_spec`) |
| `synced_at` | timestamp | |

---

## 4. Metrics Layer

### Overview

Three tables handle all metric data:

| Table | What it stores | Grain |
|---|---|---|
| `metrics_daily` | Scalar (single-value) metrics | 1 row per entity per day |
| `metric_action_stats` | Array metrics (`list<AdsActionStats>`) | 1 row per entity × day × field × action_type |
| `metric_breakdowns` | Scalar metrics split by a dimension | 1 row per entity × day × breakdown_type × breakdown_value |

---

### 4.1 `metrics_daily` — Scalar Metrics

One row per entity (account / campaign / ad_group / ad) per calendar day.

#### Key columns

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `entity_type` | varchar | `account` \| `campaign` \| `ad_group` \| `ad` |
| `entity_id` | uuid | FK to the corresponding entity table |
| `platform_id` | varchar | |
| `account_id` | uuid | Denormalized for fast filtering |
| `date` | date | Calendar day (in account's timezone) |

#### Core performance

| Column | Type | Meta field | Notes |
|---|---|---|---|
| `impressions` | bigint | `impressions` | |
| `reach` | bigint | `reach` | Unique people |
| `frequency` | numeric(10,4) | `frequency` | impressions ÷ reach |
| `clicks` | bigint | `clicks` | All click types |
| `spend` | numeric(14,4) | `spend` | In account currency |
| `ctr` | numeric(10,6) | `ctr` | % (platform-computed) |
| `cpm` | numeric(14,4) | `cpm` | Cost per 1k impressions |
| `cpc` | numeric(14,4) | `cpc` | Cost per click |
| `cpp` | numeric(14,4) | `cpp` | Cost per 1k reach |

#### Click detail

| Column | Type | Meta field |
|---|---|---|
| `unique_clicks` | bigint | `unique_clicks` |
| `inline_link_clicks` | bigint | `inline_link_clicks` |
| `unique_inline_link_clicks` | bigint | `unique_inline_link_clicks` |
| `inline_link_click_ctr` | numeric(10,6) | `inline_link_click_ctr` |
| `unique_ctr` | numeric(10,6) | `unique_ctr` |
| `cost_per_inline_link_click` | numeric(14,4) | `cost_per_inline_link_click` |
| `cost_per_unique_click` | numeric(14,4) | `cost_per_unique_click` |

> `outbound_clicks` and `unique_outbound_clicks` are `list<AdsActionStats>` — stored in `metric_action_stats`.

#### Engagement

| Column | Type | Meta field |
|---|---|---|
| `inline_post_engagement` | bigint | `inline_post_engagement` |
| `cost_per_inline_post_engagement` | numeric(14,4) | `cost_per_inline_post_engagement` |

#### Auction (diagnostic)

| Column | Type | Meta field |
|---|---|---|
| `auction_bid` | numeric(14,4) | `auction_bid` |
| `auction_competitiveness` | numeric(6,4) | `auction_competitiveness` (0–1) |
| `auction_max_competitor_bid` | numeric(14,4) | `auction_max_competitor_bid` |

#### Aggregates / totals

| Column | Type | Meta field |
|---|---|---|
| `total_actions` | bigint | `total_actions` |
| `total_unique_actions` | bigint | `total_unique_actions` |
| `result_rate` | numeric(10,6) | `result_rate` |

#### Estimated / brand

| Column | Type | Meta field | Notes |
|---|---|---|---|
| `estimated_ad_recall_rate` | numeric(10,6) | `estimated_ad_recall_rate` | Directional only |
| `estimated_ad_recallers` | bigint | `estimated_ad_recallers` | |

#### Sync metadata

| Column | Type | Notes |
|---|---|---|
| `fetched_at` | timestamp | When this row was last fetched from the platform |
| `is_estimated` | boolean | True if data is provisional (intraday / not yet settled) |
| `attribution_window` | varchar | Attribution window used for this fetch |

---

### 4.2 `metric_action_stats` — Array Metrics

Stores all `list<AdsActionStats>` fields. Each platform-returned array item becomes one row.

#### Schema

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `entity_type` | varchar | `account` \| `campaign` \| `ad_group` \| `ad` |
| `entity_id` | uuid | |
| `platform_id` | varchar | |
| `account_id` | uuid | Denormalized |
| `date` | date | |
| `field_name` | varchar | Which API field this came from (see below) |
| `action_type` | varchar | The `action_type` value from the array item |
| `value` | numeric(18,4) | The `value` from the array item |
| `fetched_at` | timestamp | |

#### `field_name` values

| `field_name` | Meta source field | What `value` represents |
|---|---|---|
| `actions` | `actions` | Count of this action type |
| `action_values` | `action_values` | Revenue value of this action type |
| `unique_actions` | `unique_actions` | Unique people who took this action |
| `cost_per_action_type` | `cost_per_action_type` | Average cost per this action |
| `cost_per_unique_action_type` | `cost_per_unique_action_type` | Cost per unique action |
| `conversions` | `conversions` | Conversion event count |
| `conversion_values` | `conversion_values` | Conversion event value |
| `cost_per_conversion` | `cost_per_conversion` | Cost per conversion |
| `purchase_roas` | `purchase_roas` | ROAS multiplier |
| `website_purchase_roas` | `website_purchase_roas` | Website-only ROAS |
| `mobile_app_purchase_roas` | `mobile_app_purchase_roas` | App-only ROAS |
| `outbound_clicks` | `outbound_clicks` | Outbound click count |
| `unique_outbound_clicks` | `unique_outbound_clicks` | Unique outbound clicks |
| `cost_per_outbound_click` | `cost_per_outbound_click` | Cost per outbound click |
| `video_play_actions` | `video_play_actions` | Video starts |
| `video_avg_time_watched_actions` | `video_avg_time_watched_actions` | Avg watch time (ms) |
| `video_continuous_2_sec_watched_actions` | `video_continuous_2_sec_watched_actions` | 2s+ views |
| `video_thruplay_watched_actions` | `video_thruplay_watched_actions` | ThruPlay completions |
| `video_30_sec_watched_actions` | `video_30_sec_watched_actions` | 30s+ views |
| `video_p25_watched_actions` | `video_p25_watched_actions` | 25% completion |
| `video_p50_watched_actions` | `video_p50_watched_actions` | 50% completion |
| `video_p75_watched_actions` | `video_p75_watched_actions` | 75% completion |
| `video_p95_watched_actions` | `video_p95_watched_actions` | 95% completion |
| `video_p100_watched_actions` | `video_p100_watched_actions` | 100% completion |
| `cost_per_thruplay` | `cost_per_thruplay` | Cost per ThruPlay |
| `cost_per_2_sec_continuous_video_view` | `cost_per_2_sec_continuous_video_view` | Cost per 2s view |
| `results` | `results` | Objective result count |
| `cost_per_result` | `cost_per_result` | Cost per objective result |

> **Unique tip from API reference:** Never mix unique metrics (reach, unique_clicks) with non-unique metrics in the same API call — it significantly slows the query. Fetch them in separate requests but store together in `metrics_daily`.

---

### 4.3 `metric_breakdowns` — Breakdown Dimensions

Stores scalar metrics split by a single demographic or placement dimension. Populated on demand (not on every background sync — only when a breakdown view is requested).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `entity_type` | varchar | |
| `entity_id` | uuid | |
| `platform_id` | varchar | |
| `account_id` | uuid | |
| `date` | date | |
| `breakdown_type` | varchar | See breakdown types below |
| `breakdown_value` | varchar | The dimension value (e.g. `"25-34"`, `"female"`, `"US"`) |
| `impressions` | bigint | |
| `clicks` | bigint | |
| `spend` | numeric(14,4) | |
| `ctr` | numeric(10,6) | |
| `cpm` | numeric(14,4) | |
| `cpc` | numeric(14,4) | |
| `fetched_at` | timestamp | |

> `reach` is intentionally excluded here — Meta dropped reach support for breakdowns with dates older than 13 months (June 2025). For breakdown reach queries, use async jobs (max 10/account/day).

#### `breakdown_type` values

| `breakdown_type` | Meta param | Values |
|---|---|---|
| `age` | `age` | `18-24` \| `25-34` \| `35-44` \| `45-54` \| `55-64` \| `65+` |
| `gender` | `gender` | `male` \| `female` \| `unknown` |
| `country` | `country` | ISO 3166-1 alpha-2 (e.g. `US`, `GB`) |
| `region` | `region` | Geographic region name |
| `publisher_platform` | `publisher_platform` | `facebook` \| `instagram` \| `audience_network` \| `messenger` |
| `platform_position` | `platform_position` | `feed` \| `story` \| `reels` \| `right_hand_column` \| … |
| `device_platform` | `device_platform` | `mobile` \| `desktop` |
| `impression_device` | `impression_device` | Specific device type |
| `age_gender` | `age,gender` combined | Stored as `"25-34__female"` — compound breakdown |

> **Constraint:** Never combine more than 2 breakdowns in one API call — high timeout risk. `age_gender` is the only pre-approved compound stored here.

---

## 5. Sync & Job Tracking

### `sync_jobs`

Tracks every background fetch from a platform API. Used to diagnose failures, prevent duplicate fetches, and enforce cache TTLs.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `account_id` | uuid FK → accounts | |
| `platform_id` | varchar | |
| `job_type` | varchar | `structure` \| `insights_daily` \| `insights_async` \| `creatives` \| `breakdown` |
| `entity_type` | varchar | What entity level this covers: `account` \| `campaign` \| `ad_group` \| `ad` |
| `date_start` | date | Coverage start (for insights jobs) |
| `date_stop` | date | Coverage end |
| `breakdown_type` | varchar | Null unless job_type is `breakdown` |
| `status` | varchar | `pending` \| `running` \| `completed` \| `failed` \| `skipped` |
| `platform_job_id` | varchar | Meta `report_run_id` for async jobs; null for sync |
| `rows_written` | int | Records upserted on success |
| `error_message` | text | Error detail on failure |
| `rate_limit_pct_at_start` | int | `app_id_util_pct` recorded before this job ran |
| `started_at` | timestamp | |
| `completed_at` | timestamp | |
| `created_at` | timestamp | |

#### Cache TTL guidance (enforced by sync scheduler)

| `job_type` | TTL | Notes |
|---|---|---|
| `structure` | 30–60 min | Campaigns, ad groups, ads rarely change |
| `insights_daily` | 15 min | Meta refreshes every ~15 min anyway |
| `insights_async` | 60 min | Async jobs are expensive — cache aggressively |
| `creatives` | 60 min | Very rarely change |
| `breakdown` | 30 min | On-demand only |

---

## 6. Platform Mapping Reference

How each platform's native concepts map to internal schema entities:

| Internal | Meta Ads | Google Ads | TikTok Ads | Google Analytics |
|---|---|---|---|---|
| `account` | Ad Account | Customer | Ad Account | Property |
| `campaign` | Campaign | Campaign | Campaign | — |
| `ad_group` | Ad Set | Ad Group | Ad Group | — |
| `ad` | Ad | Ad | Ad | — |
| `creative` | Ad Creative | Ad Asset | Ad Material | — |
| `objective` | `OUTCOME_SALES` etc. | `CONVERSIONS` etc. | `CONVERSIONS` etc. | — |
| `spend` | `spend` | `cost_micros ÷ 1M` | `spend` | — |
| `conversions` | `actions[purchase]` | `conversions` | `conversions` | `goal_completions` |
| `conversion_value` | `action_values[purchase]` | `conversions_value` | `total_purchase_value` | `goal_value` |

> **GA4 note:** Google Analytics has no ad hierarchy. It connects to campaigns via UTM parameters. Store GA4 data separately and join on `utm_campaign` = `campaign.name` for attribution overlap views.

---

## 7. Action Types Reference

Common `action_type` values used in `metric_action_stats.action_type`. Grouped by category for query convenience.

### Engagement
`page_engagement` · `post_engagement` · `post_reaction` · `like` · `comment` · `rsvp`

### Clicks
`link_click` · `outbound_click` · `photo_view` · `video_play`

### Conversions — Web (Pixel)
`purchase` · `lead` · `complete_registration` · `add_to_cart` · `add_to_wishlist` · `initiate_checkout` · `add_payment_info` · `view_content` · `search` · `contact` · `schedule` · `start_trial` · `submit_application` · `subscribe`

### Conversions — App
`app_install` · `app_use` · `fb_mobile_activate_app` · `fb_mobile_purchase` · `fb_mobile_add_to_cart` · `fb_mobile_initiated_checkout` · `fb_mobile_add_payment_info` · `fb_mobile_complete_registration` · `fb_mobile_content_view`

### Video
`video_view` · `video_p25_watched` · `video_p50_watched` · `video_p75_watched` · `video_p100_watched` · `video_thruplay`

### Messaging
`onsite_conversion.messaging_conversation_started_7d` · `onsite_conversion.messaging_first_reply` · `onsite_conversion.messaging_detected_purchase_deduped`

---

## 8. Schema Diagram

```
organizations ──── organization_memberships ──── users
      │
      ├── platform_connections (token per platform)
      │
      └── accounts ──── account_configs
               │
               ├── campaigns
               │       │
               │       └── ad_groups
               │               │
               │               └── ads ──── creatives
               │
               ├── metrics_daily ──────────────── (entity_type + entity_id)
               ├── metric_action_stats ─────────── (entity_type + entity_id)
               ├── metric_breakdowns ───────────── (entity_type + entity_id)
               └── sync_jobs

platforms (reference table — platform-agnostic)
```

> **Row-level security:** Every query to metrics, campaigns, ad_groups, ads, creatives, and sync_jobs must filter by `account_id` values that belong to the requesting user's `organization_id`. The backend enforces this by resolving org-scoped account IDs from the JWT before executing any DB query — never trust a client-supplied `account_id` alone.

---

## 9. Query Patterns

### Deriving ROAS at query time
```sql
-- Pull spend + conversion_value per campaign, compute ROAS
SELECT
  c.name,
  md.date,
  md.spend,
  mas.value AS conversion_value,
  CASE WHEN md.spend > 0
    THEN mas.value / md.spend
    ELSE NULL
  END AS roas
FROM metrics_daily md
JOIN campaigns c ON c.id = md.entity_id AND md.entity_type = 'campaign'
LEFT JOIN metric_action_stats mas
  ON mas.entity_id = md.entity_id
  AND mas.entity_type = 'campaign'
  AND mas.date = md.date
  AND mas.field_name = 'action_values'
  AND mas.action_type = 'purchase'  -- or from account_configs
WHERE md.date BETWEEN '2026-05-01' AND '2026-05-30';
```

### Primary conversion metric per account
```sql
-- Use account_configs.primary_conversion_action to get the right action
SELECT
  c.name,
  SUM(md.spend) AS spend,
  SUM(mas.value) AS conversions,
  SUM(md.spend) / NULLIF(SUM(mas.value), 0) AS cpa
FROM metrics_daily md
JOIN campaigns c ON c.id = md.entity_id
JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats mas
  ON mas.entity_id = md.entity_id
  AND mas.date = md.date
  AND mas.field_name = 'actions'
  AND mas.action_type = ac.primary_conversion_action
GROUP BY c.name;
```

### Video retention funnel
```sql
SELECT
  action_type,
  SUM(value) AS total
FROM metric_action_stats
WHERE entity_id = :ad_id
  AND entity_type = 'ad'
  AND field_name IN (
    'video_play_actions',
    'video_continuous_2_sec_watched_actions',
    'video_p25_watched_actions',
    'video_p50_watched_actions',
    'video_p75_watched_actions',
    'video_p100_watched_actions',
    'video_thruplay_watched_actions'
  )
  AND date BETWEEN :start AND :end
GROUP BY action_type;
```

### Breakdown by age + gender
```sql
SELECT breakdown_type, breakdown_value,
       SUM(impressions), SUM(clicks), SUM(spend)
FROM metric_breakdowns
WHERE entity_id = :campaign_id
  AND breakdown_type = 'age_gender'
  AND date BETWEEN :start AND :end
GROUP BY breakdown_type, breakdown_value;
```

---

## 10. Extension Notes

### Adding Google Ads
- Map `ad_group` (Google: "Ad Group") directly — same level
- `spend` in Google Ads is `cost_micros ÷ 1,000,000`
- `conversions` is a direct scalar field (not an actions array) — store in `metrics_daily` with a Google-specific column or normalize into `metric_action_stats` with `action_type = 'conversion'`
- ROAS is `conversions_value / cost` — same formula

### Adding TikTok Ads
- Hierarchy is identical: account → campaign → ad_group → ad
- `spend` is direct
- Conversion events map to similar action types — normalize on ingest

### Adding Google Analytics 4
- No ad hierarchy — data is at property level
- Connect via UTM parameters: `utm_campaign` → `campaigns.name`
- Store GA4 data in a separate `ga4_metrics` table with: `property_id`, `date`, `sessions`, `users`, `bounce_rate`, `avg_session_duration`, `goal_completions`, `goal_value`, `utm_campaign`, `utm_source`, `utm_medium`
- Join with campaigns only for attribution overlay views — do not force into the main metrics tables

### Field compatibility constraints (from Meta API reference)
These affect which fields can be fetched together — enforced in the sync layer, not the schema:
- Unique metrics + hourly breakdown → not compatible
- `video_p*` + `region` breakdown → not supported
- Triple breakdowns → async only
- Unique + non-unique in same call → works but slow — split into 2 fetches
