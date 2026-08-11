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
12. [Data Freshness & First-Connect Availability](#12-data-freshness--first-connect-availability)
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
| Breakdown sync | `sync.insights_breakdown` | Fetches metrics split by dimension | Periodic (1 hr) |
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
        "args": [],                            # fetches all non-disabled accounts
    },

    # Insights — daily metrics for non-disabled accounts (last 7d window)
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

### Staggered dispatch (prevents thundering herd)

Each `*_all` dispatcher calls `stagger_dispatch()` (`workers/dispatch.py`) instead of looping `.delay()` directly. It spreads per-account task enqueues across ~600s of the interval, interleaves accounts round-robin by `platform_connection_id` (so one org's accounts don't burst against the same token simultaneously), and skips connections that are currently rate-limit paused. At scale, this prevents all accounts hitting the shared Meta API quota in a single tick.

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

**Meta `account_status` mapping.** `/me/adaccounts` returns a numeric `account_status`. The worker (`META_ACCOUNT_STATUS_MAP` in `workers/tasks/structure.py`) maps it to one of three internal `account_status` values stored on `accounts`:

| Meta status | Internal `account_status` |
|---|---|
| `1` ACTIVE, `9` IN_GRACE_PERIOD | `active` |
| `3` UNSETTLED, `7` PENDING_RISK_REVIEW, `8` PENDING_SETTLEMENT | `unsettled` |
| `2` DISABLED, `100` PENDING_CLOSURE, `101` CLOSED | `disabled` |
| any unrecognized status | `unsettled` |

An `unsettled` account (unpaid balance / under review) still returns readable data, so it stays visible and syncable rather than being hidden. An unknown/unrecognized status defaults to `unsettled`, never `disabled` — a status we don't recognize must not silently vanish the account (P-2/P-4). Only the known terminal states map to `disabled`.

**Which accounts get synced.** Every `*_all` dispatcher and the eager per-connection sync gate on `account_status != "disabled"` (i.e. `active` **and** `unsettled` accounts sync; only `disabled` are skipped). This gate applies across all platforms and all task families (structure / insights / breakdowns / async).

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
            video_avg_time_watched_actions,
            catalog_segment_actions,catalog_segment_value   ← CPAS shared-item, see below
    &level=campaign
    &time_range={"since":"2026-07-27","until":"2026-08-03"}   ← resolved, see below
    &time_increment=1     ← one row per day

Call 2 — unique metrics (separate call, slower):
  GET /act_{id}/insights
    ?fields=reach,unique_clicks,unique_inline_link_clicks,unique_ctr
    &level=campaign
    &time_range={"since":"2026-07-27","until":"2026-08-03"}
    &time_increment=1
