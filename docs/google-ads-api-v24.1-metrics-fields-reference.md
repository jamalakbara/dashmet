# Google Ads API v24.1 - Reporting Fields & Metrics Reference

**API Version:** v24.1 (2026-05-13) - Latest  
**Documentation Type:** Metrics, Segments, and Fields Reference  
**Last Updated:** June 15, 2026  
**Primary Use:** Dashboard Analytics & Reporting

---

## 📊 Overview

This document provides a comprehensive reference of all available metrics, segments, and fields in Google Ads API v24.1 for building read-only analytics dashboards. All metrics and segments are queried via GAQL using the reporting fields reference.

### Quick Access Links
- **Interactive Query Builder:** https://developers.google.com/google-ads/api/fields/latest/overview_query_builder
- **Fields Reference (Searchable):** https://developers.google.com/google-ads/api/fields/latest/overview
- **Query Validator:** https://developers.google.com/google-ads/api/fields/latest/query_validator

---

## 📈 Core Metrics Categories

### Performance Metrics (Clicks, Impressions, Cost)

#### Clicks Metrics
- `metrics.clicks` - Total number of clicks
- `metrics.all_clicks` - All clicks including cross-device
- `metrics.clicks_unique_query_clusters` - Unique query clusters (Smart Bidding Exploration)

#### Impressions Metrics
- `metrics.impressions` - Number of impressions
- `metrics.impressions_unique_query_clusters` - Unique impressions by query cluster

#### Cost Metrics
- `metrics.cost_micros` - Total cost in micro currency (divide by 1,000,000 for standard units)
- `metrics.all_cost_micros` - All cost including cross-device

#### Engagement Metrics (v24 New)
- `metrics.engagements` - Number of engagements
- `metrics.engagement_rate` - Engagement rate percentage
- `metrics.average_cpe` - Average cost per engagement

#### View Metrics
- `metrics.video_views` (renamed in v22: from `video_views`)
- `metrics.trueview_views` (v22+)
- `metrics.video_watch_time_duration_millis` - Total video watch time
- `metrics.average_video_watch_time_duration_millis` - Average watch time per impression

---

### Conversion Metrics

#### Basic Conversions
- `metrics.conversions` - Standard conversions
- `metrics.all_conversions` - All conversions (including offline)
- `metrics.conversions_value` - Total conversion value
- `metrics.all_conversions_value` - All conversion value

#### Conversion Rate & Value
- `metrics.conversion_rate` - Conversion rate percentage
- `metrics.value_per_conversion` - Average conversion value
- `metrics.value_per_all_conversions` - Average value for all conversions
- `metrics.cost_per_conversion` - Cost divided by conversions
- `metrics.cost_per_all_conversions` - Cost per all conversions

#### Conversion by Attribution Date (v23+)
- `metrics.conversions_by_conversion_date` - Conversions grouped by date
- `metrics.all_conversions_by_conversion_date` - All conversions by date
- `metrics.conversions_value_by_conversion_date` - Value by conversion date
- `metrics.all_conversions_value_by_conversion_date` - All value by conversion date

#### Conversion Adjustments
- `metrics.conversion_value_adjustment_micros` - Adjustment value (micros)
- `metrics.all_conversion_value_adjustment_micros` - All adjustment value

#### Unique Conversions
- `metrics.conversions_unique_query_clusters` - Unique conversions by query cluster

#### Indirect Install Conversions (v22+)
- `metrics.biddable_indirect_install_first_in_app_conversion_micros` - Indirect app installs

#### Experiment Metrics (v24 New)
- `metrics.conversions_absolute_change_point_estimate` - Conversion change estimate
- `metrics.conversions_absolute_change_margin_of_error` - Conversion margin of error
- `metrics.conversions_absolute_change_p_value` - P-value for conversion difference

---

### CTR & Performance Ratios

#### Click-Through Rate
- `metrics.ctr` - Click-through rate (clicks/impressions)

#### Cost Per Click
- `metrics.average_cpc` - Average cost per click
- `metrics.average_cpe` - Average cost per engagement

#### Impressions & View Rates
- `metrics.video_trueview_view_rate` (renamed in v22)
- `metrics.video_trueview_view_rate_in_stream` - In-stream view rate
- `metrics.video_trueview_view_rate_in_feed` - In-feed view rate
- `metrics.video_trueview_view_rate_shorts` - Shorts view rate

#### Average Position
- `metrics.average_position` - Average ad position

#### Quality Score
- `metrics.quality_score` - Landing page quality score (1-10)

---

### Reach & Frequency Metrics

