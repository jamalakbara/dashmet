# dashmet vs. BDDAI — Code-Level Comparison

**Purpose.** This document answers one question: *given that BDDAI already exists and does roughly
the same job, why was dashmet built from scratch instead of extended?*

It is written from reading the code, not the docs. Every claim below points at a file and line.
It is deliberately **two-sided** — Section 9 lists the places where BDDAI is genuinely better than
dashmet today, and Section 8 lists dashmet's own unfixed violations of its own rules. A comparison
that only flatters the new thing isn't an assessment, it's a pitch.

**Repos analysed** (as of 2026-08-06):

| Repo | Role | Lang/stack | Files | LOC | Test fns | Last commit |
|---|---|---|---|---|---|---|
| `dashmet` | monorepo: API + workers + web | FastAPI/Postgres/Celery + Next 16/React 19 | ~1,891 | 33,151 | 202 | 2026-08-05 |
| `bddai-service` | read API | FastAPI/MySQL+MongoDB | 64 | 22,094 | ~0 | 2026-07-17 |
| `bddai-scheduler` | sync workers | Python CLI + cron | 196 | 31,678 | 264 | 2026-07-21 |
| `bddai-binding-app` | OAuth / account binding | FastAPI | 41 | 5,498 | ~0 | 2026-03-08 |
| `bddai-fe` | web client | Vite/React 18/Mantine | 145 | 22,900 | 0 | 2026-01-27 |

BDDAI totals ~82k LOC across four separately-deployed repos. dashmet is ~33k in one.

---

## 1. The one-sentence answer

BDDAI's four repos do not share a data model, a date resolver, a metric definition, a response
envelope, or an auth/tenancy model. They share a *database*. That means a correctness fix has to be
applied four times, in four languages of thought, with no compiler or test to tell you when you
missed one — and the evidence in the code is that this is exactly what happened.

dashmet was rebuilt not because BDDAI's features are wrong, but because the **contract between
layers** is the thing that needed to change, and that is not a thing you can refactor incrementally
across four repos with 0 CI pipelines and (in `bddai-service` and `bddai-fe`) essentially no tests.

---

## 2. Architecture & repo topology

### 2.1 BDDAI: four repos, one shared database, no shared contract

```
bddai-binding-app ──writes──┐
                            ├──► MySQL (users, credentials, account_configuration)
bddai-scheduler   ──writes──┤
                            └──► MongoDB (meta_insights_campaign, tiktok_insights_ad, …)
bddai-service     ──reads───┘         ▲
                                      │
bddai-fe ──HTTP──► bddai-service ─────┘
         └─HTTP──► bddai-binding-app  (second base URL, second deployment)
```

The frontend talks to **two different backends** with two axios instances:

```ts
// bddai-fe/src/axios/index.ts:4-18
export const restEP  = axios.create({ baseURL: import.meta.env.VITE_REST_SERVICE_URL })
export const bindEP  = axios.create({ baseURL: import.meta.env.VITE_REST_BINDING_URL })
```

The same MySQL tables are re-declared, independently, in each backend repo — e.g.
`UserAdAccountCredentialInformation` is defined in **both**
`bddai-service/app/models/user_model.py:20` and `bddai-binding-app/app/models/user_model.py:19`,
with different column sets (the binding-app copy has an extra `account_id` column the service copy
lacks). Nothing enforces they stay in sync. Both point at a table literally named
`bak_user_ad_account_credential_information` — a backup-prefixed table serving production reads.

MongoDB collections are the write target of `bddai-scheduler` and the read source of
`bddai-service`, but the document shape is defined nowhere shared: the writer builds it from
`MetaInsight(**insight, date=..., data=data_metrics).dict()`
(`bddai-scheduler/platforms/meta/jobs/insights_shared.py:205`) and the reader hand-writes a
Mongo aggregation pipeline against field names it assumes exist
(`bddai-service/app/repository/meta_repository.py:344`).

**There are zero `create_index` calls anywhere in `bddai-scheduler`.** Document uniqueness is
enforced only by the application-level `ReplaceOne(filter=…, upsert=True)` filter built in
`create_filter()` (`insights_shared.py:209-243`). If two writers race, or a filter key is
constructed slightly differently by a different job, you get silent duplicates with no database
guard.

### 2.2 dashmet: one repo, one schema, one writer

```
dashmet/
├── backend/app/          FastAPI: api → services → models (one SQLAlchemy schema)
├── backend/workers/      Celery: the ONLY writer to metrics tables
├── backend/migrations/   Alembic (7 versioned migrations)
├── backend/tests/        202 test functions
└── frontend/src/         Next 16, consumes exactly one API
```

Both the read path and the write path import the *same* Python objects.
`workers/date_range.py:15` imports `resolve_date_range` from `app.services.insights` — the worker
literally cannot drift from the API's notion of "last 30 days", because there is one function.

### 2.3 The layering rule that was written but never enforced

`bddai-service/.claude/rules/layered-architecture.md` states:

> Violation check: `grep -r "from app.repository" app/endpoints/` must return 0 results.

Actual result today: **23 matches** across 8 endpoint files. Related evidence that the intended
refactor was started and abandoned:

- `app/endpoints/v4/handlers/{meta,tiktok,google_ads,…}/` exist as directories containing **only
  `__pycache__`** — every source file is gone, and `v4` is not routed.
- The rules mandate `app/service/` (singular) for platform API clients and `app/config.py` flat.
  Neither exists; the code uses `app/services/` and `app/core/config.py`.
- The rules mandate `SuccessResponse[T]` for all endpoints. `grep "SuccessResponse" app/endpoints/v3/`
  returns **0**. Endpoints return the deprecated `ReturnData` (41 raw `return {` statements remain).
- The rules describe an `_live_data_error` envelope for platform API failures. The only occurrences
  of that string in the repo are inside stale `.pyc` files — the source implementing it was deleted.

