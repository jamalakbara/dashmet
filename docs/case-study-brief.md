# dashmet — Case Study Brief

**Submission for:** Super Staff Leveling Program 2026 — Back-End Developer Assessment, Mission 1
**Product:** dashmet
**Repo:** https://github.com/jamalakbara/dashmet
**Companion documents:** `docs/prd.md` (product requirements), `docs/architecture-spec.md` (system design),
`docs/backend-api-spec.md` (API reference), `docs/internal-schema-spec.md` + `docs/erd.md` (database schema),
`docs/sync-worker-spec.md` (Celery task behavior), `docs/dashmet-vs-bddai.md` (full code-level comparison
against the reference product, with file:line citations for every claim in this brief)

---

## 1. The selected product / reference

The reference product is **BDDAI's ad-metrics dashboard** — a multi-platform marketing analytics
tool that syncs Meta, TikTok, Google Ads (and several commerce platforms) into a database and
serves the data through a dashboard and report exports. It's built as four separately-deployed
repositories: `bddai-fe` (web client), `bddai-service` (read API), `bddai-scheduler` (sync workers),
and `bddai-binding-app` (OAuth/account binding) — together roughly 82,000 lines across MySQL and
MongoDB.

dashmet targets the same product category and the same core user (a marketer or agency who wants
one place to see ad performance across platforms) but is built as a single repository with one
schema and one shared code path between reads and writes.

## 2. The chosen approach

**Approach A — build a new product of a similar type from scratch.**

This was chosen over reimagining-in-place or forking after reading BDDAI's own codebase closely.
The problems worth fixing are not in any one feature — they're in the *topology*: four repos share
a MySQL/MongoDB database but not a data model, a date-resolution function, a response envelope, or
a tenancy model. Concretely:

- Each repo independently reimplements date-range resolution (`bddai-scheduler` alone has three
  separate implementations, all using naive server-local time), so there is no guarantee the date
  window a sync worker *wrote* is the same window the API *reads*.
- `bddai-service`'s own project rules already specify the target architecture (`SuccessResponse[T]`
  envelope, strict `handler → service → repository` layering, `app/service/` singular for platform
  clients) — and the code violates it in 23 places against a documented target of zero. The refactor
  was correctly diagnosed and started, then stalled: `app/endpoints/v4/handlers/` exists as empty
  directories, and the repo has effectively no test suite to refactor safely against.
- Several correctness issues live specifically in the *write path* (a sync job that returns
  all-zero metrics is dropped rather than stored; an attribution-window fallback chain silently
  substitutes windows and terminates in a stored `0` when nothing matches; there are zero database
  indexes enforcing document uniqueness in MongoDB). These aren't features to add — they require
  redesigning how data is written, which is materially harder to do safely inside four repos with
  ~0 CI and ~0 tests than to demonstrate correctly in a new one.

Given the assessment's evaluation criteria (data management, APIs, services, system architecture),
building a new product from scratch let the submission demonstrate the *fix* directly — one
resolver, one schema, one writer — rather than describing it as a plan. The full evidence for this
reasoning, file-by-file, is in `docs/dashmet-vs-bddai.md`.

## 3. User flow changes, new feature ideas, and their rationale

| Change | What it is | Problem it solves |
|---|---|---|
| **Freshness as a first-class UI state** | Every dashboard section reads its own `sync_jobs` status and renders "Syncing…" / "No data" / "Sync failed" instead of one global timestamp | BDDAI's freshness indicator is a single `latest_sync \|\| 0` value with no branch for "never synced" — an unbound section silently looks like genuine zero data |
| **Organizations & per-member account access** | `organizations` → `organization_memberships` (owner/member) → `membership_accounts` allowlist, with an invite/accept-invite flow | BDDAI has no tenant concept at all — everything is keyed by `user_id`, so there's no way for an agency to give one staff member access to one client's accounts without giving them everything |
| **AI-assisted diagnosis (on-demand, not automatic)** | `POST /insights/overview/summary` asks an LLM to *diagnose* an already-computed overview (headline/driver/watch/next-step), grounded strictly in numbers the read path already produced — the model is explicitly instructed never to do arithmetic, only quote and select | Turns "here are some numbers" into "here's what changed and why," without the model being able to invent a figure. Cached against the same freshness token as the underlying data, so a re-sync invalidates it automatically rather than on a timer |
| **PPTX export reusing the live read path** | `GET /insights/overview/export.pptx` builds a branded deck from the exact same `get_overview`/`get_table`/`get_timeseries` functions the dashboard calls — no separate query path | BDDAI has no report-export capability; any client deck today is assembled by hand. Reusing the same functions guarantees the deck and the dashboard can't disagree — not by convention, by construction |
| **Idempotent, non-destructive upserts** | `INSERT … ON CONFLICT DO UPDATE SET col = COALESCE(excluded.col, table.col)` — a re-sync never overwrites a known value with an absent one | BDDAI drops all-zero rows before writing and, on one sync path, deletes-then-reinserts a date range non-transactionally — both can silently lose previously-correct data on a retry |
| **One shared date resolver, imported by both read and write paths** | `workers/date_range.py` imports `resolve_date_range` directly from the API service layer | Guarantees the window a worker fetches from Meta/TikTok/Google is the same window the API later queries — read/write parity by construction, not by four repos agreeing independently |
| **Per-platform Celery queues + non-blocking rate-limit backoff** | Separate queues (`meta`/`tiktok`/`google`/`poll`), horizontally scalable per platform; a rate-limited task reschedules itself instead of sleeping a worker slot | BDDAI runs everything through cron on one box — a slow Google Ads batch can delay Meta's sync slot, and its rate limiting doesn't read the platform's actual throttle headers |