#### Reach Metrics
- `metrics.active_view_impressions` - Impressions with viewable ad
- `metrics.active_view_measurability_rate` - Measurable impression percentage
- `metrics.active_view_measurable_cost_micros` - Cost of measurable impressions
- `metrics.active_view_viewability_rate` - Actual viewability percentage

#### Frequency Metrics (v21+)
- `metrics.unique_users_two_plus` - Unique users seeing ad 2+ times
- `metrics.unique_users_three_plus` - Unique users 3+ times
- `metrics.unique_users_four_plus` - Unique users 4+ times
- `metrics.unique_users_five_plus` - Unique users 5+ times
- `metrics.unique_users_ten_plus` - Unique users 10+ times

---

### Mobile & Device Metrics

#### Mobile Metrics
- `metrics.mobile_friendly_clicks` - Mobile-friendly click count
- `metrics.mobile_unfriendly_clicks` - Mobile-unfriendly clicks

#### Cross-Device
- `metrics.cross_device_conversions` - Conversions across devices
- `metrics.cross_device_conversions_value` - Cross-device conversion value

---

### Interaction & Engagement Metrics

#### Clicks by Type
- `metrics.interaction_rate` - Rate of interactions
- `metrics.interaction_event_types` - Types of interaction events
- `metrics.video_interaction_event_types` - Video interaction types

#### Call Metrics
- `metrics.phone_calls` - Number of phone calls
- `metrics.phone_impressions` - Impressions with phone option
- `metrics.phone_through_rate` - Phone call rate

#### Store Visits
- `metrics.phone_call_clicks` - Click to call conversions
- `metrics.local_stores_visited` - Store visits from ads

---

### Asset & Creative Performance Metrics (v21+)

#### Asset Performance
- `metrics.average_cpm` - Average cost per thousand impressions
- `metrics.average_cpv` - Average cost per video view
- `metrics.video_trueview_average_cpv` - Average CPV (viewable)

#### Impression Share
- `metrics.search_impression_share` - Search impression share %
- `metrics.search_budget_lost_impression_share` - Lost IS (budget)
- `metrics.search_rank_lost_impression_share` - Lost IS (rank)

---

## 🎯 Segment Categories (Group By Dimensions)

### Time Segments

#### Date Grouping
- `segments.date` - Single day (YYYY-MM-DD format)
- `segments.week` - Week grouping
- `segments.month` - Month (YYYYMM)
- `segments.quarter` - Quarter (YYYYQX)
- `segments.year` - Year (YYYY)

#### Day of Week
- `segments.day_of_week` - Monday through Sunday (numeric 1-7)

#### Hour
- `segments.hour` - Hour of day (0-23)

#### Time Zones
- `segments.advertising_partner_id` - Partner IDs
- `segments.conversion_date` - Date conversion occurred

---

### Device & Platform Segments

#### Device Type
- `segments.device` - Desktop, Mobile, Tablet
- `segments.mobile_device_platform` (NEW v24.1) - iOS, Android, Other

#### Device Category
- `segments.ad_format_type` - Display format type
- `segments.device` - Device type (DESKTOP, MOBILE, TABLET, OTHER)

---

### Campaign & Ad Group Segments

#### Campaign Level
- `segments.campaign_id` - Campaign ID
- `segments.campaign_name` - Campaign name
- `segments.campaign_type` - Campaign type (Search, Display, Shopping, etc.)
- `segments.campaign_status` - Campaign status
- `segments.campaign_base_campaign_id` - Base campaign ID

#### Ad Group Level
- `segments.ad_group_id` - Ad group ID
- `segments.ad_group_name` - Ad group name
- `segments.ad_group_status` - Ad group status

---

### Network & Placement Segments

#### Network
- `segments.network` - Search Network or Display Network
- `segments.ad_network_type` - Network breakdown (Google Search, Partner, Display, YouTube, Gmail)
- `segments.ad_sub_network_type` (v23+) - Sub-network (YouTube In-stream, Shorts, In-feed, Gmail, etc.)

#### Click Type
- `segments.click_type` - Type of click (Traffic, call, etc.)

#### Conversion Attribution
- `segments.conversion_action` - Conversion action ID
- `segments.conversion_action_category` - Conversion category
- `segments.conversion_action_name` - Conversion name
- `segments.conversion_attribution_event_type` (NEW v24) - CLICK, VIEW, ENGAGED_VIEW

---

### Audience & Demographics Segments

#### Location
- `segments.geo_target_constant` - Geographic location
- `segments.country_code` - Country code
- `segments.city` - City
- `segments.region` - Region/State
- `segments.metro` - Metropolitan area

#### Demographics
- `segments.age_range` - Age bracket
- `segments.gender` - Gender (Male, Female, Unknown)
- `segments.parental_status` - Parent status (Parent, Not parent, Unknown)