```

> **`date_preset` is never sent to Meta (PRD §2.3 / P-7).** The task takes a
> preset (`last_7d`, `last_30d`, …) but resolves it to an explicit `time_range`
> in the account's timezone via `workers.date_range.meta_time_range`, which wraps
> the same `app.services.insights.resolve_date_range` the read/API path uses.
> This guarantees synced days == queried days by construction. Enforced by
> `tests/test_date_range_parity.py`.

Both calls write to the same `metrics_daily` rows via upsert — they merge, not overwrite.

> **CPAS shared-item (catalog-segment) conversions.** `catalog_segment_actions`
> and `catalog_segment_value` are requested in Call 1 for **all** Meta accounts
> (campaign / adset / ad non-unique fetches). For Collaborative Ads accounts the
> retailer owns the pixel, so regular `actions` / `action_values` / `purchase_roas`
> come back empty and `catalog_segment_*` is the only conversion source (see
> `docs/meta-ad-account-types.md` §7). These fields return empty (not an error) for
> non-catalog accounts, so requesting them unconditionally is safe; they are **not**
> added to the unique-metrics call or the breakdown fetch. Each array entry is
> stored into `metric_action_stats` keeping `field_name` verbatim, with the
> `action_type` normalized to a canonical bucket (`purchase` / `add_to_cart` /
> `view_content`) by `_normalize_catalog_segment_action` — unknown types stored
> as-is. See `docs/meta-ads-metrics-reference.md` §15 for the full normalization
> table.

> **TikTok insights metric tiers (`workers/tasks/tiktok_insights.py`).** TikTok's
> integrated reporting request is built from three lists:
> - `SCALAR_METRICS` — core spend/impression/rate fields, written to `metrics_daily`.
> - `ACTION_METRICS` — video/engagement/result fields, requested on **every** call
>   (part of `base_metrics`); each maps through `TIKTOK_ACTION_MAP` into a
>   `metric_action_stats` row. Includes `average_video_play` and
>   `average_video_play_per_user` (both stored as `field_name = "average_video_play*"`,
>   `action_type = "video_view"`, average values — never summed across rows, P-4).
>   Also includes `engagements` (standard aggregate engagement metric, not Pixel /
>   feature-gated → stays in the always-requested tier), stored as
>   `field_name = "engagements"`, `action_type = "engagement"`.
> - `EVENT_METRICS` — website/app page-event fields that require a Pixel / app SDK.
>   TikTok rejects the **whole** request with "invalid metric fields" if these are
>   requested for an advertiser without a Pixel configured, so they are in a
>   **graceful-fallback tier**: on the first such error the worker sets
>   `event_supported = False` and retries once with `base_metrics` only, so core
>   metrics still sync (this is a distinguishable degraded state, not a fake zero, P-4).
>   Onsite/shop fields currently requested (TikTok's ONSITE family, not the
>   pixel-web `page_event_*` family): `onsite_shopping`,
>   `total_onsite_shopping_value`, `onsite_on_web_cart`,
>   `total_onsite_on_web_cart_value`, `onsite_initiate_checkout_count`,
>   `total_onsite_initiate_checkout_count_value`, `ix_page_view_count`, and
>   `app_event_install`. Also in this graceful-fallback tier: the interactive-addon
>   field `ix_product_click_count` and the LIVE fields `live_effective_views` and
>   `live_product_clicks` — all three are feature-gated and dropped on the same
>   "invalid metric fields" fallback if the advertiser hasn't enabled them.
>
> Each `EVENT_METRICS` field maps through `TIKTOK_ACTION_MAP` into `metric_action_stats`:
> counts land under `field_name = "page_events"` (action_types `purchase`,
> `add_to_cart`, `checkout`, `page_view`) and monetary values under
> `field_name = "page_event_values"` (action_types `purchase`, `add_to_cart`,
> `checkout`). App installs land under `field_name = "app_events"`, `action_type = "install"`.
> The three added feature-gated fields keep `field_name` verbatim:
> `ix_product_click_count` → (`ix_product_click_count`, `product_click`),
> `live_effective_views` → (`live_effective_views`, `live_view`),
> `live_product_clicks` → (`live_product_clicks`, `product_click`).
> No DB migration is needed — `metric_action_stats` is a generic
> `(field_name, action_type, value)` store. See `docs/tiktok-api-metrics-reference.md`
> §5, §12, §16 for the upstream field definitions.

### Breakdown fetches (hourly beat)

Breakdowns are synced hourly via the `sync_breakdowns_all` beat task → `sync_breakdowns_for_account` per account. Each run fetches `last_30d` of data, covering the default UI date range. Results are stored in `metric_breakdowns` and queried directly by the breakdown API.

Each run records a `sync_jobs` row with `job_type = "breakdown"` (singular, matching `JOB_TTLS` and the `/sync/status` envelope) — committed running before the first API call, finalized on every exit path (P-8). This is what lets the freshness badge / breakdown section tell "syncing" from "done"; without it the badge is stuck on "partially synced". All platforms use the singular `"breakdown"` string (Meta, TikTok, Google).

Supported breakdown dimensions:
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
| `insights_app_pct` | > 80% | Reschedule task 30s later (account scope) |
| `insights_app_pct` | > 95% | Pause entire connection 300s + reschedule |
| `insights_acc_pct` | > 80% | Reschedule task 30s later |
| `structure_acc_pct` | > 80% | Reschedule task 30s later |
| `app_call_count` | > 80 | Reschedule task 60s later |

```python
def apply_backoff(account_id: str, connection_id: str | None = None) -> None:
    """Raises RateLimitBackoff. Does NOT sleep — task reschedules itself on catch."""
    state = RateLimitState(account_id, connection_id)

    if state.insights_app_pct > 95:             # HARD — shared app quota
        countdown = int(state.quota_reset_seconds) or 300
        if connection_id:
            pause_connection(connection_id, countdown)  # pauses ALL accounts on this token
        raise RateLimitBackoff(countdown, scope="connection")

    soft = 0
    if state.insights_app_pct > 80 or state.insights_acc_pct > 80: soft = 30
    if state.structure_acc_pct > 80:  soft = max(soft, 30)
    if state.app_call_count > 80:     soft = max(soft, 60)
    if soft:
        raise RateLimitBackoff(soft, scope="account")
