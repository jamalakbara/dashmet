# Meta Ad Account Types — Standard vs CPAS

> **Relevance:** Understanding which account type you're working with affects how you
> fetch data, what metrics are available, and how your dashboard should handle each case.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Standard Ad Account](#2-standard-ad-account)
3. [CPAS — Collaborative Performance Advertising Solution](#3-cpas--collaborative-performance-advertising-solution)
4. [Side-by-Side Comparison](#4-side-by-side-comparison)
5. [How Each Works (Flow Diagrams)](#5-how-each-works-flow-diagrams)
6. [API Differences](#6-api-differences)
7. [Metrics Availability by Account Type](#7-metrics-availability-by-account-type)
8. [Dashboard Handling Guide](#8-dashboard-handling-guide)
9. [Common Dashboard Insights by Account Type](#9-common-dashboard-insights-by-account-type)

---

## 1. Overview

Meta has two fundamentally different ad account models. The difference lies in **who owns the catalog**, **who owns the pixel/conversion data**, and **how attribution flows**.

```
Standard  →  Brand runs ads → Brand's own website → Brand owns all data
CPAS      →  Brand runs ads → Retailer's website  → Retailer owns conversion data
```

CPAS is especially common in **Southeast Asia** — used heavily with marketplace platforms like:
- 🛍️ Lazada (Alibaba Group)
- 🛍️ Shopee (Sea Group)
- 🛍️ Tokopedia / TikTok Shop
- 🛍️ Zalora
- 🛍️ JD.ID

---

## 2. Standard Ad Account

### What it is

A regular Meta ad account where a business runs ads that link directly to **their own website or app**. The business controls everything end-to-end.

### Key Characteristics

| Property | Value |
|---|---|
| Catalog ownership | The advertiser (brand) |
| Pixel / CAPI | The advertiser |
| Landing page | Brand's own website or app |
| Conversion data | Flows directly to the brand's ad account |
| Attribution | Fully visible in brand's account |
| Data sharing | Not required |
| Setup complexity | Low |

### Who uses it

Any business advertising directly to consumers — retailers, apps, service businesses, direct-to-consumer (DTC) brands, and more.

### How it works

```
┌────────────────┐     run ads      ┌─────────────────────┐
│   Brand /      │ ───────────────▶ │   Meta Ads Platform  │
│   Advertiser   │                  └────────┬────────────┘
│                │                           │ serves ad
│  owns:         │                           ▼
│  - Catalog     │                  ┌─────────────────────┐
│  - Pixel       │                  │   User sees ad       │
│  - Budget      │                  └────────┬────────────┘
│  - Ad Account  │                           │ clicks
└────────────────┘                           ▼
        ▲                           ┌─────────────────────┐
        │ conversion data           │  Brand's website     │
        │ (purchase, lead, etc.)    │  (pixel fires here)  │
        └───────────────────────────└─────────────────────┘
```

### API Access

Full access — no restrictions. All metrics, all endpoints, full conversion/ROAS data flows into the ad account.

---

## 3. CPAS — Collaborative Performance Advertising Solution

### What it is

A partnership model where a **brand** runs ads but the destination is the **retailer's product page** (e.g., the brand's store on Lazada or Shopee). The retailer shares their product catalog with the brand so the brand can advertise those products.

> Think of it as: the brand pays for the ads, the retailer provides the storefront.

### Key Characteristics

| Property | Value |
|---|---|
| Catalog ownership | The **retailer** (shared to brand) |
| Pixel / CAPI | The **retailer** |
| Landing page | Retailer's platform (e.g., Lazada product page) |
| Conversion data | Stays with the **retailer** — partially shared back |
| Attribution | Limited visibility from the brand's side |
| Data sharing | Required — retailer must grant catalog access |
| Setup complexity | Higher — requires partnership setup in Business Manager |

### Who uses it

Consumer goods brands, FMCG companies, fashion brands — any brand that sells through third-party marketplaces and wants to run paid ads driving traffic to their products on that marketplace.

**Examples:**
- Unilever runs Meta ads → user clicks → lands on Unilever's Shopee store
- Samsung runs Meta ads → user clicks → lands on Samsung's Lazada page
- L'Oréal runs Meta ads → user clicks → lands on L'Oréal's Tokopedia store

### How it works

```
┌────────────────┐   1. Retailer shares catalog   ┌─────────────────┐
│    Retailer    │ ────────────────────────────▶  │  Brand /        │
│  (Lazada,      │                                 │  Advertiser     │
│   Shopee, etc.)│ ◀──────────────────────────── │                  │
│                │   4. Partial conversion data    │  owns:          │
│  owns:         │      shared back                │  - Budget       │
│  - Catalog     │                                 │  - Ad Account   │
│  - Pixel       │                                 │  - Creatives    │
│  - Store page  │                                 └────────┬────────┘
└────────────────┘                                          │
                                                    2. Brand runs ad
                                                           ▼
                                                  ┌─────────────────┐
                                                  │  Meta Ads       │
                                                  │  Platform       │
                                                  └────────┬────────┘
                                                           │ 3. User clicks
                                                           ▼
                                                  ┌─────────────────┐
                                                  │ Retailer's page │
                                                  │ (Lazada/Shopee) │
                                                  │ Pixel fires     │
                                                  │ here (retailer) │
                                                  └─────────────────┘
```

### Setup Requirements

1. **Retailer** creates a Collaborative Ads partnership in Meta Business Manager
2. **Retailer** shares a catalog segment with the brand's Business Manager
3. **Brand** accepts the catalog share and uses it to create ads
4. **Brand** cannot directly access full sales data — the retailer controls what is shared

### API Access — Catalog

The brand receives a **shared catalog segment**, not the full catalog.

```http
GET /v25.0/act_{BRAND_AD_ACCOUNT_ID}/product_audiences
GET /v25.0/{SHARED_CATALOG_SEGMENT_ID}/products
```

The brand can only query the specific segment shared by the retailer, not the retailer's full catalog.

---

## 4. Side-by-Side Comparison

| Dimension | Standard | CPAS |
|---|---|---|
| **Who runs the ads** | Brand | Brand |
| **Who owns the catalog** | Brand | Retailer (shared to brand) |
| **Landing page** | Brand's own website/app | Retailer's platform page |
| **Pixel owner** | Brand | Retailer |
| **CAPI owner** | Brand | Retailer |
| **Purchase data visibility** | Full | Partial (retailer-controlled) |
| **ROAS visibility** | Full | Partial / limited |
| **Conversion attribution** | Full (in brand account) | Partial (retailer shares subset) |
| **Catalog management** | Brand manages | Retailer manages, brand uses |
| **Catalog segment** | Full catalog | Only shared segment |
| **Business Manager setup** | Standard | Requires Collaborative Ads partnership |
| **Permission level needed** | `ads_read`, `read_insights` | `ads_read`, `read_insights` + catalog share accepted |
| **API endpoint scope** | Full | Limited by shared catalog segment |
| **Primary market** | Global | Especially strong in SEA (Southeast Asia) |
| **Common use case** | DTC, e-commerce, apps, leads | Brands selling via marketplaces |

---

## 5. How Each Works (Flow Diagrams)

### Standard — Data Flow

```
Brand Ad Account
│
├── Campaigns
│   └── Ad Sets → targeting your own audiences
│       └── Ads → link to brand.com
│
├── Pixel (brand.com/pixel.js)
│   └── fires on: PageView, AddToCart, Purchase
│
└── Insights (full data)
    ├── impressions, clicks, spend
    ├── purchase_roas         ✅ full
    ├── conversions           ✅ full
    └── action_values         ✅ full
```

### CPAS — Data Flow

```
Brand Ad Account
│
├── Campaigns
│   └── Ad Sets → targeting retailer's audiences (shared)
│       └── Ads → link to lazada.com/brand-store
│
├── Shared Catalog Segment (from retailer)
│   └── read-only — brand cannot modify
│
└── Insights (partial data)
    ├── impressions, clicks, spend  ✅ full
    ├── purchase_roas               ⚠️ partial — retailer controls
    ├── conversions                 ⚠️ partial — retailer must share
    └── action_values               ⚠️ partial — retailer controls
```

---

## 6. API Differences

### Authentication & Permissions

Both account types use the same auth method. No difference in token type or permission scope required. The difference is in **what data is accessible**, not how you authenticate.

```
Standard:  ads_read + read_insights → full data
CPAS:      ads_read + read_insights → same call, but conversion data may be empty/partial
```

### Fetching Campaigns & Ads

The API calls are **identical** for both account types:

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/campaigns
  ?fields=id,name,status,objective
  &access_token=<TOKEN>

GET /v25.0/act_{AD_ACCOUNT_ID}/ads
  ?fields=id,name,creative{id,title,body,image_url}
  &access_token=<TOKEN>
```

### Fetching Insights

The API call is the same — but the **response content differs**:

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/insights
  ?fields=impressions,reach,clicks,spend,purchase_roas,actions,action_values
  &date_preset=last_30d
  &access_token=<TOKEN>
```

**Standard response:**

```json
{
  "data": [{
    "impressions": "45000",
    "reach": "18000",
    "clicks": "1200",
    "spend": "850.00",
    "purchase_roas": [{ "action_type": "omni_purchase", "value": "3.85" }],
    "actions": [
      { "action_type": "purchase", "value": "42" },
      { "action_type": "link_click", "value": "1100" }
    ],
    "action_values": [{ "action_type": "purchase", "value": "3272.50" }]
  }]
}
```

**CPAS response (typical):**

```json
{
  "data": [{
    "impressions": "45000",
    "reach": "18000",
    "clicks": "1200",
    "spend": "850.00",
    "purchase_roas": [],
    "actions": [
      { "action_type": "link_click", "value": "1100" }
    ],
    "action_values": []
  }]
}
```

> `purchase_roas` and `action_values` return **empty** or missing in CPAS because the
> pixel (on Lazada/Shopee) belongs to the retailer, not the brand. The brand only sees
> what the retailer explicitly shares back.

### Catalog Access

**Standard:**

```http
GET /v25.0/act_{AD_ACCOUNT_ID}/product_audiences
GET /v25.0/{CATALOG_ID}/products
```
Full access — brand owns the catalog.

**CPAS:**

```http
GET /v25.0/{SHARED_CATALOG_SEGMENT_ID}/products
```
Read-only, scoped to the segment the retailer shared. Brand cannot add, edit, or delete products.

### Identifying Account Type Programmatically

There is no single API field that says "this is a CPAS account." You can infer it by checking:

1. **Catalog segment source** — if the product catalog is owned by another Business Manager, it is CPAS
2. **Empty ROAS/conversion data** despite active spend — strong CPAS signal
3. **Landing URLs in creatives** — if they point to marketplace domains (`lazada.com`, `shopee.com`, `tokopedia.com`), it's CPAS

```http
GET /v25.0/{CATALOG_ID}
  ?fields=id,name,business,product_count
  &access_token=<TOKEN>
```

If `business.id` in the catalog response does not match your brand's Business Manager ID, the catalog is shared — likely CPAS.

---

## 7. Metrics Availability by Account Type

| Metric | Standard | CPAS | Notes |
|---|---|---|---|
| `impressions` | ✅ Full | ✅ Full | Always available |
| `reach` | ✅ Full | ✅ Full | Always available |
| `frequency` | ✅ Full | ✅ Full | Always available |
| `clicks` | ✅ Full | ✅ Full | Always available |
| `spend` | ✅ Full | ✅ Full | Always available |
| `ctr` | ✅ Full | ✅ Full | Always available |
| `cpm` | ✅ Full | ✅ Full | Always available |
| `cpc` | ✅ Full | ✅ Full | Always available |
| `link_click` (in actions) | ✅ Full | ✅ Full | Traffic to retailer page |
| `outbound_clicks` | ✅ Full | ✅ Full | Clicks leaving Meta |
| `purchase` (in actions) | ✅ Full | ⚠️ Partial | Depends on retailer sharing |
| `purchase_roas` | ✅ Full | ⚠️ Partial | Often empty in CPAS |
| `action_values` | ✅ Full | ⚠️ Partial | Revenue data — retailer-controlled |
| `cost_per_conversion` | ✅ Full | ⚠️ Partial | Only if conversion data shared |
| `conversions` | ✅ Full | ⚠️ Partial | Retailer must share |
| `lead` (in actions) | ✅ Full | ❌ N/A | Not applicable to CPAS |
| `add_to_cart` | ✅ Full | ⚠️ Partial | If retailer pixel fires it |
| `video_*` metrics | ✅ Full | ✅ Full | Creative-level, not conversion |
| `canvas_avg_view_*` | ✅ Full | ✅ Full | Creative-level |
| `catalog_segment_*` | ✅ Full | ✅ Available | Product-level data from segment |
| `converted_product_*` | ✅ Full | ⚠️ Partial | If retailer shares product data |

**Legend:**
- ✅ Full — always returns data
- ⚠️ Partial — depends on retailer sharing agreement
- ❌ N/A — not applicable to this account type

---

## 8. Dashboard Handling Guide

Since both account types use the same API, your dashboard needs to handle both gracefully.

### DashMet Implementation

`account_type` is **stored, not auto-detected** — it's a column on `accounts` (`'standard' | 'cpas'`, default `'standard'`) set manually per account.

- **Where it's set:** Settings → Accounts (`/settings/accounts`). Each Meta account row has a Standard/CPAS dropdown.
- **Meta-only by design:** CPAS is a Meta concept. Non-Meta (e.g. TikTok) accounts show no selector — just a muted `—` — and the API **rejects** `account_type='cpas'` when `platform != 'meta'` with `409 CONFLICT` ("CPAS account type is only available for Meta accounts"). Guard lives in `update_account_config` (`backend/app/services/accounts.py`).
- **How it's consumed:** the stored `account_type` drives platform/account-type-aware metric sets (`use-platform-metrics.ts` on the frontend) — CPAS hides ROAS/conversion metrics per the rules below.

The `detectAccountType()` heuristic below is a fallback/reference only; DashMet trusts the stored value.

### Detecting Account Type

```javascript
function detectAccountType(insights) {
  const hasPurchaseRoas = insights.purchase_roas?.length > 0;
  const hasActionValues = insights.action_values?.length > 0;
  const hasPurchaseActions = insights.actions?.some(
    a => a.action_type === 'purchase'
  );

  if (!hasPurchaseRoas && !hasActionValues && !hasPurchaseActions) {
    return 'cpas_or_awareness'; // likely CPAS or non-conversion objective
  }
  return 'standard';
}
```

### Conditional Metric Display

```javascript
function buildDashboardMetrics(insights, accountType) {
  // Always show — available for both account types
  const base = {
    impressions:  insights.impressions,
    reach:        insights.reach,
    frequency:    insights.frequency,
    clicks:       insights.clicks,
    spend:        insights.spend,
    ctr:          insights.ctr,
    cpm:          insights.cpm,
    cpc:          insights.cpc,
  };

  // Only show for Standard accounts (or when data is present)
  const conversionMetrics = {
    roas:         insights.purchase_roas?.[0]?.value ?? null,
    revenue:      insights.action_values?.[0]?.value ?? null,
    purchases:    insights.actions?.find(a => a.action_type === 'purchase')?.value ?? null,
    costPerPurch: insights.cost_per_action_type?.find(a => a.action_type === 'purchase')?.value ?? null,
  };

  if (accountType === 'cpas') {
    // Show traffic metrics instead of conversion metrics
    return {
      ...base,
      outboundClicks: insights.outbound_clicks?.[0]?.value ?? null,
      costPerClick:   insights.cost_per_outbound_click?.[0]?.value ?? null,
      // ROAS/purchase fields shown with a "Not available" notice
      roas:     null,
      revenue:  null,
    };
  }

  return { ...base, ...conversionMetrics };
}
```

### UI Recommendations

**For Standard accounts** — show the full dashboard with ROAS and conversion panels.

**For CPAS accounts** — adapt the dashboard:

| Panel | Standard | CPAS |
|---|---|---|
| Overview | Spend, Reach, ROAS, CPA | Spend, Reach, CTR, CPC |
| Performance | Conversions, Revenue, ROAS | Clicks, Outbound Clicks, CPM |
| ROAS widget | Show value | Show "Data owned by retailer" |
| Conversion funnel | Full funnel | Traffic metrics only |
| Creative analysis | CTR + ROAS per ad | CTR + CPC per ad |

**Example UI message for CPAS:**

```
ℹ️  Conversion data (ROAS, purchases, revenue) for this account is
    managed by the retailer and may not be available here.
    Contact your retail partner for full performance reporting.
```

### Summary

```
If account type = Standard:
  → Show full dashboard: Spend, Reach, CTR, CPM, ROAS, Conversions, Revenue

If account type = CPAS:
  → Show traffic dashboard: Spend, Reach, Clicks, CTR, CPM, CPC, Outbound Clicks
  → Hide or grey out: ROAS, Purchases, Revenue, CPA
  → Add notice explaining that conversion data belongs to the retailer
```

---

## 9. Common Dashboard Insights by Account Type

This section defines exactly which metrics each dashboard panel should show,
split by account type. Use this as the blueprint when building your dashboard UI.

---

### 9.1 Standard Account — Full Dashboard

#### Panel 1 — Overview / KPI Cards

These are the top-level numbers shown at a glance, typically as big number cards.

| Metric | Field | Why |
|---|---|---|
| Total Spend | `spend` | Primary budget tracker |
| Impressions | `impressions` | Scale of delivery |
| Reach | `reach` | Unique audience size |
| Frequency | `frequency` | Audience saturation signal — alert if > 3.5 |
| Clicks | `clicks` | Total interactions |
| CTR | `ctr` | Creative relevance |
| CPM | `cpm` | Auction cost efficiency |
| Results | `actions` → objective action | The actual goal (purchase, lead, etc.) |
| CPA | `cost_per_action_type` | Cost per result |
| ROAS | `purchase_roas` | Revenue per $1 spent — the #1 e-commerce metric |

```http
fields=impressions,reach,frequency,clicks,spend,ctr,cpm,
       actions,cost_per_action_type,purchase_roas
&date_preset=last_30d
&level=account
```

---

#### Panel 2 — Campaign Performance Table

A sortable table showing every campaign and its core metrics.

| Metric | Field |
|---|---|
| Campaign Name | `campaign_name` |
| Status | *(from campaigns endpoint, not insights)* |
| Spend | `spend` |
| Impressions | `impressions` |
| Reach | `reach` |
| Frequency | `frequency` |
| Clicks | `clicks` |
| CTR | `ctr` |
| CPM | `cpm` |
| Results | `actions` (objective action type) |
| CPA | `cost_per_action_type` |
| ROAS | `purchase_roas` |

```http
fields=campaign_id,campaign_name,impressions,reach,frequency,
       clicks,spend,ctr,cpm,actions,cost_per_action_type,purchase_roas
&level=campaign
&date_preset=last_30d
```

---

#### Panel 3 — Ad Set Performance Table

Drill-down into audience and budget efficiency.

| Metric | Field |
|---|---|
| Ad Set Name | `adset_name` |
| Campaign | `campaign_name` |
| Spend | `spend` |
| Reach | `reach` |
| Frequency | `frequency` |
| CPM | `cpm` |
| CTR | `ctr` |
| Results | `actions` |
| CPA | `cost_per_action_type` |
| ROAS | `purchase_roas` |

```http
fields=adset_id,adset_name,campaign_id,campaign_name,
       impressions,reach,frequency,clicks,spend,ctr,cpm,
       actions,cost_per_action_type,purchase_roas
&level=adset
&date_preset=last_30d
```

---

#### Panel 4 — Ad (Creative) Performance Table

Shows which individual ads perform best — the most actionable view for creative decisions.

| Metric | Field |
|---|---|
| Ad Name | `ad_name` |
| Ad Set | `adset_name` |
| Impressions | `impressions` |
| Reach | `reach` |
| Frequency | `frequency` |
| CTR | `ctr` |
| CPM | `cpm` |
| CPC | `cpc` |
| Spend | `spend` |
| Results | `actions` |
| CPA | `cost_per_action_type` |
| ROAS | `purchase_roas` |

```http
fields=ad_id,ad_name,adset_id,adset_name,campaign_id,
       impressions,reach,frequency,clicks,ctr,cpm,cpc,spend,
       actions,cost_per_action_type,purchase_roas
&level=ad
&date_preset=last_30d
```

---

#### Panel 5 — Daily Trend Chart (Time Series)

Line/bar chart showing performance over time.

| Metric | Field |
|---|---|
| Daily Spend | `spend` |
| Daily Impressions | `impressions` |
| Daily Reach | `reach` |
| Daily Clicks | `clicks` |
| Daily Results | `actions` |
| Daily ROAS | `purchase_roas` |

```http
fields=impressions,reach,clicks,spend,actions,purchase_roas
&time_increment=1
&date_preset=last_30d
&level=account
```

---

#### Panel 6 — Conversion Funnel

Shows the path from impression to purchase.

| Stage | Metric | Field |
|---|---|---|
| Delivered | Impressions | `impressions` |
| Seen by unique | Reach | `reach` |
| Clicked | Link Clicks | `actions` → `link_click` |
| Added to cart | Add to Cart | `actions` → `add_to_cart` |
| Initiated checkout | Checkout Started | `actions` → `initiate_checkout` |
| Purchased | Purchases | `actions` → `purchase` |
| Revenue | Purchase Value | `action_values` → `purchase` |

```http
fields=impressions,reach,actions,action_values
&date_preset=last_30d
&level=account
```

Filter `actions` client-side for: `link_click`, `add_to_cart`, `initiate_checkout`, `purchase`.

---

#### Panel 7 — Demographic Breakdown

Audience performance split — helps identify best-converting segments.

| Dimension | Breakdown param | Metrics to show |
|---|---|---|
| Age + Gender | `breakdowns=age,gender` | impressions, clicks, spend, CTR, CPA |
| Country | `breakdowns=country` | impressions, reach, spend, CTR, CPA |
| Platform | `breakdowns=publisher_platform` | impressions, clicks, spend, CTR, CPM |
| Placement | `breakdowns=publisher_platform,platform_position` | impressions, spend, CTR, CPM |
| Device | `breakdowns=device_platform` | impressions, clicks, spend, CTR |

> Query each breakdown separately — do not combine more than 2 breakdowns per call.

---

#### Panel 8 — Video Performance (if applicable)

Only show when the account runs video ads.

| Metric | Field |
|---|---|
| Video Plays | `video_play_actions` |
| Avg Watch Time | `video_avg_time_watched_actions` |
| 2-sec Views | `video_continuous_2_sec_watched_actions` |
| 25% Watched | `video_p25_watched_actions` |
| 50% Watched | `video_p50_watched_actions` |
| 75% Watched | `video_p75_watched_actions` |
| 100% Watched | `video_p100_watched_actions` |
| ThruPlays | `video_thruplay_watched_actions` |
| Cost per ThruPlay | `cost_per_thruplay` |

```http
fields=ad_id,ad_name,impressions,spend,
       video_play_actions,video_avg_time_watched_actions,
       video_p25_watched_actions,video_p50_watched_actions,
       video_p75_watched_actions,video_p100_watched_actions,
       video_thruplay_watched_actions,cost_per_thruplay
&level=ad
&date_preset=last_30d
```

---

### 9.2 CPAS Account — Dashboard

Because CPAS accounts have limited conversion data (pixel belongs to retailer),
the dashboard focuses on **traffic and delivery quality** instead of ROAS and purchases.

---

#### Panel 1 — Overview / KPI Cards (CPAS)

| Metric | Field | Why |
|---|---|---|
| Total Spend | `spend` | Budget tracker |
| Impressions | `impressions` | Scale of delivery |
| Reach | `reach` | Unique audience size |
| Frequency | `frequency` | Saturation — alert if > 3.5 |
| Outbound Clicks | `outbound_clicks` | Clicks to retailer page — the key traffic metric |
| Outbound CTR | `outbound_clicks_ctr` | Quality of traffic sent to retailer |
| CPC (Outbound) | `cost_per_outbound_click` | Cost efficiency to drive traffic |
| CPM | `cpm` | Auction efficiency |
| *(ROAS)* | *Not available* | *Show "Retailer-managed" notice* |

```http
fields=impressions,reach,frequency,clicks,spend,ctr,cpm,
       outbound_clicks,outbound_clicks_ctr,cost_per_outbound_click
&date_preset=last_30d
&level=account
```

---

#### Panel 2 — Campaign Performance Table (CPAS)

| Metric | Field |
|---|---|
| Campaign Name | `campaign_name` |
| Spend | `spend` |
| Impressions | `impressions` |
| Reach | `reach` |
| Frequency | `frequency` |
| Outbound Clicks | `outbound_clicks` |
| Outbound CTR | `outbound_clicks_ctr` |
| Cost per Outbound Click | `cost_per_outbound_click` |
| CPM | `cpm` |
| Link Clicks | `actions` → `link_click` |

```http
fields=campaign_id,campaign_name,impressions,reach,frequency,
       clicks,spend,cpm,ctr,outbound_clicks,outbound_clicks_ctr,
       cost_per_outbound_click,actions
&level=campaign
&date_preset=last_30d
```

---

#### Panel 3 — Ad (Creative) Performance Table (CPAS)

| Metric | Field |
|---|---|
| Ad Name | `ad_name` |
| Impressions | `impressions` |
| Reach | `reach` |
| Frequency | `frequency` |
| CTR | `ctr` |
| CPM | `cpm` |
| CPC | `cpc` |
| Outbound Clicks | `outbound_clicks` |
| Cost per Outbound Click | `cost_per_outbound_click` |
| Spend | `spend` |

---

#### Panel 4 — Daily Trend Chart (CPAS)

| Metric | Field |
|---|---|
| Daily Spend | `spend` |
| Daily Impressions | `impressions` |
| Daily Reach | `reach` |
| Daily Outbound Clicks | `outbound_clicks` |
| Daily CPM | `cpm` |

```http
fields=impressions,reach,spend,cpm,outbound_clicks
&time_increment=1
&date_preset=last_30d
&level=account
```

---

#### Panel 5 — Demographic Breakdown (CPAS)

Same structure as Standard, but replace CPA/ROAS with outbound click metrics:

| Dimension | Metrics to show |
|---|---|
| Age + Gender | impressions, spend, CTR, outbound CTR, CPM |
| Country | impressions, reach, spend, outbound clicks |
| Platform | impressions, spend, CPM, outbound CTR |
| Placement | impressions, spend, CPM, outbound CTR |

---

### 9.3 Full Comparison — What Each Panel Shows

| Dashboard Panel | Standard | CPAS |
|---|---|---|
| **KPI Cards** | Spend, Reach, ROAS, CPA, CTR, CPM | Spend, Reach, Outbound Clicks, CPC, CTR, CPM |
| **Campaign Table** | Spend, ROAS, CPA, Conversions, CTR | Spend, Outbound Clicks, Outbound CTR, CPC, CPM |
| **Ad Set Table** | Spend, ROAS, CPA, Frequency, CTR | Spend, Outbound CTR, CPC, Frequency |
| **Ad / Creative Table** | CTR, ROAS, CPA, Frequency, Spend | CTR, Outbound CTR, CPC, Frequency, Spend |
| **Daily Trend** | Spend, ROAS, Impressions, Results | Spend, Impressions, Outbound Clicks |
| **Conversion Funnel** | Impression → Click → Cart → Checkout → Purchase | ❌ Not applicable |
| **Demographics** | CTR, CPA, ROAS per segment | CTR, Outbound CTR, CPM per segment |
| **Video Panel** | Full video retention metrics | Full video retention metrics (same) |
| **ROAS Widget** | ✅ Show with value | ⚠️ Show with "Retailer-managed" notice |
| **Purchase / Revenue** | ✅ Show | ❌ Hide or show notice |

---

### 9.4 Recommended Metrics Priority (Both Account Types)

When building the dashboard, implement in this priority order:

```
Priority 1 — Always show (both account types)
────────────────────────────────────────────
spend · impressions · reach · frequency · clicks · ctr · cpm · cpc

Priority 2 — Standard accounts
────────────────────────────────────────────
purchase_roas · actions (purchase, lead) · cost_per_action_type
action_values · conversions · cost_per_conversion

Priority 2 — CPAS accounts
────────────────────────────────────────────
outbound_clicks · outbound_clicks_ctr · cost_per_outbound_click

Priority 3 — Add when drilling into creatives
────────────────────────────────────────────
frequency (creative fatigue) · ad-level CTR · ad-level CPA/ROAS

Priority 4 — Add for video ads
────────────────────────────────────────────
video_p25/p50/p75/p100_watched_actions
video_thruplay_watched_actions · video_avg_time_watched_actions

Priority 5 — Add for demographic analysis
────────────────────────────────────────────
breakdowns: age+gender · country · publisher_platform · platform_position

Priority 6 — Advanced / on demand only
────────────────────────────────────────────
unique_clicks · unique_actions · auction_competitiveness
catalog_segment_* (CPAS product metrics, if retailer shares)
```

---

## References

- [Collaborative Ads Overview — Meta for Developers](https://developers.facebook.com/documentation/ads-commerce/marketing-api/collaborative-ads)
- [Managed Partner Ads — API Guide](https://developers.facebook.com/documentation/ads-commerce/marketing-api/collaborative-ads/managed-partner-ads/api-guide)
- [Partner Premium Options](https://developers.facebook.com/documentation/ads-commerce/marketing-api/collaborative-ads/partner-premium-options)
- [Catalog API — Meta for Developers](https://developers.facebook.com/documentation/ads-commerce/catalog)
