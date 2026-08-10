# Meta Ads Dashboard — API Reference

> **Purpose:** Read-only dashboard showing ad metrics and ad content  
> **API version:** `v25.0`  
> **Base URL:** `https://graph.facebook.com/v25.0`  
> **Required permission:** `ads_read`, `read_insights`  

---

## Table of Contents

1. [Authentication & Access Tokens](#1-authentication--access-tokens)
2. [App Access Tiers](#2-app-access-tiers)
3. [Dashboard Flow Overview](#3-dashboard-flow-overview)
4. [Endpoint Contracts](#4-endpoint-contracts)
   - [4.1 List Ad Accounts](#41-list-ad-accounts)
   - [4.2 List Campaigns](#42-list-campaigns)
   - [4.3 List Ad Sets](#43-list-ad-sets)
   - [4.4 List Ads](#44-list-ads)
   - [4.5 Get Ad Creative (Content)](#45-get-ad-creative-content)
   - [4.6 Insights — Account Level](#46-insights--account-level)
   - [4.7 Insights — Campaign Level](#47-insights--campaign-level)
   - [4.8 Insights — Ad Set Level](#48-insights--ad-set-level)
   - [4.9 Insights — Ad Level](#49-insights--ad-level)
   - [4.10 Async Insights Jobs (large queries)](#410-async-insights-jobs-large-queries)
5. [Common Fields Reference](#5-common-fields-reference)
   - [5.1 Insights Metrics Fields](#51-insights-metrics-fields)
   - [5.2 Breakdowns](#52-breakdowns)
   - [5.3 Date Presets](#53-date-presets)
6. [Pagination](#6-pagination)
7. [Rate Limits](#7-rate-limits)
   - [7.1 Rate Limit Types](#71-rate-limit-types)
   - [7.2 Response Headers to Monitor](#72-response-headers-to-monitor)
   - [7.3 Error Codes](#73-error-codes)
   - [7.4 Rate Limit Strategy for a Dashboard](#74-rate-limit-strategy-for-a-dashboard)
8. [Error Handling](#8-error-handling)
9. [Recommended Dashboard Architecture](#9-recommended-dashboard-architecture)

---

## 1. Authentication & Access Tokens

For a server-side dashboard, use a **System User Access Token** — it doesn't expire and doesn't require user interaction.

### Steps

1. Create a **System User** in Meta Business Manager → Settings → System Users
2. Assign the system user to the Ad Account with **Analyst** role (read-only is enough)
3. Generate an access token with the scopes: `ads_read`, `read_insights`
4. Store the token securely server-side; pass it on every request

### Usage

```http
GET /v25.0/{endpoint}?access_token=<SYSTEM_USER_TOKEN>
```

Or via header:

```http
Authorization: Bearer <SYSTEM_USER_TOKEN>
```

> **Security:** Never expose the token client-side. All API calls should be proxied through your backend.

### Token lifecycle — expiry probe & refresh

DashMet accepts a pasted long-lived / system-user token at connect, then manages its lifecycle via two Graph calls (both use the same app credentials — must be the Meta app that minted the token):

**`GET /debug_token`** — read a token's real expiry at connect time. Called with an **app access token** (`{META_APP_ID}|{META_APP_SECRET}`) and the pasted token as `input_token`:

```http
GET /debug_token?input_token=<TOKEN>&access_token=<APP_ID>|<APP_SECRET>
```

Response `data.expires_at` is a unix timestamp; **`0` (or absent) means the token never expires** (true system-user token). DashMet stores a finite `expires_at` into `platform_connections.token_expires_at` and leaves it `NULL` for never-expiring tokens. A `debug_token` failure is logged and swallowed — it must not break the connect flow (the token was already validated by a `/me/adaccounts` call).

**`GET /oauth/access_token?grant_type=fb_exchange_token`** — refresh a still-valid long-lived token for a fresh ~60-day one:

```http
GET /oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=<META_APP_ID>
  &client_secret=<META_APP_SECRET>
  &fb_exchange_token=<CURRENT_LONG_LIVED_TOKEN>
```

Returns `{ "access_token", "expires_in", ... }`. **Must run while the current token is still alive** — a dead token cannot be exchanged, so the refresh worker fires proactively (within 7 days of expiry), not after. Hard ceilings this does **not** solve: it does not reset Meta's ~90-day data-access expiration, cannot regenerate a true system-user token, and cannot heal a revoked/permission-changed token — those require a manual re-paste (see `docs/sync-worker-spec.md` → "Token refresh & token-failure alerting").

---

## 2. App Access Tiers

Your app's rate limits depend on which tier it's in. This affects everything.

| Tier | How to get it | Insights calls/hour | Ads mgmt calls/hour |
|---|---|---|---|
| `development_access` | Default for new apps | `600 + 400 * active_ads` | `300` per ad account |
| `standard_access` | Apply for Advanced Access to *Ads Management Standard Access* in App Review | `190,000 + 400 * active_ads` | `100,000` per ad account |

> **Action:** Apply for `standard_access` before going to production. Development tier will throttle quickly for a real dashboard.

Check your current tier in any API response header:

```json
"X-FB-Ads-Insights-Throttle": {
  "ads_api_access_tier": "standard_access"
}
```

---

## 3. Dashboard Flow Overview

```
[1] GET /me/adaccounts          → list of ad account IDs
        ↓
[2] GET /act_{id}/campaigns     → campaigns list (structure)
    GET /act_{id}/adsets        → ad sets list
    GET /act_{id}/ads           → ads list + creative IDs
        ↓
[3] GET /{creative_id}          → ad creative content (images, text, video)
        ↓
[4] GET /act_{id}/insights      → account-level metrics
    GET /{campaign_id}/insights → campaign-level metrics
    GET /{adset_id}/insights    → ad set-level metrics
    GET /{ad_id}/insights       → ad-level metrics
```

**Recommended loading order for a dashboard:**

1. Fetch structure (campaigns/adsets/ads) first — these are fast and cached
2. Fetch insights per level on demand (heavy — respect rate limits)
3. Fetch creatives lazily when user drills into an ad

---

## 4. Endpoint Contracts

### 4.1 List Ad Accounts

Fetch all ad accounts the system user has access to.

**Request**

```http
GET /v25.0/me/adaccounts
  ?fields=id,name,account_id,account_status,currency,timezone_name,business
  &access_token=<TOKEN>
```

**Response**

```json
{
  "data": [
    {
      "id": "act_1234567890",
      "name": "My Ad Account",
      "account_id": "1234567890",
      "account_status": 1,
      "currency": "USD",
      "timezone_name": "America/Los_Angeles",
      "business": {
        "id": "9876543210",
        "name": "My Business"
      }
    }
  ],
  "paging": {
    "cursors": { "before": "...", "after": "..." },
    "next": "https://graph.facebook.com/..."
  }
}
```

**account_status values**

| Value | Meaning |
|---|---|
| `1` | Active |
| `2` | Disabled |
| `3` | Unsettled |
| `7` | Pending review |
| `9` | In grace period |
| `101` | Temporarily closed |
| `201` | Closed |

---

### 4.2 List Campaigns

**Request**

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/campaigns
  ?fields=id,name,status,effective_status,objective,daily_budget,lifetime_budget,
          start_time,stop_time,created_time,updated_time
  &limit=100
  &access_token=<TOKEN>
```

**Key fields**

| Field | Type | Description |
|---|---|---|
| `id` | string | Campaign ID |
| `name` | string | Campaign name |
| `status` | enum | `ACTIVE`, `PAUSED`, `DELETED`, `ARCHIVED` |
| `effective_status` | enum | Actual delivery status (accounts for parent state) |
| `objective` | enum | `OUTCOME_AWARENESS`, `OUTCOME_TRAFFIC`, `OUTCOME_ENGAGEMENT`, `OUTCOME_LEADS`, `OUTCOME_APP_PROMOTION`, `OUTCOME_SALES` |
| `daily_budget` | string | Budget in account currency cents |
| `lifetime_budget` | string | Lifetime budget in account currency cents |
| `start_time` | datetime | ISO 8601 |
| `stop_time` | datetime | ISO 8601 |

**Response shape**

```json
{
  "data": [
    {
      "id": "23845000000000000",
      "name": "Summer Sale Campaign",
      "status": "ACTIVE",
      "effective_status": "ACTIVE",
      "objective": "OUTCOME_SALES",
      "daily_budget": "5000",
      "start_time": "2025-06-01T00:00:00+0000",
      "created_time": "2025-05-15T10:23:00+0000"
    }
  ],
  "paging": { "cursors": { "before": "...", "after": "..." } }
}
```

**Filter by status (optional)**

```http
&filtering=[{"field":"campaign.effective_status","operator":"IN","value":["ACTIVE","PAUSED"]}]
```

---

### 4.3 List Ad Sets

**Request**

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/adsets
  ?fields=id,name,status,effective_status,campaign_id,daily_budget,lifetime_budget,
          targeting,optimization_goal,billing_event,bid_amount,
          start_time,stop_time,created_time,updated_time
  &limit=100
  &access_token=<TOKEN>
```

**Key fields**

| Field | Type | Description |
|---|---|---|
| `id` | string | Ad set ID |
| `campaign_id` | string | Parent campaign ID |
| `optimization_goal` | enum | `IMPRESSIONS`, `REACH`, `LINK_CLICKS`, `CONVERSIONS`, `LEADS`, `APP_INSTALLS`, etc. |
| `billing_event` | enum | `IMPRESSIONS`, `LINK_CLICKS`, `THRUPLAY` |
| `bid_amount` | int | Bid in account currency cents |
| `targeting` | object | Audience targeting spec |

---

### 4.4 List Ads

**Request**

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/ads
  ?fields=id,name,status,effective_status,adset_id,campaign_id,
          creative{id,name,title,body,image_url,thumbnail_url,video_id,
                   object_story_spec,call_to_action_type},
          created_time,updated_time
  &limit=100
  &access_token=<TOKEN>
```

**Key fields**

| Field | Type | Description |
|---|---|---|
| `id` | string | Ad ID |
| `adset_id` | string | Parent ad set ID |
| `campaign_id` | string | Parent campaign ID |
| `creative` | object | Inline expanded creative (see 4.5) |

> **Tip:** Request `creative{...}` fields inline with the ads call to avoid a separate creative fetch round-trip.

---

### 4.5 Get Ad Creative (Content)

Fetch the full content of an ad creative — text, images, video thumbnails, CTA.

**Request**

```http
GET /v25.0/{CREATIVE_ID}
  ?fields=id,name,title,body,image_url,thumbnail_url,
          video_id,call_to_action_type,
          object_story_spec,asset_feed_spec,
          effective_object_story_id
  &access_token=<TOKEN>
```

**Key fields**

| Field | Type | Description |
|---|---|---|
| `title` | string | Headline text |
| `body` | string | Primary ad body text |
| `image_url` | string | Image URL (direct link) |
| `thumbnail_url` | string | Video thumbnail URL |
| `video_id` | string | Video asset ID if video ad |
| `call_to_action_type` | enum | `SHOP_NOW`, `LEARN_MORE`, `SIGN_UP`, `BOOK_NOW`, `DOWNLOAD`, etc. |
| `object_story_spec` | object | Full creative spec including link, page, and media |
| `asset_feed_spec` | object | Dynamic creative assets (multiple images/texts) |

**Sample response**

```json
{
  "id": "23845000000000001",
  "name": "Summer Ad Creative",
  "title": "Shop Summer Deals",
  "body": "Enjoy up to 50% off. Limited time only.",
  "image_url": "https://scontent.facebook.com/...",
  "call_to_action_type": "SHOP_NOW",
  "object_story_spec": {
    "page_id": "123456789",
    "link_data": {
      "link": "https://example.com/summer-sale",
      "message": "Enjoy up to 50% off.",
      "name": "Shop Summer Deals",
      "description": "Limited time only.",
      "image_hash": "abc123..."
    }
  }
}
```

---

### 4.6 Insights — Account Level

Aggregate metrics across all campaigns in an ad account.

**Request**

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/insights
  ?fields=impressions,reach,clicks,spend,ctr,cpc,cpm,cpp,
          frequency,actions,cost_per_action_type,
          date_start,date_stop
  &date_preset=last_30d
  &level=account
  &access_token=<TOKEN>
```

---

### 4.7 Insights — Campaign Level

**Request**

```http
GET /v25.0/{CAMPAIGN_ID}/insights
  ?fields=campaign_id,campaign_name,
          impressions,reach,clicks,spend,ctr,cpc,cpm,
          actions,cost_per_action_type,
          date_start,date_stop
  &date_preset=last_7d
  &access_token=<TOKEN>
```

Or fetch all campaigns under an account in one call with the `level` param:

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/insights
  ?fields=campaign_id,campaign_name,impressions,reach,clicks,spend,ctr,cpc,cpm
  &level=campaign
  &date_preset=last_7d
  &access_token=<TOKEN>
```

---

### 4.8 Insights — Ad Set Level

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/insights
  ?fields=adset_id,adset_name,campaign_id,
          impressions,reach,clicks,spend,ctr,cpc,cpm,
          actions,cost_per_action_type
  &level=adset
  &date_preset=last_7d
  &access_token=<TOKEN>
```

---

### 4.9 Insights — Ad Level

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/insights
  ?fields=ad_id,ad_name,adset_id,campaign_id,
          impressions,reach,clicks,spend,ctr,cpc,cpm,
          actions,cost_per_action_type,video_avg_time_watched_actions
  &level=ad
  &date_preset=last_7d
  &access_token=<TOKEN>
```

**With breakdowns (e.g. by day and country)**

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/insights
  ?fields=impressions,clicks,spend,ctr
  &level=campaign
  &breakdowns=country
  &time_increment=1
  &date_preset=last_30d
  &access_token=<TOKEN>
```

> `time_increment=1` returns one row per day. Use `time_increment=monthly` for monthly rollup.

---

### 4.10 Async Insights Jobs (large queries)

Use async when: querying lifetime data, many ad objects, multiple breakdowns, or when sync calls time out.

**Step 1 — Submit the job (POST)**

```http
POST /v25.0/act_{AD_ACCOUNT_ID}/insights
  ?level=ad
  &fields=ad_id,impressions,clicks,spend,ctr,cpc,actions
  &date_preset=last_90d
  &access_token=<TOKEN>
```

**Response**

```json
{
  "report_run_id": "6023920149050"
}
```

**Step 2 — Poll job status**

```http
GET /v25.0/{REPORT_RUN_ID}
  ?access_token=<TOKEN>
```

```json
{
  "id": "6023920149050",
  "async_status": "Job Completed",
  "async_percent_completion": 100
}
```

**Async job status values**

| Status | Meaning |
|---|---|
| `Job Not Started` | Queued |
| `Job Started` | Accepted |
| `Job Running` | Processing |
| `Job Completed` | Ready to fetch |
| `Job Failed` | Resubmit with simpler query |
| `Job Skipped` | Expired (>30 days) — resubmit |

**Step 3 — Fetch results**

```http
GET /v25.0/{REPORT_RUN_ID}/insights
  ?access_token=<TOKEN>
```

```json
{
  "data": [
    {
      "ad_id": "23845000000000000",
      "impressions": "12400",
      "clicks": "340",
      "spend": "85.42",
      "ctr": "2.7419",
      "date_start": "2025-03-01",
      "date_stop": "2025-05-29"
    }
  ],
  "paging": { "cursors": { "before": "...", "after": "..." } }
}
```

> **Note:** `report_run_id` expires after 30 days. Do not store it permanently.

---

## 5. Common Fields Reference

### 5.1 Insights Metrics Fields

| Field | Description |
|---|---|
| `impressions` | Total times ads were shown |
| `reach` | Unique accounts that saw the ad |
| `frequency` | Avg times each person saw the ad (`impressions / reach`) |
| `clicks` | All clicks (on ad, CTA, link, etc.) |
| `unique_clicks` | Unique people who clicked |
| `ctr` | Click-through rate (`clicks / impressions * 100`) |
| `cpc` | Cost per click |
| `cpm` | Cost per 1,000 impressions |
| `cpp` | Cost per 1,000 people reached |
| `spend` | Total amount spent |
| `actions` | Array of action types (purchases, leads, app installs, etc.) |
| `cost_per_action_type` | Cost per each action type |
| `video_avg_time_watched_actions` | Average video watch time |
| `video_p25_watched_actions` | % who watched 25% of video |
| `video_p50_watched_actions` | % who watched 50% of video |
| `video_p75_watched_actions` | % who watched 75% of video |
| `video_p100_watched_actions` | % who watched 100% of video |
| `date_start` | Start of reporting period |
| `date_stop` | End of reporting period |

> **Note (from June 10, 2025):** `reach` with `breakdowns` is no longer returned for `start_date` older than 13 months. For historical reach with breakdowns, use async jobs (max 10/account/day).

### 5.2 Breakdowns

Use the `breakdowns` parameter to split metrics by dimension.

| Breakdown | Description |
|---|---|
| `age` | Age ranges: `18-24`, `25-34`, `35-44`, `45-54`, `55-64`, `65+` |
| `gender` | `male`, `female`, `unknown` |
| `country` | 2-letter country code |
| `region` | Geographic region |
| `publisher_platform` | `facebook`, `instagram`, `audience_network`, `messenger` |
| `platform_position` | `feed`, `story`, `reels`, `right_hand_column`, etc. |
| `device_platform` | `mobile`, `desktop` |
| `impression_device` | Specific device type |
| `action_device` | Device where conversion occurred |
| `hourly_stats_aggregated_by_advertiser_time_zone` | Hourly stats |
| `product_id` | Product in catalog ads |

**Combining breakdowns — allowed pairs**

Not all combinations work. Safest for a dashboard:

- `age` + `gender` ✅
- `publisher_platform` + `platform_position` ✅
- `country` alone ✅
- `device_platform` alone ✅
- `age` + `country` ✅
- Three or more breakdowns → high timeout risk ⚠️

### 5.3 Date Presets

Use `date_preset` for common ranges (more efficient than custom `time_range`).

| Preset | Range |
|---|---|
| `today` | Today |
| `yesterday` | Yesterday |
| `this_week_sun_today` | This week (Sun–today) |
| `last_week_sun_sat` | Last full week |
| `last_7d` | Last 7 days |
| `last_14d` | Last 14 days |
| `last_28d` | Last 28 days |
| `last_30d` | Last 30 days |
| `last_90d` | Last 90 days |
| `this_month` | Current month |
| `last_month` | Previous month |
| `this_year` | Current year |
| `lifetime` | All time (use async) |

For custom ranges, use `time_range`:

```
&time_range={"since":"2025-01-01","until":"2025-05-31"}
```

---

## 6. Pagination

All list endpoints return paginated results using cursor-based pagination.

**Response shape**

```json
{
  "data": [...],
  "paging": {
    "cursors": {
      "before": "cursor_string_before",
      "after":  "cursor_string_after"
    },
    "next": "https://graph.facebook.com/v25.0/...&after=cursor_string_after",
    "previous": "https://graph.facebook.com/v25.0/...&before=cursor_string_before"
  }
}
```

**Fetching next page**

```http
GET /v25.0/act_{ID}/campaigns
  ?after={cursor_string_after}
  &limit=100
  &access_token=<TOKEN>
```

**Tips**

- Default `limit` is 25. Set `limit=100` for dashboard loading
- Pagination ends when there is no `next` key in `paging`
- Max `limit` per call is 500 for most endpoints (200 for insights)
- Always follow `next` URL directly — it already includes all params

---

## 7. Rate Limits

### 7.1 Rate Limit Types

The Marketing API uses **Business Use Case (BUC) rate limits**, not simple per-minute counters.

**Ads Insights BUC**

Quota per 1-hour rolling window:

| Tier | Formula |
|---|---|
| `development_access` | `600 + 400 × active_ads` per ad account |
| `standard_access` | `190,000 + 400 × active_ads` per ad account |

Where `active_ads` = number of ads currently running per ad account.

**Ads Management BUC** (for reading campaign/ad structure)

| Tier | Quota |
|---|---|
| `development_access` | `300` per ad account per hour |
| `standard_access` | `100,000` per ad account per hour |

Both BUCs share the same ad account pool. Exhausting one affects the other.

### 7.2 Response Headers to Monitor

Check these headers on **every API response**:

**`X-FB-Ads-Insights-Throttle`** (insights calls)

```json
{
  "app_id_util_pct": 45,
  "acc_id_util_pct": 12,
  "ads_api_access_tier": "standard_access"
}
```

| Key | Meaning |
|---|---|
| `app_id_util_pct` | % of app-level quota used |
| `acc_id_util_pct` | % of ad account quota used |
| `ads_api_access_tier` | Current tier |

**`X-Ad-Account-Usage`** (structure calls)

```json
{
  "acc_id_util_pct": 9.67,
  "reset_time_duration": 3600,
  "ads_api_access_tier": "standard_access"
}
```

| Key | Meaning |
|---|---|
| `acc_id_util_pct` | % used for this ad account |
| `reset_time_duration` | Seconds until quota resets |

**`X-Fb-Ads-Insights-Reach-Throttle`** (reach with breakdowns)

```json
{
  "reach_throttle_pct": 60
}
```

Max 10 async requests per ad account per day for historical reach data (>13 months).

**`X-App-Usage`** (general platform limit)

```json
{
  "call_count": 28,
  "total_time": 25,
  "total_cputime": 25
}
```

Any of these hitting 100 means you're at the limit.

### 7.3 Error Codes

| Code | Subcode | Meaning | Action |
|---|---|---|---|
| `4` | `1504022` | App-level insights rate limit hit | Back off, wait, retry |
| `4` | `1504039` | Same — too many app calls | Exponential back-off |
| `4` | *(none)* | App request limit reached | Slow down all calls |
| `17` | — | User rate limit | Reduce per-user calls |
| `32` | — | Pages API limit | N/A for ads dashboard |
| `100` | `1487534` | Data per call limit (too many rows) | Narrow date range or filters |
| `613` | — | Custom rate limit hit | Check specific API docs |

**Error response shape**

```json
{
  "error": {
    "message": "Application request limit reached",
    "type": "OAuthException",
    "code": 4,
    "error_subcode": 1504022,
    "fbtrace_id": "AbCdEfG123"
  }
}
```

### 7.4 Rate Limit Strategy for a Dashboard

**Read headers on every response**

```python
def check_rate_limit(response):
    throttle = response.headers.get("X-FB-Ads-Insights-Throttle")
    usage    = response.headers.get("X-Ad-Account-Usage")

    if throttle:
        data = json.loads(throttle)
        if data.get("app_id_util_pct", 0) > 80:
            time.sleep(30)   # back off before next call
        if data.get("app_id_util_pct", 0) > 95:
            time.sleep(300)  # hard pause

    if usage:
        data = json.loads(usage)
        if data.get("acc_id_util_pct", 0) > 80:
            time.sleep(30)
```

**Exponential back-off on error code 4**

```python
def call_with_backoff(url, params, max_retries=5):
    for attempt in range(max_retries):
        response = requests.get(url, params=params)
        if response.status_code == 200:
            check_rate_limit(response)
            return response.json()

        error = response.json().get("error", {})
        if error.get("code") == 4:
            wait = (2 ** attempt) * 10  # 10s, 20s, 40s, 80s, 160s
            time.sleep(wait)
        else:
            raise Exception(f"API error: {error}")

    raise Exception("Max retries exceeded")
```

**Batch requests to reduce call count**

```http
POST /v25.0/
  ?access_token=<TOKEN>

batch=[
  {"method":"GET","relative_url":"v25.0/{CAMPAIGN_ID_1}/insights?fields=impressions,spend&date_preset=last_7d"},
  {"method":"GET","relative_url":"v25.0/{CAMPAIGN_ID_2}/insights?fields=impressions,spend&date_preset=last_7d"},
  {"method":"GET","relative_url":"v25.0/{CAMPAIGN_ID_3}/insights?fields=impressions,spend&date_preset=last_7d"}
]
```

One batch counts as one API call.

**Key rules for a dashboard**

- Prefer `date_preset` over custom `time_range` — more efficient
- Fetch at account level first, drill down on demand — fewer calls
- Use `level=campaign` on account insights instead of N separate campaign calls
- Avoid more than 2 breakdowns per query — complexity multiplies fast
- For heavy queries (lifetime, 90d, many ads), always use async
- Use `filtering=[{field:"ad.impressions",operator:"GREATER_THAN",value:0}]` to skip empty objects
- Cache structure (campaigns/adsets/ads) for 15–60 minutes — it rarely changes
- Cache insights for at least 15 minutes — data only refreshes every 15 minutes
- Spread calls over time — don't fire all at once on page load

---

## 8. Error Handling

**Common errors and responses**

| Situation | Code | Solution |
|---|---|---|
| Invalid token | `190` | Re-generate system user token |
| Insufficient permission | `200` | Add `ads_read` or `read_insights` to token |
| Object not found | `100` | Check the ID, may be deleted |
| Too much data per call | `100` subcode `1487534` | Narrow date range, add filters |
| Timeout (sync) | `1` | Switch to async POST |
| Rate limit hit | `4` | Exponential back-off |
| Global overload | `4` subcode `1504022` | Wait and retry |
| Reach throttle | — | `x-Fb-Ads-Insights-Reach-Throttle` header hit 100 |

**Standard error shape**

```json
{
  "error": {
    "message": "...",
    "type": "OAuthException",
    "code": 190,
    "error_subcode": 460,
    "error_user_title": "Access Token Error",
    "error_user_msg": "Your access token has expired.",
    "fbtrace_id": "AbCdEfG123"
  }
}
```

Always log `fbtrace_id` — Meta support needs it for investigation.

---

## 9. Recommended Dashboard Architecture

```
┌─────────────────────────────────┐
│           Frontend               │
│  (React / Vue / etc.)           │
│                                 │
│  Campaign Table  │  Metrics     │
│  Ad Preview      │  Charts      │
└────────┬────────────────────────┘
         │ REST / GraphQL
┌────────▼────────────────────────┐
│         Backend (Your API)      │
│                                 │
│  ┌──────────────────────────┐   │
│  │  Rate Limit Middleware   │   │
│  │  - Read headers          │   │
│  │  - Back-off logic        │   │
│  │  - Queue manager         │   │
│  └──────────────────────────┘   │
│                                 │
│  ┌──────────────────────────┐   │
│  │  Cache Layer (Redis)     │   │
│  │  - Structure: 30–60 min  │   │
│  │  - Insights:  15 min     │   │
│  │  - Creatives: 1 hour     │   │
│  └──────────────────────────┘   │
│                                 │
│  ┌──────────────────────────┐   │
│  │  Meta API Client         │   │
│  │  - System user token     │   │
│  │  - Batch requests        │   │
│  │  - Async job manager     │   │
│  └──────────────────────────┘   │
└────────┬────────────────────────┘
         │
┌────────▼────────────────────────┐
│       Meta Graph API v25.0      │
└─────────────────────────────────┘
```

**Loading strategy**

| Data type | Method | Cache TTL |
|---|---|---|
| Ad accounts | Sync GET | 60 min |
| Campaigns list | Sync GET | 30 min |
| Ad sets list | Sync GET | 30 min |
| Ads list + creatives | Sync GET | 30 min |
| Today's insights | Sync GET | 15 min |
| Last 7–30d insights | Sync GET | 15 min |
| Last 90d / lifetime | Async POST | 60 min |
| Breakdown by country/age | Sync or Async | 30 min |

---

## References

- [Insights API](https://developers.facebook.com/docs/marketing-api/insights/)
- [Insights Limits & Best Practices](https://developers.facebook.com/docs/marketing-api/insights/best-practices/)
- [Insights Breakdowns](https://developers.facebook.com/docs/marketing-api/insights/breakdowns)
- [Graph API Rate Limits](https://developers.facebook.com/docs/graph-api/overview/rate-limiting/)
- [Marketing API Rate Limiting](https://developers.facebook.com/docs/marketing-api/overview/rate-limiting/)
- [Ad Account Reference](https://developers.facebook.com/docs/marketing-api/reference/ad-account/)
- [Ad Creative Reference](https://developers.facebook.com/docs/marketing-api/reference/ad-creative/)
- [Batch Requests](https://developers.facebook.com/docs/graph-api/batch-requests)