This is the strongest single argument for a rebuild: the BDDAI team had already **correctly
diagnosed** the architecture problems and written the target state down. The refactor stalled
because there is no CI, no test suite in that repo to refactor against, and a 1,079-line
`meta.py` with 20 module-level singletons is not safely movable by hand.

dashmet's equivalent check passes by construction: endpoints import services and (read-only) ORM
models, never raw sessions or Mongo clients. Its largest endpoint file is 565 LOC
(`insights.py`) versus BDDAI's 1,851 (`google_ads.py`).

---

## 3. Data model & metrics storage

### 3.1 Storage shape

| | BDDAI | dashmet |
|---|---|---|
| Metrics store | MongoDB, ~20+ collections, one per platform×level×breakdown | Postgres, 3 tables (`metrics_daily`, `metric_action_stats`, `metric_breakdowns`) |
| Uniqueness | application-level `ReplaceOne` filter, **no DB index** | `UniqueConstraint` used as the `ON CONFLICT` target |
| Adding a platform | new collections + new repository + new endpoint + new FE page | new worker module writing the same 3 tables |
| Adding a metric | new field in Mongo doc + new entry in `calculated_metrics()` per repo | new column, or (better) a row in `metric_action_stats` — no schema change |

BDDAI's collection sprawl is visible in one file: `bddai-service/app/endpoints/v3/google_ads.py:26-38`
declares **13 module-level repository singletons**, one per collection
(`google_ads_insights_campaign`, `_adgroup`, `_age`, `_audience_segment`,
`_audience_segment_ad_shown`, `_ad_performance`, `_search_term`, `_keywords`,
`_yt_ad_performance`, `_gender`, `_content`, `_ad`, `_campaign_live`). Meta has 6, TikTok has 6+.
Each one is a separate `MongoClient(MONGODB_URL)` opened at import time
(`app/repository/google_ads_repository.py:10`).

dashmet's `metric_action_stats` is the key design difference: conversion/action metrics are stored
**long** (`entity_id, date, field_name, action_type, value` —
`backend/app/models/metrics.py:78-101`), not as ever-widening columns. Adding "post saves" or
"onsite add-to-cart value" is a worker change with no migration. The BOARD shows this paying off:
several 2026-08 entries add 4–8 new metrics end-to-end with the note "No migration."

### 3.2 Upsert semantics — the biggest correctness gap

**dashmet** (`backend/workers/db_helpers.py:87-124`):

```python
stmt = stmt.on_conflict_do_update(
    index_elements=["entity_type", "entity_id", "date"],
    set_={col: func.coalesce(exc_col, tbl_col) for col in NULLABLE_METRIC_COLUMNS …},
)
```

`COALESCE(excluded.col, table.col)` means a re-sync that returns `NULL` for a column **never
overwrites** a previously-good value with nothing. Re-running the same sync twice is a no-op.

**BDDAI** (`bddai-scheduler/platforms/meta/jobs/insights_shared.py:255-256`):

```python
if all(value == 0 for key, value in data_metrics.dict().items() if key != "objective"):
    return None, for_update_ad_account_information
```

Any row whose metrics are all zero is **dropped before the upsert is built**. Combined with the
delete-then-replace flow in the same function (`build_delete_filter` at line 336, `ReplaceOne` at
245), the consequence is: a campaign that Meta later restates to zero keeps its old non-zero
numbers forever, because the row that would have corrected it is filtered out as "noise." This is
not a hypothetical — it is the documented anti-requirement `§2.3 "Never drop all-zero rows"` in
dashmet's own `.claude/rules/product-principles.md`, written because of this code.

### 3.3 Attribution windows

BDDAI resolves attribution with a **silent fallback cascade**
(`insights_shared.py:169-194`):

```python
if attribution == "1d_click":
    fallback_columns = ["1d_click", "value", "1d_view", "7d_click"]
…
for column in fallback_columns:
    if column and column in val and val.get(column) not in (None, ""):
        nested_metrics[key] = _coerce_meta_action_number(val[column])
        return nested_metrics
nested_metrics[key] = 0          # ← nothing matched: store a zero
```

Two problems. First, a single stored number may have come from **any** of four attribution windows
and the document does not record which — so "purchases" for two campaigns may not be the same
measurement. Second, the terminal `= 0` converts "this window has no data" into "this window has
zero conversions," which is a different and much more damaging claim.

dashmet stores `attribution_window` as a first-class column on `metrics_daily`
(`app/models/metrics.py:76`), resolved per account from `account_configs.attribution_window`
(`app/models/platform.py:112`) and passed explicitly to the Meta API
(`workers/tasks/insights.py:227,300`). See §8.1 for where this is still incomplete.

### 3.4 Multi-tenancy

BDDAI **has no organization/tenant concept at all.** `grep -rn "organization\|org_id\|tenant"
bddai-service/app/models/` returns nothing. Everything hangs off `user_id`:

```python
# bddai-service/app/utils/utils.py:274-283
account_configuration = await retry_async(…get_account_id_and_access_token_by_user_id_and_account_id,
                                          user_info["uid"], account_id, platform_id)
if not account_configuration:
    raise HTTPException(status_code=401, detail="Your ad account has not been binded to bddai. …")
```

Isolation is a side effect of "the credential row is keyed by your uid," not an explicit check.
Note also that "you haven't connected this account" is returned as **HTTP 401**, which the frontend
interceptor unconditionally treats as session expiry — it wipes `localStorage` and force-navigates
to `/sign-in` (`bddai-fe/src/axios/index.ts:47-53`). An unbound account logs the user out.

dashmet has `organizations`, `organization_memberships`, `membership_accounts`, `role` (owner/member),
and an explicit `assert_account_belongs_to_org()` guard called by every insights read path, with
10 dedicated tests in `backend/tests/test_account_access.py` asserting cross-org access returns 403.

---

## 4. Data sync

### 4.1 The structural difference: cron CLI vs. queue

