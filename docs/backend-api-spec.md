# DashMet — Backend API Specification

> **Version:** 0.1  
> **Status:** Draft  
> **Base URL:** `/api/v1`  
> **Format:** REST · JSON  
> **Auth:** JWT Bearer token

---

## Table of Contents

1. [Conventions](#1-conventions)
2. [Authentication](#2-authentication)
3. [Common Query Parameters](#3-common-query-parameters)
4. [Response Envelope](#4-response-envelope)
5. [Error Shapes](#5-error-shapes)
6. [Endpoints](#6-endpoints)
   - [6.1 Organization](#61-organization)
   - [6.2 Platform Connections](#62-platform-connections)
   - [6.3 Accounts](#63-accounts)
   - [6.4 Campaigns](#64-campaigns)
   - [6.5 Ad Groups](#65-ad-groups)
   - [6.6 Ads](#66-ads)
   - [6.7 Creatives](#67-creatives)
   - [6.8 Overview](#68-overview)
   - [6.9 Time Series (Periodic)](#69-time-series-periodic)
   - [6.10 Table Metrics](#610-table-metrics)
   - [6.11 Breakdown](#611-breakdown)
   - [6.12 Combined Dashboard (Cross-Platform)](#612-combined-dashboard-cross-platform)
   - [6.13 Engagement (TikTok)](#613-engagement-tiktok)
   - [6.14 Sync Status](#614-sync-status)
7. [Metric Field Names](#7-metric-field-names)
8. [Enum Reference](#8-enum-reference)

---

## 1. Conventions

- All timestamps are **ISO 8601 UTC** (`2026-05-30T12:00:00Z`)
- All dates are **YYYY-MM-DD** (`2026-05-30`)
- All monetary values are in the **account's currency**, as a float (e.g. `12.50` = $12.50)
- All rate/percentage metrics are returned as floats (e.g. `ctr: 2.34` = 2.34%)
- Numeric string IDs from Meta are stored and returned as strings
- Null means "not available" (field not requested, no data). Missing key means field doesn't apply.
- All list endpoints support pagination via `page` + `per_page`
- All list endpoints return results sorted by `created_at DESC` unless `sort_by` is specified

---

## 2. Authentication

### JWT payload

Every JWT includes the user's identity and their current organization context.

```json
{
  "sub":     "user-uuid",
  "org_id":  "org-uuid",
  "role":    "owner",
  "email":   "user@example.com",
  "exp":     1748649600
}
```

The `org_id` and `role` claims are used server-side to enforce tenant isolation and permission checks on every request. The backend never trusts a client-supplied `org_id` — it always reads from the JWT.

---

### `POST /api/v1/auth/signup`

Create a new user and organization in one step.

**Request body**
```json
{
  "name":          "Akbar",
  "email":         "user@example.com",
  "password":      "...",
  "org_name":      "Acme Marketing"
}
```

**Response `201`**
```json
{
  "data": {
    "message": "Account created. Check your email to verify."
  }
}
```

> User cannot log in until email is verified.

---

### `POST /api/v1/auth/verify-email`

**Request body**
```json
{
  "token": "<email-verify-token>"
}
```

**Response `200`**
```json
{
  "data": {
    "access_token": "eyJ...",
    "token_type":   "bearer",
    "expires_in":   86400
  }
}
```

---

### `POST /api/v1/auth/login`

**Request body**
```json
{
  "email":    "user@example.com",
  "password": "..."
}
```

**Response `200`**
```json
{
  "data": {
    "access_token": "eyJ...",
    "token_type":   "bearer",
    "expires_in":   86400,
    "user": {
      "id":    "uuid",
      "name":  "Akbar",
      "email": "user@example.com"
    },
    "org": {
      "id":   "uuid",
      "name": "Acme Marketing",
      "slug": "acme-marketing",
      "role": "owner"
    }
  }
}
```

---

### `POST /api/v1/auth/forgot-password`

**Request body**
```json
{ "email": "user@example.com" }
```

**Response `200`** — always returns success (don't reveal whether email exists)
```json
{ "data": { "message": "If that email exists, a reset link has been sent." } }
```

---

### `POST /api/v1/auth/reset-password`

**Request body**
```json
{
  "token":        "<reset-token>",
  "new_password": "..."
}
```

**Response `200`**
```json
{ "data": { "message": "Password updated. You can now log in." } }
```

---

### `POST /api/v1/auth/logout`

Invalidates the current token server-side.

**Headers:** `Authorization: Bearer <token>`  
**Response `204`** — no body

---

### `GET /api/v1/auth/me`

**Response `200`**
```json
{
  "data": {
    "id":    "uuid",
    "email": "user@example.com",
    "name":  "Akbar",
    "org": {
      "id":   "uuid",
      "name": "Acme Marketing",
      "slug": "acme-marketing",
      "role": "owner"
    }
  }
}
```

---

## 3. Common Query Parameters

These parameters apply to all insight/metrics endpoints unless noted otherwise.

| Param | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | ✅ | Internal account UUID |
| `date_preset` | string | one of these two | Predefined range — see [date presets](#date-presets) |
| `date_start` + `date_end` | string (YYYY-MM-DD) | one of these two | Custom date range. Both required if either is set. |
| `platform` | string | ❌ | Filter by platform. Default: all. Values: `meta` \| `google_ads` \| `tiktok` |
| `campaign_id` | string | ❌ | Filter to a specific campaign |
| `adgroup_id` | string | ❌ | Filter to a specific ad group |
| `status` | string | ❌ | Filter by entity status. Default: all active. Values: see [status enum](#status) |
| `sort_by` | string | ❌ | Metric or field name to sort by (e.g. `spend`, `ctr`, `name`) |
| `sort_order` | string | ❌ | `asc` \| `desc`. Default: `desc` |
| `page` | int | ❌ | Page number. Default: `1` |
| `per_page` | int | ❌ | Results per page. Default: `25`. Max: `200` |

### Date presets

| Value | Range |
|---|---|
| `today` | Today |
| `yesterday` | Yesterday |
| `last_7d` | Last 7 days |
| `last_14d` | Last 14 days |
| `last_28d` | Last 28 days |
| `last_30d` | Last 30 days |
| `last_90d` | Last 90 days |
| `this_month` | Current month |
| `last_month` | Previous month |
| `this_year` | Current year |
| `lifetime` | All time |

---

## 4. Response Envelope

All responses wrap their payload in a standard envelope.

### Success (single object)
```json
{
  "data": { ... },
  "meta": {
    "request_id": "uuid",
    "cached": true,
    "cached_at": "2026-05-30T11:45:00Z"
  }
}
```

### Success (list)
```json
{
  "data": [ ... ],
  "pagination": {
    "total": 120,
    "page": 1,
    "per_page": 25,
    "total_pages": 5
  },
  "meta": {
    "request_id": "uuid",
    "cached": false,
    "cached_at": null
  }
}
```

### `meta` object fields

| Field | Description |
|---|---|
| `request_id` | Unique ID for this request — include in bug reports |
| `cached` | Whether this response came from cache |
| `cached_at` | When the cached data was last fetched from the platform |

> `cached_at` is what the frontend should display as "Last updated" — never show `now()`, always show when the data was actually fetched.

---

## 5. Error Shapes

### Standard error
```json
{
  "error": {
    "code": "INVALID_DATE_RANGE",
    "message": "date_end must be after date_start",
    "field": "date_end"
  }
}
```

### Validation error (multiple fields)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      { "field": "account_id", "message": "Required" },
      { "field": "date_preset", "message": "Invalid value 'last_500d'" }
    ]
  }
}
```

### HTTP status codes used

| Status | When |
|---|---|
| `200` | Success |
| `204` | Success, no body |
| `400` | Bad request / validation error |
| `401` | Missing or invalid token |
| `403` | Valid token but no access to this resource |
| `404` | Resource not found |
| `429` | Internal rate limit (platform API exhausted — try again later) |
| `500` | Unexpected server error |
| `503` | Platform API unavailable / sync not yet run |

> **`429` from the backend** means the Meta API quota is exhausted and the backend cannot serve fresh data. The frontend should display cached data with a banner saying the data may be delayed.

---

## 6. Endpoints

---

### 6.1 Organization

#### `GET /api/v1/org`

Get the current user's organization.

**Response `200`**
```json
{
  "data": {
    "id":         "uuid",
    "name":       "Acme Marketing",
    "slug":       "acme-marketing",
    "created_at": "2026-01-15T09:00:00Z"
  }
}
```

#### `PATCH /api/v1/org`

Update org name. **Owner only.**

**Request body**
```json
{ "name": "Acme Digital" }
```

**Response `200`** — returns updated org object.

---

#### `GET /api/v1/org/members`

List all members of the current org.

**Response `200`**
```json
{
  "data": [
    {
      "id":          "uuid",
      "name":        "Akbar",
      "email":       "akbar@example.com",
      "role":        "owner",
      "joined_at":   "2026-01-15T09:00:00Z"
    },
    {
      "id":          "uuid",
      "name":        null,
      "email":       "teammate@example.com",
      "role":        "member",
      "joined_at":   null,
      "invite_pending": true
    }
  ]
}
```

#### `POST /api/v1/org/members/invite`

Invite a new member by email. **Owner only.** Sends an invite email with a link to accept.

**Request body**
```json
{
  "email": "teammate@example.com",
  "role":  "member"
}
```

**Response `201`**
```json
{
  "data": {
    "message": "Invite sent to teammate@example.com"
  }
}
```

#### `POST /api/v1/org/members/accept-invite`

Accept an invite token (called when the invitee clicks the email link). Creates user account if new, adds to org.

**Request body**
```json
{
  "token":    "<invite-token>",
  "name":     "Teammate Name",
  "password": "..."
}
```

**Response `200`** — returns access token (user is logged in immediately).

#### `DELETE /api/v1/org/members/:user_id`

Remove a member from the org. **Owner only.** Cannot remove yourself.

**Response `204`** — no body.

---

### 6.2 Platform Connections

Manages the linked ad platform accounts (Meta, etc.) for the org. **Owner only** for write operations.

#### `GET /api/v1/connections`

List all platform connections for the current org.

**Response `200`**
```json
{
  "data": [
    {
      "id":          "uuid",
      "platform":    "meta",
      "is_active":   true,
      "scopes":      ["ads_read", "read_insights"],
      "token_type":  "system_user",
      "connected_by": "Akbar",
      "connected_at": "2026-02-01T10:00:00Z",
      "last_used_at": "2026-05-30T11:45:00Z"
    }
  ]
}
```

> The `access_token` itself is **never returned** — only metadata about the connection.

#### `POST /api/v1/connections`

Connect a new platform ad account. **Owner only.**

**Request body**
```json
{
  "platform":     "meta",
  "access_token": "EAABwzLixnjY...",
  "token_type":   "system_user"
}
```

The backend validates the token immediately by calling `/me` on the platform API before saving. If the token is invalid or missing required scopes, returns `400`.

**Response `201`**
```json
{
  "data": {
    "id":        "uuid",
    "platform":  "meta",
    "is_active": true,
    "scopes":    ["ads_read", "read_insights"],
    "message":   "Connection verified. Ad accounts are being imported."
  }
}
```

On success, immediately triggers a `structure` sync job to import the org's ad accounts.

#### `DELETE /api/v1/connections/:id`

Disconnect a platform. **Owner only.** Sets `is_active = false` on the connection and pauses all sync jobs for affected accounts.

**Response `204`** — no body.

---

### 6.3 Accounts


#### `GET /api/v1/accounts`

List ad accounts the authenticated user has access to. Supports server-side search and platform scoping so the account picker never has to load the full org (orgs can have 200–1000+ accounts).

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `search` | string | — | Case-insensitive substring match on `name`, `external_id`, **and** `business_name` (ILIKE) |
| `platform` | string | — | Scope to one platform (`meta`, `tiktok`, …) |
| `page` | int | 1 | Page number |
| `per_page` | int | 25 | Page size (max 200) |

Disabled accounts (`account_status = "disabled"`) are always excluded.

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "platform": "meta",
      "external_id": "act_1234567890",
      "name": "My Ad Account",
      "currency": "USD",
      "timezone": "America/Los_Angeles",
      "account_status": "active",
      "account_type": "standard",
      "business_name": "My Business",
      "last_synced_at": "2026-05-30T11:45:00Z"
    }
  ],
  "pagination": { "total": 3, "page": 1, "per_page": 25, "total_pages": 1 }
}
```

#### `GET /api/v1/accounts/:id`

Single account detail.

Disabled accounts (`account_status = "disabled"`) read as **`404`**, mirroring `GET /accounts` — a stale client selection (an `account_id` kept from before a disconnect+reconnect) resolves to gone so the UI falls back to a live account. Cross-org access is still `403` (checked before the status filter, so status never leaks).

**Response `200`** — same shape as single item above, plus:
```json
{
  "data": {
    "...": "...",
    "config": {
      "primary_conversion_action": "purchase",
      "attribution_window": "7d_click_1d_view",
      "roas_action_type": "purchase"
    }
  }
}
```

#### `PATCH /api/v1/accounts/:id/config`

Update per-account configuration. All fields optional; only provided fields change.

**Request body**
```json
{
  "primary_conversion_action": "lead",
  "attribution_window": "1d_click",
  "roas_action_type": "purchase",
  "account_type": "standard"
}
```

| Field | Type | Notes |
|---|---|---|
| `primary_conversion_action` | string | Conversion action used for CPA/conversions |
| `attribution_window` | string | e.g. `7d_click_1d_view` |
| `roas_action_type` | string | Action type ROAS is computed from |
| `account_type` | `"standard"` \| `"cpas"` | **Meta-only.** `cpas` (Collaborative Ads) is rejected for non-Meta accounts |

**Response `200`** — returns updated account object.

**Errors**

| Status | Code | When |
|---|---|---|
| `409` | `CONFLICT` | `account_type` = `cpas` on a non-Meta account (`platform != "meta"`) |
| `404` | `NOT_FOUND` | Account not found |
| `403` | `FORBIDDEN` | Account belongs to another org |

---

### 6.4 Campaigns

#### `GET /api/v1/campaigns`

List campaigns for an account. Used to populate campaign tables and filter dropdowns.

**Query params:** `account_id` (required), `status`, `sort_by`, `sort_order`, `page`, `per_page`

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "platform": "meta",
      "platform_campaign_id": "23845000000000000",
      "name": "Summer Sale Campaign",
      "status": "active",
      "effective_status": "active",
      "objective": "sales",
      "daily_budget": 50.00,
      "lifetime_budget": null,
      "buying_type": "auction",
      "start_date": "2026-05-01",
      "end_date": null,
      "created_at": "2026-04-28T10:23:00Z"
    }
  ],
  "pagination": { "total": 14, "page": 1, "per_page": 25, "total_pages": 1 }
}
```

---

### 6.5 Ad Groups

#### `GET /api/v1/adgroups`

**Query params:** `account_id` (required), `campaign_id`, `status`, `sort_by`, `sort_order`, `page`, `per_page`

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "platform_adgroup_id": "23845000000000001",
      "campaign_id": "uuid",
      "campaign_name": "Summer Sale Campaign",
      "name": "Lookalike — Purchasers",
      "status": "active",
      "effective_status": "active",
      "optimization_goal": "conversions",
      "billing_event": "impressions",
      "bid_amount": 5.00,
      "daily_budget": null,
      "start_date": "2026-05-01",
      "end_date": null
    }
  ],
  "pagination": { "..." : "..." }
}
```

---

### 6.6 Ads

#### `GET /api/v1/ads`

**Query params:** `account_id` (required), `campaign_id`, `adgroup_id`, `status`, `sort_by`, `sort_order`, `page`, `per_page`

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "platform_ad_id": "23845000000000002",
      "adgroup_id": "uuid",
      "campaign_id": "uuid",
      "name": "Summer Ad — Image v1",
      "status": "active",
      "effective_status": "active",
      "has_creative": true,
      "created_at": "2026-05-01T09:00:00Z"
    }
  ],
  "pagination": { "..." : "..." }
}
```

---

### 6.7 Creatives

#### `GET /api/v1/ads/:id/creative`

Get the creative content for a specific ad. Triggers a lazy fetch if not yet cached.

**Response `200`**
```json
{
  "data": {
    "ad_id": "uuid",
    "creative": {
      "id": "uuid",
      "platform_creative_id": "23845000000000003",
      "format": "image",
      "title": "Shop Summer Deals",
      "body": "Enjoy up to 50% off. Limited time only.",
      "image_url": "https://scontent.facebook.com/...",
      "thumbnail_url": null,
      "video_id": null,
      "cta_type": "shop_now",
      "destination_url": "https://example.com/summer-sale",
      "synced_at": "2026-05-30T11:00:00Z"
    }
  }
}
```

**Response `202`** — if creative hasn't been fetched yet, returns immediately with:
```json
{
  "data": null,
  "meta": {
    "status": "fetching",
    "message": "Creative is being fetched. Retry in a few seconds."
  }
}
```

> The frontend should poll this endpoint with a short interval (2–3s) until `data` is non-null when it receives `202`.

---

### 6.8 Overview

The main summary panel — aggregated metrics for an account over a period, with period-over-period comparison.

#### `GET /api/v1/insights/overview`

**Query params:** `account_id` (required), `date_preset` or `date_start`+`date_end`, `status`, `search`

**Campaign filter** (shared with `timeseries` and the Table/Ads tabs — driven by the Control-strip Filter popover):

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | string | — | Restrict to campaigns with this status (`active` \| `paused` \| `archived`). Omitted = all. |
| `search` | string | — | Restrict to campaigns whose name matches (`ILIKE '%search%'`). |

When either is set, the summary, `vs_previous`, and `top_campaigns` aggregate only the matching campaigns' rows. A filter that matches no campaign yields empty/`null` metrics (not a silent all-rows fallback). Resolved once via `_resolve_campaign_ids` → `entity_id = ANY(...)` predicate in `app/services/insights.py`.

**Response `200`**
```json
{
  "data": {
    "period": {
      "date_start": "2026-05-23",
      "date_stop": "2026-05-30",
      "preset": "last_7d"
    },
    "summary": {
      "spend":            1234.56,
      "impressions":      450000,
      "reach":            210000,
      "frequency":        2.14,
      "clicks":           8900,
      "inline_link_clicks": 7200,
      "ctr":              1.978,
      "cpm":              2.74,
      "cpc":              0.14,
      "cpp":              5.88,
      "conversions":      234,
      "conversion_value": 7890.00,
      "roas":             6.39,
      "cpa":              5.27
    },
    "previous": {
      "spend":            1099.10,
      "impressions":      465000,
      "reach":            205000,
      "frequency":        2.27,
      "clicks":           8190,
      "inline_link_clicks": 6800,
      "ctr":              1.762,
      "cpm":              2.36,
      "cpc":              0.13,
      "cpp":              5.36,
      "conversions":      191,
      "conversion_value": 7010.00,
      "roas":             6.38,
      "cpa":              5.75
    },
    "vs_previous": {
      "spend":       12.3,
      "impressions": -3.1,
      "clicks":      8.7,
      "ctr":         11.2,
      "conversions": 22.5,
      "roas":        9.1
    },
    "top_campaigns": [
      {
        "id":          "uuid",
        "name":        "Summer Sale Campaign",
        "spend":       780.00,
        "conversions": 150,
        "roas":        7.1
      }
    ]
  },
  "meta": {
    "cached": true,
    "cached_at": "2026-05-30T11:45:00Z"
  }
}
```

**`previous`:** the full prior-period summary — the exact same key set as `summary`, aggregated over the prior period (see *Prior-period resolution* below). Always present (not gated behind a query param); the frontend uses it to render period-over-period delta pills. Same one-writer/aggregate-then-ratio path as `summary` (ratios computed after aggregation, never average-of-averages).

**`vs_previous` values:** percentage change vs the **prior period** (see *Prior-period resolution* below). Positive = improved, negative = declined. `null` if no prior data.

**Prior-period resolution** — shared by `overview`, `timeseries`, and `combined` (implemented once in `resolve_prior_period`, `app/services/insights.py`):

- If the selected range is **exactly one full calendar month** (the 1st through the last day of the same month), the prior period is the **previous calendar month** — e.g. `May 1–31` → `Apr 1–30`, `Mar 1–31` → `Feb 1–28/29`, `Jan 1–31` → `Dec 1–31` of the prior year. The day is clamped to the shorter month.
- Otherwise — rolling presets (`last_7d`, `last_30d`, …) or custom multi-month spans — the prior period is the **equal-length window immediately before** the range (e.g. a 7-day range → the preceding 7 days).

**`roas` and `cpa`** are computed from `account_configs.roas_action_type` and `primary_conversion_action` respectively.

---

#### `GET /api/v1/insights/overview/export.pptx`

Server-rendered PowerPoint (.pptx) export of a single-account overview. Same query params and date/tenant resolution as `GET /insights/overview`.

**Query params:** `account_id` (required), `date_preset` or `date_start`+`date_end`, `status`, `search`

**Response `200`** — binary PPTX (not JSON):

| Header | Value |
|---|---|
| `Content-Type` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| `Content-Disposition` | `attachment; filename="<Account> - Monthly Report - <Month Year>.pptx"; filename*=UTF-8''…` (e.g. `Polki Indonesia - Monthly Report - July 2026.pptx`) |

The download name is `"<Account name> - Monthly Report - <period-start Month Year>.pptx"` (`_report_filename` in `app/api/v1/endpoints/insights.py`). The header carries both an ASCII-stripped `filename` fallback and an RFC 5987 `filename*=UTF-8''…` for spaces/non-ASCII account names (`_content_disposition`). CORS exposes `Content-Disposition` (`app/main.py`) so the browser can read the name cross-origin; the frontend parses it (`parseContentDispositionFilename` in `lib/api/insights.ts`) for the download. Body is a `StreamingResponse` over the raw `.pptx` bytes built by `app/services/export.py:generate_overview_pptx`.

**Parity (P-6/P-7):** the endpoint reuses the shared read functions `get_overview` / `get_timeseries` (called with `compare_previous=True` for the trend overlay) / `get_table` (the same functions behind `GET /overview`, `GET /timeseries`, `GET /table`) — no second query path against the metrics tables. Deck = **6 slides**, a branded monthly-report template (neutral dashmet branding, no third-party logos): (1) dark gradient-blob **cover** with account/period; (2) **Monthly Performance** — a Current-vs-Previous spend hero plus metric cards (impressions, clicks, CTR, CPM, conversions, ROAS) showing coloured period-over-period deltas and prior values; (3) **daily spend trend** — a native pptx line chart overlaying current vs previous period with a thinned date axis; (4) **Top Campaigns** — styled table; (5) **Top Ads** — top-6 (`level="ad"`, spend-desc) with 4:5 letterboxed creative thumbnails; (6) **closing** slide. Content slides carry an editable purple "insight" placeholder box. A missing/failed thumbnail degrades to a neutral placeholder, never a fake image.

> **Known gap (P-1):** the single-account `get_overview()` read path does **not** return a `data_as_of` / `coverage` / `cached_at` freshness envelope (the combined path does, via `meta.cached_at`). The export's cover therefore stamps only "Data as of `<date_stop>`" derived from the period, not a true freshness/coverage marker. Tracked as a follow-up in `BOARD.md`.

---

### 6.9 Time Series (Periodic)

Daily metric trend data — powers line/bar charts in the Periodic view.

#### `GET /api/v1/insights/timeseries`

**Query params:** `account_id` (required), `date_preset` or `date_start`+`date_end`, `level`, `campaign_id`, `adgroup_id`, `metrics` (comma-separated list), `time_increment`, `status`, `search`

**Additional params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `level` | string | `account` | `account` \| `campaign` \| `adgroup` \| `ad` |
| `metrics` | string | `spend,impressions,clicks,ctr` | Comma-separated metric names to include |
| `time_increment` | string | `day` | `day` \| `week` \| `month` |
| `compare_previous` | boolean | `false` | Include previous period data for overlay comparison |
| `status` | string | — | Campaign filter — same semantics as `overview`. Applied to the `account`-level series and to the `campaign`-level breakdown; ignored for `adgroup`/`ad` breakdowns (campaign ids don't match those grains). |
| `search` | string | — | Campaign-name filter — same semantics as `overview`. |

**Response `200`**
```json
{
  "data": {
    "level": "campaign",
    "time_increment": "day",
    "metrics": ["spend", "impressions", "clicks", "ctr"],
    "period": {
      "date_start": "2026-05-01",
      "date_stop":  "2026-05-30"
    },
    "series": [
      {
        "date":        "2026-05-01",
        "spend":       45.20,
        "impressions": 18500,
        "clicks":      320,
        "ctr":         1.73
      },
      {
        "date":        "2026-05-02",
        "spend":       51.80,
        "impressions": 21200,
        "clicks":      390,
        "ctr":         1.84
      }
    ],
    "previous_series": null
  }
}
```

When `compare_previous=true`, `previous_series` has the same shape as `series` — aligned by relative position (point 1 of current vs point 1 of prior period), so the frontend can overlay them directly. The prior period follows the *Prior-period resolution* rule in §6.8 (full calendar month → previous calendar month; otherwise equal-length preceding window). At non-account levels, each entry in `series_by_entity` also carries its own `previous_series` (same alignment, per entity); it is `[]` for entities with no data in the prior period.

**Campaign-level breakdown** (when `level=campaign`, response includes a group per campaign):
```json
{
  "data": {
    "level": "campaign",
    "series_by_entity": [
      {
        "entity": {
          "id":   "uuid",
          "name": "Summer Sale Campaign"
        },
        "series": [
          { "date": "2026-05-01", "spend": 30.10, "impressions": 12000 }
        ],
        "previous_series": [
          { "date": "2026-04-01", "spend": 27.40, "impressions": 10800 }
        ]
      },
      {
        "entity": {
          "id":   "uuid",
          "name": "Brand Awareness Q2"
        },
        "series": [
          { "date": "2026-05-01", "spend": 15.10, "impressions": 6500 }
        ],
        "previous_series": []
      }
    ]
  }
}
```

> The frontend decides whether to render this as stacked bars or individual lines.
> `previous_series` per entity is present only when `compare_previous=true`; it is `[]` for entities with no prior-period data (e.g. campaigns that launched after the prior window).

---

### 6.10 Table Metrics

Tabular view of campaigns / ad groups / ads with their performance metrics. Powers the Table dashboard view.

#### `GET /api/v1/insights/table`

**Query params:** `account_id` (required), `date_preset` or `date_start`+`date_end`, `level`, `campaign_id`, `adgroup_id`, `status`, `search`, `sort_by`, `sort_order`, `page`, `per_page`

**Additional params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `level` | string | `campaign` | `campaign` \| `adgroup` \| `ad` |
| `search` | string | — | Filter rows by name (case-insensitive substring) |
| `compare_previous` | boolean | `false` | When `true`, each row also carries `metrics_previous` (prior-period values, same key set as `metrics`) for period-over-period delta pills |

**Response `200`**
```json
{
  "data": [
    {
      "id":               "uuid",
      "name":             "Summer Sale Campaign",
      "status":           "active",
      "effective_status": "active",
      "objective":        "sales",
      "platform":         "meta",
      "daily_budget":     50.00,
      "metrics": {
        "spend":            780.00,
        "impressions":      310000,
        "reach":            145000,
        "frequency":        2.14,
        "clicks":           5800,
        "inline_link_clicks": 4900,
        "ctr":              1.87,
        "cpm":              2.52,
        "cpc":              0.13,
        "cpp":              5.38,
        "conversions":      150,
        "conversion_value": 5460.00,
        "roas":             7.00,
        "cpa":              5.20
      },
      "period": {
        "date_start": "2026-05-01",
        "date_stop":  "2026-05-30"
      }
    }
  ],
  "pagination": {
    "total":       14,
    "page":         1,
    "per_page":    25,
    "total_pages":  1
  },
  "meta": {
    "cached":    true,
    "cached_at": "2026-05-30T11:45:00Z"
  }
}
```

**Ad-level rows** additionally include a `creative_preview` object (thumbnail + title) to give the table a visual column without a separate creative fetch:
```json
{
  "id": "uuid",
  "name": "Summer Ad — Image v1",
  "status": "active",
  "creative_preview": {
    "title":         "Shop Summer Deals",
    "thumbnail_url": "https://scontent.facebook.com/...",
    "format":        "image",
    "cta_type":      "shop_now"
  },
  "metrics": { "..." : "..." }
}
```

**`compare_previous=true`** — each row additionally carries `metrics_previous`, the same key set as `metrics` aggregated over the prior period (see *Prior-period resolution* in §6.8). Entities absent from the prior window (e.g. launched after it) get a `metrics_previous` dict of nulls rather than being omitted. Prior-period metrics reuse the same aggregate-then-ratio SQL/finalize path as the current period (ratios computed after aggregation). The Ads dashboard view drives its per-ad-card delta pills off this via `level=ad`:
```json
{
  "id": "uuid",
  "name": "Summer Sale Campaign",
  "metrics":          { "spend": 780.00, "roas": 7.00, "..." : "..." },
  "metrics_previous": { "spend": 690.00, "roas": 6.80, "..." : "..." }
}
```

---

### 6.11 Breakdown

Metrics split by a demographic or placement dimension. Powers breakdown charts in the Periodic and Table views.

#### `GET /api/v1/insights/breakdown`

**Query params:** `account_id` (required), `date_preset` or `date_start`+`date_end`, `level`, `campaign_id`, `adgroup_id`, `breakdown`

**Additional params:**

| Param | Type | Required | Description |
|---|---|---|---|
| `breakdown` | string | ✅ | One of: `age_gender` \| `country` \| `platform_position` \| `device` |
| `level` | string | ❌ | `account` \| `campaign` \| `adgroup`. Default: `account` |

**Response `200`**
```json
{
  "data": {
    "breakdown": "age_gender",
    "level":     "account",
    "period": {
      "date_start": "2026-05-01",
      "date_stop":  "2026-05-30"
    },
    "rows": [
      {
        "breakdown_value": "25-34__female",
        "dimensions": {
          "age":    "25-34",
          "gender": "female"
        },
        "metrics": {
          "impressions": 82000,
          "clicks":      1540,
          "spend":       210.00,
          "ctr":         1.88,
          "cpm":         2.56,
          "cpc":         0.14
        }
      },
      {
        "breakdown_value": "25-34__male",
        "dimensions": {
          "age":    "25-34",
          "gender": "male"
        },
        "metrics": {
          "impressions": 71000,
          "clicks":      1230,
          "spend":       185.00,
          "ctr":         1.73,
          "cpm":         2.61,
          "cpc":         0.15
        }
      }
    ]
  },
  "meta": {
    "cached":    true,
    "cached_at": "2026-05-30T11:45:00Z"
  }
}
```

**Platform/placement breakdown** (`breakdown=platform_position`) example rows:
```json
{
  "breakdown_value": "instagram__story",
  "dimensions": {
    "publisher_platform": "instagram",
    "platform_position":  "story"
  },
  "metrics": { "..." : "..." }
}
```

> Breakdown data may not be available if the sync hasn't run for this dimension yet. In that case, return `503` with `meta.status = "sync_pending"` — the frontend can show a "loading" state and poll.

---

### 6.12 Combined Dashboard (Cross-Platform)

The combined endpoints aggregate metrics across a user-selected set of accounts from any platform. They are used by the `/dashboard` page.

**Currency rule:** if every selected account shares one currency, monetary metrics (spend, cpm, cpc, roas, cpa) are summed. If currencies differ, the backend returns `combined: false, currency_mismatch: true` and only per-account rows — the frontend degrades to a side-by-side view.

**Combinable metrics:** spend, impressions, reach, frequency, clicks, ctr, cpm, cpc (and conversions count where available). ROAS is recomputed at the aggregate level (`SUM(conv_value)/SUM(spend)`), never averaged. `conversions`/`roas` are currently tagged Meta-only in the metric registry — TikTok conversions use a different storage field and would undercount if naively combined.

#### `GET /api/v1/insights/combined`

Returns combined KPI summary + per-account breakdown + period-over-period deltas.

**Query params**

| Param | Type | Required | Description |
|---|---|---|---|
| `account_ids` | string | — | Comma-separated account UUIDs (all must belong to the caller's org). **Empty/omitted = all org accounts** — lets the dashboard send "All accounts" without enumerating ids client-side. |
| `date_preset` | string | ✓† | One of the standard presets |
| `date_start` | date | ✓† | YYYY-MM-DD (custom range) |
| `date_end` | date | ✓† | YYYY-MM-DD (custom range) |

† Either `date_preset` or both `date_start`+`date_end` required.

When `account_ids` is empty the backend resolves the org's account ids via `get_org_account_ids` (already org-scoped); explicit ids are still validated per-id. Applies to both `combined` and `combined-timeseries`.

**Response — single currency**

```json
{
  "data": {
    "combined": true,
    "currency_mismatch": false,
    "currency": "IDR",
    "currencies": ["IDR"],
    "period": { "date_start": "2026-05-01", "date_stop": "2026-05-31", "preset": "last_30d" },
    "summary": {
      "spend": 12500000,
      "impressions": 450000,
      "reach": 210000,
      "frequency": 2.14,
      "clicks": 9800,
      "ctr": 2.18,
      "cpm": 27.78,
      "cpc": 1275,
      "conversions": 340,
      "conversion_value": 48000000,
      "roas": 3.84,
      "cpa": 36765
    },
    "vs_previous": {
      "spend": 4.2,
      "impressions": -1.1,
      "clicks": 7.8,
      "ctr": 0.3,
      "conversions": 12.5,
      "roas": 8.1
    },
    "per_account": [
      {
        "account_id": "uuid",
        "name": "Npure X Shopee",
        "platform": "meta",
        "currency": "IDR",
        "summary": { "spend": 8000000, "impressions": 300000 }
      }
    ],
    "account_count": 5
  },
  "meta": { "cached": true, "cached_at": "2026-06-04T17:23:54Z" }
}
```

**Response — mixed currencies** (`combined: false, currency_mismatch: true`)

```json
{
  "data": {
    "combined": false,
    "currency_mismatch": true,
    "currency": null,
    "currencies": ["IDR", "USD"],
    "period": { ... },
    "summary": {},
    "vs_previous": {},
    "per_account": [ ... ],
    "account_count": 3
  }
}
```

`vs_previous` percentage changes follow the *Prior-period resolution* rule in §6.8.

`meta.cached_at` = the latest `fetched_at` across all included accounts. Never `now()`.

---

#### `GET /api/v1/insights/combined-timeseries`

Daily (or weekly/monthly) trend series aggregated across all selected accounts. Same currency rule applies — monetary metrics are `null` in each series point when `currency_mismatch: true`.

**Query params:** same as `combined` + `time_increment` (`day` | `week` | `month`, default `day`)

**Response**

```json
{
  "data": {
    "combined": true,
    "currency_mismatch": false,
    "currency": "IDR",
    "currencies": ["IDR"],
    "period": { ... },
    "series": [
      {
        "date": "2026-05-01",
        "spend": 400000,
        "impressions": 14500,
        "reach": 7200,
        "clicks": 320,
        "ctr": 2.21,
        "cpm": 27.59,
        "cpc": 1250,
        "conversions": 11,
        "roas": 3.7
      }
    ]
  }
}
```

---

### 6.13 Engagement (TikTok)

TikTok-specific social engagement metrics (likes, comments, shares) aggregated from `metric_action_stats`. Used by the `/tiktok/engagement` curated view.

#### `GET /api/v1/insights/engagement`

**Query params:** `account_id` (required) + date params (preset or custom range).

**Response**

```json
{
  "data": {
    "period": { "date_start": "2026-05-01", "date_stop": "2026-05-31", "preset": "last_30d" },
    "summary": {
      "likes": 6843,
      "comments": 11279,
      "shares": 330,
      "total_engagements": 18452,
      "impressions": 450000,
      "engagement_rate": 4.1004
    },
    "series": [
      { "date": "2026-05-01", "engagements": 612 },
      { "date": "2026-05-02", "engagements": 580 }
    ]
  },
  "meta": { "cached": true, "cached_at": "2026-06-04T17:23:54Z" }
}
```

`engagement_rate` = `total_engagements / impressions × 100`. `null` when no impressions.
`series` aggregates all three action types (like + comment + share) per day.

---

### 6.14 Sync Status

#### `GET /api/v1/sync/status`

Returns current sync state for an account — used by the dashboard to show "Last updated" and staleness warnings.

**Query params:** `account_id` (required)

**Response `200`**
```json
{
  "data": {
    "account_id": "uuid",
    "jobs": {
      "structure": {
        "status":       "completed",
        "last_run_at":  "2026-05-30T11:30:00Z",
        "next_run_at":  "2026-05-30T12:00:00Z",
        "is_stale":     false
      },
      "insights_daily": {
        "status":       "completed",
        "last_run_at":  "2026-05-30T11:45:00Z",
        "next_run_at":  "2026-05-30T12:00:00Z",
        "is_stale":     false
      },
      "insights_async": {
        "status":       "running",
        "last_run_at":  "2026-05-30T06:00:00Z",
        "next_run_at":  "2026-05-30T12:00:00Z",
        "is_stale":     false,
        "percent_complete": 72
      }
    },
    "rate_limit": {
      "insights_app_pct":  45,
      "insights_acc_pct":  12,
      "structure_acc_pct": 8,
      "access_tier":       "standard_access"
    },
    "has_warning": false
  }
}
```

`has_warning: true` when any job is `failed` or `is_stale: true`. The frontend can use this as a simple boolean to show/hide a staleness banner.

#### `POST /api/v1/sync/trigger`

Manually trigger a sync for an account. Useful for "Refresh" button in the UI.

**Request body**
```json
{
  "account_id": "uuid",
  "job_types": ["structure", "insights_daily"]
}
```

**Response `202`**
```json
{
  "data": {
    "message": "Sync jobs queued",
    "job_ids": ["uuid1", "uuid2"]
  }
}
```

> This endpoint enqueues Celery tasks and returns immediately — it does not wait for completion. The frontend should poll `GET /sync/status` to track progress.

---

## 7. Metric Field Names

Standard metric keys used in `metrics` objects across all endpoints.

| Key | Description |
|---|---|
| `spend` | Total spend in account currency |
| `impressions` | Total impressions |
| `reach` | Unique people reached |
| `frequency` | Avg impressions per person |
| `clicks` | All clicks |
| `inline_link_clicks` | Link clicks (destination URL) |
| `unique_clicks` | Unique people who clicked |
| `ctr` | Click-through rate (%) |
| `inline_link_click_ctr` | CTR for link clicks only (%) |
| `cpm` | Cost per 1,000 impressions |
| `cpc` | Cost per click |
| `cpp` | Cost per 1,000 people reached |
| `conversions` | Primary conversion count (from `account_configs`) |
| `conversion_value` | Revenue from primary conversion |
| `roas` | Return on ad spend (conversion_value ÷ spend) |
| `cpa` | Cost per primary conversion (spend ÷ conversions) |
| `video_plays` | Video starts |
| `video_p25` | Reached 25% of video |
| `video_p50` | Reached 50% of video |
| `video_p75` | Reached 75% of video |
| `video_p100` | Completed video |
| `video_thruplay` | ThruPlay completions |
| `video_avg_watch_time_ms` | Average watch time in milliseconds |

---

## 8. Enum Reference

### `status`
`active` · `paused` · `deleted` · `archived`

### `level`
`account` · `campaign` · `adgroup` · `ad`

### `platform`
`meta` · `google_ads` · `tiktok` · `google_analytics`

### `breakdown`
`age_gender` · `country` · `platform_position` · `device`

### `objective`
`awareness` · `traffic` · `engagement` · `leads` · `app_promotion` · `sales`

### `format` (creative)
`image` · `video` · `carousel` · `collection` · `instant_experience` · `text`

### `cta_type` (creative)
`shop_now` · `learn_more` · `sign_up` · `book_now` · `download` · `contact_us` · `get_quote` · `subscribe` · `watch_more`

### `time_increment`
`day` · `week` · `month`

### `job_type` (sync)
`structure` · `insights_daily` · `insights_async` · `creatives` · `breakdown`

### `job_status` (sync)
`pending` · `running` · `completed` · `failed` · `skipped`

`skipped` — task hit a hard rate limit mid-execution; job is marked skipped, connection paused, task rescheduled automatically. Distinct from `failed` (which is a permanent or max-retry-exhausted error). A skipped job will retry once the connection pause expires.