```

**Backoff is non-blocking.** `apply_backoff` raises `RateLimitBackoff` instead of calling `time.sleep`. The task catches it and calls `self.apply_async(countdown=N)`, freeing the worker slot immediately. Rate-limit reschedules are kept off the error-retry budget (`max_retries` stays reserved for genuine API errors).

**Called at task entry** (once, before the first API call), not before every individual request.

### Connection-scoped pause (shared-token gate)

One `platform_connections.access_token` is shared by all accounts in an org. Meta's app-level throttle (`app_id_util_pct`) is shared across that whole token — so when one account hits the hard limit (>95%), all sibling accounts must also back off, not just one.

When `apply_backoff` detects `app_id_util_pct > 95%` **or** a hard Meta error code (4/17/32/613/80000–80004) is caught mid-task, it calls `pause_connection(connection_id, seconds)` — which sets a Redis key `rate_limit:conn:{id}:paused` with TTL. Every per-account task checks `connection_paused_remaining(connection_id)` at entry before touching the API; if the key is live, it calls `self.apply_async(countdown=remaining)` and returns. The staggered dispatcher also skips paused connections entirely, so tasks aren't re-enqueued during the pause window.

### Overlap lock (per-account, per-job-type)

A single account should not have two concurrent runs of the same sync job. A Redis `SET NX EX` lock (`rate_limit:lock:{job_type}:{account_id}`, TTL = task hard time limit + 120s) is acquired at task entry after the connection-pause check. If another run holds the lock, the task returns immediately without creating a `sync_jobs` row. Released via atomic Lua check-and-delete in a `finally` block. Works correctly with `task_acks_late=True`: a crashed worker's lock expires via TTL, after which the redelivered message re-acquires cleanly.

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
| `4` | `1504022` | App-level insights rate limit | Pause connection 300s, reschedule. |
| `4` | `1504039` | Too many app calls | Pause connection 300s, reschedule. |
| `4` | *(none)* | Generic app limit | Pause connection 300s, reschedule. |
| `17` | — | User rate limit | Pause connection 300s, reschedule. |
| `32` | — | Page rate limit | Pause connection 300s, reschedule. |
| `613` | — | Custom rate limit | Pause connection 300s, reschedule. |
| `80000`–`80004` | — | Ads/insights rate limit codes | Pause connection 300s, reschedule. |
| `100` | `1487534` | Too much data per call | Narrow the date range (split into two calls), or switch to async. Do not retry as-is. |
| `1` | — | Timeout (sync) | Switch to async job automatically. |

All rate-limit codes (4, 17, 32, 613, 80000–80004) are caught by `is_meta_rate_limit_error(code)` in `workers/rate_limit.py` and trigger `pause_connection(connection_id)` — the same hard-pause path as the >95% header threshold. This is important because Meta can return code 4 while `app_id_util_pct` still reads near zero.

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

### Token refresh & token-failure alerting

Two token lifetimes are managed proactively rather than only reacting to a `190`/`200` at fetch time:

**Meta — `refresh_meta_tokens`** (`workers/tasks/meta_token_refresh.py`, `meta` queue, beat `refresh-meta-tokens` daily **00:45 UTC**, staggered off TikTok's 00:30). Selects active Meta connections with a non-NULL `token_expires_at` inside a **7-day** window (NULL expiry = never-expiring system-user token or an unprobed connection → skipped) and exchanges the still-valid long-lived token via `MetaClient.exchange_long_lived_token()` (Meta's `fb_exchange_token` grant — must run while the token is *alive*, hence the proactive window). On success it stores the new encrypted `access_token`, recomputes `token_expires_at` from `expires_in` — or sets it to **NULL** when the exchange returns a falsy `expires_in` (Meta treating the token as non-expiring), so the connection is skipped by the `token_expires_at IS NOT NULL` guard on subsequent runs instead of being re-exchanged every night — clears connection health, and resolves any open alert (P-2). Only exchange-shaped errors (`MetaAPIError`, `httpx.HTTPError`, the empty-token `ValueError`) are treated as a token failure and leave a durable trace (P-8); genuinely unexpected errors (DB down, decrypt misconfig) fall through to `self.retry` so Celery's backoff engages and no false token warning is lit (P-2). Unlike TikTok it **does not deactivate** the connection: a Meta token typically recovers on manual re-paste (P-5). Requires `META_APP_ID`/`META_APP_SECRET`; if unset the task logs and returns early (no-op).

**TikTok — `refresh_tiktok_tokens`** (unchanged schedule, daily 00:30 UTC). On refresh failure it still deactivates the connection (`is_active=False`), and now *also* records the failure trace + alert. On success it clears health and resolves the alert.

**Google** — the SDK auto-refreshes the access token, so there is no refresh task. Instead the sync tasks classify authentication/authorization failures: `GoogleAdsClientError.is_auth` is set in `google_client._wrap` from the gRPC status (`UNAUTHENTICATED`/`PERMISSION_DENIED`) and the typed GAQL `AuthenticationError`/`AuthorizationError` codes, and `GoogleClient.search` re-raises google-auth `RefreshError` (invalid_grant — refresh token expired/revoked) as an auth error. Each Google sync task's `except GoogleAdsClientError` block raises the alert when `is_auth`, additive to (never a swallow of) the normal `sync_jobs` failure + retry — including `sync_google_accounts_for_connection` (account import), which is the *first* Google call to run against a connection, so a revoked/expired grant surfaces there first.

**Sync-path auth alerting now covers all three platforms, not just Google + the refresh tasks.** A dead access token hit during a normal *sync* (not just a refresh) previously left failed `sync_jobs` but no notification / `last_error` for Meta and TikTok — the Meta refresh task also can't catch a manual-paste connection whose `token_expires_at` is NULL (its selection query filters `IS NOT NULL`), so a dead Meta token fell through every alert path. The same `is_auth` classify-then-alert pattern used by Google is now mirrored on the other two clients: `MetaAPIError.is_auth` (code `190`/`102` or OAuth subcodes `458,459,460,463,464,467,492`) and `TikTokAPIError.is_auth` (code `40100` invalid token / `40101` expired / `40200` permission-denied, per `docs/tiktok-api-dashboard-contract.md` §10). Every Meta sync task's `except MetaAPIError` block (`insights.py` insights_daily + breakdown, `structure.py` structure + `sync_accounts_for_connection` account import, `async_jobs.py` submit + `poll_async_jobs` + `fetch_async_results`) and every TikTok sync task's `except TikTokAPIError` block (`tiktok_insights.py`, `tiktok_structure.py` structure + account import, `tiktok_breakdowns.py`) calls `alert_connection_token_failure(...)` when `is_auth` — additive to the existing `finalize_sync_job(..., "failed")` + retry, gated on `is_auth` only so rate-limit `"skipped"`/transient errors never cry wolf (P-2). `connection_id` is the value already resolved from the account's `platform_connection_id` in each task's read phase. Because the dedup key is per-connection (`token_expired:{connection_id}`), a connection failing every 15-minute beat cycle collapses to one notification + one email until it recovers.

**Notification emission (one writer, P-7).** All three platforms funnel through `workers/token_alerts.py`, which is the only worker-side caller of `app/services/notifications.py` — worker paths never touch the `notifications` table directly, and notifications are never emitted as a side effect of a read (anti-req §2.3). Behavior:

- `record_token_failure` — stamps `platform_connections.last_error`/`last_error_at` and upserts a deduped notification. Dedup key scheme **`{type}:{connection_id}`** (e.g. `token_expired:<uuid>`); DB unique constraint `(organization_id, dedup_key)` is the dedup mechanism. `create_notification` upserts `ON CONFLICT DO UPDATE … WHERE status='resolved'`: while a row is still open (`unread`/`read`) a repeated failure is a no-op (never dupes, never bounces a `read` row back to `unread`), but a **resolved** row is **re-opened** (back to `unread`, `resolved_at` cleared, title/body/severity/`created_at` refreshed) so a condition that recurs *after* recovery re-alerts instead of staying silent (P-2 alarm-when-not-fine, P-8 trace reflects reality).
- `clear_token_failure` — recovery (P-2): clears `last_error`/`last_error_at` and resolves the `token_expired` / `token_expiring` / `refresh_failed` rows for that connection so the badge/banner auto-disappears. Does not commit (caller owns the txn). Both the dedup-key format `{type}:{connection_id}` (`token_dedup_key`) and the `(token_expired, token_expiring, refresh_failed)` class tuple (`TOKEN_ALERT_TYPES`) are defined once in `app/services/notifications.py` and imported here (P-7).
- **Sync-success recovery (all three platforms).** An alert also clears the moment a normal *sync* succeeds — not only on the nightly refresh or a reconnect. Every platform sync task's SUCCESS/completion path (right after `finalize_sync_job(..., "completed")`) calls `clear_connection_token_failure(connection_id)`, a one-shot helper in `workers/token_alerts.py` that opens its **own committed transaction** (mirroring `alert_connection_token_failure`'s funnel), re-fetches the `PlatformConnection`, and — **only when `last_error is not None`** (guard: a healthy connection skips the resolve query on every 15-min/30-min beat, P-2 "silent when fine") — funnels through `clear_token_failure`. It swallows and logs its own errors so clearing a stale alert can never fail a sync that otherwise succeeded. This means a transient auth blip (or a reconnect the refresh task hasn't re-probed yet) auto-resolves as soon as the next successful sync lands, instead of leaving the badge lit until the nightly refresh. Wired at: Meta `insights.py` (insights_daily + breakdown), `structure.py` (structure + `sync_accounts_for_connection` account import), `async_jobs.py` (`fetch_async_results` fetch/finalize); TikTok `tiktok_insights.py`, `tiktok_structure.py` (structure + account import), `tiktok_breakdowns.py`; Google `google_structure.py` (structure + account import), `google_insights.py`, `google_breakdowns.py`. Goes through the one writer (P-7) — never touches the `notifications` table directly.
- **Reconnect recovery (org+platform level).** An alert also clears the moment the user *reconnects* — not only on the nightly refresh. The connect flow (`POST /connections`, TikTok/Google OAuth callbacks) calls `app/services/notifications.py::resolve_platform_token_alerts(org_id, platform)` on success. This resolves alerts + clears health for **every** `platform_connection` of that org+platform, not just the newly-created one, because reconnect INSERTs a new connection row (no unique constraint on `(organization_id, platform_id)`) and the pre-existing alert's dedup key still points at the old dead connection id. Google matches `platform_id="google_ads"` (the stored id), not the `"google"` URL label.
- **Email gating** — email (to the org owner, via `app/services/email.py`) is sent only when the notification was *newly created or re-opened*. `create_notification`'s upsert can't signal that to the caller, so the caller queries for an existing **unresolved** row first (`is_new = not _has_open_notification(...)`); a repeated failure while the row is still open never re-emails, but a genuine recurrence after recovery (the row was `resolved` → re-opened) counts as new and re-emails. Email is best-effort and outside the trace transaction — a mail failure never loses the durable notification.

The failure trace is committed in its own transaction so it survives even when the surrounding sync/refresh path rolls back (P-8).

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
    &time_range={"since":...,"until":...}   ← preset resolved in account tz (§2.3)
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
    # CPAS shared-item conversions (Collaborative Ads — retailer owns the pixel)
    "catalog_segment_actions", "catalog_segment_value",
}

def parse_insight_row(entity_type, entity_id, date, raw_row):
    scalars = {}
    action_stats = []

    for field, value in raw_row.items():
        if field in ACTION_STAT_FIELDS:
            # value is a list: [{"action_type": "purchase", "value": "12"}, ...]
            for item in (value or []):
                action_type = item["action_type"]
                # CPAS shared-item: Meta returns varying pixel-dependent action
                # types; normalize to purchase / add_to_cart / view_content so the
                # read layer has a stable contract. Scoped to catalog_segment_*
                # only — regular actions/action_values kept verbatim.
                if field in ("catalog_segment_actions", "catalog_segment_value"):
                    action_type = _normalize_catalog_segment_action(action_type)
                action_stats.append({
                    "entity_type":  entity_type,
                    "entity_id":    entity_id,
                    "date":         date,
                    "field_name":   field,
                    "action_type":  action_type,
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
for each non-disabled account:
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
for each non-disabled account:
    skip if not stale (TTL: 15 min)
    create sync_job(type='insights_daily', status='running')
    token = db.get_decrypted_token(account.platform_connection_id)

    # Call 1: non-unique metrics
    apply_backoff(account_id)
    response = meta_client.get_insights(
        account_id,
        fields=NON_UNIQUE_FIELDS,
        level='campaign',
        time_range=meta_time_range(date_preset, account.timezone),  # §2.3
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
        time_range=meta_time_range(date_preset, account.timezone),  # §2.3
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
for each non-disabled account:
    skip if an async job for this account + date_preset is already running or fresh

    create sync_job(type='insights_async', status='running')

    response = meta_client.post_insights_async(
        account_id,
        fields=FULL_AD_LEVEL_FIELDS,
        level='ad',
        time_range=meta_time_range('last_90d', account.timezone)  # §2.3
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

                                  │ rate limit mid-run
                                  ▼
                               skipped ──> task rescheduled (countdown)
```