| | BDDAI (`bddai-scheduler`) | dashmet (`backend/workers`) |
|---|---|---|
| Trigger | crontab shell entries → `python main.py <job_name>` | Celery beat → task queue |
| Concurrency control | `flock` file lock + `concurrencyPolicy: forbid` | per-queue workers, `worker_prefetch_multiplier=1`, Redis in-flight lock |
| Isolation | one process per job name, all platforms in one box | 5 queues (`meta`/`tiktok`/`google`/`poll`/`default`) |
| Failure recovery | `utils/failed_task_recovery.py`, drain re-queue with backoff | `task_acks_late=True` (re-queue on worker crash) + `sync_jobs` row |
| Retry | exponential backoff in `db/crud_sync_job.py:47` | Celery `countdown` re-dispatch (`workers/rate_limit.py`) |

Both are legitimate designs. BDDAI's newer **drain engine** (`drain/`, `db/crud_sync_job.py`) is
good work — it claims tickets `FOR UPDATE`, has a documented write-ownership boundary, exponential
backoff, and a `LockWaitTimeout` → "skip tick" semantic. See §9.

The material difference is *what happens when a job dies*.

**dashmet** commits a `running` row **before** the first API call, in its own transaction:

```python
# backend/workers/db_helpers.py:41-56
def create_sync_job(account_id, platform_id, job_type) -> uuid.UUID:
    with get_worker_db() as db:      # ← its own commit
        job = SyncJob(status="running", started_at=now(), …)
```

and finalizes in a **second** transaction (`finalize_sync_job`, line 66), so a hard crash still
leaves evidence. Error text is scrubbed of `access_token=` before storage (`_sanitize_error`, line 59).
`GET /sync/status` then reports per-job-type `status / last_run_at / next_run_at / is_stale`, with
stuck-job detection (a `running` job older than 2× its TTL is reported as `timed_out`,
`app/services/sync.py:76-88`).

**BDDAI's** websocket sync path has no such record. Worse, it is *destructive*:

```python
# bddai-binding-app/app/endpoints/v3/websocket_sync.py:441-451
await _delete_data_async(collection, {"account_id": …, "date": {"$gte": …, "$lte": …}})
await _insert_bulk_data_async(collection, formatted_data)
```

Delete the date range, then insert. MongoDB gives no transaction here. If the process dies, the
client disconnects, or the insert fails, **the range is gone and nothing records that it was lost.**

The UI is honest about this, which is the tell:

```tsx
// bddai-fe/src/components/misc/sync-data-info/index.tsx:29-33
<Text fz={20} c="white">Warning: Synchronizing Data</Text>
This account is currently undergoing data-synchronization process.
<b>Please DO NOT reload this tab on your browser or this process will be terminated!</b>
```

That sentence is the architecture leaking into the product. A sync whose lifetime is bound to a
browser tab cannot be a background system. dashmet's sync runs on beat schedules
(`workers/celery_app.py:84-130`) with no client involvement; the browser only *observes* it.

### 4.2 Date resolution

This is where a shared resolver earns its keep.

**BDDAI** has at least four independent date resolvers:

- `bddai-scheduler/utils/date_utils.py:11` — `get_date_range_by_preset`
- `bddai-scheduler/utils/utils.py` — a second copy imported by `platforms/meta/jobs/references.py:17-22`
- `bddai-scheduler/platforms/google_ads/jobs/insights_shared.py:66-70` — inline `if/elif` chain
- `bddai-service/app/utils/utils.py` — `get_date_range`, `split_date_range_month`, `split_date_range_week`

All of them use naive server-local time:

```python
# bddai-scheduler/utils/date_utils.py:49-55
def get_date_range() -> Dict[str, str]:
    """Generate date range from yesterday to today."""
    today = datetime.now()                      # ← no tz; server local
    yesterday = today - timedelta(days=1)
```

and `get_week_date_range()` (line 59) returns Monday **through Sunday of the current week** —
i.e. it requests dates that haven't happened yet. Meanwhile `bddai-service` computes its own range
for the read query. Nothing guarantees the window the scheduler *wrote* is the window the API
*reads*, especially for accounts whose ad-platform timezone differs from the server's.

**dashmet** has exactly one resolver, timezone-aware, used by both sides:

```python
# backend/app/services/insights.py:23-33
def resolve_date_range(date_preset, account_timezone: str = "UTC") -> tuple[date, date]:
    tz = ZoneInfo(account_timezone)
    today = datetime.now(tz).date()
```

```python
# backend/workers/date_range.py:15-20  (the worker imports the API's resolver)
from app.services.insights import resolve_date_range
def meta_time_range(date_preset, account_timezone) -> str:
    since, until = resolve_date_range(date_preset, account_timezone)
    return json.dumps({"since": since.isoformat(), "until": until.isoformat()})
```

and a test that asserts the parity holds (`backend/tests/test_date_range_parity.py`). The module
docstring explains *why*, which matters more than the code:

> never send `date_preset` to a platform API — resolve it to an explicit `time_range` in the
> account's timezone *first*… Sending a raw preset lets Meta pick the calendar-day boundary with
> its own clock, so synced rows and queried rows could cover different days.

### 4.3 Rate limiting

BDDAI has a client-side `AsyncRateLimiter` (`bddai-scheduler/utils/async_utils.py:60`) — a fixed
concurrency cap. It does not read Meta's actual throttle headers; there are no matches for
`X-FB-Ads-Insights-Throttle` or `x-business-use-case-usage` anywhere in the repo.

dashmet parses Meta's real utilization headers and feeds them into Redis
(`backend/workers/meta_client.py:53-80`), then applies **non-blocking** backoff — the task raises
`RateLimitBackoff` and re-dispatches itself with a countdown instead of sleeping a worker slot
(`workers/rate_limit.py:38-49`). Because Meta's app-level throttle is shared by every account under
one token, a hard limit pauses the whole **connection**, and sibling accounts check that key at
task entry.

It also staggers fan-out rather than enqueueing every account at once:

