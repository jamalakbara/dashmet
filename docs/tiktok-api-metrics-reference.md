# TikTok Business API — Complete Metrics Reference

> **Endpoint:** `GET /open_api/v1.3/report/integrated/get/`
> **Version:** v1.3
> Metrics are passed as a JSON array in the `metrics` parameter.
> Not all metrics are available for all `report_type` + `data_level` combinations — see the availability column.

---

## Table of Contents

1. [Report Types Overview](#1-report-types-overview)
2. [Core Performance Metrics](#2-core-performance-metrics)
3. [Cost & Efficiency Metrics](#3-cost--efficiency-metrics)
4. [Video Play Metrics](#4-video-play-metrics)
5. [Engagement Metrics](#5-engagement-metrics)
6. [Conversion Metrics](#6-conversion-metrics)
7. [Real-Time Metrics](#7-real-time-metrics)
8. [Attribution Metrics (CTA / VTA)](#8-attribution-metrics-cta--vta)
9. [Website / Page Event Metrics](#9-website--page-event-metrics)
10. [App Event Metrics](#10-app-event-metrics)
11. [SKAN Metrics (iOS 14+)](#11-skan-metrics-ios-14)
12. [LIVE Metrics](#12-live-metrics)
13. [Reach & Frequency Metrics](#13-reach--frequency-metrics)
14. [Offline Metrics](#14-offline-metrics)
15. [Onsite / Shopping Metrics](#15-onsite--shopping-metrics)
16. [Interactive Add-on Metrics](#16-interactive-add-on-metrics)
17. [Focused View Metrics](#17-focused-view-metrics)
18. [Metrics Availability Matrix](#18-metrics-availability-matrix)
19. [Dashboard Recommended Metric Sets](#19-dashboard-recommended-metric-sets)

---

## 1. Report Types Overview

Before selecting metrics, choose the right `report_type`:

| `report_type` | Best For | Notes |
|---|---|---|
| `BASIC` | Broadest coverage — cost, clicks, video, conversions, app, website, LIVE, attribution | Default choice for most dashboards |
| `AUDIENCE` | Same core metrics as BASIC but broken down by audience segments (age, gender, country, device, placement) | Use when you need demographic breakdowns |
| `PLAYABLE_MATERIAL` | Playable ad creative performance | Niche — only for interactive/playable ad types |
| `REACH_FREQUENCY` | Reach, frequency, and unique event metrics with configurable time windows | Use for brand awareness reporting |

---

## 2. Core Performance Metrics

These are available across all report types and data levels.

| API Field Name | Display Name | Description |
|---|---|---|
| `spend` | Cost / Spend | Total amount of money spent on your ads (in account currency) |
| `impressions` | Impressions | Total number of times your ads were shown |
| `clicks` | Clicks (Destination) | Number of clicks leading to a specified destination (landing page, app store, etc.) |
| `clicks_all` | Clicks (All) | All clicks including social interactions (likes, shares, follows) |
| `reach` | Reach | Number of unique users who saw your ads at least once |
| `frequency` | Frequency | Average number of times each unique user saw your ad |
| `ctr` | CTR | Click-through rate — clicks ÷ impressions (%) |
| `cpc` | CPC | Cost per destination click |
| `cpm` | CPM | Cost per 1,000 impressions |

---

## 3. Cost & Efficiency Metrics

| API Field Name | Display Name | Description |
|---|---|---|
| `spend` | Total Cost | Total ad spend |
| `cpc` | CPC (Destination) | Average cost per destination click |
| `cpm` | CPM | Average cost per 1,000 impressions |
| `cost_per_1000_reached` | Cost per 1,000 Reached | Average spend to reach 1,000 unique users |
| `cost_per_conversion` | Cost per Conversion | Spend ÷ total conversions |
| `cost_per_result` | Cost per Result | Spend ÷ optimization results |
| `result` | Result | Number of times the optimization goal was achieved |
| `result_rate` | Result Rate | Percentage of impressions resulting in the goal (%) |
| `cost_cash` | Cost (Cash) | Ad spend charged by cash |
| `cost_voucher` | Cost (Voucher) | Ad spend charged by voucher/credit |

---

## 4. Video Play Metrics

Available for `BASIC` and `AUDIENCE` report types, at Ad and Ad Group levels.

| API Field Name | Display Name | Description |
|---|---|---|
| `video_play_actions` | Video Views | Total number of times the video was played |
| `video_watched_2s` | 2-Second Video Views | Plays lasting at least 2 seconds (replays not counted) |
| `video_watched_6s` | 6-Second Video Views | Plays lasting at least 6 seconds (replays not counted) |
| `video_views_p25` | Video Views at 25% | Users who watched at least 25% of the video |
| `video_views_p50` | Video Views at 50% | Users who watched at least 50% of the video |
| `video_views_p75` | Video Views at 75% | Users who watched at least 75% of the video |
| `video_views_p100` | Video Views at 100% | Users who watched the video to completion |
| `average_video_play` | Avg. Watch Time Per View | Average seconds watched per video play |
| `average_video_play_per_user` | Avg. Watch Time Per Person | Average seconds watched per unique user |

---

## 5. Engagement Metrics

| API Field Name | Display Name | Description |
|---|---|---|
| `engagements` | Paid Engagements | Total paid engagement actions on an ad (aggregate of likes, comments, shares, follows, etc.) |
| `likes` | Paid Likes | Number of likes on an ad during the impression |
| `comments` | Paid Comments | Number of comments on an ad |
| `shares` | Paid Shares | Number of shares on an ad |
| `follows` | Paid Followers | New followers gained from an ad |
| `profile_visits` | Paid Profile Visits | Number of profile visits from an ad |
| `music_plays` | Music Clicks | Number of music icon clicks (leads to TikTok music page) |
| `anchor_clicks` | Anchor Clicks | Number of clicks on the anchor (link sticker) |
| `duet_clicks` | Duet Clicks | Number of clicks on the Duet button |
| `stitch_clicks` | Stitch Clicks | Number of clicks on the Stitch button |
| `engagement_rate` | Engagement Rate | (Likes + Comments + Shares) ÷ Impressions (%) |

---

## 6. Conversion Metrics

| API Field Name | Display Name | Description |
|---|---|---|
| `conversion` | Conversions | Number of times the selected optimization event occurred |
| `conversion_rate` | Conversion Rate (CVR) | Conversions ÷ Impressions (%) |
| `conversion_rate_v2` | Conversion Rate (CVR, Clicks) | Conversions ÷ Destination Clicks (%) |
| `cost_per_conversion` | Cost per Conversion | Spend ÷ Conversions |
| `result` | Result | Goal-based optimization result count |
| `result_rate` | Result Rate (%) | Result ÷ Impressions |
| `cost_per_result` | Cost per Result | Spend ÷ Results |

---

## 7. Real-Time Metrics

Real-time metrics have lower reporting latency than standard metrics. Available in `BASIC` report.

| API Field Name | Display Name | Description |
|---|---|---|
| `real_time_conversion` | Real-Time Conversions | Conversions counted in near real-time |
| `real_time_conversion_rate` | Real-Time CVR | Real-time Conversions ÷ Impressions (%) |
| `real_time_conversion_rate_v2` | Real-Time CVR (Clicks) | Real-time Conversions ÷ Clicks (%) |
| `real_time_cost_per_conversion` | Real-Time Cost per Conversion | Spend ÷ Real-Time Conversions |
| `real_time_result` | Real-Time Result | Real-time optimization results |
| `real_time_result_rate` | Real-Time Result Rate (%) | Real-time result rate |
| `real_time_cost_per_result` | Real-Time Cost per Result | Spend ÷ Real-Time Results |
| `real_time_app_install` | Real-Time App Installs | App installs counted in near real-time |

---

## 8. Attribution Metrics (CTA / VTA)

Click-Through Attribution (CTA) and View-Through Attribution (VTA). Available in `BASIC` report.

| API Field Name | Display Name | Description |
|---|---|---|
| `total_purchase_value` | Total Purchase Value | Total value of purchases attributed to your ads |
| `cta_conversion` | CTA Conversions | Conversions attributed to clicks on the ad |
| `cta_purchase` | CTA Purchase | Purchases attributed to clicks |
| `cta_registration` | CTA Registration | Registrations attributed to clicks |
| `cta_app_install` | CTA App Install | App installs attributed to clicks |
| `cost_per_cta_conversion` | Cost per CTA Conversion | Spend ÷ CTA Conversions |
| `cost_per_cta_purchase` | Cost per CTA Purchase | Spend ÷ CTA Purchases |
| `cost_per_cta_registration` | Cost per CTA Registration | Spend ÷ CTA Registrations |
| `vta_conversion` | VTA Conversions | Conversions attributed to views (not clicks) |
| `vta_purchase` | VTA Purchase | Purchases attributed to views |
| `vta_registration` | VTA Registration | Registrations attributed to views |
| `vta_app_install` | VTA App Install | App installs attributed to views |
| `cost_per_vta_conversion` | Cost per VTA Conversion | Spend ÷ VTA Conversions |
| `cost_per_vta_purchase` | Cost per VTA Purchase | Spend ÷ VTA Purchases |
| `cost_per_vta_registration` | Cost per VTA Registration | Spend ÷ VTA Registrations |

---

## 9. Website / Page Event Metrics

Track actions users take on your **website** after clicking an ad. Requires TikTok Pixel. Available in `BASIC` report.

> Note: the sync worker does **not** request these pixel-web `page_event_*` fields.
> The reporting design's "(Shop)"/"(Onsite)" metrics map to TikTok's ONSITE family —
> see §15 for the exact fields (`onsite_*`, `total_onsite_*`, `ix_*`) the worker requests.

| API Field Name | Display Name | Description |
|---|---|---|
| `page_event_page_view` | Page Views (Website) | Number of page view events |
| `page_event_landing_page_view` | Landing Page Views (Website) | Number of landing page views |
| `page_event_button_click` | Button Clicks (Website) | Number of button click events |
| `page_event_form_submit` | Form Submissions (Website) | Number of form submission events |
| `page_event_download` | Downloads (Website) | Number of download events |
| `page_event_subscribe` | Subscriptions (Website) | Number of subscription events |
| `page_event_subscribe_value` | Subscription Value (Website) | Total value of subscriptions |
| `page_event_register` | Registrations (Website) | Number of registration events |
| `page_event_purchase` | Purchases (Website) | Number of purchase events |
| `page_event_purchase_value` | Purchase Value (Website) | Total purchase value attributed |
| `page_event_add_to_cart` | Add to Cart (Website) | Number of add-to-cart events |
| `page_event_add_to_cart_value` | Add to Cart Value (Website) | Total value of items added to cart |
| `page_event_checkout` | Checkout Initiated (Website) | Number of initiated checkouts |
| `page_event_checkout_value` | Checkout Value (Website) | Total value of initiated checkouts |
| `page_event_search` | Searches (Website) | Number of search events |
| `page_event_add_to_wishlist` | Adds to Wishlist (Website) | Number of add-to-wishlist events |
| `page_event_add_payment_info` | Payment Info Added (Website) | Number of payment info addition events |
| `page_event_order` | Orders Placed (Website) | Number of orders placed |
| `page_event_order_value` | Order Value (Website) | Total value of orders placed |
| `cost_per_page_event_purchase` | Cost per Purchase (Website) | Spend ÷ Website Purchases |

---

## 10. App Event Metrics

Track actions users take **in your app** after seeing an ad. Requires TikTok SDK. Available in `BASIC` report.

| API Field Name | Display Name | Description |
|---|---|---|
| `app_event_install` | App Installs | Total app installation events |
| `install_cost` | Install Cost | Average spend per app install |
| `app_event_add_to_cart` | Add to Cart (App) | Number of in-app add-to-cart events |
| `app_event_add_to_cart_value` | Add to Cart Value (App) | Total value of in-app add-to-cart events |
| `app_event_purchase` | Purchases (App) | Number of in-app purchase events |
| `app_event_purchase_value` | Purchase Value (App) | Total in-app purchase value |
| `app_event_register` | Registrations (App) | Number of in-app registration events |
| `app_event_checkout` | Total Checkout (App) | Number of in-app checkout events |
| `app_event_add_to_wishlist` | Add to Wishlist (App) | Number of in-app add-to-wishlist events |
| `app_event_add_to_wishlist_value` | Add to Wishlist Value (App) | Total value of in-app wishlisted items |
| `app_event_content_view` | Content Views (App) | Number of in-app content view events |
| `app_event_content_view_value` | Content View Value (App) | Total value of in-app content views |
| `app_event_search` | Searches (App) | Number of in-app search events |
| `app_event_add_payment_info` | Payment Info Adds (App) | Number of payment info addition events |
| `app_event_achieve_level` | Levels Achieved (App) | Number of level achievement events |
| `app_event_spend_credit` | Credit Spends (App) | Number of credit spend events |
| `app_event_subscribe` | Subscriptions (App) | Number of in-app subscription events |
| `app_event_launch` | App Launches | Number of app launch events |
| `app_install_by_conversion_time` | App Installs (by Conversion Time) | App installs counted by conversion time |

---

## 11. SKAN Metrics (iOS 14+)

Apple's SKAdNetwork attribution for iOS campaigns. Available in `BASIC` report.

| API Field Name | Display Name | Description |
|---|---|---|
| `skan_conversion` | Conversions (SKAN) | SKAN-attributed conversions |
| `skan_app_install` | App Install (SKAN) | SKAN-attributed app installs |
| `skan_result` | Result (SKAN) | SKAN-attributed optimization results |
| `skan_purchase` | Purchases (SKAN) | SKAN-attributed purchases |
| `skan_registration` | Registrations (SKAN) | SKAN-attributed registrations |
| `skan_add_to_cart` | Add to Cart (SKAN) | SKAN-attributed add-to-cart events |
| `skan_add_to_wishlist` | Add to Wishlist (SKAN) | SKAN-attributed add-to-wishlist events |
| `skan_checkout` | Checkout (SKAN) | SKAN-attributed checkout events |
| `skan_view_content` | View Content (SKAN) | SKAN-attributed content view events |
| `skan_add_payment_info` | Payment Info Added (SKAN) | SKAN-attributed payment info events |
| `skan_tutorial_complete` | Tutorial Completion (SKAN) | SKAN-attributed tutorial completions |
| `skan_achieve_level` | Level Achieved (SKAN) | SKAN-attributed level achievements |
| `skan_launch_app` | App Launch (SKAN) | SKAN-attributed app launches |
| `skan_generate_lead` | Generate Lead (SKAN) | SKAN-attributed lead generation events |
| `skan_login` | Login (SKAN) | SKAN-attributed login events |
| `skan_start_trial` | Start Trial (SKAN) | SKAN-attributed trial start events |
| `skan_subscribe` | Subscribe (SKAN) | SKAN-attributed subscription events |

---

## 12. LIVE Metrics

For TikTok LIVE ad campaigns. Available in `BASIC` report.

| API Field Name | Display Name | Description |
|---|---|---|
| `live_views` | LIVE Views | Total number of views for LIVE sessions |
| `live_unique_views` | LIVE Unique Views | Unique viewers for LIVE sessions |
| `live_effective_views` | Effective LIVE Views | LIVE views meeting a minimum engagement threshold |
| `live_product_clicks` | LIVE Product Clicks | Number of product clicks during LIVE sessions |

---

## 13. Reach & Frequency Metrics

Available when `report_type=REACH_FREQUENCY`. Supports configurable time windows: **1, 7, 14, 30, 60, 90 days, Month to Date, Lifetime**.

| API Field Name | Display Name | Description |
|---|---|---|
| `reach` | Reach | Number of unique users who saw your ads |
| `frequency` | Frequency | Average times each user saw your ad |
| `cost_per_1000_reached` | Cost per 1,000 Reached | Average spend to reach 1,000 unique users |
| `unique_purchase` | Unique Purchase | Unique users who completed a purchase |
| `unique_registration` | Unique Registration | Unique users who completed a registration |
| `unique_add_to_cart` | Unique Add to Cart | Unique users who added to cart |
| `unique_checkout` | Unique Checkout | Unique users who initiated checkout |
| `unique_view_content` | Unique View Content | Unique users who viewed content |
| `unique_day1_retention` | Unique Day 1 Retention | Unique users retained on day 1 |
| `unique_add_payment_info` | Unique Add Payment Info | Unique users who added payment info |
| `unique_add_to_wishlist` | Unique Add to Wishlist | Unique users who added to wishlist |
| `unique_launch_app` | Unique Launch App | Unique users who launched the app |
| `unique_complete_tutorial` | Unique Complete Tutorial | Unique users who completed a tutorial |
| `unique_achieve_level` | Unique Achieve Level | Unique users who achieved a level |
| `unique_subscribe` | Unique Subscribe | Unique users who subscribed |
| `unique_start_trial` | Unique Start Trial | Unique users who started a trial |
| `unique_generate_lead` | Unique Generate Lead | Unique users who completed a lead form |
| `unique_login` | Unique Login | Unique users who logged in |
| `unique_search` | Unique Search | Unique users who searched |
| `unique_inapp_ad_click` | Unique In-App Ad Click | Unique users who clicked an in-app ad |
| `unique_inapp_ad_impression` | Unique In-App Ad Impression | Unique users who saw an in-app ad |

---

## 14. Offline Metrics

For offline conversion tracking (e.g. in-store purchases). Available in `BASIC` report only.

| API Field Name | Display Name | Description |
|---|---|---|
| `offline_purchase` | Purchases (Offline) | Number of offline purchase events attributed to ads |
| `offline_purchase_value` | Purchase Value (Offline) | Total value of offline purchases attributed to ads |

---

## 15. Onsite / Shopping Metrics

For TikTok Shop and onsite commerce events. Available in `BASIC` report.

| API Field Name | Display Name | Description |
|---|---|---|
| `total_onsite_shopping_cart_abandonment` | Cart Abandonments (Onsite) | Number of onsite shopping cart abandonments |
| `total_onsite_add_billing_info` | Add Billing Info (Onsite) | Number of billing info additions onsite |
| `total_onsite_form_submit` | Form Submissions (Onsite) | Number of onsite form submission events |
| `total_purchase_gmv` | Total Purchase GMV | Total Gross Merchandise Value of purchases |
| `onsite_add_to_cart` | Adds to Cart (Onsite) | Number of onsite add-to-cart actions |
| `onsite_initiate_checkout` | Checkout Initiated (Onsite) | Number of onsite checkout initiations |
| `onsite_purchase` | Purchases (Onsite) | Number of purchases made onsite |
| `onsite_purchase_value` | Purchase Value (Onsite) | Total value of onsite purchases |

The following ONSITE-family fields are the ones the sync worker requests as its
graceful-fallback `EVENT_METRICS` tier (see `docs/sync-worker-spec.md`). These are
the correct "(Shop)"/"(Onsite)" fields — **not** the pixel-web `page_event_*` family
in §9:

| API Field Name | Display Name | Stored as `(field_name, action_type)` |
|---|---|---|
| `ix_page_view_count` | Page Views (Onsite) | (`page_events`, `page_view`) |
| `onsite_on_web_cart` | Adds to Cart (Onsite) | (`page_events`, `add_to_cart`) |
| `total_onsite_on_web_cart_value` | Add to Cart Value (Onsite) | (`page_event_values`, `add_to_cart`) |
| `onsite_initiate_checkout_count` | Checkout Initiated (Onsite) | (`page_events`, `checkout`) |
| `total_onsite_initiate_checkout_count_value` | Checkout Value (Onsite) | (`page_event_values`, `checkout`) |
| `onsite_shopping` | Purchases (Onsite / Shop) | (`page_events`, `purchase`) |
| `total_onsite_shopping_value` | Purchase Value (Onsite / Shop) | (`page_event_values`, `purchase`) |

### GMV Max view — KPI → metric mapping

The frontend **TikTok GMV Max** view (`/tiktok/gmv-max`, ADS lens of the reference
dashboard) is scoped to campaigns whose raw `objective_type` is `PRODUCT_SALES`
(the GMV Max objective; stored as `campaigns.platform_objective` — the normalized
`objective` collapses it to `sales`, so the raw value is what identifies GMV Max).
Its headline KPIs map to metrics dashmet already reads:

| GMV Max KPI | dashmet metric key | Source |
|---|---|---|
| Cost | `spend` | `metrics_daily.spend` |
| Gross Revenue | `web_purchase_value` | (`page_event_values`, `purchase`) |
| Orders | `web_purchases` | (`page_events`, `purchase`) |
| Cost per Order | `cost_per_web_purchase` | `spend ÷ web_purchases` (derived after aggregation) |
| ROAS (Shop) | `roas_shop` | `web_purchase_value ÷ spend` (derived after aggregation) |

The reference mockup's **Net cost** and a separate **ROI** are intentionally
**not** surfaced: TikTok's ads reporting exposes no refund/adjustment feed to back
a "net" figure, and inventing one would violate P-4 (refuse rather than answer
wrong). ROAS (Shop) stands in as the return metric. The mockup's **TikTok Shop**
and **Ads × Shop** modes need the TikTok Shop **Open API** (orders, products,
LIVE, affiliate, finance, channel attribution), which dashmet does not integrate —
they render locked in the UI, never as fabricated data.

The sync worker's `EVENT_METRICS` graceful-fallback tier also requests these
feature-gated interactive-addon (§16) and LIVE (§12) fields. They keep
`field_name` verbatim and are dropped on the same "invalid metric fields"
fallback if the advertiser hasn't enabled the feature:

| API Field Name | Display Name | Stored as `(field_name, action_type)` |
|---|---|---|
| `ix_product_click_count` | Product Card Clicks (Interactive) | (`ix_product_click_count`, `product_click`) |
| `live_effective_views` | Effective LIVE Views | (`live_effective_views`, `live_view`) |
| `live_product_clicks` | LIVE Product Clicks | (`live_product_clicks`, `product_click`) |

The standard `engagements` field (§5) is instead requested in the always-on
`ACTION_METRICS` tier and stored as (`engagements`, `engagement`).

---

## 16. Interactive Add-on Metrics

For ads using interactive overlays and stickers. Available in `BASIC` report.

| API Field Name | Display Name | Description |
|---|---|---|
| `interactive_addon_impressions` | Interactive Add-on Impressions | Times the interactive add-on was shown |
| `interactive_addon_destination_clicks` | Interactive Add-on Destination Clicks | Clicks that led to a destination |
| `interactive_addon_activity_clicks` | Interactive Add-on Activity Clicks | Clicks on interactive activity elements |
| `interactive_addon_option_a_clicks` | Option A Clicks | Clicks on Option A in a poll/quiz |
| `interactive_addon_option_b_clicks` | Option B Clicks | Clicks on Option B in a poll/quiz |
| `ix_product_click_count` | Product Card Clicks (Interactive) | Clicks on the interactive-addon product card |
| `countdown_sticker_recall_clicks` | Countdown Sticker Recall Clicks | Clicks on countdown sticker recall notifications |

---

## 17. Focused View Metrics

Measures quality video views with engagement intent. Available in `BASIC` report with country breakdown.

| API Field Name | Display Name | Description |
|---|---|---|
| `focused_view_6s` | 6-Second Focused Views | Plays of 6+ seconds OR with engagement within the first 6 seconds |
| `focused_view_15s` | 15-Second Focused Views | Plays of 15+ seconds OR played fully if shorter than 15 seconds |
| `cost_per_focused_view` | Cost per Focused View | Spend ÷ Focused Views |

---

## 18. Metrics Availability Matrix

This matrix shows which metric categories are available per `report_type`.

| Metric Category | `BASIC` | `AUDIENCE` | `REACH_FREQUENCY` | `RESERVATION` |
|---|:---:|:---:|:---:|:---:|
| Core Performance (spend, impressions, clicks) | ✅ | ✅ | ✅ | ✅ |
| Cost & Efficiency (CPM, CPC, CPR) | ✅ | ✅ | ✅ | ✅ |
| Video Play Metrics | ✅ | ✅ | ❌ | ✅ |
| Engagement (likes, shares, follows) | ✅ | ✅ | ❌ | ✅ (partial) |
| Conversion Metrics | ✅ | ✅ | ❌ | ❌ |
| Real-Time Metrics | ✅ | ❌ | ❌ | ❌ |
| Attribution (CTA / VTA) | ✅ | ❌ | ❌ | ❌ |
| Website / Page Events | ✅ | ❌ | ❌ | ❌ |
| App Events | ✅ | ❌ | ❌ | ❌ |
| SKAN Metrics | ✅ | ❌ | ❌ | ❌ |
| LIVE Metrics | ✅ | ❌ | ❌ | ❌ |
| Reach & Frequency (Unique events) | ❌ | ❌ | ✅ | ❌ |
| Offline Metrics | ✅ | ❌ | ❌ | ❌ |
| Onsite / Shopping | ✅ | ❌ | ❌ | ❌ |
| Interactive Add-on | ✅ | ❌ | ❌ | ❌ |
| Focused View | ✅ (+ country) | ❌ | ❌ | ❌ |

---

## 19. Dashboard Recommended Metric Sets

Ready-to-use metric arrays for common dashboard panels.

### Overview / KPI Panel
```json
["spend", "impressions", "clicks", "ctr", "cpc", "cpm", "reach", "frequency", "conversion", "cost_per_conversion", "result", "cost_per_result"]
```

### Video Performance Panel
```json
["impressions", "video_play_actions", "video_watched_2s", "video_watched_6s", "video_views_p25", "video_views_p50", "video_views_p75", "video_views_p100", "average_video_play", "average_video_play_per_user"]
```

### Engagement Panel
```json
["impressions", "likes", "comments", "shares", "follows", "profile_visits", "engagement_rate"]
```

### Conversion & Attribution Panel
```json
["conversion", "conversion_rate", "cost_per_conversion", "real_time_conversion", "real_time_cost_per_conversion", "cta_conversion", "cta_purchase", "vta_conversion", "vta_purchase"]
```

### E-Commerce / Onsite Panel (ONSITE family — what the sync worker requests)
```json
["spend", "onsite_shopping", "total_onsite_shopping_value", "onsite_on_web_cart", "total_onsite_on_web_cart_value", "onsite_initiate_checkout_count", "total_onsite_initiate_checkout_count_value", "ix_page_view_count"]
```

### App Installs Panel
```json
["spend", "app_event_install", "install_cost", "real_time_app_install", "app_event_add_to_cart", "app_event_purchase", "app_event_purchase_value"]
```

### Reach & Brand Awareness Panel
`report_type=REACH_FREQUENCY` required:
```json
["reach", "frequency", "cost_per_1000_reached", "impressions", "spend"]
```

---

## Notes

1. **Metric names are case-sensitive.** Always pass them exactly as shown (lowercase with underscores).
2. **Mixing incompatible metrics causes an error.** For example, you cannot mix `BASIC`-only metrics with `REACH_FREQUENCY`-only metrics in a single request.
3. **Not all metrics are available at all data levels.** Some metrics are only returned when `data_level=AUCTION_AD` (e.g. video metrics require ad-level granularity).
4. **Country code dimension unlocks extra metrics.** Some BASIC metrics (focused views, certain website events) require `country_code` to be included in `dimensions`.
5. **Audience-breakdown metrics** require `report_type=AUDIENCE` and a breakdown dimension (`age`, `gender`, `country_code`, `platform`, `placement`, etc.).
6. **SKAN metrics** only apply to iOS 14+ campaigns that use Apple's SKAdNetwork attribution framework.
7. **Reporting lag:** Standard metrics can lag 24–48 hours. Use `real_time_*` variants where low latency matters for your dashboard.
