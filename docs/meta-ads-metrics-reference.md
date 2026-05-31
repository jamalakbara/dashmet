# Meta Ads Insights API — Complete Metrics Reference

> **Source:** Graph API v25.0 — `/{object_id}/insights`  
> **Last updated:** May 2026  
> **Permission required:** `ads_read`, `read_insights`

All fields are passed as a comma-separated `fields=` parameter. Fields return as `string` (numeric) unless noted.

---

## Table of Contents

1. [Identity Fields](#1-identity-fields)
2. [Core Performance](#2-core-performance)
3. [Click Metrics](#3-click-metrics)
4. [Spend & Cost Efficiency](#4-spend--cost-efficiency)
5. [Actions & Conversions](#5-actions--conversions)
6. [ROAS & Revenue](#6-roas--revenue)
7. [Video Metrics](#7-video-metrics)
8. [Engagement Metrics](#8-engagement-metrics)
9. [Unique Metrics](#9-unique-metrics-deduplicated)
10. [Catalog & Product Metrics](#10-catalog--product-metrics)
11. [Auction Metrics](#11-auction-metrics)
12. [App & Mobile Metrics](#12-app--mobile-metrics)
13. [Messaging Metrics](#13-messaging-metrics)
14. [Estimated / In-Development Metrics](#14-estimated--in-development-metrics)
15. [Action Types Reference](#15-action-types-reference)
16. [Dashboard Recommended Field Sets](#16-dashboard-recommended-field-sets)

---

## 1. Identity Fields

These are always returned by default or used for grouping. Not metrics — they are dimension/label fields.

| Field | Type | Description |
|---|---|---|
| `account_id` | string | Ad account ID *(default)* |
| `account_name` | string | Ad account name |
| `account_currency` | string | Account currency code (e.g. `USD`) |
| `campaign_id` | string | Campaign ID *(default)* |
| `campaign_name` | string | Campaign name |
| `adset_id` | string | Ad set ID *(default)* |
| `adset_name` | string | Ad set name |
| `ad_id` | string | Ad ID *(default)* |
| `ad_name` | string | Ad name |
| `date_start` | string | Start of reporting window (`YYYY-MM-DD`) |
| `date_stop` | string | End of reporting window (`YYYY-MM-DD`) |
| `buying_type` | string | `AUCTION`, `RESERVED` — campaign level only |
| `attribution_setting` | string | Attribution window used for results |

---

## 2. Core Performance

The fundamental delivery metrics every dashboard needs.

| Field | Type | Description |
|---|---|---|
| `impressions` | string | Total number of times your ads were shown |
| `reach` | string | Unique accounts that saw your ad at least once |
| `frequency` | string | Average times each person saw your ad (`impressions ÷ reach`) |
| `clicks` | string | All clicks on your ad (link, reaction, comment, share, etc.) |
| `spend` | string | Total amount spent in account currency |
| `ctr` | string | Click-through rate = `clicks ÷ impressions × 100` (%) |
| `cpm` | string | Cost per 1,000 impressions |
| `cpp` | string | Cost per 1,000 people reached |
| `cpc` | string | Average cost per click (all clicks) |

> ⚠️ **Note (June 10, 2025):** `reach` is no longer returned for breakdown queries with `start_date` older than 13 months. Use async jobs for historical reach (max 10/account/day).

---

## 3. Click Metrics

Granular breakdown of click types.

| Field | Type | Description |
|---|---|---|
| `clicks` | string | All clicks (all interactions) |
| `unique_clicks` | string | Unique accounts who clicked at least once |
| `inline_link_clicks` | string | Clicks on links within the ad (destination URL) |
| `unique_inline_link_clicks` | string | Unique accounts who clicked a link in the ad |
| `outbound_clicks` | list\<AdsActionStats\> | Clicks that take people off Meta platforms |
| `unique_outbound_clicks` | list\<AdsActionStats\> | Unique people who clicked outbound |
| `cost_per_inline_link_click` | string | Average cost per inline link click |
| `cost_per_outbound_click` | list\<AdsActionStats\> | Average cost per outbound click |
| `cost_per_unique_click` | string | Average cost per unique click |
| `inline_link_click_ctr` | string | CTR for inline link clicks only |
| `outbound_clicks_ctr` | list\<AdsActionStats\> | CTR for outbound clicks |

**Click type summary**

```
clicks (all)
 ├── inline_link_clicks     → clicks going to your URL
 │     └── outbound_clicks  → clicks leaving Meta entirely
 └── other interactions     → likes, comments, shares, page name clicks
```

---

## 4. Spend & Cost Efficiency

| Field | Type | Description |
|---|---|---|
| `spend` | string | Total amount spent |
| `cpm` | string | Cost per 1,000 impressions |
| `cpc` | string | Cost per click (all) |
| `cpp` | string | Cost per 1,000 people reached |
| `ctr` | string | Click-through rate (all clicks) |
| `cost_per_action_type` | list\<AdsActionStats\> | Cost per each action type (purchases, leads, etc.) |
| `cost_per_unique_action_type` | list\<AdsActionStats\> | Cost per unique action per person |
| `cost_per_conversion` | list\<AdsActionStats\> | Average cost per conversion |
| `cost_per_result` | list\<AdsInsightsResult\> | Average cost per objective result |
| `cost_per_objective_result` | list\<AdsInsightsResult\> | Cost per result based on campaign objective |
| `cost_per_inline_link_click` | string | Average cost per inline link click |
| `cost_per_inline_post_engagement` | string | Average cost per inline post engagement |
| `cost_per_outbound_click` | list\<AdsActionStats\> | Average cost per outbound click |
| `cost_per_unique_click` | string | Average cost per unique click |
| `cost_per_ad_click` | list\<AdsActionStats\> | Cost per ad-level click |
| `cost_per_dda_countby_convs` | string | Cost per data-driven attribution conversion |
| `cost_per_one_thousand_ad_impression` | list\<AdsActionStats\> | CPM variant for ad impressions |

---

## 5. Actions & Conversions

Actions are returned as an **array** — each item has `action_type` and `value`. They cover everything from link clicks to purchases.

| Field | Type | Description |
|---|---|---|
| `actions` | list\<AdsActionStats\> | All actions taken attributed to your ads, by type |
| `action_values` | list\<AdsActionStats\> | Total monetary value of all conversions |
| `unique_actions` | list\<AdsActionStats\> | Unique accounts who took each action |
| `cost_per_action_type` | list\<AdsActionStats\> | Average cost per action, by type |
| `cost_per_unique_action_type` | list\<AdsActionStats\> | Average cost per unique action per person |
| `conversions` | list\<AdsActionStats\> | Conversion events attributed to ads |
| `conversion_values` | list\<AdsActionStats\> | Value of conversions (if value tracking set up) |
| `cost_per_conversion` | list\<AdsActionStats\> | Cost per conversion event |
| `total_actions` | string | Total count of all actions |
| `total_unique_actions` | string | Total unique actions across all types |
| `result_rate` | string | Percentage of impressions that resulted in a result |
| `results` | list\<AdsInsightsResult\> | Objective results (e.g., purchases, leads) |
| `objective_result_count` | list\<AdsInsightsResult\> | Count of results for the campaign objective |

**Sample `actions` response**

```json
"actions": [
  { "action_type": "link_click",            "value": "340" },
  { "action_type": "purchase",              "value": "12"  },
  { "action_type": "lead",                  "value": "45"  },
  { "action_type": "app_install",           "value": "8"   },
  { "action_type": "page_engagement",       "value": "510" },
  { "action_type": "post_engagement",       "value": "480" },
  { "action_type": "post_reaction",         "value": "120" },
  { "action_type": "comment",               "value": "23"  },
  { "action_type": "video_view",            "value": "1240"}
]
```

---

## 6. ROAS & Revenue

Return on Ad Spend fields. Require purchase value tracking via Pixel or CAPI.

| Field | Type | Description |
|---|---|---|
| `purchase_roas` | list\<AdsActionStats\> | Total ROAS — all purchase sources combined |
| `website_purchase_roas` | list\<AdsActionStats\> | ROAS from website purchases (Pixel) |
| `mobile_app_purchase_roas` | list\<AdsActionStats\> | ROAS from mobile app purchases (App SDK) |
| `action_values` | list\<AdsActionStats\> | Total value of all conversions |
| `conversion_values` | list\<AdsActionStats\> | Conversion event values |
| `catalog_segment_value_omni_purchase_roas` | list\<AdsActionStats\> | ROAS for catalog segment — all channels |
| `catalog_segment_value_website_purchase_roas` | list\<AdsActionStats\> | ROAS for catalog segment — website |
| `catalog_segment_value_mobile_purchase_roas` | list\<AdsActionStats\> | ROAS for catalog segment — mobile app |

**How ROAS is calculated**

```
ROAS = total_conversion_value ÷ spend
```

The API returns ROAS as a direct multiplier (e.g. `3.5` = $3.50 returned per $1 spent).

---

## 7. Video Metrics

Available when the ad contains a video. Not all metrics available for all placements.

| Field | Type | Description |
|---|---|---|
| `video_play_actions` | list\<AdsActionStats\> | Number of times video started playing |
| `video_avg_time_watched_actions` | list\<AdsActionStats\> | Average watch time in milliseconds |
| `video_continuous_2_sec_watched_actions` | list\<AdsActionStats\> | Times video played for at least 2 continuous seconds |
| `video_thruplay_watched_actions` | list\<AdsActionStats\> | Times video played to completion or 15s+ if longer |
| `video_30_sec_watched_actions` | list\<AdsActionStats\> | Times video played for at least 30 seconds |
| `video_p25_watched_actions` | list\<AdsActionStats\> | Times video reached 25% played |
| `video_p50_watched_actions` | list\<AdsActionStats\> | Times video reached 50% played |
| `video_p75_watched_actions` | list\<AdsActionStats\> | Times video reached 75% played |
| `video_p95_watched_actions` | list\<AdsActionStats\> | Times video reached 95% played |
| `video_p100_watched_actions` | list\<AdsActionStats\> | Times video played to 100% completion |
| `unique_video_continuous_2_sec_watched_actions` | list\<AdsActionStats\> | Unique people who watched 2s continuously |
| `unique_video_view_15_sec` | list\<AdsActionStats\> | Unique people who watched 15+ seconds |
| `cost_per_thruplay` | list\<AdsActionStats\> | Cost per ThruPlay *(in development)* |
| `cost_per_2_sec_continuous_video_view` | list\<AdsActionStats\> | Cost per 2-second continuous view |
| `cost_per_15_sec_video_view` | list\<AdsActionStats\> | Cost per 15-second view |

> ⚠️ `video_p25–p100` do not support `region` breakdown.  
> ⚠️ `hourly` breakdowns do not support `video_thruplay_watched_actions`.

**Video retention funnel (example)**

```
video_play_actions          → 5,000  (started)
video_continuous_2_sec      → 4,200  (84% — watched 2s)
video_p25_watched_actions   → 2,100  (42% — watched 25%)
video_p50_watched_actions   → 1,050  (21% — watched 50%)
video_p75_watched_actions   →   630  (13% — watched 75%)
video_p100_watched_actions  →   350  ( 7% — watched all)
video_thruplay              →   400  ( 8% — ThruPlay)
```

---

## 8. Engagement Metrics

On-ad interactions beyond clicks.

| Field | Type | Description |
|---|---|---|
| `inline_post_engagement` | string | On-ad engagements (reactions, comments, shares, link clicks) |
| `cost_per_inline_post_engagement` | string | Average cost per in-ad engagement |
| `canvas_avg_view_percent` | string | Average % of Instant Experience viewed |
| `canvas_avg_view_time` | string | Average seconds spent in Instant Experience |
| `ad_click_actions` | list\<AdsActionStats\> | Click actions on the ad itself |
| `ad_impression_actions` | list\<AdsActionStats\> | Impression-based actions |

---

## 9. Unique Metrics (Deduplicated)

Count unique people rather than total events. More expensive to compute — query separately from non-unique metrics.

| Field | Type | Description |
|---|---|---|
| `reach` | string | Unique people who saw the ad |
| `unique_clicks` | string | Unique people who clicked (any) |
| `unique_inline_link_clicks` | string | Unique people who clicked a link |
| `unique_outbound_clicks` | list\<AdsActionStats\> | Unique people who clicked off Meta |
| `unique_actions` | list\<AdsActionStats\> | Unique people per action type |
| `unique_action_types` | list\<AdsActionStats\> | Unique action type counts |
| `cost_per_unique_click` | string | Cost per unique click |
| `cost_per_unique_action_type` | list\<AdsActionStats\> | Cost per unique action type |
| `cost_per_unique_inline_link_click` | string | Cost per unique inline link click |
| `cost_per_unique_outbound_click` | list\<AdsActionStats\> | Cost per unique outbound click |
| `unique_ctr` | string | Unique click-through rate |
| `unique_inline_link_click_ctr` | string | Unique CTR for inline links |
| `unique_outbound_clicks_ctr` | list\<AdsActionStats\> | Unique outbound CTR |
| `unique_video_continuous_2_sec_watched_actions` | list\<AdsActionStats\> | Unique 2-second continuous views |
| `unique_video_view_15_sec` | list\<AdsActionStats\> | Unique 15-second views |

> **Performance tip:** Always query unique metrics in a **separate API call** from non-unique metrics. Mixing them slows the query significantly.

---

## 10. Catalog & Product Metrics

For Advantage+ Catalog Ads (formerly Dynamic Product Ads).

| Field | Type | Description |
|---|---|---|
| `catalog_segment_actions` | list\<AdsActionStats\> | Actions from catalog segment ads |
| `catalog_segment_value` | list\<AdsActionStats\> | Conversion value from catalog segment |
| `catalog_segment_value_omni_purchase_roas` | list\<AdsActionStats\> | Total ROAS for catalog segment |
| `catalog_segment_value_website_purchase_roas` | list\<AdsActionStats\> | Website ROAS for catalog segment |
| `catalog_segment_value_mobile_purchase_roas` | list\<AdsActionStats\> | Mobile app ROAS for catalog segment |
| `converted_product_quantity` | list\<AdsActionStats\> | Products purchased (by product ID) |
| `converted_product_value` | list\<AdsActionStats\> | Purchase value (by product ID) |
| `converted_product_omni_purchase` | list\<AdsActionStats\> | Omni-channel purchases per product |
| `converted_product_website_pixel_purchase` | list\<AdsActionStats\> | Website pixel purchases per product |
| `converted_product_app_custom_event_fb_mobile_purchase` | list\<AdsActionStats\> | App purchases per product |
| `converted_promoted_product_quantity` | list\<AdsActionStats\> | Promoted product purchases (quantity) |
| `converted_promoted_product_value` | list\<AdsActionStats\> | Promoted product purchase value |
| `converted_promoted_product_omni_purchase` | list\<AdsActionStats\> | Promoted product omni-channel purchases |

> These product-level fields require the `product_id` breakdown to be meaningful.

---

## 11. Auction Metrics

Insight into how your ad is competing in the auction. Useful for diagnosing delivery issues.

| Field | Type | Description |
|---|---|---|
| `auction_bid` | string | Your bid in the auction |
| `auction_competitiveness` | string | How competitive your bid is vs others (0–1) |
| `auction_max_competitor_bid` | string | The highest competing bid you faced |

---

## 12. App & Mobile Metrics

For app install and app event campaigns.

| Field | Type | Description |
|---|---|---|
| `actions` with `action_type: app_install` | — | App installs |
| `actions` with `action_type: app_use` | — | App opens / uses |
| `actions` with `action_type: fb_mobile_purchase` | — | In-app purchases |
| `actions` with `action_type: fb_mobile_activate_app` | — | App activations |
| `actions` with `action_type: fb_mobile_add_to_cart` | — | Add to cart in app |
| `mobile_app_purchase_roas` | list\<AdsActionStats\> | Mobile app purchase ROAS |
| `total_postbacks` | string | Total SKAdNetwork postbacks (iOS) |
| `total_postbacks_detailed` | list | Detailed postback data by conversion ID |
| `total_postbacks_detailed_v4` | list | v4 detailed postbacks with coarse conversion |

---

## 13. Messaging Metrics

For Click-to-Message and Messaging campaigns.

| Field | Type | Description |
|---|---|---|
| `actions` with `action_type: onsite_conversion.messaging_conversation_started_7d` | — | Conversations started within 7 days |
| `actions` with `action_type: onsite_conversion.messaging_first_reply` | — | First replies in conversation |
| `actions` with `action_type: onsite_conversion.messaging_detected_purchase_deduped` | — | Purchases detected in messaging |
| `onsite_conversion_messaging_detected_purchase_deduped` | list\<AdsActionStats\> | Deduped messaging purchases |

---

## 14. Estimated / In-Development Metrics

These metrics are directional — use for guidance, not precise historical comparison.

| Field | Status | Description |
|---|---|---|
| `estimated_ad_recall_rate` | Estimated | % of people who would remember your ad |
| `estimated_ad_recall_rate_lower_bound` | Estimated | Lower bound of recall estimate |
| `estimated_ad_recall_rate_upper_bound` | Estimated | Upper bound of recall estimate |
| `estimated_ad_recallers` | Estimated | Estimated number of people who recall ad |
| `cost_per_thruplay` | In Development | Cost per ThruPlay view |
| `multi_event_conversion_attribution_setting` | In Development | Multi-event attribution setting |

> ⚠️ `estimated_ad_recall_rate` does not support `dma` breakdown.

---

## 15. Action Types Reference

The `actions` field returns an array. Each item has `action_type` and `value`. These are the most common action types.

### Engagement

| `action_type` | Description |
|---|---|
| `page_engagement` | All on-page interactions (sum of below) |
| `post_engagement` | All post interactions |
| `post_reaction` | Reactions (like, love, haha, wow, sad, angry) |
| `like` | Page or post likes |
| `comment` | Comments on post |
| `post` | Posts made on your page |
| `checkin` | Check-ins at your location |
| `rsvp` | Event RSVPs |

### Clicks

| `action_type` | Description |
|---|---|
| `link_click` | Clicks on links in the ad |
| `outbound_click` | Clicks that leave Meta |
| `photo_view` | Clicks to view a photo |
| `video_play` | Video play starts |

### Conversions — Standard Events

| `action_type` | Description |
|---|---|
| `purchase` | Purchases (web + app combined) |
| `lead` | Lead form submissions |
| `complete_registration` | Registration completions |
| `add_to_cart` | Add-to-cart events |
| `add_to_wishlist` | Add-to-wishlist events |
| `initiate_checkout` | Checkout starts |
| `add_payment_info` | Payment info added |
| `view_content` | Content/product page views |
| `search` | Search events |
| `contact` | Contact events |
| `customize_product` | Product customization events |
| `donate` | Donation events |
| `find_location` | Location search/find events |
| `schedule` | Appointment scheduling events |
| `start_trial` | Trial start events |
| `submit_application` | Application submissions |
| `subscribe` | Subscription events |

### App Events

| `action_type` | Description |
|---|---|
| `app_install` | App installs |
| `app_use` | App opens/usage |
| `fb_mobile_activate_app` | App activations |
| `fb_mobile_purchase` | In-app purchases |
| `fb_mobile_add_to_cart` | In-app add-to-cart |
| `fb_mobile_add_to_wishlist` | In-app add-to-wishlist |
| `fb_mobile_initiated_checkout` | In-app checkout started |
| `fb_mobile_add_payment_info` | In-app payment info |
| `fb_mobile_complete_registration` | In-app registration |
| `fb_mobile_search` | In-app search |
| `fb_mobile_content_view` | In-app content view |
| `fb_mobile_level_achieved` | Game level achieved |
| `fb_mobile_achievement_unlocked` | Achievement unlocked |
| `fb_mobile_spent_credits` | Credits spent (gaming) |
| `fb_mobile_tutorial_completion` | Tutorial completed |

### Messaging

| `action_type` | Description |
|---|---|
| `onsite_conversion.messaging_conversation_started_7d` | Conversation started |
| `onsite_conversion.messaging_first_reply` | First reply received |
| `onsite_conversion.messaging_detected_purchase_deduped` | Purchase in messaging |

### Video

| `action_type` | Description |
|---|---|
| `video_view` | Video views (3 seconds or more) |
| `video_p25_watched` | Watched 25% |
| `video_p50_watched` | Watched 50% |
| `video_p75_watched` | Watched 75% |
| `video_p100_watched` | Watched 100% |
| `video_thruplay` | ThruPlay (full or 15s+) |

---

## 16. Dashboard Recommended Field Sets

Pre-built field strings optimized for common dashboard views.

### Overview / Summary Panel

```
fields=impressions,reach,frequency,clicks,spend,ctr,cpm,cpc,cpp,
       actions,action_values,cost_per_action_type,
       date_start,date_stop
```

### Spend & Efficiency Table

```
fields=campaign_id,campaign_name,impressions,reach,clicks,
       spend,ctr,cpm,cpc,cpp,
       cost_per_action_type,purchase_roas,
       date_start,date_stop
```

### Conversion & ROAS Panel

```
fields=campaign_id,campaign_name,adset_id,adset_name,
       spend,actions,action_values,
       purchase_roas,website_purchase_roas,mobile_app_purchase_roas,
       cost_per_conversion,conversions,conversion_values,
       date_start,date_stop
```

### Ad Content Performance (Creative Analysis)

```
fields=ad_id,ad_name,adset_id,campaign_id,
       impressions,reach,frequency,clicks,ctr,spend,cpm,
       actions,cost_per_action_type,
       date_start,date_stop
```

### Video Performance Panel

```
fields=ad_id,ad_name,impressions,reach,spend,
       video_play_actions,video_avg_time_watched_actions,
       video_p25_watched_actions,video_p50_watched_actions,
       video_p75_watched_actions,video_p100_watched_actions,
       video_thruplay_watched_actions,cost_per_thruplay,
       date_start,date_stop
```

### Demographic Breakdown (age + gender)

```
fields=impressions,reach,clicks,spend,ctr,cpm,actions
&breakdowns=age,gender
&level=campaign
```

### Platform / Placement Breakdown

```
fields=impressions,clicks,spend,ctr,cpm,cpc,actions
&breakdowns=publisher_platform,platform_position
&level=adset
```

### Daily Trend (time series)

```
fields=impressions,reach,clicks,spend,ctr,cpm,actions
&time_increment=1
&date_preset=last_30d
&level=account
```

---

## Notes on Field Compatibility

Some fields cannot be used together or with certain breakdowns:

| Constraint | Detail |
|---|---|
| Unique metrics + hourly breakdown | Not compatible — returns `0` for reach/frequency |
| `video_p*` + `region` breakdown | Not supported |
| `reach` + breakdown + >13 months old | Returns empty since June 10, 2025 |
| `app_store_clicks`, `newsfeed_*` | Cannot be used with any breakdown |
| `estimated_ad_recall_rate` + `dma` | Not compatible |
| Triple breakdowns | Very high timeout risk — use async |
| Unique metrics + non-unique metrics | Works, but slower — split into 2 calls for performance |

---

## Source

- [Graph API v25.0 — Ad Insights Reference](https://developers.facebook.com/docs/graph-api/reference/adgroup/insights/)
- [Insights API — Marketing API](https://developers.facebook.com/docs/marketing-api/insights/)
- [Insights Breakdowns](https://developers.facebook.com/docs/marketing-api/insights/breakdowns/)
- [Insights Limits & Best Practices](https://developers.facebook.com/docs/marketing-api/insights/best-practices/)