```python
# backend/workers/dispatch.py:17-53 — round-robin across connections, spread over `spread_seconds`,
# skipping any connection currently rate-limit paused.
```

with a test (`backend/tests/test_stagger_dispatch.py`).

---

## 5. Connecting platform accounts

| | BDDAI (`bddai-binding-app`) | dashmet |
|---|---|---|
| Endpoints | 7 near-duplicate `POST /bind-<platform>` handlers in a 1,063-line file | one `POST /connections` + per-platform OAuth callbacks |
| Token at rest | **plaintext**, `String(255)` | Fernet-encrypted, `Text` |
| OAuth CSRF state | none found in `bind.py` | `secrets.token_urlsafe(32)` in Redis, 600 s TTL |
| Token validated before save? | `get_debug_token` result is discarded on error (`if "error" in token: token = {}`) | token is exercised against `/me/adaccounts` first; a rejection is a 400 |
| Scope | per **user** | per **organization**, owner-only |
| After connect | `BackgroundTasks` in the request process | Celery task `sync_accounts_for_connection.delay(...)` |

Details worth flagging:

**Plaintext, length-capped tokens.** `bddai-binding-app/app/models/user_model.py:25`:

```python
token = Column('access_token', String(255))
refresh_token = Column('refresh_token', String(255))
```

No encryption at the service or binding layer (`grep TOKEN_FERNET|TokenCipher` in both repos:
0 hits). `VARCHAR(255)` is also a real hazard — Meta System User tokens routinely exceed it, and
MySQL will either truncate or error depending on strict mode.

**dashmet** encrypts on write (`app/services/accounts.py:209` → `encrypt_token`, Fernet,
`app/services/auth.py:55`) into a `Text` column (`app/models/platform.py:36`).

**Credit where due:** `bddai-scheduler/db/token_crypto.py` is a well-built `MultiFernet` cipher
with key rotation and an `is_ciphertext()` probe, explicitly designed to be copied verbatim into
the other two repos. It just hasn't been — which is the four-repo problem in miniature. A security
fix landed in one repo and stalled at the boundary.

**Validation before persist.** dashmet refuses to store a token it can't use:

```python
# backend/app/api/v1/endpoints/connections.py:45-56
MetaClient(body.access_token).get("/me/adaccounts", {"fields": "id,name", "limit": "1"})
except MetaAPIError as e:
    raise HTTPException(400, f"Meta token rejected: {e}")
```

BDDAI calls `get_debug_token` and then *throws the failure away*
(`bddai-binding-app/app/endpoints/v3/bind.py:113-118` — `if "error" in token: token = {}`, and the
token is persisted at line 154 either way), storing the token regardless. The user sees
"Successfully binded to Meta" and discovers the failure hours later as missing data.

**Per-account configuration.** dashmet has an `account_configs` table
(`app/models/platform.py:100-127`) holding `attribution_window`, `roas_action_type`, and
`primary_conversion_action` per ad account, which the workers and the ROAS SQL both read
(`COALESCE(ac.roas_action_type, 'purchase')` at `app/services/insights.py:362`). BDDAI's
`account_configuration` table stores presentation-ish fields (`web_api_key`, `tag`, `currency`)
with the actual configuration serialized into a `Text` column named `account_platform_type`
(`bddai-service/app/models/user_model.py:47`).

---

## 6. Fetching & serving metrics

### 6.1 Handler shape

BDDAI's `GET /overview` (`bddai-service/app/endpoints/v3/meta.py:49-190`) is a single ~140-line
async function that:

- takes a `platform` query param matching 7 platforms — one handler, all platforms;
- defines four nested closures inside the handler body;
- calls `ThreadPoolExecutor` inside an `async def` to wrap blocking `pymongo` calls
  (`meta.py:123-127`) — that is a thread pool per request, on top of a `MongoClient` per repository
  singleton;
- ends with `except Exception: traceback.print_exc(); raise HTTPException(500, str(e))` — every
  failure is a 500 with the raw exception text in the body.

There are **101** `print(` / `traceback.print_exc()` calls across `app/endpoints/`,
`app/repository/`, `app/services/`.

dashmet's endpoints are thin (`insights.py` is 565 LOC covering 8 routes); the query work lives in
`app/services/insights.py` as parameterized SQL with named result columns.

### 6.2 Ratio math — BDDAI gets this right

Worth stating clearly, because it's the failure everyone expects and BDDAI avoided it:
BDDAI computes ratios **after** aggregation. The Mongo pipeline is
`[{$match}, {$group}, {$addFields: metric_calc}]` (`meta_repository.py:344-352`), and
`__add_metric_calculation` divides the already-summed numerator by the already-summed denominator
(`meta_repository.py:168-203`). No average-of-averages. dashmet does the same in SQL
(`CASE WHEN SUM(md.impressions) > 0 THEN SUM(md.clicks)::float / SUM(md.impressions) * 100 END`,
`app/services/insights.py:319-321`). **Tie.**

### 6.3 Zero vs. null — where they diverge

BDDAI returns `0` for undefined ratios and for missing metrics, in two separate places:

```python
# bddai-service/app/repository/meta_repository.py:171-176
"$cond": [{"$eq": [f"${val_b}", 0]}, 0, {"$divide": [val_a, val_b]}]
```

```python
# bddai-service/app/endpoints/v3/meta.py:114-122
def fill_missing_data(data, metrics):
    for metric in metrics:
        new_data[metric] = 0 if metric not in data else data[metric]
```

So an ad with zero clicks reports **CPC = 0** — indistinguishable from "clicks are free" — and a
metric the platform never returned reports **0** rather than absent. dashmet returns `NULL` in both
cases (`ELSE NULL END` throughout `insights.py`; `_null_fill_missing` explicitly documents
"A null here is honest absence of a metric, not a fake zero," `insights.py:290-301`).

### 6.4 Currency