#### Keywords & Search Terms
- `segments.keyword` - Keyword ID
- `segments.keyword_matching_variant` - Keyword match type
- `segments.search_term` - Actual search term
- `segments.search_term_match_type` (NEW v24) - KEYWORD, BROAD_MATCH, AI_MAX, PERFORMANCE_MAX

---

### Product & Shopping Segments

#### Product Data (Shopping)
- `segments.product_aggregator_id` - Product aggregator ID
- `segments.product_brand` - Brand (from feed)
- `segments.product_category_id` - Product category
- `segments.product_channel` - Sales channel
- `segments.product_channel_exclusivity` - Channel exclusivity
- `segments.product_class` - Product class
- `segments.product_condition` - New/Used/Refurbished
- `segments.product_country` - Country of sale
- `segments.product_custom_attribute` - Custom feed attribute
- `segments.product_id` - Product ID
- `segments.product_item_id` - Item ID
- `segments.product_language` - Language
- `segments.product_title` - Product title
- `segments.product_type_l1` through `product_type_l5` - Category hierarchy

---

### Video & YouTube Segments

#### Video Engagement
- `segments.video` - YouTube video ID
- `segments.video_duration` - Video length
- `segments.video_id` - Video identifier
- `segments.video_partner_paid` - Partner network indicator

#### YouTube Targeting
- `segments.youtube_video` - Video ID from targeting
- `segments.youtube_channel` - Channel ID
- `segments.youtube_content_id` - Content ID

---

### Vertical Ads Segments (v24 New)

#### Travel & Vertical Ads
- `segments.vertical_ads_event_participant_display_names` - Participant names (Events)
- `segments.vertical_ads_hotel_class` - Hotel class rating
- `segments.vertical_ads_listing` - Listing ID
- `segments.vertical_ads_listing_brand` - Listing brand
- `segments.vertical_ads_listing_city` - Listing city
- `segments.vertical_ads_listing_country` - Listing country
- `segments.vertical_ads_listing_region` - Listing region
- `segments.vertical_ads_listing_user_rating` (NEW v24.1) - User rating
- `segments.vertical_ads_listing_venue` (NEW v24.1) - Venue information
- `segments.vertical_ads_partner_account` - Partner account
- `segments.vertical_ads_vertical` - Vertical type (Travel, Events, etc.)

---

### Quality & Landing Page Segments

#### Landing Page
- `segments.landing_page` - Landing page URL
- `segments.landing_page_source` - Landing page source type
- `segments.final_url` - Final destination URL
- `segments.feed_item_id` - Feed item ID
- `segments.feed_item_set_id` - Feed item set ID

#### Quality Metrics
- `segments.search_term_targeting_status` - Targeting status
- `segments.search_term_match_source` - Match source type

---

### Asset & Ad Type Segments

#### Asset Type
- `segments.asset_id` - Asset ID
- `segments.asset_type` - Asset type (Image, Video, Text, etc.)
- `segments.asset_interaction_target` - Asset interaction target
- `segments.asset_performance_label` - Performance label (removed v22+)
- `segments.served_asset_field_type` - Asset field being served

#### Ad Format
- `segments.ad_format_type` - Display format (Responsive, Text, etc.)

---

## 🔗 Resource-Metrics Compatibility Matrix

### Campaign Resource Metrics
Available metrics for: `SELECT metrics.* FROM campaign`
- All performance metrics (clicks, impressions, cost)
- All conversion metrics
- All CTR and engagement metrics
- Reach & frequency metrics
- Device and network segments

### Ad Group Resource Metrics
Available metrics for: `SELECT metrics.* FROM ad_group`
- All campaign metrics
- Additional asset performance metrics (v21+)
- Ad group specific breakdowns

### Keyword Resource Metrics
Available metrics for: `SELECT metrics.* FROM keyword_view`
- Performance metrics
- Conversion metrics
- Quality score
- Keyword-specific segments

### Ad Resource Metrics
Available metrics for: `SELECT metrics.* FROM ad_group_ad`
- All standard metrics
- Ad-specific performance data
- Asset field information

### Asset Resource Metrics
Available metrics for: `SELECT metrics.* FROM asset_group_asset`
- `metrics.engagements` (v23+)
- `metrics.engagement_rate` (v23+)
- `metrics.average_cpe` (v23+)
- Asset-specific performance

### Shopping Performance View
Available metrics for: `SELECT metrics.* FROM shopping_performance_view`
- Product-specific metrics
- Shopping network metrics
- Conversion attribution by product

### Search Term View
Available metrics for: `SELECT metrics.* FROM search_term_view`
- Search term performance
- Search term match type (v21+)
- Query clustering metrics

