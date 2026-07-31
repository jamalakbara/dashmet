# TikTok Business API — Dashboard API Contract & Integration Flow

> **Scope:** Read-only dashboard covering **Metrics Data** and **Ads Content**
> **API Version:** v1.3
> **Base URL:** `https://business-api.tiktok.com/open_api/v1.3`

---

## Table of Contents

1. [Authentication & Authorization Flow](#1-authentication--authorization-flow)
2. [Required App Permissions (Scopes)](#2-required-app-permissions-scopes)
3. [Rate Limits](#3-rate-limits)
4. [API Contract — Ads Content (Read)](#4-api-contract--ads-content-read)
   - [4.1 Get Advertiser Info](#41-get-advertiser-info)
   - [4.2 Get Campaigns](#42-get-campaigns)
   - [4.3 Get Ad Groups](#43-get-ad-groups)
   - [4.4 Get Ads](#44-get-ads)
   - [4.5 Get Video Info](#45-get-video-info)
5. [API Contract — Metrics & Reporting](#5-api-contract--metrics--reporting)
   - [5.1 Synchronous Report (Recommended for Dashboard)](#51-synchronous-report-recommended-for-dashboard)
   - [5.2 Asynchronous Report (For Large Datasets)](#52-asynchronous-report-for-large-datasets)
6. [Data Levels & Dimensions Reference](#6-data-levels--dimensions-reference)
7. [Audience Breakdown by Age & Gender](#7-audience-breakdown-by-age--gender)
8. [Common Metrics Reference](#8-common-metrics-reference)
9. [Standard Response Envelope](#9-standard-response-envelope)
10. [Error & Return Codes](#10-error--return-codes)
11. [End-to-End Integration Flow](#11-end-to-end-integration-flow)
12. [Dashboard Data Flow Diagram](#12-dashboard-data-flow-diagram)

---

## 1. Authentication & Authorization Flow

TikTok uses **OAuth 2.0** for all API access. Every API call requires an `Access-Token` header.

### Step 1 — Register Your App

1. Create a **TikTok for Business** account at [business.tiktok.com](https://business.tiktok.com)
2. Register as a developer at the [TikTok for Business Developer Portal](https://business-api.tiktok.com/portal)
3. Create a developer app — you'll receive an **App ID** and **App Secret**

### Step 2 — Direct User to Authorization URL

Redirect the advertiser to TikTok's authorization page:

```
https://business-api.tiktok.com/portal/auth
  ?app_id={YOUR_APP_ID}
  &state={YOUR_CUSTOM_STATE}
  &redirect_uri={YOUR_REDIRECT_URI}
```

After approval, TikTok redirects back to your URI with:
```
https://your-redirect-uri.com?auth_code=XXXX&state=YOUR_STATE
```

### Step 3 — Exchange Auth Code for Access Token

```http
POST /open_api/v1.3/oauth2/access_token/
Content-Type: application/json
```

**Request Body:**
```json
{
  "app_id": "YOUR_APP_ID",
  "secret": "YOUR_APP_SECRET",
  "auth_code": "AUTH_CODE_FROM_REDIRECT"
}
```

**Response:**
```json
{
  "code": 0,
  "message": "OK",
  "data": {
    "access_token": "act.xxxxxxxxxxxxx",
    "advertiser_ids": ["1234567890", "9876543210"],
    "scope": [4, 7]
  }
}
```

> **Token Lifetime:**
> - Access token valid for **24 hours**
> - Refresh token valid for **1 year**
> - Refresh daily using the refresh token; after 1 year, re-authorize

### Step 4 — Get Authorized Advertisers

```http
GET /open_api/v1.3/oauth2/advertiser/get/?app_id={APP_ID}&secret={APP_SECRET}
Access-Token: {ACCESS_TOKEN}
```

Returns the list of advertiser accounts the token has access to manage.

### Token Usage in All Subsequent Requests

Every API call must include the access token as a **header**:
```
Access-Token: act.xxxxxxxxxxxxx
```

---

## 2. Required App Permissions (Scopes)

When creating your app, select **only** the scopes your dashboard needs:

| Scope | Purpose | Required? |
|---|---|---|
| `Ads Management` | Read campaign, ad group, ad data | ✅ Yes |
| `Reporting` | Access reporting/metrics endpoints | ✅ Yes |
| `Creative Management` | Read video/creative assets | ✅ Yes (for ad content) |

> **Note:** Request only what you need. Excessive scope requests slow app approval (typically 2–7 business days) and may raise flags. Since your dashboard is **read-only**, you do not need write/create permissions.

---

## 3. Rate Limits

TikTok applies rate limits **per advertiser account** and **per app**. Key rules:

| Rule | Detail |
|---|---|
| General recommendation | ~900 requests/hour per app (practical safe limit) |
| Max concurrent requests | ~8 concurrent requests |
| Reporting endpoint | Up to 10,000–20,000 ads per call; use batch filtering beyond that |
| Batch filter limit | Max 100 IDs per `campaign_ids` / `adgroup_ids` / `ad_ids` filter |
| Pagination | Use `page` and `page_size` (max `page_size=1000`) |

**Best practices for your dashboard:**
- Cache static data (audience IDs, creative asset IDs) — don't fetch on every request
- Use date-range filtering to minimize response sizes
- Always use UTC for date parameters — API data is UTC-based
- Reporting data can lag **24–48 hours** for some metrics

---

## 4. API Contract — Ads Content (Read)

### 4.1 Get Advertiser Info

Retrieve metadata for one or more advertiser accounts.

```http
GET /open_api/v1.3/advertiser/info/
Access-Token: {ACCESS_TOKEN}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `advertiser_ids` | `string[]` (JSON) | ✅ | e.g. `["1234567890"]` |

**Example Request:**
```
GET /open_api/v1.3/advertiser/info/?advertiser_ids=["1234567890"]
Access-Token: act.xxxxx
```

**Response Data Fields:**
```json
{
  "data": {
    "list": [
      {
        "advertiser_id": "1234567890",
        "advertiser_name": "My Brand",
        "currency": "USD",
        "timezone": "America/New_York",
        "status": "STATUS_ENABLE",
        "balance": 1500.00
      }
    ]
  }
}
```

---

### 4.2 Get Campaigns

Retrieve all campaigns for an advertiser account.

```http
GET /open_api/v1.3/campaign/get/
Access-Token: {ACCESS_TOKEN}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `advertiser_id` | `string` | ✅ | Advertiser account ID |
| `filtering` | `object` (JSON) | ❌ | Filter by campaign IDs, status, etc. |
| `page` | `integer` | ❌ | Page number (default: 1) |
| `page_size` | `integer` | ❌ | Results per page (default: 10, max: 1000) |
| `fields` | `string[]` (JSON) | ❌ | Specific fields to return |

**Filtering Object Example:**
```json
{
  "campaign_ids": ["111111", "222222"],
  "primary_status": "STATUS_ENABLE"
}
```

**Key Response Fields:**
```json
{
  "data": {
    "list": [
      {
        "campaign_id": "111111",
        "campaign_name": "Summer Sale 2025",
        "objective_type": "CONVERSIONS",
        "status": "STATUS_ENABLE",
        "budget": 5000.00,
        "budget_mode": "BUDGET_MODE_DAY",
        "create_time": "2025-06-01 00:00:00",
        "modify_time": "2025-06-15 12:00:00"
      }
    ],
    "page_info": {
      "page": 1,
      "page_size": 10,
      "total_number": 45,
      "total_page": 5
    }
  }
}
```

---

### 4.3 Get Ad Groups

Retrieve ad groups (adsets) for an advertiser.

```http
GET /open_api/v1.3/adgroup/get/
Access-Token: {ACCESS_TOKEN}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `advertiser_id` | `string` | ✅ | Advertiser account ID |
| `filtering` | `object` (JSON) | ❌ | Filter by campaign IDs, adgroup IDs, status |
| `page` | `integer` | ❌ | Page number (default: 1) |
| `page_size` | `integer` | ❌ | Results per page (max: 1000) |
| `fields` | `string[]` (JSON) | ❌ | Specific fields to return |
| `exclude_field_types_in_response` | `string[]` | ❌ | Field types to exclude |

**Filtering Object Example:**
```json
{
  "campaign_ids": ["111111"],
  "adgroup_ids": ["333333", "444444"],
  "primary_status": "STATUS_ENABLE"
}
```

**Key Response Fields:**
```json
{
  "data": {
    "list": [
      {
        "adgroup_id": "333333",
        "adgroup_name": "Retargeting — Mobile Users",
        "campaign_id": "111111",
        "status": "STATUS_ENABLE",
        "budget": 500.00,
        "budget_mode": "BUDGET_MODE_DAY",
        "placement_type": "PLACEMENT_TYPE_AUTOMATIC",
        "optimization_goal": "CONVERT",
        "bid_type": "BID_TYPE_NO_BID",
        "schedule_start_time": "2025-06-01 00:00:00",
        "schedule_end_time": "2025-06-30 23:59:59",
        "location_ids": ["2347791"],
        "age_groups": ["AGE_25_34", "AGE_35_44"]
      }
    ]
  }
}
```

---

### 4.4 Get Ads

Retrieve individual ads for an advertiser.

```http
GET /open_api/v1.3/ad/get/
Access-Token: {ACCESS_TOKEN}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `advertiser_id` | `string` | ✅ | Advertiser account ID |
| `filtering` | `object` (JSON) | ❌ | Filter by campaign IDs, adgroup IDs, ad IDs, status |
| `page` | `integer` | ❌ | Page number (default: 1) |
| `page_size` | `integer` | ❌ | Results per page (max: 1000) |
| `fields` | `string[]` (JSON) | ❌ | Specific fields to return |

**Filtering Object Example:**
```json
{
  "adgroup_ids": ["333333"],
  "primary_status": "STATUS_ENABLE"
}
```

**Key Response Fields (Ad Content):**
```json
{
  "data": {
    "list": [
      {
        "ad_id": "555555",
        "adgroup_id": "333333",
        "campaign_id": "111111",
        "ad_name": "Summer Sale Video 01",
        "status": "STATUS_ENABLE",
        "ad_text": "Shop our summer sale now! Up to 50% off.",
        "call_to_action": "SHOP_NOW",
        "landing_page_url": "https://brand.com/sale",
        "video_id": "v09123abc",
        "image_ids": ["img_001"],
        "ad_format": "SINGLE_VIDEO",
        "create_time": "2025-06-01 00:00:00",
        "modify_time": "2025-06-10 09:30:00",
        "review_status": "AUDIT_STATUS_APPROVED"
      }
    ]
  }
}
```

---

### 4.5 Get Video Info

Retrieve metadata and playback info for creative videos in your ad account.

```http
GET /open_api/v1.3/file/video/ad/info/
Access-Token: {ACCESS_TOKEN}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `advertiser_id` | `string` | ✅ | Advertiser account ID |
| `video_ids` | `string[]` (JSON) | ✅ | List of video IDs to fetch |

**Key Response Fields:**
```json
{
  "data": {
    "list": [
      {
        "video_id": "v09123abc",
        "video_name": "Summer Sale Hero",
        "duration": 15,
        "width": 1080,
        "height": 1920,
        "cover_url": "https://cdn.tiktok.com/cover/abc.jpg",
        "preview_url": "https://cdn.tiktok.com/preview/abc.mp4",
        "create_time": 1717200000,
        "size": 5242880
      }
    ]
  }
}
```

---

## 5. API Contract — Metrics & Reporting

### 5.1 Synchronous Report (Recommended for Dashboard)

The primary endpoint for fetching metrics. Returns up to **10,000–20,000 records** per call.

```http
GET /open_api/v1.3/report/integrated/get/
Access-Token: {ACCESS_TOKEN}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `advertiser_id` | `string` | ✅* | Required when `report_type` is `BASIC` or `AUDIENCE` |
| `report_type` | `string` | ✅ | `BASIC`, `AUDIENCE`, `PLAYABLE_MATERIAL` |
| `data_level` | `string` | ✅ | See [Data Levels](#6-data-levels--dimensions-reference) |
| `dimensions` | `string[]` (JSON) | ✅ | Grouping fields (e.g. `["campaign_id","stat_time_day"]`) |
| `metrics` | `string[]` (JSON) | ✅ | Metrics to return (e.g. `["spend","impressions"]`) |
| `start_date` | `string` | ✅* | Format: `YYYY-MM-DD`. Required unless `query_lifetime=true` |
| `end_date` | `string` | ✅* | Format: `YYYY-MM-DD`. Required unless `query_lifetime=true` |
| `query_lifetime` | `boolean` | ❌ | `true` to get all-time data, ignoring date range |
| `filtering` | `object[]` (JSON) | ❌ | Filter by specific campaign/adgroup/ad IDs |
| `order_field` | `string` | ❌ | Field to sort by (e.g. `"spend"`) |
| `order_type` | `string` | ❌ | `ASC` or `DESC` |
| `page` | `integer` | ❌ | Page number (default: 1) |
| `page_size` | `integer` | ❌ | Results per page (default: 10, max: 1000) |
| `enable_total_metrics` | `boolean` | ❌ | `true` to include aggregate totals across all pages |
| `multi_adv_report_in_utc_time` | `boolean` | ❌ | Force UTC time for multi-advertiser reports |

**Example — Campaign-level daily metrics:**
```
GET /open_api/v1.3/report/integrated/get/
  ?advertiser_id=1234567890
  &report_type=BASIC
  &data_level=AUCTION_CAMPAIGN
  &dimensions=["campaign_id","stat_time_day"]
  &metrics=["spend","impressions","clicks","ctr","cpc","cpm","reach","conversion","cost_per_conversion","roas"]
  &start_date=2025-06-01
  &end_date=2025-06-30
  &order_field=spend
  &order_type=DESC
  &page=1
  &page_size=200
Access-Token: act.xxxxx
```

**Example — Ad-level metrics with filter:**
```
GET /open_api/v1.3/report/integrated/get/
  ?advertiser_id=1234567890
  &report_type=BASIC
  &data_level=AUCTION_AD
  &dimensions=["ad_id","stat_time_day"]
  &metrics=["spend","impressions","clicks","video_play_actions","video_watched_2s","video_watched_6s"]
  &start_date=2025-06-01
  &end_date=2025-06-30
  &filtering=[{"field_name":"campaign_ids","filter_type":"IN","filter_value":"[\"111111\"]"}]
  &page_size=1000
Access-Token: act.xxxxx
```

**Response:**
```json
{
  "code": 0,
  "message": "OK",
  "data": {
    "list": [
      {
        "dimensions": {
          "campaign_id": "111111",
          "stat_time_day": "2025-06-01"
        },
        "metrics": {
          "spend": "250.50",
          "impressions": "120000",
          "clicks": "3600",
          "ctr": "3.00",
          "cpc": "0.07",
          "cpm": "2.09",
          "reach": "95000",
          "conversion": "180",
          "cost_per_conversion": "1.39",
          "roas": "4.20"
        }
      }
    ],
    "page_info": {
      "page": 1,
      "page_size": 200,
      "total_number": 45,
      "total_page": 1
    }
  }
}
```

---

### 5.2 Asynchronous Report (For Large Datasets)

Use this when data volume exceeds what the synchronous endpoint can handle.

#### Step 1 — Create Report Task

```http
POST /open_api/v1.3/report/task/create/
Content-Type: application/json
Access-Token: {ACCESS_TOKEN}
```

**Request Body:**
```json
{
  "advertiser_id": "1234567890",
  "report_type": "BASIC",
  "data_level": "AUCTION_AD",
  "dimensions": ["ad_id", "stat_time_day"],
  "metrics": ["spend", "impressions", "clicks", "conversion"],
  "start_date": "2025-01-01",
  "end_date": "2025-06-30"
}
```

**Response:**
```json
{
  "code": 0,
  "data": { "task_id": "task_abc123" }
}
```

#### Step 2 — Poll Task Status

```http
GET /open_api/v1.3/report/task/check/?task_id=task_abc123&advertiser_id=1234567890
Access-Token: {ACCESS_TOKEN}
```

**Response:**
```json
{
  "data": {
    "task_id": "task_abc123",
    "status": "SUCCESS",
    "download_url": "https://cdn.tiktok.com/reports/task_abc123.csv"
  }
}
```

> Task statuses: `PENDING` → `PROCESSING` → `SUCCESS` / `FAILED`

#### Step 3 — Cancel Task (if needed)

```http
POST /open_api/v1.3/report/task/cancel/
Content-Type: application/json
Access-Token: {ACCESS_TOKEN}
```
```json
{ "task_id": "task_abc123" }
```

---

## 6. Data Levels & Dimensions Reference

### Data Levels (`data_level`)

| Value | Description |
|---|---|
| `AUCTION_ADVERTISER` | Advertiser-level aggregation |
| `AUCTION_CAMPAIGN` | Campaign-level aggregation |
| `AUCTION_ADGROUP` | Ad group-level aggregation |
| `AUCTION_AD` | Individual ad-level aggregation |

### Dimensions

| Dimension | Category | Description |
|---|---|---|
| `advertiser_id` | ID | Advertiser account |
| `campaign_id` | ID | Campaign |
| `adgroup_id` | ID | Ad group |
| `ad_id` | ID | Individual ad |
| `stat_time_day` | Time | Group by day |
| `stat_time_hour` | Time | Group by hour |
| `country_code` | Location | Country breakdown |
| `gender` | Audience | Gender breakdown |
| `age` | Audience | Age group breakdown |
| `platform` | Device | iOS / Android |

> **Rule:** The `data_level` and `dimensions` must be compatible. For example, if `data_level=AUCTION_CAMPAIGN`, your dimensions must include `campaign_id`.

---

## 7. Audience Breakdown by Age & Gender

TikTok's API supports demographic breakdowns (age, gender, country, device, and more) but **requires switching from `report_type=BASIC` to `report_type=AUDIENCE`**. The endpoint URL is identical — only the parameters change.

### Available Audience Breakdown Dimensions

| Dimension Value | Breaks Down By | Notes |
|---|---|---|
| `age` | Age groups | 13–17, 18–24, 25–34, 35–44, 45–54, 55+ |
| `gender` | Gender | MALE, FEMALE, UNKNOWN |
| `age,gender` | Age + Gender combined | Single request for both |
| `country_code` | Country | ISO country codes |
| `platform` | Operating system | IOS, ANDROID |
| `placement` | Ad placement | TIKTOK, PANGLE, etc. |
| `language` | Device language | e.g. en, id, ja |
| `ac` | Network type | WIFI, 4G, 3G, 2G |
| `device` | Device model | Device brand/model strings |

### Example — Breakdown by Age

```
GET /open_api/v1.3/report/integrated/get/
  ?advertiser_id=1234567890
  &report_type=AUDIENCE
  &data_level=AUCTION_ADGROUP
  &dimensions=["adgroup_id","age"]
  &metrics=["spend","impressions","clicks","ctr","cpm","conversion","cost_per_conversion"]
  &start_date=2025-06-01
  &end_date=2025-06-30
Access-Token: act.xxxxx
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "list": [
      {
        "dimensions": {
          "adgroup_id": "333333",
          "age": "AGE_18_24"
        },
        "metrics": {
          "spend": "80.20",
          "impressions": "42000",
          "clicks": "1260",
          "ctr": "3.00",
          "cpm": "1.91",
          "conversion": "55",
          "cost_per_conversion": "1.46"
        }
      },
      {
        "dimensions": {
          "adgroup_id": "333333",
          "age": "AGE_25_34"
        },
        "metrics": {
          "spend": "120.10",
          "impressions": "60000",
          "clicks": "1800",
          "ctr": "3.00",
          "cpm": "2.00",
          "conversion": "90",
          "cost_per_conversion": "1.33"
        }
      }
    ]
  }
}
```

**Age group enum values returned in response:**

| Value | Age Range |
|---|---|
| `AGE_13_17` | 13–17 years |
| `AGE_18_24` | 18–24 years |
| `AGE_25_34` | 25–34 years |
| `AGE_35_44` | 35–44 years |
| `AGE_45_54` | 45–54 years |
| `AGE_55_PLUS` | 55 and above |

### Example — Breakdown by Gender

```
GET /open_api/v1.3/report/integrated/get/
  ?advertiser_id=1234567890
  &report_type=AUDIENCE
  &data_level=AUCTION_ADGROUP
  &dimensions=["adgroup_id","gender"]
  &metrics=["spend","impressions","clicks","ctr","conversion","cost_per_conversion"]
  &start_date=2025-06-01
  &end_date=2025-06-30
Access-Token: act.xxxxx
```

### Example — Breakdown by Age + Gender Combined

```
GET /open_api/v1.3/report/integrated/get/
  ?advertiser_id=1234567890
  &report_type=AUDIENCE
  &data_level=AUCTION_ADGROUP
  &dimensions=["adgroup_id","age_gender"]
  &metrics=["spend","impressions","clicks","ctr","conversion"]
  &start_date=2025-06-01
  &end_date=2025-06-30
Access-Token: act.xxxxx
```

### ⚠️ Important Caveats

**1. `AUDIENCE` has narrower metric coverage than `BASIC`.**

Metrics available with `AUDIENCE`:

| Category | Available? |
|---|---|
| Core (spend, impressions, clicks, CTR, CPM, reach) | ✅ |
| Video play metrics | ✅ |
| Conversions & CVR | ✅ |
| Engagement (likes, shares, follows) | ✅ |
| Attribution (CTA / VTA) | ❌ |
| Website / Page Events | ❌ |
| App Events | ❌ |
| SKAN Metrics | ❌ |
| LIVE Metrics | ❌ |
| Real-Time Metrics | ❌ |

**2. You cannot mix `AUDIENCE` and `BASIC`-only metrics in a single request** — it will return an error.

**3. Recommended two-call pattern for your dashboard:**

```
Call 1 — BASIC report:
  report_type=BASIC
  → Full conversion, attribution, app/website event metrics
  → No demographic breakdown

Call 2 — AUDIENCE report:
  report_type=AUDIENCE
  dimensions includes "age" or "gender"
  → Demographic breakdown of core metrics only
```

Make these calls in parallel and merge results client-side by `adgroup_id` or `campaign_id`.

---

## 8. Common Metrics Reference

### Performance Metrics

| Metric | Description |
|---|---|
| `spend` | Total amount spent (in account currency) |
| `impressions` | Total number of times ads were shown |
| `clicks` | Total number of clicks |
| `ctr` | Click-through rate (%) |
| `cpc` | Cost per click |
| `cpm` | Cost per 1,000 impressions |
| `reach` | Unique users who saw the ad |

### Conversion Metrics

| Metric | Description |
|---|---|
| `conversion` | Total conversion events |
| `cost_per_conversion` | Spend divided by conversions |
| `roas` | Return on ad spend |
| `real_time_conversion` | Real-time conversions (lower latency) |

### Video Metrics

| Metric | Description |
|---|---|
| `video_play_actions` | Total number of video plays |
| `video_watched_2s` | Users who watched at least 2 seconds |
| `video_watched_6s` | Users who watched at least 6 seconds |
| `video_views_p25` | Users who watched 25% of video |
| `video_views_p50` | Users who watched 50% of video |
| `video_views_p75` | Users who watched 75% of video |
| `video_views_p100` | Users who watched 100% of video |
| `average_video_play` | Average seconds watched per view |

---

## 9. Standard Response Envelope

All API responses follow this envelope structure:

```json
{
  "code": 0,
  "message": "OK",
  "request_id": "2025060100123456789",
  "data": { ... }
}
```

| Field | Type | Description |
|---|---|---|
| `code` | `integer` | `0` = success; any other value = error |
| `message` | `string` | Human-readable status message |
| `request_id` | `string` | Unique ID for this request (use for support) |
| `data` | `object` | Response payload |

Paginated responses include a `page_info` object inside `data`:
```json
"page_info": {
  "page": 1,
  "page_size": 200,
  "total_number": 4500,
  "total_page": 23
}
```

---

## 10. Error & Return Codes

| Code | Meaning | Action |
|---|---|---|
| `0` | Success | Proceed normally |
| `40001` | Invalid parameter | Check request params |
| `40002` | Missing required parameter | Add missing fields |
| `40100` | Invalid access token | Refresh or re-authorize |
| `40101` | Access token expired | Refresh token |
| `40200` | Permission denied | Check app scopes |
| `40300` | Rate limit exceeded | Back off and retry |
| `50002` | Internal server error | Retry with exponential backoff |

**HTTP Status Codes:**

| Status | Meaning |
|---|---|
| `200` | Request processed (check `code` field for business-level result) |
| `400` | Bad request |
| `401` | Unauthorized |
| `429` | Too many requests |
| `500` | Server error |

---

## 11. End-to-End Integration Flow

```
[User / Advertiser]
       |
       | 1. Click "Connect TikTok Account" in dashboard
       ↓
[Dashboard Backend]
       |
       | 2. Redirect to TikTok OAuth URL
       ↓
[TikTok Auth Page]
       |
       | 3. Advertiser grants permission
       | 4. TikTok redirects back with auth_code
       ↓
[Dashboard Backend]
       |
       | 5. Exchange auth_code → access_token + advertiser_ids
       | 6. Store access_token securely (encrypted at rest)
       ↓
[Dashboard Frontend loads]
       |
       | 7. Fetch advertiser list → display account selector
       | 8. Fetch campaigns → populate campaign dropdown/list
       | 9. Fetch ad groups → filtered by selected campaign
       | 10. Fetch ads → display creative content panel
       | 11. Fetch report metrics → populate charts and tables
       ↓
[Scheduled Background Jobs]
       |
       | 12. Refresh access_token daily (before 24h expiry)
       | 13. Sync metrics data periodically (account for 24-48h lag)
```

---

## 12. Dashboard Data Flow Diagram

### Suggested Dashboard Data Architecture

```
                    ┌─────────────────────────────────┐
                    │         Dashboard UI             │
                    │  ┌──────────┐  ┌─────────────┐  │
                    │  │ Metrics  │  │ Ads Content │  │
                    │  │ Charts   │  │   Viewer    │  │
                    │  └────┬─────┘  └──────┬──────┘  │
                    └───────┼───────────────┼─────────┘
                            │               │
                    ┌───────▼───────────────▼─────────┐
                    │         Backend API Layer        │
                    │  (Token management, caching,     │
                    │   rate limit handling)           │
                    └───────────────┬─────────────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
    ┌─────────▼──────┐  ┌──────────▼────────┐  ┌─────────▼──────────┐
    │  Ads Content   │  │  Metrics/Reporting │  │   Auth Endpoints   │
    │                │  │                    │  │                    │
    │ /campaign/get  │  │ /report/integrated │  │ /oauth2/access_    │
    │ /adgroup/get   │  │        /get/       │  │       token/       │
    │ /ad/get        │  │                    │  │ /oauth2/advertiser │
    │ /file/video/   │  │ /report/task/      │  │       /get/        │
    │   ad/info/     │  │ create|check|cancel│  │                    │
    └────────────────┘  └────────────────────┘  └────────────────────┘
              │                     │
              └──────────┬──────────┘
                         │
             ┌───────────▼───────────┐
             │  TikTok Business API  │
             │  v1.3                 │
             │  business-api.tiktok  │
             │  .com                 │
             └───────────────────────┘
```

---

### Recommended Fetch Strategy for Dashboard

| Dashboard Section | Endpoint | Frequency |
|---|---|---|
| Account overview | `advertiser/info/` | On load, cache 1h |
| Campaign list | `campaign/get/` | On load / user refresh |
| Ad group list | `adgroup/get/` | On campaign select |
| Ad creative content | `ad/get/` | On ad group select |
| Video previews | `file/video/ad/info/` | On ad select, cache per ID |
| Today's metrics | `report/integrated/get/` (day granularity) | Every 30–60 min |
| Historical charts | `report/integrated/get/` (date range) | On date filter change |
| Large exports | `report/task/create` + `check` | On demand |

---

## Notes & Gotchas

1. **Metric lag:** Reporting data can be 24–48 hours behind for some metrics. Always use UTC dates.
2. **Pagination:** Always implement pagination. Never assume all data fits in a single response.
3. **Token refresh:** Build a daily refresh job. Don't wait for the token to expire — refresh proactively.
4. **App vs account auth:** App approval and individual advertiser account authorization are **separate**. Each advertiser must go through the OAuth flow to grant your app access.
5. **Report type compatibility:** Not all metrics are available for all `report_type` + `data_level` combinations. Test combinations in the [TikTok API Playground](https://business-api.tiktok.com/portal/docs/api-playground/v1.3) before building.
6. **Dimensions rule:** A report's `dimensions` must include the ID field that matches the `data_level`. For `AUCTION_AD`, include `ad_id`; for `AUCTION_CAMPAIGN`, include `campaign_id`.
7. **Read-only safety:** Since your dashboard is read-only, you only call `GET` endpoints and the reporting `POST` (`/report/task/create`) which is purely a data-pull action, not a mutation.