dashmet refuses to combine accounts with different currencies rather than converting or silently
summing: `currency_mismatch: True, currency: None` and the caller degrades to a per-account view
(`app/services/insights.py:1368-1400`). BDDAI stores `currency` on `account_configuration` but has
no multi-account aggregate view for it to matter to — accounts are viewed one at a time.

### 6.5 Freshness in the response

dashmet's overview returns a `cached_at` freshness token computed as `MAX(fetched_at)` over the
period, and `GET /sync/status` returns a per-job-type freshness map. BDDAI returns a single
account-level `latest_sync` timestamp with no per-metric or per-job granularity — see §7.3.

---

## 7. UI / UX

### 7.1 Information architecture: shared views vs. per-platform copies

**BDDAI** has one page directory per platform, each a full re-implementation:

```
src/pages/dashboard-meta/          1,270 LOC  (index.tsx 676 + config.ts 594)
src/pages/dashboard-tiktok/        1,385 LOC
src/pages/dashboard-google-ads/    1,202 LOC
src/pages/dashboard-instagram/       372 LOC
src/pages/dashboard-google-analytics/ 295
src/pages/dashboard-marketplace/     242
src/pages/dashboard-website/         149
```

plus 7 `binding-<platform>/` directories. A change to how the overview grid behaves is 3–7 edits.

**dashmet** has 6 platform-agnostic view components consumed by 5-line route files:

```
src/components/views/overview-view.tsx   568     src/app/(dashboard)/meta/overview/page.tsx     5
src/components/views/table-view.tsx      796     src/app/(dashboard)/tiktok/overview/page.tsx   5
src/components/views/ads-view.tsx        751     src/app/(dashboard)/google_ads/overview/…      5
src/components/views/periodic-view.tsx   390
src/components/views/funnel-view.tsx     173
```

This is the frontend expression of the same "one code path" principle as §4.2 — and it's why
dashmet's frontend is 13,258 LOC against BDDAI's 22,900 while covering a comparable surface.

### 7.2 State & routing

| | BDDAI | dashmet |
|---|---|---|
| Framework | Vite + React 18 + react-router 6 | Next 16 (App Router) + React 19 |
| Server state | `react-query` **v3** (unmaintained since 2023) | `@tanstack/react-query` v5 |
| Charts | Highcharts **and** recharts **and** `@mantine/charts` (three) | recharts |
| Filter state | zustand stores (`useAccountsStore`, `useSyncAccountStore`) | URL query params via `nuqs` |
| Auth token | `localStorage` + custom `Uid` header | cookie, `SameSite=Lax` |
| Bundle extras | `aws-sdk` v2, `crypto-js`, `html2canvas`, tiptap editor | — |

Storing account/date selection in a zustand store rather than the URL means a dashboard view isn't
linkable or shareable, and a reload loses context. dashmet's `useQueryState("account_id")` /
`useQueryState("date_preset")` makes every view a URL. Shipping `aws-sdk` v2 into a browser bundle
is also a meaningful weight and a credential-handling smell.

### 7.3 Freshness & empty states — the P-1/P-2 difference

BDDAI's freshness indicator is unconditional and unguarded:

```tsx
// bddai-fe/src/components/layouts/dashboard-layout/header.tsx:110,146
const latestSync = headerprops?.latest_sync || 0;
<LastUpdatedIndicator ms={new Date(latestSync).getTime()} />
```

When `latest_sync` is absent, `|| 0` yields the Unix epoch and the pill renders a nonsense age
("56 years ago") via `msToDeltaTimeIndicator` (`src/utils/index.ts:322`). There is no branch for
"never synced," "syncing now," or "sync failed" — one number, one account, always rendered.

There is also no way to tell "the sync hasn't run" from "there is genuinely no data": the empty
state (`src/components/misc/platform-data-empty-state/index.tsx`) only distinguishes "you have
accounts, pick one" from "you have no accounts."

dashmet makes the distinction structural. `SyncAwareEmpty`
(`frontend/src/components/shared/sync-aware-empty.tsx`) consults **the section's own sync job**
before choosing its message:

```tsx
if (state === "syncing")      label = "Syncing… this fills in once the first sync finishes";
else if (state === "failed")  label = "Sync failed — it will retry automatically";
else                          label = "No data for this period";
```

and `SyncStatusBadge` resolves which job types matter for the *currently selected date preset*
(`RANGE_JOBS`, `sync-status-badge.tsx:18-27`), attaches an ETA per job type, and deliberately
renders the fresh state as neutral rather than lit-green:

```tsx
// fresh is calm, not lit-green (P-2): reuse the neutral idle treatment.
fresh: "border-border bg-muted/40 text-muted-foreground",
```

Manual sync is a *recovery path*, not a permanent button: it's owner-gated and shown alongside the
staleness reason. BDDAI's model is the inverse — the user initiates a websocket sync and is told
not to reload the tab.

---

## 8. Where dashmet is not yet living up to its own rules

Stating these plainly is part of the assessment. All are verifiable in the current tree.

**8.1 `attribution_window` is stored but never filtered on, and is not in the unique key.**
`.claude/rules/product-principles.md` P-9 calls this the flagship invariant. Reality:
- `metrics_daily`'s unique constraint is `(entity_type, entity_id, date)`
  (`app/models/metrics.py:16-19`) — `attribution_window` is **not** in it.
- `grep attribution_window app/services/insights.py` → **0 matches**. No read query filters it.

So today, changing an account's attribution window and re-syncing overwrites the previous window's
rows rather than storing both, and the "compare windows" capability the column exists for doesn't
work. This is the exact failure mode the rule was written to prevent, reproduced.

**8.2 `has_warning` is permanently true.** `app/services/sync.py:96-101` sets `has_warning = True`
for any job type with no row, and the `creatives` job type has **no producer** — `create_sync_job`
is called for `structure`, `insights_daily`, `insights_async`, `breakdown`, but never `creatives`
(`grep create_sync_job workers/tasks/`). So `jobs_status["creatives"]` is forever `pending` /
`is_stale: true`. That is BDDAI's own always-lit-warning bug, reproduced. It is at least tracked —
`BOARD.md` Todo item 4.

