# DashMet — Sync Worker Logic Specification

> **Version:** 0.1  
> **Status:** Draft  
> **Stack:** Python 3.12 · FastAPI 0.115 · Celery 5.4 · Redis 7 · PostgreSQL 16  
> **Scope:** Background sync layer that fetches from Meta Ads API and writes to the internal schema.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Job Types](#2-job-types)
3. [Scheduling Strategy](#3-scheduling-strategy)
4. [Fetch Strategy (what to call and when)](#4-fetch-strategy)
5. [Rate Limit Handling](#5-rate-limit-handling)
6. [Error Handling & Retry Logic](#6-error-handling--retry-logic)
7. [Async Insights Jobs (Meta)](#7-async-insights-jobs-meta)
8. [Data Ingestion Pipeline](#8-data-ingestion-pipeline)
9. [Worker Task Definitions (Pseudocode)](#9-worker-task-definitions)
10. [Sync State Machine](#10-sync-state-machine)
11. [Configuration Reference](#11-configuration-reference)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                     Celery Beat                      │
│           (scheduler — runs periodic tasks)          │
└────────────────────┬─────────────────────────────────┘
                     │ enqueues tasks
                     ▼
┌──────────────────────────────────────────────────────┐
│                  Redis (broker)                      │
│         queue: sync.structure                        │
│         queue: sync.insights                         │
│         queue: sync.async_poll                       │
│         queue: sync.creatives                        │
└────────────────────┬─────────────────────────────────┘
                     │ consumes tasks
                     ▼
┌──────────────────────────────────────────────────────┐
│              Celery Workers (N processes)            │
│                                                      │
│  StructureWorker   InsightsWorker   PollWorker        │
│  (1 concurrency)   (2 concurrency)  (1 concurrency)  │
└────────────────────┬─────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   Meta Graph API v25.0    PostgreSQL DB
   (rate-limited)          (internal schema)
```

**Key principle:** Workers never call the Meta API in response to a user request. The dashboard reads only from the DB. All API calls happen in background workers on a schedule.

**Multi-tenancy:** Every job is scoped to a specific `account_id`, which belongs to an `organization_id`. The worker resolves the correct `access_token` from `platform_connections` for that org before making any API call. Jobs from different orgs are fully isolated — a rate limit or failure in one org's jobs does not affect another's.

**Redis serves two roles:**
- Celery message broker (task queue)
- Cache layer (rate limit state, in-progress job IDs, per-account throttle counters)

---

## 2. Job Types

| Job type | Celery task name | What it does | Trigger |
|---|---|---|---|
| Structure sync | `sync.structure` | Fetches campaigns, ad sets, ads | Periodic (30 min) |
| Insights sync | `sync.insights_daily` | Fetches scalar + action metrics | Periodic (15 min) |
| Breakdown sync | `sync.insights_breakdown` | Fetches metrics split by dimension | On-demand |
| Async job submit | `sync.async_submit` | POSTs async insights job to Meta | Periodic (60 min) for 90d/lifetime |
| Async job poll | `sync.async_poll` | Polls `report_run_id` until complete | Periodic (2 min, conditional) |
| Creative sync | `sync.creatives` | Fetches ad creative content | On-demand (first drill-in) |

Each job creates a `sync_jobs` row on start and updates it on completion/failure.

---

## 3. Scheduling Strategy

### Celery Beat schedule

```python
CELERYBEAT_SCHEDULE = {

    # Structural data — campaigns, ad sets, ads
    "sync-structure-all-accounts": {
        "task": "sync.structure",
        "schedule": crontab(minute="*/30"),   # every 30 min
        "args": [],                            # fetches all active accounts
    },

    # Insights — daily metrics for active accounts (last 7d window)
    "sync-insights-active": {
        "task": "sync.insights_daily",
        "schedule": crontab(minute="*/15"),   # every 15 min
        "kwargs": {"date_preset": "last_7d", "level": "campaign"},
    },

    # Insights — wider window, runs less often
    "sync-insights-last-30d": {
        "task": "sync.insights_daily",
        "schedule": crontab(minute=0, hour="*/2"),  # every 2 hours
        "kwargs": {"date_preset": "last_30d", "level": "campaign"},
    },

    # Async jobs for 90d+ data
    "sync-insights-async": {
        "task": "sync.async_submit",
        "schedule": crontab(minute=0, hour="*/6"),  # every 6 hours
        "kwargs": {"date_preset": "last_90d"},
    },

    # Poll pending async jobs
    "poll-async-jobs": {
        "task": "sync.async_poll",
        "schedule": crontab(minute="*/2"),    # every 2 min
    },
}
```

### TTL enforcement (don't re-fetch if fresh)

Before each fetch, the worker checks the last `completed_at` for that job type + account + date range against the TTL. If fresh, it skips.

```python
def is_stale(account_id, job_type, ttl_minutes):
    last_sync = db.query(
        "SELECT completed_at FROM sync_jobs "
        "WHERE account_id = %s AND job_type = %s AND status = 'completed' "
        "ORDER BY completed_at DESC LIMIT 1",
        [account_id, job_type]
    )
    if not last_sync:
        return True
    age = datetime.utcnow() - last_sync.completed_at
    return age.total_seconds() > ttl_minutes * 60
```

---

## 4. Fetch Strategy

### Guiding rules

1. **Account level before campaign level.** Fetch account-level insights first (one call covers everything). Only drill to campaign/ad level when needed.
2. **Use `level=` param, not N separate calls.** `GET /act_{id}/insights?level=campaign` returns all campaigns in one call — far better than a separate call per campaign.
3. **Batch structure fetches.** Use Meta's batch endpoint to fetch campaigns + ad sets + ads in a single HTTP request (counts as one API call).
4. **Separate unique from non-unique.** Never mix `reach`, `unique_clicks` with non-unique metrics in the same call — it degrades performance significantly. Two calls per sync.
5. **Async for anything over 30 days.** Sync calls timeout on large date ranges. Use the async submit → poll → fetch pattern.

### Structure fetch order

```
1. GET /me/adaccounts                          → upsert accounts
2. BATCH [
     GET /act_{id}/campaigns?fields=...        → upsert campaigns
     GET /act_{id}/adsets?fields=...           → upsert ad_groups
     GET /act_{id}/ads?fields=id,name,status,
               adset_id,campaign_id,creative{id}  → upsert ads + creative IDs
   ]
```

Pagination: follow `paging.next` until absent. Use `limit=100`.

### Insights fetch order (per account, per sync cycle)

```
Call 1 — non-unique scalars:
  GET /act_{id}/insights
    ?fields=impressions,clicks,spend,ctr,cpm,cpc,cpp,
            frequency,inline_link_clicks,
            actions,action_values,cost_per_action_type,
            purchase_roas,website_purchase_roas,
            video_play_actions,video_p25_watched_actions,
            video_p50_watched_actions,video_p75_watched_actions,
            video_p100_watched_actions,video_thruplay_watched_actions,
            video_avg_time_watched_actions
    &level=campaign
    &date_preset=last_7d
    &time_increment=1     ← one row per day

Call 2 — unique metrics (separate call, slower):
  GET /act_{id}/insights
    ?fields=reach,unique_clicks,unique_inline_link_clicks,unique_ctr
    &level=campaign
    &date_preset=last_7d
    &time_increment=1
```

Both calls write to the same `metrics_daily` rows via upsert — they merge, not overwrite.

### Breakdown fetches (on-demand only)

Breakdowns are NOT included in the periodic sync. They are triggered when a user navigates to a breakdown view in the dashboard. The API request is made once, result cached in `metric_breakdowns`, TTL 30 minutes.

Supported on-demand breakdowns:
- `age,gender` (always fetched together as a compound)
- `country`
- `publisher_platform,platform_position` (always together)
- `device_platform`

---

## 5. Rate Limit Handling

### Response header inspection

After **every** Meta API response, extract and process rate limit headers:

```python
import json
import time

class RateLimitState:
    """Persisted in Redis, keyed by account_id."""

    def update_from_response(self, account_id, response):
        headers = response.headers

        # Insights throttle
        insights = headers.get("X-FB-Ads-Insights-Throttle")
        if insights:
            data = json.loads(insights)
            self._store(account_id, "insights_app_pct",  data.get("app_id_util_pct", 0))
            self._store(account_id, "insights_acc_pct",  data.get("acc_id_util_pct", 0))
            self._store(account_id, "access_tier",       data.get("ads_api_access_tier"))

        # Structure throttle
        usage = headers.get("X-Ad-Account-Usage")
        if usage:
            data = json.loads(usage)
            self._store(account_id, "structure_acc_pct",   data.get("acc_id_util_pct", 0))
            self._store(account_id, "quota_reset_seconds", data.get("reset_time_duration", 3600))

        # General app limit
        app_usage = headers.get("X-App-Usage")
        if app_usage:
            data = json.loads(app_usage)
            self._store(account_id, "app_call_count", data.get("call_count", 0))
```

### Back-off thresholds

| Metric | Threshold | Action |
|---|---|---|
| `insights_app_pct` | > 80% | Sleep 30s before next insights call |
| `insights_app_pct` | > 95% | Sleep 300s — hard pause |
| `insights_acc_pct` | > 80% | Sleep 30s |
| `structure_acc_pct` | > 80% | Sleep 30s before next structure call |
| `app_call_count` | > 80 | Sleep 60s |

```python
def apply_backoff(account_id):
    state = RateLimitState.load(account_id)

    if state.insights_app_pct > 95:
        logger.warning(f"[{account_id}] Hard rate limit pause (5 min)")
        time.sleep(300)
        return

    if state.insights_app_pct > 80 or state.insights_acc_pct > 80:
        logger.info(f"[{account_id}] Soft rate limit back-off (30s)")
        time.sleep(30)

    if state.structure_acc_pct > 80:
        time.sleep(30)
```

**This function is called before every API call, not just on error.** Proactive throttling prevents hitting hard limits.

### Development tier awareness

Development tier limit: `600 + 400 × active_ads` per hour.  
Standard tier limit: `190,000 + 400 × active_ads` per hour.

During development, set a conservative `CALLS_PER_MINUTE_CAP = 5` in config and enforce it via a token bucket in Redis. Remove the cap in production after applying for standard_access.

```python
# Token bucket in Redis
def acquire_api_token(account_id, tier="development"):
    cap = 5 if tier == "development" else 50  # calls per minute
    key = f"rate_bucket:{account_id}"
    # Lua script: increment counter with 60s expiry
    allowed = redis.eval(TOKEN_BUCKET_SCRIPT, 1, key, cap)
    if not allowed:
        time.sleep(60 / cap)  # wait for slot
```

---

## 6. Error Handling & Retry Logic

### Celery retry configuration (base)

```python
@app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,     # 1 min base
    autoretry_for=(requests.exceptions.ConnectionError,),
    retry_backoff=True,          # exponential: 60, 120, 240, 480, 960s
    retry_backoff_max=900,       # cap at 15 min
    retry_jitter=True,           # add randomness to avoid thundering herd
)
def sync_insights_daily(self, account_id, ...):
    ...
```

### Meta API error codes → actions

| Code | Subcode | Meaning | Action |
|---|---|---|---|
| `190` | any | Invalid / expired token | Alert operator — do not retry automatically. Token must be re-generated. |
| `200` | any | Insufficient permissions | Alert operator — token missing `ads_read` or `read_insights`. |
| `4` | `1504022` | App-level insights rate limit | Exponential back-off. Retry after `2^attempt × 10s`. |
| `4` | `1504039` | Too many app calls | Same as above. |
| `4` | *(none)* | Generic app limit | Back-off 60s, retry. |
| `17` | — | User rate limit | Back-off 60s, retry. |
| `100` | `1487534` | Too much data per call | Narrow the date range (split into two calls), or switch to async. Do not retry as-is. |
| `1` | — | Timeout (sync) | Switch to async job automatically. |
| `613` | — | Custom rate limit | Back-off 120s, retry. |

```python
def handle_api_error(self, response_json, account_id):
    error = response_json.get("error", {})
    code = error.get("code")
    subcode = error.get("error_subcode")
    fbtrace_id = error.get("fbtrace_id")

    logger.error(f"Meta API error code={code} subcode={subcode} trace={fbtrace_id}")

    # Token errors — don't retry, alert
    if code == 190 or code == 200:
        notify_operator(account_id, error)
        raise PermanentError(f"Token error for account {account_id}: {error['message']}")

    # Too much data — narrow and retry
    if code == 100 and subcode == 1487534:
        raise NarrowRangeError("Response too large — caller must split date range")

    # Timeout — escalate to async
    if code == 1:
        raise EscalateToAsyncError("Sync call timed out")

    # Rate limits — exponential back-off via Celery retry
    if code in (4, 17, 613):
        attempt = self.request.retries
        wait = min((2 ** attempt) * 10, 900)
        raise self.retry(countdown=wait)

    # Unknown error
    raise self.retry(countdown=60)
```

### Permanent errors vs transient errors

| Error type | Behavior |
|---|---|
| **Permanent** (token invalid, no permission) | Mark `sync_jobs.status = 'failed'`, set `error_message`, notify operator, do not retry |
| **Transient** (rate limit, timeout, network) | Retry with exponential back-off up to `max_retries` |
| **Data error** (too much data) | Split the request into smaller chunks and requeue |

---

## 7. Async Insights Jobs (Meta)

Use async when:
- `date_preset` is `last_90d`, `last_year`, or `lifetime`
- Sync call returns error code `1` (timeout)
- Request includes 2+ breakdowns

### Flow

```
Step 1: Submit
  POST /v25.0/act_{id}/insights
    ?level=ad
    &fields=...
    &date_preset=last_90d
    → { "report_run_id": "6023920149050" }
  
  → Store report_run_id in sync_jobs.platform_job_id
  → Set sync_jobs.status = 'running'

Step 2: Poll (runs every 2 min via sync.async_poll)
  GET /v25.0/{report_run_id}
  → { "async_status": "Job Running", "async_percent_completion": 45 }
  
  Status mapping:
    "Job Not Started" | "Job Started" | "Job Running" → keep polling
    "Job Completed"                                   → proceed to Step 3
    "Job Failed"                                      → resubmit with simpler query
    "Job Skipped"                                     → expired (>30d), resubmit

Step 3: Fetch
  GET /v25.0/{report_run_id}/insights
    ?limit=200
  → paginate through all results
  → upsert into metrics_daily + metric_action_stats
  → set sync_jobs.status = 'completed'
```

### Poll task logic

```python
@app.task(name="sync.async_poll")
def poll_async_jobs():
    # Find all running async jobs
    running_jobs = db.query(
        "SELECT * FROM sync_jobs WHERE job_type = 'insights_async' "
        "AND status = 'running' AND platform_job_id IS NOT NULL"
    )

    for job in running_jobs:
        status_response = meta_client.get(f"/{job.platform_job_id}")
        async_status = status_response["async_status"]
        pct = status_response.get("async_percent_completion", 0)

        if async_status == "Job Completed":
            fetch_async_results.delay(job.id, job.platform_job_id)

        elif async_status == "Job Failed":
            # Resubmit with narrower query (split date range in half)
            resubmit_async_job.delay(job.id, split_date_range=True)

        elif async_status == "Job Skipped":
            # Expired — resubmit fresh
            resubmit_async_job.delay(job.id, split_date_range=False)

        # else: still running — do nothing, poll again next cycle
        logger.info(f"Async job {job.platform_job_id}: {async_status} ({pct}%)")
```

### report_run_id expiry

`report_run_id` expires after 30 days. Never store it as a permanent reference. The `sync_jobs.platform_job_id` column holds it temporarily — once the job reaches `completed` or `failed`, the ID is no longer needed.

---

## 8. Data Ingestion Pipeline

Each API response goes through a standard pipeline before hitting the DB:

```
Raw API response JSON
        │
        ▼
[1] Validate & log
    - Check for error object first
    - Log fbtrace_id on any non-200
    - Record rate limit headers (→ RateLimitState)

        │
        ▼
[2] Normalize
    - Parse string numbers to float/int ("12400" → 12400)
    - Convert date strings to date objects
    - Map platform status values to internal enum
      ("ACTIVE" → "active", "PAUSED" → "paused")
    - Normalize objective names
      ("OUTCOME_SALES" → "sales")
    - Map currency cents to units if needed (Meta: already in units)

        │
        ▼
[3] Split scalars from action stats
    - Scalar fields  → metrics_daily row dict
    - list<AdsActionStats> fields → metric_action_stats row list

        │
        ▼
[4] Upsert to DB
    - metrics_daily: upsert on (entity_type, entity_id, date)
      MERGE non-null fields only — unique + non-unique fetches
      both write to same row without overwriting each other
    - metric_action_stats: upsert on (entity_id, date, field_name, action_type)
    - Update sync_jobs: set status='completed', rows_written=N, completed_at=now()
```

### Parsing `list<AdsActionStats>`

```python
ACTION_STAT_FIELDS = {
    "actions", "action_values", "unique_actions",
    "cost_per_action_type", "cost_per_unique_action_type",
    "conversions", "conversion_values", "cost_per_conversion",
    "purchase_roas", "website_purchase_roas", "mobile_app_purchase_roas",
    "outbound_clicks", "unique_outbound_clicks", "cost_per_outbound_click",
    "video_play_actions", "video_avg_time_watched_actions",
    "video_continuous_2_sec_watched_actions", "video_thruplay_watched_actions",
    "video_p25_watched_actions", "video_p50_watched_actions",
    "video_p75_watched_actions", "video_p100_watched_actions",
    "results", "cost_per_result",
}

def parse_insight_row(entity_type, entity_id, date, raw_row):
    scalars = {}
    action_stats = []

    for field, value in raw_row.items():
        if field in ACTION_STAT_FIELDS:
            # value is a list: [{"action_type": "purchase", "value": "12"}, ...]
            for item in (value or []):
                action_stats.append({
                    "entity_type":  entity_type,
                    "entity_id":    entity_id,
                    "date":         date,
                    "field_name":   field,
                    "action_type":  item["action_type"],
                    "value":        float(item["value"]),
                })
        else:
            scalars[field] = _coerce(value)

    return scalars, action_stats


def _coerce(value):
    """Parse Meta's string-typed numeric fields."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        pass
    try:
        return float(value)
    except (ValueError, TypeError):
        pass
    return value  # leave as string (dates, IDs, enums)
```

### Upsert strategy

Use `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL). Only update non-null incoming values — this allows the two separate fetches (unique vs non-unique metrics) to merge into one row:

```sql
INSERT INTO metrics_daily (entity_type, entity_id, date, impressions, clicks, spend, reach, ...)
VALUES (%s, %s, %s, %s, %s, %s, %s, ...)
ON CONFLICT (entity_type, entity_id, date)
DO UPDATE SET
  impressions  = COALESCE(EXCLUDED.impressions, metrics_daily.impressions),
  clicks       = COALESCE(EXCLUDED.clicks,      metrics_daily.clicks),
  spend        = COALESCE(EXCLUDED.spend,       metrics_daily.spend),
  reach        = COALESCE(EXCLUDED.reach,       metrics_daily.reach),
  fetched_at   = NOW();
```

The `COALESCE(EXCLUDED.x, metrics_daily.x)` pattern means incoming nulls never overwrite existing data — the two partial fetches safely compose.

---

## 9. Worker Task Definitions

High-level pseudocode for each major task.

### `sync.structure` (runs every 30 min)

```
for each active account:
    skip if not stale (TTL: 30 min)
    create sync_job(type='structure', status='running')
    token = db.get_decrypted_token(account.platform_connection_id)
    apply_backoff(account_id)

    # Batch: campaigns + ad_groups + ads in one HTTP call
    batch_response = meta_client.batch([
        build_campaigns_request(account_id),
        build_adgroups_request(account_id),
        build_ads_request(account_id),
    ])

    for each response in batch_response:
        check_api_error(response)
        update_rate_limit_state(account_id, response.headers)
        paginate_and_upsert(response)

    update sync_job(status='completed', rows_written=N)
```

### `sync.insights_daily` (runs every 15 min)

```
for each active account:
    skip if not stale (TTL: 15 min)
    create sync_job(type='insights_daily', status='running')
    token = db.get_decrypted_token(account.platform_connection_id)

    # Call 1: non-unique metrics
    apply_backoff(account_id)
    response = meta_client.get_insights(
        account_id,
        fields=NON_UNIQUE_FIELDS,
        level='campaign',
        date_preset=date_preset,
        time_increment=1
    )
    check_api_error(response)
    update_rate_limit_state(account_id, response.headers)
    rows = paginate_all(response)
    for row in rows:
        scalars, action_stats = parse_insight_row(...)
        upsert_metrics_daily(scalars)
        bulk_upsert_action_stats(action_stats)

    # Call 2: unique metrics (separate — performance)
    apply_backoff(account_id)
    response = meta_client.get_insights(
        account_id,
        fields=UNIQUE_FIELDS,  # reach, unique_clicks, unique_ctr, ...
        level='campaign',
        date_preset=date_preset,
        time_increment=1
    )
    check_api_error(response)
    # Upsert merges into same rows via COALESCE
    rows = paginate_all(response)
    for row in rows:
        upsert_metrics_daily(parse_scalars_only(row))

    update sync_job(status='completed')
```

### `sync.async_submit` (runs every 6 hours)

```
for each active account:
    skip if an async job for this account + date_preset is already running or fresh

    create sync_job(type='insights_async', status='running')

    response = meta_client.post_insights_async(
        account_id,
        fields=FULL_AD_LEVEL_FIELDS,
        level='ad',
        date_preset='last_90d'
    )
    check_api_error(response)

    report_run_id = response['report_run_id']
    update sync_job(platform_job_id=report_run_id)
    # Polling handled separately by sync.async_poll
```

### `sync.creatives` (on-demand)

```
# Triggered when user first views an ad's creative
def sync_creative(ad_id):
    ad = db.get_ad(ad_id)
    if ad.creative_id and creative_is_fresh(ad.creative_id, ttl=3600):
        return  # already cached

    apply_backoff(ad.account_id)
    response = meta_client.get(
        f"/{ad.platform_creative_id}",
        fields="id,name,title,body,image_url,thumbnail_url,"
               "video_id,call_to_action_type,object_story_spec,asset_feed_spec"
    )
    check_api_error(response)
    creative = parse_creative(response)
    upsert_creative(creative)
    link_creative_to_ad(ad_id, creative.id)
```

---

## 10. Sync State Machine

Each `sync_job` row moves through these states:

```
            ┌──────────────────────────────────────────┐
            │                                          │
   enqueue  ▼     start      ┌──────────┐   success   ▼
  ─────────> pending ──────> in_progress ──────────> completed
                                  │                    
                                  │ error (permanent)  
                                  ▼                    
                               failed ──────> notify operator
                                  │                    
                                  │ error (transient)  
                                  ▼                    
                              [Celery retry queue]     
                                  │                    
                                  │ max retries hit    
                                  ▼                    
                               failed (final)          
```

For async jobs specifically:

```
   submitted   polling          results ready
  ──────────> running ─────────────────────> completed
                 │
                 │ "Job Failed" from Meta
                 ▼
              failed → resubmit with simpler query (auto)
                 │
                 │ "Job Skipped" (expired)
                 ▼
              skipped → resubmit fresh (auto)
```

---

## 11. Configuration Reference

All values in environment variables or a config table per account.

| Config key | Default | Notes |
|---|---|---|
| `META_ACCESS_TOKEN` | — | **Not used.** Tokens are stored per org in `platform_connections.access_token` (encrypted). The worker reads the token from the DB at job execution time — never from env. |
| `META_API_VERSION` | `v25.0` | Bump when upgrading |
| `SYNC_STRUCTURE_TTL_MINUTES` | `30` | Skip structure sync if fresher than this |
| `SYNC_INSIGHTS_TTL_MINUTES` | `15` | Skip insights sync if fresher than this |
| `SYNC_CREATIVE_TTL_MINUTES` | `60` | Creative cache duration |
| `RATE_LIMIT_SOFT_THRESHOLD` | `80` | % utilization before 30s back-off |
| `RATE_LIMIT_HARD_THRESHOLD` | `95` | % utilization before 5 min pause |
| `DEV_MODE_CALLS_PER_MINUTE` | `5` | Token bucket cap in development tier |
| `ASYNC_POLL_INTERVAL_SECONDS` | `120` | How often async poll task runs |
| `MAX_PAGINATION_PAGES` | `50` | Safety cap on paginated requests |
| `INSIGHTS_DEFAULT_LEVEL` | `campaign` | Lowest level fetched in regular sync |
| `INSIGHTS_ASYNC_DATE_PRESET` | `last_90d` | Date range for async jobs |

### Per-account config (in DB `account_configs`)

| Config key | Notes |
|---|---|
| `primary_conversion_action` | Which `action_type` = "a conversion" for this account |
| `attribution_window` | Must match native platform setting to get 1:1 numbers |
| `roas_action_type` | Usually `purchase`; `fb_mobile_purchase` for app-focused accounts |