`skipped` means the task hit a hard rate limit during execution (connection paused), marked the job `skipped`, and rescheduled itself. It is not a permanent failure — the task will retry automatically once the connection pause expires.

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

---

## 12. Data Freshness & First-Connect Availability

### Two distinct concepts

**Freshness** — ongoing data staleness during normal operation. How old the data is when a user opens the dashboard on any given day.

**First-connect availability** — one-time wait for a brand-new account. How long until a date range first populates after connecting a platform.

These differ because freshness is controlled by Beat schedule intervals, while first-connect time is controlled by an immediate task chain that bypasses Beat entirely.

### Freshness model (ongoing operation)

| Date range | Data source | Staleness |
|---|---|---|
| Today / Yesterday / Last 7d | 15min Beat sync (`last_7d`) | ~15 min |
| Last 14d — Meta | Days 1–7: 15min sync; Days 8–14: async 90d job | Days 8–14: up to 6hr |
| Last 30d — Meta | Days 1–7: 15min sync; Days 8–30: async 90d job | Days 8–30: up to 6hr |
| Last 90d — Meta | Days 1–7: 15min sync; Days 8–90: async 90d job | Days 8–90: up to 6hr |
| Last 14d — TikTok | Days 1–7: 15min sync; Days 8–14: `insights_historical` (90d) | Days 8–14: up to 6hr |
| Last 30d — TikTok | Days 1–7: 15min sync; Days 8–30: `insights_historical` (90d) | Days 8–30: up to 6hr |
| Last 90d / Last month + compare — TikTok | Days 1–7: 15min sync; Days 8–90: `insights_historical` (90d) | Days 8–90: up to 6hr |