**8.3 `reach` is summed.** P-4 says non-additive metrics are never summed across rows.
`SUM(md.reach) AS reach` appears at `app/services/insights.py:315, 576, 806, 1206, 1259`. Summing
daily reach over 30 days overstates unique reach, sometimes badly.

**8.4 `frequency` looks inverted.** `insights.py:331-333` computes
`SUM(reach) / SUM(impressions)`. Meta defines frequency as impressions ÷ reach, so this returns the
reciprocal (a value < 1). Consistent across all five call sites, so it's a definition error rather
than a typo — but it should be verified against a live account before being relied on.

**8.5 No CI.** `.claude/rules/test-required-for-done.md` exists because BDDAI shipped without CI.
dashmet has no `.github/workflows/` either. 202 tests that nobody is forced to run are a
convention, not a gate. (Neither do any of the four BDDAI repos — this is a shared gap, not a
dashmet-specific one.)

**8.6 Reconciliation isn't built.** P-3 ("explainable drift is information") and the whole
reconciliation vocabulary in the rules describe a subsystem that does not exist —
`workers/tasks/reconcile.py` survives only as a stale `.pyc`. The docs currently over-promise
relative to the code.

**8.7 `docs/prd-parity.md` doesn't exist.** Four `.claude/rules` files cite it as the source of
truth. `BOARD.md` acknowledges this in a header note. The rules are real; their anchor isn't.

---

## 9. Where BDDAI is genuinely better

**9.1 Platform coverage.** BDDAI covers Meta, TikTok, TikTok Shop, Google Ads, Google Analytics 4,
Instagram, Shopee (ads + orders + campaigns), Shopify, plus budget tracking and notifications.
dashmet covers Meta, TikTok, Google Ads. The commerce side (Shopee/Shopify order data joined
against ad spend) is a real product capability dashmet has no equivalent for.

**9.2 `bddai-scheduler` is well-engineered — and is where the good work is.** 264 test functions
across 30 test files, including *parity* tests (`test_sc2_meta_parity.py`,
`test_sc2_tiktok_parity.py`, `test_sc2_google_ads_parity.py`, `test_sc2_gmv_parity.py`) and a
`MIGRATED_JOB_CONTRACTS` table (`testing/contracts.py`) that asserts a refactored job still matches
its legacy implementation symbol-for-symbol. That is a more disciplined migration technique than
anything in dashmet. Its drain engine (`db/crud_sync_job.py`) is carefully reasoned — the docstring
explains *why* plain `FOR UPDATE` instead of `SKIP LOCKED` (MariaDB 10.3), which is the kind of
constraint documentation dashmet mostly lacks.

**9.3 Production observability.** Sentry is wired in both `bddai-scheduler`
(`utils/observability.py`, with a bounded `shutdown_timeout` traced to a specific 2026-07-20 incident
where the default atexit flush held a cron flock past job completion) and `bddai-fe`
(`SENTRY_INTEGRATION.md`). dashmet has none. BDDAI's comment quality around incidents is better
than dashmet's — it records what actually broke in production, which dashmet cannot, because it
hasn't run in production.

**9.4 It works at scale, today.** 385 commits since Dec 2024, real accounts, real tokens, real
Meta throttling, real MariaDB 10.3 constraints. dashmet has 56 commits since May 2026 and has never
faced a rate limit it didn't simulate. Many of dashmet's clean invariants are untested against
adversarial reality, and some of BDDAI's ugliness is scar tissue from problems dashmet hasn't met yet.

**9.5 Operational maturity.** `DEPLOY.md` (18,953 bytes), `railway.json`, `.ecosystem.yml`,
`cron/manage_cron.sh`, `cron/migrate_to_hybrid.sh`, capacity planning docs. dashmet has a
`docker-compose.yml`.

**9.6 Token cipher design.** `bddai-scheduler/db/token_crypto.py` uses `MultiFernet` (key rotation)
where dashmet uses a single `Fernet` key (`app/services/auth.py:56`). BDDAI's is the better design;
dashmet should adopt it.

---

## 10. Verdict — why rebuild rather than extend

The rebuild is justified by four things that are *structural*, not cosmetic:

1. **One writer, one resolver, one metric definition is a topology property.** You cannot get
   read-write date parity across four repos that each own their own date code. The dashmet worker
   importing `app.services.insights.resolve_date_range` is not a nicer version of BDDAI's code —
   it is a shape BDDAI's repo boundaries make impossible.

2. **The refactor was already attempted in-place and stalled.** `bddai-service`'s empty `v4/handlers/`
   directories, its unenforced layering rule (23 violations against a documented target of 0), and
   its deleted-but-still-referenced `_live_data_error` envelope are the artifacts of a correct plan
   that couldn't land. With 0 tests in that repo and 1,000+ line endpoint files, it wasn't going to.

3. **A trust-first product needs the envelope in the schema, not the view.** "Never show a number
   without stating how trustworthy it is" requires `sync_jobs`, `fetched_at`, `attribution_window`,
   and per-job freshness to exist as first-class data. Retrofitting that into schemaless collections
   with no indexes, written by a delete-then-insert websocket, is a bigger job than writing it.

4. **The correctness bugs are in the write path, and the write path is the hardest thing to change
   safely.** Dropping all-zero rows, the attribution fallback cascade with a terminal `= 0`,
   `fill_missing_data` → 0, naive `datetime.now()`, no unique indexes — each is individually fixable,
   but they compound: you cannot verify a fix to any of them without a backfill, and you cannot
   safely backfill data whose provenance (`fetched_at`, `attribution_window`) was never recorded.