## 4. Technical decisions and system design considerations

**Stack.** FastAPI 0.115 + SQLAlchemy 2 (async) + Pydantic 2 on PostgreSQL 16; Celery + Redis for
background sync; Next.js 16 + React 19 + TanStack Query 5 for the frontend. Full rationale for each
choice is in `docs/architecture-spec.md`.

**Layering.** Strict `endpoint → service → SQLAlchemy session`; endpoints parse/validate and call
one service function, services own business logic and queries. This is the layering rule BDDAI's
own docs describe but the code doesn't enforce (`grep "from app.repository" bddai-service/app/endpoints/`
returns 23 hits against a documented target of 0) — dashmet's version holds by construction: its
largest endpoint file is 565 lines versus BDDAI's largest at 1,851.

**Data model.** One normalized structural hierarchy (`account → campaign → ad_group → ad →
creative`) plus a shared, platform-agnostic metrics layer (`metrics_daily`, `metric_action_stats`,
`metric_breakdowns`) so Meta, TikTok, and Google Ads write through the same shape instead of one
Mongo collection per platform per level (BDDAI has 13+ collections for Google Ads alone). Adding a
new metric is a new row in `metric_action_stats`, not a schema migration.

**Multi-tenancy & security.** JWT auth (HS256, single shared secret — appropriate for a
single-service deployment; documented in `architecture-spec.md` as a decision that would need to
change to an asymmetric key-pair if this became a multi-service architecture). Every account
belongs to exactly one organization; every account-scoped query resolves against the requesting
user's accessible account IDs before running. Platform OAuth tokens are encrypted at rest (Fernet)
rather than stored plaintext. Ten dedicated tests assert cross-organization access returns 403.

**Scalability & caching.** Each platform's Celery workers run as separate processes/queues, scaled
independently (`docker compose up --scale celery-worker=N`, or the equivalent replica count under
an orchestrator) rather than by raising concurrency on one shared pool — so a backlog on one
platform's queue never blocks another's. Rate-limit backoff is non-blocking (a throttled task
re-dispatches itself with a countdown instead of holding a worker) and scoped per-connection via a
Redis-backed state key, so one organization's rate-limited Meta token doesn't stall other
organizations' Meta syncs. Client-side caching via TanStack Query stale-time; the AI-summary
endpoint additionally caches in Redis under a key that embeds the data's own freshness token, so a
cache hit is only possible when nothing has changed since the summary was generated.

**Backend standards.** Pydantic-validated request/response schemas throughout; centralized
exception handlers (`NotFoundError`, `ForbiddenError`, `ConflictError`, `InvalidTokenError`,
`RequestValidationError`) so error shape is consistent across the API rather than each endpoint
building its own; sync-job lifecycle is tracked as data (`sync_jobs` row committed *before* an
external call, in its own transaction, finalized in a second transaction) so a worker crash mid-sync
still leaves a record instead of a silent gap.

**Known gaps**, documented rather than hidden: `attribution_window` is stored per metric row but is
not yet part of the table's unique key and isn't filtered on in reads, so re-syncing an account
after changing its attribution window currently overwrites rather than versions the prior window's
data; there is no CI pipeline yet enforcing the test suite (202 tests exist, but nothing blocks a
merge on them failing); a reconciliation subsystem described in the product principles is not yet
built. These are named explicitly in `docs/dashmet-vs-bddai.md` §8 rather than left implicit.

## 5. Deployment notes