### First-connect availability

When an account is first connected, `sync_accounts_for_connection` imports the
ad accounts and then eagerly enqueues the first sync — no waiting for Beat:

```
sync_accounts_for_connection             → accounts imported            (~10–30s)
  ├─ sync_structure_all                  → structure, all accounts       (staggered, skips-fresh)
  ├─ stagger_dispatch(insights_daily)    → THIS connection's accounts, last_7d
  └─ stagger_dispatch(breakdowns)        → THIS connection's accounts, last_30d
```

Insights and breakdowns are enqueued via `stagger_dispatch` (spread over the
window, paused connections skipped) rather than raw `.delay` per account, so a
multi-account connection does not burst the shared token. They are **scoped to
the just-connected connection**, not fanned out globally — `insights_daily`
skips-fresh so a global fan-out would be cheap, but `sync_breakdowns_for_account`
has **no staleness guard**, so a global breakdown fan-out on every connect would
re-fetch every account's breakdowns. `sync_insights_for_account` runs its
structure-dependency guard if it is picked up before structure completes.

> **Structure-dependency guard (livelock prevention).** `sync_insights_for_account`
> checks `camp_map` right after reading it, **before constructing `MetaClient` or
> making any API call**. If the account has no campaigns yet:
> - a `structure` job has already `completed` → return cleanly (the account
>   genuinely has 0 campaigns; nothing to sync, no failed `sync_jobs` row);
> - otherwise → trigger `sync_structure_for_account.delay(...)` and defer,
>   **without hitting Meta**. Structure re-kicks insights on completion
>   (`structure.py`), and the 15-min beat is a backstop, so no self-reschedule.
>
> Why before the API call: on a rate-limited shared Meta app, `structure`'s
> up-front `apply_backoff` trips the 80% (`SOFT_PCT`) app-usage gate and finalizes
> `skipped`, so `campaigns` stays empty. If insights instead fetched campaign +
> per-campaign adset/ad insights and only *then* raised on the empty `adgroup_map`,
> that doomed run would drain the exact app quota structure needs — a **livelock**
> (insights drains quota → structure skips → maps stay empty → insights fails). The
> pre-existing `adgroup_map`/`ad_map` empty-guard `RuntimeError`s are kept as a
> safety net for the rarer campaigns-present-but-adsets-lagging case. Enforced by
> `tests/test_insights_structure_guard.py`.