**What the rebuild has *not* yet earned:** production hardening, platform breadth, observability,
and — per §8 — several of its own headline invariants. The honest framing for the assessment is
that dashmet is a *proof that the contract can be fixed*, demonstrated across three platforms, not
a replacement for BDDAI as it stands. The strongest next moves are (a) close §8.1 and §8.2, since
they're the two claims the whole "trustworthy numbers" thesis rests on, (b) add CI so §8.5 stops
undermining the 202 tests, and (c) port `MultiFernet` and the parity-contract testing technique
*from* BDDAI, which are the two places BDDAI is unambiguously ahead.

---

## 11. Net-new capabilities — dashmet features with no BDDAI equivalent

Four things came up in review that don't map onto an existing BDDAI capability at all — they're
not "dashmet does it better," they're "BDDAI doesn't do this." Confirmed by grep across all four
BDDAI repos, excluding `venv`/`node_modules`: zero matches for `openai|anthropic|claude|gpt-` and
zero for `pptx|reportlab|jspdf|pdfkit` in actual source (the only hits were inside the Sentry SDK's
own optional AI-integration modules, which is dependency noise, not app code).

### 11.1 Organization / multi-tenancy

| | BDDAI | dashmet |
|---|---|---|
| Tenant concept | none — everything is keyed by `user_id` | `organizations` → `organization_memberships` → `users`, `role IN ('owner','member')` (`app/models/auth.py:65-108`) |
| Team access | N/A — one account credential row per user | Invite flow: `POST /org/members/invite` generates a token + expiry, `POST /org/members/accept-invite` redeems it (`app/api/v1/endpoints/org.py:71-133`) |
| Per-member scoping | N/A | `membership_accounts` — an explicit allowlist table; owners see every account, members see only what's granted, "no row = no access" (`app/models/auth.py:114-141`) |
| `role` field | exists (`Enum("admin","user")`, `user_model.py:11`) but **unenforced** — `grep "role ==\|RoleChecker\|Depends(.*Role"` across `bddai-service/app/` → 0 hits. It's read and displayed, nothing gates on it. | Enforced via typed dependencies — `OwnerUser` vs `CurrentUser` on every mutating org/connection/sync-trigger route |
| Duplicate invite guard | N/A | Partial unique index: one pending invite per email per org (`uq_membership_org_invite_email … WHERE invite_email IS NOT NULL`) |

BDDAI's `role` column is the tell here: the schema gestures at permissions but nothing reads it to
make a decision. dashmet's org model isn't an incremental improvement on that column — it's the
first time the product has an actual multi-user account boundary, which is a precondition for
selling to an agency (one BDD org, several client accounts, several staff with different account
access) rather than one login per client.

### 11.2 AI summary (on-demand diagnosis, not automation)

`backend/app/services/ai_summary.py` (508 LOC) — two entry points, both grounded strictly in
numbers the shared read path already computed:

- `generate_overview_diagnosis` — the on-screen card (`{headline, driver, watch, next_step}`).
- `generate_narrative` — prose for the PPTX export (§11.3).

What makes this more than "call OpenAI and hope": the system prompt enforces the same P-4/P-7
discipline as the rest of the product — *"NEVER perform arithmetic… every percentage change is
already given — QUOTE it, do not recompute it"* (`ai_summary.py:88-99`). The model is handed
pre-formatted strings, not raw floats, specifically so it isn't tempted to do math dashmet doesn't
trust it to do correctly. A missing key, timeout, API error, or unparseable completion raises
`AISummaryError`, which the endpoint maps to **502**, never a 200 with placeholder text
(`ai_summary.py:36-44` — P-4, "refuse to answer rather than answer wrong").

It's also cached against the same freshness token as the rest of the app, not a flat TTL:

```python
# app/api/v1/endpoints/insights.py:194-227
# aisum:v1:{account_id}:{period}:{filter_hash}:{cached_at_iso|nodata}
# cached_at = the get_overview freshness token — a re-sync moves it → new key → miss
```

so a stale AI summary can never outlive the data it was generated from, and re-syncing invalidates
it automatically rather than on a timer. There's a cache-only `GET /overview/summary/peek` (204 on
miss) so the card can show a previously-generated summary on page load **without spending a token**
— generation is `force`-gated, explicitly opt-in (P-5: manual is a recovery path, not automatic).

BDDAI has no LLM integration anywhere in any of the four repos — this is a genuinely new product
surface, not a reimplementation.

### 11.3 PPTX export ("deliverable, not just a dashboard")