**Current state.** The full stack runs via Docker Compose for local development: `frontend` (Next.js
dev server, port 3000), `backend` (FastAPI with `--reload`, port 8000, OpenAPI docs at `/api/docs`),
`postgres` (16-alpine, healthchecked), `redis` (7-alpine, healthchecked), and five Celery processes
(`celery-worker` for Meta, `celery-worker-tiktok`, `celery-worker-google`, `celery-poll-worker` for
Meta's async report polling, and `celery-beat` as the scheduler). All backend-family containers
build from `./backend` with the source live-mounted — this is a development configuration
(`--reload`, `npm run dev`), not a production image build. Required secrets (`SECRET_KEY` for JWT
signing, `ENCRYPTION_KEY` for token encryption) are generated locally per `README.md` and supplied
via `.env` files that are not committed.

**What a production deployment needs, not yet done here:** production-mode container builds
(dropping `--reload`/live-mount, running a real ASGI process manager), TLS termination, a secrets
manager instead of local `.env` files, and a decision on orchestration (the same Compose topology
under Kubernetes/ECS/Nomad, or a simpler single-host `docker compose -f docker-compose.prod.yml up`
depending on target scale). None of this is documented yet because the target hosting environment
for this submission wasn't finalized before this brief was written — this section will be updated
with the live URL once deployed to the environment provided for the assessment.

## 6. AI usage notes

dashmet was built using Claude Code with a deliberately narrow multi-agent setup rather than one
general-purpose assistant working across the whole codebase. Seven subagents each own one layer,
with an explicit "does NOT touch X" boundary in their own definition to stop scope creep:
`backend` (FastAPI/Pydantic/SQLAlchemy service layer), `workers-sync` (Celery tasks + platform API
clients), `db-migration` (models + Alembic, nothing else), `frontend` (Next.js/React), `docs`
(reconciles `docs/*.md` against what the code actually does, writes no feature code), `testing`
(pytest coverage, writes no production code), and `reviewer` — a read-only agent whose only output
is a punch list of findings, never a fix.

**How AI-generated changes were reviewed and constrained**, concretely:

- The `reviewer` subagent re-reads the actual `git diff` (not the authoring agent's self-report)
  against six checklists: unnecessary abstraction/over-engineering (`kiss-principle`), N+1
  queries and complexity regressions (`algorithmic-complexity-review`), async/FastAPI
  anti-patterns including blocking calls in `async def` and sync DB sessions in async paths
  (`python-backend`), Celery anti-patterns like missing retry/idempotency or unbounded fan-out
  (`celery-expert`), ORM/migration anti-patterns (`sqlalchemy-alembic-expert`), and missing test
  coverage (`python-testing-patterns`). It explicitly checks for raw SQL bypassing the ORM — the
  most direct injection surface a generated change could introduce.
- Five project-level rules gate what counts as a *complete* change, not just a correct-looking one:
  a schema/API change must land with the matching `frontend/src/lib/api/*.ts` update in the same
  change (`api-contract-parity.md`) so drift is caught at compile time, not runtime; a `docs/*.md`
  spec must be updated in the same change as the behavior it describes (`docs-sync.md`); nothing
  moves to "Done" on the task board without a named test exercising the behavior, and eight
  specific correctness invariants (attribution-window filtering, date-resolver parity, upsert
  idempotency, tenant isolation on every endpoint, among others) require a *structural* test, not
  just a passing one (`test-required-for-done.md`); and a fixed list of hard anti-requirements —
  never convert an upstream API error into a fake `200`, never sum a non-additive metric, never
  drop an all-zero row, never emit a notification as a side effect of a `GET` — are checked against
  every change touching insights/sync/reconciliation code (`product-principles.md`).
- Security-relevant decisions that came out of this process specifically: platform OAuth tokens are
  encrypted at rest (Fernet) rather than stored plaintext; the OAuth flow uses a CSRF `state` token
  in Redis with a TTL rather than trusting the callback alone; cross-organization access is denied
  and tested (10 dedicated tests asserting 403, not just documented as expected); error responses
  are sanitized to strip `access_token=` query parameters before being persisted to the `sync_jobs`
  error column, so a logged failure can't leak a live credential.
- The competitive analysis behind §2 and §3 of this brief (`docs/dashmet-vs-bddai.md`) was itself
  AI-assisted research — reading the reference product's source directly rather than its docs, with
  every claim checked against a specific file and line number, verified against the actual repo
  before being included. That verification pass caught and corrected two line-number citations that
  were off by one before the document was finalized.

What this brief does *not* claim: it does not assert 100% manual line-by-line human review of every
AI-generated diff. The claim is narrower and verifiable — the review is structural and repeatable
(a fixed reviewer checklist, five enforced project rules, a required test for named invariants)
rather than relying on a human catching every issue by inspection alone, which is the same class of
gap PARITY's own rules (`test-required-for-done.md`) name as BDDAI's original failure mode: shipping
without a test and calling it done on confidence.