---

## 🔢 Common Query Examples for Dashboard

### 1. Daily Campaign Performance
```sql
SELECT
  segments.date,
  campaign.id,
  campaign.name,
  metrics.impressions,
  metrics.clicks,
  metrics.ctr,
  metrics.cost_micros,
  metrics.average_cpc,
  metrics.conversions,
  metrics.conversion_rate,
  metrics.cost_per_conversion
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
ORDER BY segments.date DESC
```

### 2. Ad Group by Device
```sql
SELECT
  segments.device,
  ad_group.id,
  ad_group.name,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.conversion_rate
FROM ad_group
WHERE segments.date DURING LAST_7_DAYS
ORDER BY metrics.conversions DESC
```

### 3. Conversion by Network
```sql
SELECT
  segments.ad_network_type,
  campaign.name,
  metrics.clicks,
  metrics.conversions,
  metrics.conversions_value,
  metrics.cost_per_conversion
FROM campaign
WHERE segments.date DURING THIS_MONTH
ORDER BY metrics.conversions_value DESC
```

### 4. Geographic Performance
```sql
SELECT
  segments.country_code,
  segments.region,
  metrics.impressions,
  metrics.clicks,
  metrics.ctr,
  metrics.conversions,
  metrics.conversion_rate
FROM geographic_view
WHERE segments.date DURING LAST_30_DAYS
  AND metrics.conversions > 0
ORDER BY metrics.conversions DESC
```

### 5. Product Performance (Shopping)
```sql
SELECT
  segments.product_brand,
  segments.product_category_id,
  segments.product_title,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.conversions_value
FROM shopping_performance_view
WHERE segments.date DURING LAST_30_DAYS
ORDER BY metrics.conversions_value DESC
```

### 6. Campaign Status & Budget
```sql
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.campaign_budget,
  metrics.cost_micros,
  metrics.clicks,
  metrics.impressions
FROM campaign
WHERE campaign.status IN ('ENABLED', 'PAUSED')
ORDER BY metrics.cost_micros DESC
```

---

## ⚠️ Important Notes for Dashboard Implementation

### Metric Availability by Version
- Check v24.1 release notes for new metrics
- Some metrics only available after certain date (check documentation)
- Older campaigns may not have all metrics

### Field Compatibility
- Not all segments work with all metrics
- Use Query Builder to validate combinations
- Use GoogleAdsFieldService to check compatibility

### Data Aggregation Rules
- Metrics without segments show daily data by default
- Adding segments creates additional rows per segment value
- NULL values indicate no data for that combination
- Use LIMIT during development to manage data volume

### Cost Representation
- All costs in `metrics.*_micros` - divide by 1,000,000 for display
- Different currencies stored separately
- Cost may be 0 if no clicks/conversions

### Conversion Metrics Nuances
- `conversions` vs `all_conversions`: First includes only conversion-tracking metrics, second includes all
- `conversions_by_conversion_date` groups by when conversion occurred, not click date
- Cross-device conversions may have different attribution

### Device Platform Updates (v24.1)
- `segments.mobile_device_platform` NEW field for iOS/Android breakdown
- Replace older device categorization where possible

---

## 🎯 Dashboard KPIs - Recommended Metrics to Track

### Essential Metrics (Core)
1. **CTR:** clicks / impressions
2. **CPC:** cost_micros / (1,000,000 * clicks)
3. **Conversion Rate:** conversions / clicks
4. **Cost per Conversion:** cost_micros / (1,000,000 * conversions)
5. **ROAS:** conversions_value / cost_micros
6. **Impression Share:** (Google-calculated segment)

### Secondary Metrics (For Depth)
1. **Engagement Rate:** engagements / impressions (v23+)
2. **Video View Rate:** video_trueview_views / impressions
3. **Active View Rate:** active_view_impressions / impressions
4. **Cross-Device Impact:** cross_device_conversions / conversions

### Segmentation Recommendations
1. **Time:** Daily, Weekly, Monthly
2. **Campaign Type:** Separate queries by campaign type
3. **Network:** Google Search vs Partner vs Display
4. **Device:** Desktop, Mobile, Tablet
5. **Geography:** Country or Region level
6. **Conversion:** By action type

---

## 📚 Resource Reference Links

- **Full Fields Reference:** https://developers.google.com/google-ads/api/fields/latest/overview
- **Query Cookbook:** https://developers.google.com/google-ads/api/docs/query/cookbook
- **Reporting Guide:** https://developers.google.com/google-ads/api/docs/reporting/overview
- **v24.1 Release Notes:** https://developers.google.com/google-ads/api/docs/release-notes