`backend/app/services/export.py` (725 LOC) — a pure builder: `generate_overview_pptx` takes the
same dicts `get_overview`/`get_timeseries`/`get_table` already produced for the web UI and lays
them onto a branded 16:9 deck (cover, KPI hero, metric cards with coloured deltas, trend overlay,
top-ads slide, closing slide). It does **no DB access and no metric computation** — the module
docstring is explicit that this is what makes P-6 ("report numbers and dashboard numbers identical
by construction") hold: there's one code path that computes a number, and the deck reads it the
same way the screen does.

Two details worth noting:

- The color palette comment (`export.py:47`) reads *"BDD-style, generic dashmet branding"* — this
  was explicitly built to replace a manual monthly-report deck agencies were assembling by hand.
- `include_ai_summary` (default **off**) opt-in wires §11.2's narrative into "editable purple
  insight boxes" on the slides (`export.py:64`, endpoint `insights.py:358-414`) — export and AI
  summary compose, but neither forces the other on.

The frontend gate mirrors the backend's opt-in default: *"Opt-in AI insight boxes in the exported
deck. Default OFF so the standard export never spends tokens"* (`frontend/src/components/layout/control-strip.tsx:37-38`).

BDDAI has no report-generation code at all — no `pptx`, `reportlab`, or equivalent library anywhere
in any of the four repos' actual source. Any client-facing report today is manual.

### 11.4 Celery vs. cron+CLI — comparing the operating model, not just correctness

§4 already covered the correctness gap (job-run tracking, retry semantics). Setting that aside,
they're also different *operating models*, and the difference matters for anyone reading this as
an assessment of what to build going forward:

| | BDDAI (`bddai-scheduler`) | dashmet (Celery) |
|---|---|---|
| Deployment | single VM, `crontab` + `flock`, `BASE_DIR=/var/www/scheduler` (literal path in the crontab, `cron/cron_bddai_hybrid.txt:4`) | 5 independently-scalable containers: `celery-worker` (meta), `celery-worker-tiktok`, `celery-worker-google`, `celery-poll-worker`, `celery-beat` (`docker-compose.yml:48-125`) |
| Scale-out | none — adding capacity means a bigger box | `docker compose up --scale celery-worker=N`, called out explicitly in a comment at `docker-compose.yml:64` |
| Sync cadence | Meta/TikTok/content/Shopify every 2 hours (`0 */2 * * *`); Google Ads/Analytics once daily | insights every 15 min, structure every 30 min, breakdowns hourly (`workers/celery_app.py:84-113`) |
| Per-platform isolation | all jobs share one process/box; a slow Google Ads batch can delay Meta's cron slot | separate Celery queues per platform (`meta`/`tiktok`/`google`/`poll`) — one platform's backlog doesn't block another's |
| Stuck-job recovery | `find … -mmin +120 -exec … rm -f` — a cron line that force-deletes any lock file older than 2 hours, unconditionally | `task_acks_late=True` — a crashed worker's task is automatically re-queued by the broker; lock TTL is derived from the task's own hard time limit (`celery_app.py:14-15`) |
| Observability | log files (`$BASE_DIR/logs/*.log`) + Sentry | Celery's native task state (`SUCCESS`/`FAILURE`/`RETRY`) + `sync_jobs` table |

Neither is strictly "more correct" as an architecture — BDDAI's is simpler to operate on one box
and has real production mileage (§9.4); dashmet's is the shape you need once sync volume or
platform count grows past what one cron box comfortably serializes. The concrete gain is
**per-platform blast-radius isolation** (a Google Ads rate-limit incident can't delay Meta syncs)
and **horizontal scale without redesign** — both of which BDDAI's single-box-plus-crontab model
would need a rewrite to get, not a config change.

---

## Appendix — file:line index of claims

| Claim | Location |
|---|---|
| FE talks to two backends | `bddai-fe/src/axios/index.ts:4-18` |
| Duplicate MySQL model defs | `bddai-service/app/models/user_model.py:20`, `bddai-binding-app/app/models/user_model.py:19` |
| No Mongo index creation | `grep -rn "create_index" bddai-scheduler/` → 0 |
| Layering rule violated 23× | `grep -rn "from app.repository" bddai-service/app/endpoints/` |
| `v4/handlers/` empty | `find bddai-service/app/endpoints/v4 -type f` → only `.pyc` |
| No `SuccessResponse` in v3 | `grep -c SuccessResponse bddai-service/app/endpoints/v3/*.py` → 0 |
| 13 Mongo singletons, one file | `bddai-service/app/endpoints/v3/google_ads.py:26-38` |
| `MongoClient` per repository | `bddai-service/app/repository/*_repository.py:10` |
| All-zero rows dropped | `bddai-scheduler/platforms/meta/jobs/insights_shared.py:255` |
| Attribution fallback cascade → 0 | `bddai-scheduler/platforms/meta/jobs/insights_shared.py:169-194` |
| Naive `datetime.now()` in resolver | `bddai-scheduler/utils/date_utils.py:49-55` |
| Week range includes future | `bddai-scheduler/utils/date_utils.py:59-67` |
| Delete-then-insert over websocket | `bddai-binding-app/app/endpoints/v3/websocket_sync.py:441-451` |
| "DO NOT reload this tab" | `bddai-fe/src/components/misc/sync-data-info/index.tsx:33` |
| Plaintext `VARCHAR(255)` token | `bddai-binding-app/app/models/user_model.py:25` |
| Token validation discarded | `bddai-binding-app/app/endpoints/v3/bind.py:113-118` |
| Missing binding → HTTP 401 | `bddai-service/app/utils/utils.py:281` |
| 401 → force logout | `bddai-fe/src/axios/index.ts:47-53` |
| `fill_missing_data` → 0 | `bddai-service/app/endpoints/v3/meta.py:114-122` |
| Div-by-zero → 0 | `bddai-service/app/repository/meta_repository.py:171-176` |
| Ratios after `$group` (correct) | `bddai-service/app/repository/meta_repository.py:344-352` |
| `latest_sync \|\| 0` | `bddai-fe/src/components/layouts/dashboard-layout/header.tsx:110` |
| dashmet shared resolver | `backend/app/services/insights.py:23`, `backend/workers/date_range.py:15` |
| dashmet COALESCE upsert | `backend/workers/db_helpers.py:87-124` |
| dashmet two-txn sync_jobs | `backend/workers/db_helpers.py:41-80` |
| dashmet throttle headers | `backend/workers/meta_client.py:53-80` |
| dashmet staggered dispatch | `backend/workers/dispatch.py:17-53` |
| dashmet OAuth CSRF state | `backend/app/api/v1/endpoints/connections.py:86-95` |
| dashmet token encryption | `backend/app/services/auth.py:55`, `accounts.py:209` |
| dashmet token pre-validation | `backend/app/api/v1/endpoints/connections.py:45-56` |
| dashmet sync-aware empty | `frontend/src/components/shared/sync-aware-empty.tsx` |
| **dashmet**: attribution not in UK | `backend/app/models/metrics.py:16-19` |
| **dashmet**: attribution never read | `grep attribution_window backend/app/services/insights.py` → 0 |
| **dashmet**: `creatives` has no producer | `grep create_sync_job backend/workers/tasks/` |
| **dashmet**: `SUM(reach)` | `backend/app/services/insights.py:315,576,806,1206,1259` |
| **dashmet**: frequency inverted | `backend/app/services/insights.py:331-333` |
| No CI in any of the 5 repos | `ls */.github/workflows` → none |
