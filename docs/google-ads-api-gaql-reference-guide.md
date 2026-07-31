# Google Ads Query Language (GAQL) - Complete Reference Guide v24.1

**API Version:** Google Ads API v24.1  
**Query Language:** GAQL (Google Ads Query Language)  
**Purpose:** Building read-only analytics dashboard queries  
**Last Updated:** June 15, 2026

---

## 📖 Table of Contents

1. [GAQL Overview](#overview)
2. [Query Syntax & Grammar](#syntax)
3. [SELECT Clause](#select)
4. [FROM Clause](#from)
5. [WHERE Clause & Operators](#where)
6. [ORDER BY & LIMIT](#ordering)
7. [Date Functions](#dates)
8. [Query Examples](#examples)
9. [Best Practices](#best_practices)
10. [Tools & Validation](#tools)

---

## Overview

GAQL is a SQL-like query language used to retrieve data from the Google Ads API. It allows you to query performance metrics, campaign data, conversions, audiences, and more for building dashboards.

### Key Features
- **SQL-like syntax** - familiar to developers
- **Real-time queries** - get current data immediately
- **Flexible filtering** - WHERE clauses with multiple operators
- **Segmentation** - group data by dimensions
- **Aggregation** - built-in metrics and calculations
- **Field validation** - GoogleAdsFieldService provides metadata

### What GAQL Can Query
✅ Campaign, ad group, and ad performance data  
✅ Metrics (impressions, clicks, cost, conversions)  
✅ Segments (date, device, geography, demographics)  
✅ Field metadata (via GoogleAdsFieldService)  

❌ Cannot create/update/delete (read-only)  
❌ Cannot write data back to API  

---

## Syntax & Grammar

### Basic Query Structure
```
SELECT [fields]
FROM [resource]
WHERE [conditions]
ORDER BY [ordering]
LIMIT [count]
```

### Complete GAQL Grammar (Formal)

```
Query -> SelectClause FromClause WhereClause? OrderByClause? LimitClause?

SelectClause -> SELECT FieldName (, FieldName)*
FromClause -> FROM ResourceName
WhereClause -> WHERE Condition (AND Condition)*
OrderByClause -> ORDER BY Ordering (, Ordering)*
LimitClause -> LIMIT PositiveInteger

Condition -> FieldName Operator Value
Operator -> = | != | > | >= | < | <= 
          | IN | NOT IN 
          | LIKE | NOT LIKE 
          | CONTAINS ANY | CONTAINS ALL | CONTAINS NONE
          | IS NULL | IS NOT NULL 
          | DURING | BETWEEN
          | REGEXP_MATCH | NOT REGEXP_MATCH

Value -> Literal | LiteralList | Number | NumberList 
       | String | StringList | DateFunction

Ordering -> FieldName (ASC | DESC)?

FieldName -> [a-z]([a-zA-Z0-9._])*
ResourceName -> [a-z]([a-zA-Z_])*

StringList -> ( String (, String)* )
LiteralList -> ( Literal (, Literal)* )
NumberList -> ( Number (, Number)* )

PositiveInteger -> [1-9]([0-9])*
Number -> -?[0-9]+(.[0-9][0-9]*)?
String -> ('Char*') | ("Char*")
Literal -> [a-zA-Z0-9_]*

DateFunction -> LAST_14_DAYS | LAST_30_DAYS | LAST_7_DAYS
              | LAST_BUSINESS_WEEK | LAST_MONTH 
              | LAST_WEEK_MON_SUN | LAST_WEEK_SUN_SAT
              | THIS_MONTH | THIS_WEEK_MON_TODAY | THIS_WEEK_SUN_TODAY
              | TODAY | YESTERDAY
```

### Syntax Rules

1. **Case Insensitivity:** Keywords like SELECT, FROM, WHERE are case-insensitive
2. **Field Names:** Always lowercase (e.g., `campaign.id`, `metrics.clicks`)
3. **String Literals:** Enclosed in single or double quotes
4. **Comments:** Not supported in GAQL
5. **Line Breaks:** Optional; whitespace generally ignored
6. **Commas:** Required between multiple selections and conditions
7. **AND Operator:** Multiple WHERE conditions joined by AND

---

## SELECT Clause

### Purpose
Specifies which fields to return in the result set.

### Syntax
```sql
SELECT field1, field2, field3
```

### Field Categories

#### Resource Fields (Campaign Data)
```sql
SELECT 
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  campaign.campaign_budget,
  campaign.bidding_strategy
```

#### Metric Fields (Performance Data)
```sql
SELECT 
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversion_value,
  metrics.ctr,
  metrics.average_cpc
```

#### Segment Fields (Dimensions/Groups)
```sql
SELECT 
  segments.date,
  segments.device,
  segments.ad_network_type,
  segments.geo_target_constant
```

#### Attributed Resource Fields (Implicit Joins)
```sql
SELECT 
  campaign.id,
  bidding_strategy.name,  -- Implicitly joined from campaign
  customer.descriptive_name -- Implicitly joined customer info
```

### Best Practices for SELECT

1. **Select Only What You Need**
   ```sql
   -- Good: Specific fields only
   SELECT campaign.id, campaign.name, metrics.clicks
   
   -- Avoid: Using * if not needed
   SELECT * FROM campaign  -- May timeout with large datasets
   ```

2. **Order Selection Logically**
   ```sql
   SELECT
     -- Resource fields first
     campaign.id,
     campaign.name,
     -- Then metrics
     metrics.impressions,
     metrics.clicks,
     -- Then segments
     segments.date
   ```

3. **Use Aliases for Clarity (Conceptual)**
   ```sql
   -- Clear field names help with parsing results
   SELECT
     campaign.id as campaign_id,
     metrics.clicks as total_clicks,
     metrics.cost_micros as cost_cents
   ```

---

## FROM Clause

### Purpose
Specifies the resource to query from.

### Available Resources (for Read-Only Dashboards)

#### Account Resources
- `customer` - Account-level data
- `customer_client` - Linked accounts
- `customer_asset_set` - Account asset sets

#### Campaign Resources
- `campaign` - Campaign data
- `campaign_budget` - Budget information
- `campaign_draft` - Draft campaigns
- `campaign_criterion` - Campaign targeting

#### Ad Group Resources
- `ad_group` - Ad group data
- `ad_group_ad` - Individual ads
- `ad_group_asset` - Ad group assets
- `ad_group_criterion` - Ad group targeting

#### Keyword Resources
- `keyword_view` - Keyword performance
- `search_term_view` - Search queries (v21+)

#### Asset Resources
- `asset` - Asset data
- `asset_group` - Asset groups
- `asset_group_asset` - Asset group assets

#### Audience Resources
- `audience` - Audience data
- `user_list` - Custom audiences
- `combined_audience` - Combined audience data

#### Performance Views (Reporting)
- `campaign_performance_max_view` - PMax metrics
- `shopping_performance_view` - Shopping data
- `geographic_view` - Geographic breakdown
- `user_location_view` - User location data
- `placement_view` - Ad placement data
- `search_term_view` - Search term data
- `asset_group_asset_view` - Asset performance
- `ad_group_ad_asset_view` - Ad asset performance

#### Special Views
- `change_history` - Change log
- `conversion_action` - Conversion tracking
- `conversion_action_category` - Conversion types
- `dynamic_search_ads_search_term_view` - DSA data

### Examples

```sql
-- Query campaign data
FROM campaign

-- Query ad group performance
FROM ad_group

-- Query search terms and performance
FROM search_term_view

-- Query geographic performance
FROM geographic_view

-- Query shopping campaign data
FROM shopping_performance_view
```

---

## WHERE Clause & Operators

### Purpose
Filters results to specific conditions.

### Syntax
```sql
WHERE condition1 AND condition2 AND condition3
```

### Operators

#### Comparison Operators

**Equals (=)**
```sql
WHERE campaign.status = 'ENABLED'
WHERE campaign.advertising_channel_type = 'SEARCH'
WHERE metrics.clicks = 100
```

**Not Equals (!=)**
```sql
WHERE campaign.status != 'REMOVED'
WHERE ad_group.status != 'PAUSED'
```

**Greater Than (>)**
```sql
WHERE metrics.impressions > 1000
WHERE metrics.cost_micros > 500000
WHERE campaign.id > 123456789
```

**Greater Than or Equal (>=)**
```sql
WHERE metrics.ctr >= 0.05
WHERE metrics.conversion_rate >= 0.02
```

**Less Than (<)**
```sql
WHERE metrics.clicks < 10
WHERE metrics.average_cpc < 250000
```

**Less Than or Equal (<=)**
```sql
WHERE metrics.impressions <= 500
WHERE campaign.id <= 987654321
```

#### List Operators

**IN (matches any value in list)**
```sql
WHERE campaign.advertising_channel_type IN 
  ('SEARCH', 'DISPLAY', 'SHOPPING')

WHERE campaign.status IN ('ENABLED', 'PAUSED')

WHERE segments.device IN ('MOBILE', 'TABLET')
```

**NOT IN (excludes values in list)**
```sql
WHERE campaign.status NOT IN ('REMOVED', 'UNKNOWN')

WHERE segments.ad_network_type NOT IN 
  ('CONTENT_NETWORK', 'INVALID')
```

#### String Matching

**LIKE (pattern matching with % and _)**
```sql
-- Starts with "Google"
WHERE campaign.name LIKE 'Google%'

-- Ends with "Campaign"
WHERE campaign.name LIKE '%Campaign'

-- Contains "Summer"
WHERE campaign.name LIKE '%Summer%'

-- Exactly 5 characters
WHERE campaign.name LIKE '_____'

-- Escape special characters with []
WHERE campaign.name LIKE '[[]Earth[_]Campaign[]]%'
```

**NOT LIKE**
```sql
WHERE campaign.name NOT LIKE '%Paused%'

WHERE campaign.name NOT LIKE 'Test%'
```

#### Array/Set Operators

**CONTAINS ANY (matches if any value matches)**
```sql
WHERE ad_group.targeting_setting CONTAINS ANY ('PLACEMENT')
```

**CONTAINS ALL (matches if all values present)**
```sql
WHERE ad_group.final_urls CONTAINS ALL ('https://example.com')
```

**CONTAINS NONE (matches if no values match)**
```sql
WHERE user_list.targeting_status CONTAINS NONE ('EXCLUDED')
```

#### NULL Operators

**IS NULL (field is empty)**
```sql
WHERE campaign.final_url_suffix IS NULL

WHERE ad_group.tracking_url_template IS NULL
```

**IS NOT NULL (field has value)**
```sql
WHERE campaign.final_url_suffix IS NOT NULL

WHERE ad_group.campaign_id IS NOT NULL
```

#### Date Operators

**DURING (within a date range)**
```sql
WHERE segments.date DURING LAST_30_DAYS

WHERE segments.date DURING LAST_7_DAYS

WHERE segments.date DURING THIS_MONTH
```

See [Date Functions](#dates) section for all date functions.

**BETWEEN (between two numeric values)**
```sql
WHERE metrics.ctr BETWEEN 0.05 AND 0.15

WHERE metrics.cost_micros BETWEEN 100000 AND 500000

WHERE campaign.id BETWEEN 111111111 AND 999999999
```

#### Regular Expression Operators

**REGEXP_MATCH (matches regex pattern)**
```sql
-- Uses RE2 syntax (not PCRE)
WHERE campaign.name REGEXP_MATCH 'Q[1-4]_[0-9]{4}'

WHERE campaign.name REGEXP_MATCH '(Jan|Feb|Mar).*2024'
```

**NOT REGEXP_MATCH**
```sql
WHERE campaign.name NOT REGEXP_MATCH 'test.*'
```

### Combining Conditions

```sql
WHERE campaign.status = 'ENABLED'
  AND metrics.impressions > 1000
  AND metrics.clicks > 50
  AND segments.date DURING LAST_30_DAYS

WHERE campaign.advertising_channel_type IN ('SEARCH', 'DISPLAY')
  AND campaign.status = 'ENABLED'
  AND metrics.conversions > 0
```

### Important Notes

- Use **AND** to combine multiple conditions (no OR currently)
- Field compatibility matters (check what segments work with metrics)
- NULL values treated as false in comparisons
- String comparisons are case-sensitive

---

## ORDER BY & LIMIT

### ORDER BY Clause

**Purpose:** Sort results in ascending or descending order

**Syntax:**
```sql
ORDER BY field1 ASC, field2 DESC
```

**Examples:**

```sql
-- Order by campaign name alphabetically
ORDER BY campaign.name ASC

-- Order by cost (highest first)
ORDER BY metrics.cost_micros DESC

-- Multiple sort criteria
ORDER BY segments.date DESC, metrics.conversions DESC

-- Default is ASC if not specified
ORDER BY campaign.id
```

**Best Practices:**

```sql
-- Get top performing campaigns
SELECT
  campaign.id,
  campaign.name,
  metrics.conversions
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
ORDER BY metrics.conversions DESC

-- Get most recent data
SELECT *
FROM campaign
WHERE campaign.status = 'ENABLED'
ORDER BY segments.date DESC

-- Sort by date, then by value
ORDER BY segments.date DESC, metrics.cost_micros DESC
```

### LIMIT Clause

**Purpose:** Limit number of results returned

**Syntax:**
```sql
LIMIT positive_integer
```

**Examples:**

```sql
-- Get top 10 campaigns
SELECT campaign.id, metrics.conversions
FROM campaign
ORDER BY metrics.conversions DESC
LIMIT 10

-- Development query (don't return huge result set)
SELECT * FROM campaign
LIMIT 1000

-- Pagination equivalent (mental note: no OFFSET in GAQL)
SELECT * FROM keyword_view
WHERE segments.date DURING LAST_30_DAYS
LIMIT 5000
```

**Important:**
- LIMIT must be a positive integer
- No OFFSET support; use filters or last_cursor patterns
- Always use LIMIT during development
- Default limit is 10,000 if not specified

---

## Date Functions

### Available Date Functions

All date functions go in the WHERE clause with the `DURING` operator.

#### Last N Days
```sql
WHERE segments.date DURING LAST_7_DAYS     -- Last 7 calendar days

WHERE segments.date DURING LAST_14_DAYS    -- Last 14 days

WHERE segments.date DURING LAST_30_DAYS    -- Last 30 days
```

#### Last Week
```sql
WHERE segments.date DURING LAST_WEEK_MON_SUN     -- Monday-Sunday

WHERE segments.date DURING LAST_WEEK_SUN_SAT     -- Sunday-Saturday

WHERE segments.date DURING LAST_BUSINESS_WEEK    -- Mon-Fri only
```

#### Last Month
```sql
WHERE segments.date DURING LAST_MONTH            -- Full last calendar month
```

#### Current Period
```sql
WHERE segments.date DURING THIS_MONTH            -- Current calendar month

WHERE segments.date DURING THIS_WEEK_MON_TODAY   -- Mon-Today of current week

WHERE segments.date DURING THIS_WEEK_SUN_TODAY   -- Sun-Today of current week

WHERE segments.date DURING TODAY                 -- Today only

WHERE segments.date DURING YESTERDAY             -- Yesterday only
```

### Date Function Examples

```sql
-- Compare this month vs last month (run two queries)

-- This month
SELECT campaign.name, metrics.conversions
FROM campaign
WHERE segments.date DURING THIS_MONTH

-- Last month
SELECT campaign.name, metrics.conversions
FROM campaign
WHERE segments.date DURING LAST_MONTH

-- Last 7 days filtered by network
SELECT
  segments.date,
  segments.ad_network_type,
  metrics.impressions,
  metrics.clicks
FROM campaign
WHERE segments.date DURING LAST_7_DAYS
  AND segments.ad_network_type IN ('SEARCH', 'DISPLAY')
ORDER BY segments.date DESC
```

---

## Query Examples

### Dashboard Queries for Different Views

#### 1. Daily Campaign Performance Dashboard

```sql
SELECT
  segments.date,
  campaign.id,
  campaign.name,
  campaign.status,
  metrics.impressions,
  metrics.clicks,
  metrics.ctr,
  metrics.cost_micros,
  metrics.average_cpc,
  metrics.conversions,
  metrics.conversion_rate,
  metrics.conversions_value,
  metrics.cost_per_conversion
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
  AND campaign.status = 'ENABLED'
ORDER BY segments.date DESC, metrics.cost_micros DESC
LIMIT 5000
```

#### 2. Device Performance Breakdown

```sql
SELECT
  segments.device,
  segments.mobile_device_platform,  -- v24.1 new field
  campaign.name,
  metrics.impressions,
  metrics.clicks,
  metrics.ctr,
  metrics.conversions,
  metrics.conversion_rate
FROM campaign
WHERE segments.date DURING LAST_7_DAYS
  AND metrics.impressions > 100
ORDER BY metrics.conversions DESC
```

#### 3. Geographic Performance

```sql
SELECT
  segments.country_code,
  segments.region,
  segments.city,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.conversions_value,
  metrics.ctr
FROM geographic_view
WHERE segments.date DURING LAST_30_DAYS
  AND metrics.conversions > 0
ORDER BY metrics.conversions_value DESC
LIMIT 100
```

#### 4. Top Performing Search Terms

```sql
SELECT
  segments.search_term,
  metrics.impressions,
  metrics.clicks,
  metrics.ctr,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversion_rate
FROM search_term_view
WHERE segments.date DURING LAST_30_DAYS
  AND metrics.impressions > 50
ORDER BY metrics.conversions DESC
LIMIT 500
```

#### 5. Shopping Campaign Product Performance

```sql
SELECT
  segments.product_brand,
  segments.product_category_id,
  segments.product_title,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.conversions_value,
  metrics.cost_micros
FROM shopping_performance_view
WHERE segments.date DURING THIS_MONTH
  AND campaign.advertising_channel_type = 'SHOPPING'
ORDER BY metrics.conversions_value DESC
LIMIT 1000
```

#### 6. Conversion Action Performance

```sql
SELECT
  segments.conversion_action,
  segments.conversion_action_category,
  metrics.conversions,
  metrics.conversions_value,
  metrics.cost_per_conversion
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
  AND metrics.conversions > 0
  AND segments.conversion_action IS NOT NULL
ORDER BY metrics.conversions_value DESC
```

#### 7. Ad Network Comparison

```sql
SELECT
  segments.ad_network_type,
  segments.ad_sub_network_type,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
  AND campaign.advertising_channel_type = 'DISPLAY'
ORDER BY metrics.cost_micros DESC
```

#### 8. Quality Score Analysis

```sql
SELECT
  ad_group.id,
  ad_group.name,
  metrics.quality_score,
  metrics.impressions,
  metrics.ctr,
  metrics.average_cpc
FROM keyword_view
WHERE segments.date DURING LAST_30_DAYS
  AND metrics.quality_score < 7
ORDER BY metrics.ctr ASC
LIMIT 500
```

#### 9. Conversion Funnel (Click to Conversion)

```sql
SELECT
  campaign.name,
  metrics.clicks,
  metrics.conversions,
  metrics.conversion_rate,
  metrics.conversions_value,
  metrics.cost_per_conversion
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
  AND metrics.clicks > 0
ORDER BY metrics.conversions DESC
```

#### 10. Month-over-Month Comparison (Separate Queries)

```sql
-- This Month
SELECT
  campaign.name,
  SUM(metrics.conversions) as conversions,
  SUM(metrics.conversions_value) as value,
  SUM(metrics.cost_micros) / 1000000.0 as cost
FROM campaign
WHERE segments.date DURING THIS_MONTH
GROUP BY campaign.id, campaign.name

-- Last Month
SELECT
  campaign.name,
  SUM(metrics.conversions) as conversions,
  SUM(metrics.conversions_value) as value,
  SUM(metrics.cost_micros) / 1000000.0 as cost
FROM campaign
WHERE segments.date DURING LAST_MONTH
GROUP BY campaign.id, campaign.name
```

Note: GAQL doesn't support GROUP BY/aggregation directly; aggregate in application code.

---

## Best Practices

### 1. Performance Optimization

```sql
-- Good: Specific filters reduce data transfer
SELECT campaign.name, metrics.clicks
FROM campaign
WHERE campaign.status = 'ENABLED'
  AND segments.date DURING LAST_7_DAYS
  AND metrics.clicks > 0

-- Avoid: Massive unfiltered queries
SELECT * FROM campaign
-- No filters = millions of rows
```

### 2. Field Compatibility

```sql
-- Check that fields work together using GoogleAdsFieldService
-- Good: Compatible fields
SELECT
  campaign.id,
  metrics.clicks,
  segments.device
FROM campaign

-- Verify compatibility before using:
-- - Not all segments work with all metrics
-- - Some fields only available for certain campaign types
-- - Refer to fields reference for compatibility matrix
```

### 3. Null Handling

```sql
-- Explicitly handle null values
WHERE campaign.final_url_suffix IS NOT NULL

-- Account for missing data
WHERE metrics.conversions IS NOT NULL
  OR metrics.conversions = 0
```

### 4. Cost Calculation

```sql
-- Always remember costs are in MICROS (millionths)
SELECT
  campaign.name,
  metrics.cost_micros / 1000000.0 as cost_usd,
  metrics.clicks,
  (metrics.cost_micros / metrics.clicks) / 1000000.0 as cpc
FROM campaign
```

### 5. Rate Limits & Quotas

```sql
-- Use LIMIT to avoid processing huge datasets
LIMIT 10000  -- Default is 10,000

-- Check API quotas for your developer token
-- SearchStream recommended for large result sets
```

### 6. Date Range Selection

```sql
-- Be specific with date ranges
WHERE segments.date DURING LAST_30_DAYS

-- Not:
WHERE segments.date > '2024-01-01'  -- Syntax error
WHERE segments.date >= 20240101     -- Not supported

-- Use predefined date functions
```

### 7. Testing & Validation

```sql
-- Use LIMIT during development
WHERE segments.date DURING LAST_7_DAYS
LIMIT 100

-- Validate query with Query Validator
-- https://developers.google.com/google-ads/api/fields/latest/query_validator

-- Use Query Builder for construction help
-- https://developers.google.com/google-ads/api/fields/latest/overview_query_builder
```

---

## Tools & Validation

### Interactive Query Builder
**URL:** https://developers.google.com/google-ads/api/fields/latest/overview_query_builder

**Features:**
- Drag-and-drop query construction
- Real-time field suggestions
- Compatibility checking
- Query preview
- Copy generated GAQL

### Query Validator
**URL:** https://developers.google.com/google-ads/api/fields/latest/query_validator

**Purpose:**
- Validate GAQL syntax
- Check field compatibility
- Suggest corrections
- Error messages

### Recommended Workflow
1. Use **Query Builder** to construct new queries
2. Use **Query Validator** to test before implementation
3. Copy validated query into dashboard code
4. Test with small LIMIT first
5. Scale up LIMIT after validation

---

## Common Query Patterns

### Pattern 1: Top Campaigns by Metric
```sql
SELECT campaign.id, campaign.name, metrics.conversions
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
ORDER BY metrics.conversions DESC
LIMIT 10
```

### Pattern 2: Comparative Analysis
```sql
-- Run twice (one for THIS_MONTH, one for LAST_MONTH)
SELECT
  campaign.name,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.conversions_value
FROM campaign
WHERE segments.date DURING THIS_MONTH
```

### Pattern 3: Segmented Performance
```sql
SELECT
  segments.date,
  segments.device,
  metrics.impressions,
  metrics.conversions
FROM campaign
WHERE segments.date DURING LAST_7_DAYS
ORDER BY segments.date DESC, segments.device
```

### Pattern 4: Filtering by Performance
```sql
SELECT campaign.name, metrics.ctr
FROM campaign
WHERE metrics.impressions > 1000
  AND metrics.ctr < 0.02  -- Below average CTR
  AND segments.date DURING LAST_30_DAYS
```

### Pattern 5: Multiple Conditions
```sql
SELECT campaign.name, metrics.cost_per_conversion
FROM campaign
WHERE campaign.status = 'ENABLED'
  AND campaign.advertising_channel_type IN ('SEARCH', 'SHOPPING')
  AND metrics.conversions > 0
  AND segments.date DURING LAST_30_DAYS
ORDER BY metrics.cost_per_conversion ASC
```

---

## Troubleshooting Common GAQL Errors

### Error: "Field not found"
- Check field name spelling (case-sensitive)
- Verify field exists in v24.1 (check release notes)
- Use Query Validator to find correct field names

### Error: "Invalid field combination"
- Not all segments work with all resources
- Use GoogleAdsFieldService to check compatibility
- Refer to fields reference compatibility matrix

### Error: "Syntax error in WHERE clause"
- Ensure all string values in quotes: `'value'`
- Use AND between conditions (no OR)
- Check operator syntax (DURING, BETWEEN, IN)

### Error: "Query timeout"
- Add more specific WHERE filters
- Reduce date range
- Use LIMIT to restrict results
- Consider SearchStream for large result sets

### Error: "Invalid operator for this field"
- Some operators only work with specific field types
- LIKE only works on string fields
- DURING only works on date fields
- BETWEEN works on numeric fields

---

## Reference Links

- **GAQL Overview:** https://developers.google.com/google-ads/api/docs/query/overview
- **Query Grammar:** https://developers.google.com/google-ads/api/docs/query/grammar
- **Query Structure:** https://developers.google.com/google-ads/api/docs/query/structure
- **Query Cookbook:** https://developers.google.com/google-ads/api/docs/query/cookbook
- **Fields Reference:** https://developers.google.com/google-ads/api/fields/latest/overview
- **Query Builder:** https://developers.google.com/google-ads/api/fields/latest/overview_query_builder
- **Query Validator:** https://developers.google.com/google-ads/api/fields/latest/query_validator