> **Not eager on connect: `submit_async_job_for_account` (Meta 90d async).** It
> is driven only by its 6-hourly Beat task + 6hr staleness guard. So for a fresh
> account, the day-8+ tail of `last_14d`/`last_30d`/`last_90d` waits up to one
> async cycle; days 1–7 are covered immediately by the eager `insights_daily`.
> (Previous versions of this doc drew async into the connect chain — that was
> never wired; documented here rather than silently reconciled.)

| Date range | First data after connect |
|---|---|
| Today / Yesterday / Last 7d | ~2–8 min |
| Breakdowns (age/gender/country/device) | ~2–8 min (was up to 1hr — now eager) |
| Last 14d / Last 30d / Last 90d — Meta (day 8+ tail) | up to next async cycle |
| Last 14d / Last 30d — TikTok | ~3–10 min |
| Last 90d / Last month + compare — TikTok | ~3–10 min (day 8+ tail up to 6hr) |

### Implementation notes

- `submit_async_job_for_account` has a 6hr staleness guard. It is **not** triggered on connect — only by its own Beat task.
- TikTok uses `job_type="insights_historical"` with a 6hr TTL, separate from `"insights_daily"` (15min TTL), so the two do not block each other. The historical job runs `last_90d` (was `last_30d`), matching Meta's 90-day backfill so "Last month" **and** its prior-period compare (the month before) are both in range — a 30-day window left the compare month empty.
- **TikTok reports are chunked to ≤30 days.** TikTok's `stat_time_day` reporting rejects any range wider than 30 days (`"max time span is 30 days when use stat_time_day"`). `sync_tiktok_insights_for_account` splits `[start, end]` into contiguous ≤30-day windows (`_date_chunks`) and calls `get_report` per chunk, merging rows — so `last_90d` becomes three requests. The event-metric fallback (`event_supported` → core-only on `invalid metric`) persists across chunks and data levels.
- The async job submit fires in parallel with the insights sync, not after. Structure sync completes first (~30s–3min), and Meta async jobs take 1–10min to process — so `camp_map` is always populated before `fetch_async_results` runs.
