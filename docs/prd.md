# dashmet — Product Requirements Document

> **Version:** 0.3
> **Status:** Draft — living document, updated as the product changes
> **Product:** dashmet
> **As of:** 2026-08-05, `development` branch
> **Companion doc:** `docs/architecture-spec.md` covers technology stack, system components, and deployment — kept separate so this document stays focused on what dashmet does and why, not how it's built.

---

## Table of Contents

1. [Overview & Vision](#1-overview--vision)
2. [Goals](#2-goals)
3. [Users](#3-users)
4. [Platforms Supported](#4-platforms-supported)
5. [Functional Requirements](#5-functional-requirements)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [Guardrails](#7-guardrails)
8. [Non-Goals](#8-non-goals)
9. [Known Gaps & Risks](#9-known-gaps--risks)
10. [Roadmap](#10-roadmap)
11. [Glossary](#11-glossary)

---

## 1. Overview & Vision

dashmet is a multi-platform marketing analytics dashboard. It syncs ad performance data from Meta Ads, TikTok Ads, and Google Ads into one normalized database and serves it through a REST API to a web dashboard, with report export and an AI-assisted narrative layer on top.

The core promise: **every number on screen should be traceable** — how fresh it is, what date range and attribution window it covers, and whether the account is still mid-sync. A dashboard that shows a confident-looking number with no way to tell if it's an hour old or silently wrong is worse than no dashboard at all.

## 2. Goals

- Give a marketer or agency one place to see performance across Meta, TikTok, and Google Ads, instead of three separate ad managers.
- Make data freshness and trustworthiness a visible property of every number, not an assumption the user has to make.
- Make exported reports and the live dashboard structurally unable to disagree — same numbers, same code path.
- Support multiple organizations and teams with real access control, so an agency managing several clients' ad accounts can do it safely — one teammate's access to Client A's account doesn't imply access to Client B's.

## 3. Users

- **Org owner** — connects ad platforms, invites teammates, has unrestricted access to every account in the organization.
- **Org member** — invited by an owner; sees only the accounts explicitly granted to them.
- **Marketer / media buyer** (inferred from the feature set, not confirmed via user research) — checks performance regularly, compares periods, exports reports for stakeholders.
- **Agency account manager** (inferred) — manages multiple client accounts within one org and needs to control who on their team sees what.

## 4. Platforms Supported

| Platform | Coverage |
|---|---|
| Meta Ads | Campaign → ad group → ad → creative, daily metrics, breakdowns, CPAS shared-item metrics |
| TikTok Ads | Same structure, plus onsite/shop, engagement, and LIVE metrics |
| Google Ads | Campaign → ad group → ad → creative, daily metrics |
| TikTok Shop / GMV Max | Built, not yet shown to users — see [§9](#9-known-gaps--risks) |

Support for additional platforms is a real possibility but isn't scoped or committed anywhere in the current codebase — adding one is new scope, not a documented gap.

## 5. Functional Requirements

### FR-1 — Authentication & Organizations
- **FR-1.1** Users can create an account with email and password.
- **FR-1.2** New accounts go through an email verification step.
- **FR-1.3** Users can log in and log out.
- **FR-1.4** Users can reset a forgotten password via an emailed link.
- **FR-1.5** A user can belong to more than one organization, each with a role of `owner` or `member`.
- **FR-1.6** Organization owners can invite new members by email.

*Status: Shipped.*

### FR-2 — Platform Connections
- **FR-2.1** An organization can connect one account per supported platform (Meta, TikTok, Google Ads) via OAuth (Meta via a system-user token).
- **FR-2.2** A platform connection can be deactivated without deleting the historical data synced under it.

*Status: Shipped.*

### FR-3 — Account Management & Access Control
- **FR-3.1** All ad accounts visible under a connection are discoverable and selectable within the org.
- **FR-3.2** An account can be disabled, hiding it from every view without deleting its data.
- **FR-3.3** Organization owners can grant or revoke individual members' access to specific accounts.
- **FR-3.4** Each account has configurable settings: primary conversion action, attribution window, and ROAS action type.

*Status: Shipped.*

### FR-4 — Data Sync
- **FR-4.1** The system automatically syncs campaign/ad group/ad/creative structure and daily performance metrics on a recurring schedule.
- **FR-4.2** A newly connected account's first sync is triggered immediately rather than waiting for the next scheduled run.
- **FR-4.3** Every sync attempt is recorded with a status (`pending`/`running`/`completed`/`failed`), independent of whether it succeeded.
- **FR-4.4** Users can manually trigger a sync as a recovery action.

*Status: Shipped — except the `creatives` sync type doesn't yet satisfy FR-4.3 (see §9).*

### FR-5 — Insights Dashboard
- **FR-5.1** Users can view an Overview (headline KPIs), Trends (time series), Table (entity breakdown), Ads (creative-level), and Funnel (conversion steps) for each connected platform.
- **FR-5.2** Users can view a combined dashboard rolling up all connected platforms side by side.
- **FR-5.3** Users can toggle a period-over-period comparison, shown as visual deltas.
- **FR-5.4** Each dashboard section reflects its own sync status (syncing / no data / has data) rather than one global loading state.

*Status: Shipped; FR-5.4's badge/empty-state wiring still needs verification (see §9).*

### FR-6 — Reporting & Export
- **FR-6.1** Users can export a single account's overview as a PowerPoint file.
- **FR-6.2** Exported numbers are generated from the same functions that power the live dashboard.

*Status: Shipped.*

### FR-7 — AI-Assisted Insights
- **FR-7.1** Users can request an AI-generated diagnosis of an account's performance (headline, likely driver, something to watch, a suggested next step).
- **FR-7.2** The diagnosis is cached and reused until the underlying data changes.
- **FR-7.3** Users can optionally include the AI diagnosis in a PPTX export.

*Status: Shipped.*

## 6. Non-Functional Requirements

dashmet's non-functional requirements come from a small set of principles that are also enforced as active engineering rules in this repo (`.claude/rules/product-principles.md`), not just aspirational text: show your work, stay quiet when things are fine, and refuse to answer rather than answer wrong.

- **NFR-1 — Data trustworthiness & freshness.** Every insights response must indicate how fresh and complete the underlying data is, not just the number itself (e.g. a `data_as_of` timestamp derived from the actual last-synced time, never `now()`).
- **NFR-2 — Consistency & correctness.** A given metric must be computed the same way everywhere it appears — dashboard, export, and API share one definition and one code path. Rate metrics (CTR, CPM, ROAS, …) are computed only after aggregation, never averaged row-by-row. Non-additive metrics (e.g. `reach`) are never summed across rows.
- **NFR-3 — Reliability & fault tolerance.** A sync failure must leave a queryable record, not just a gap in the data. A failed upstream platform request must never be silently reported as a `0`.
- **NFR-4 — Security & multi-tenancy isolation.** An organization must never be able to see another organization's data. Platform access tokens are encrypted at rest. Member-level access is enforced per account, not just per organization.
- **NFR-5 — Testability.** Invariants that are expensive to get wrong — date-range resolution, cross-org isolation, sync-type completeness, upsert idempotency — must be covered by an automated test, not left to code review alone.
- **NFR-6 — Usability: calm by default.** Warnings, sync badges, and loading states must reflect actual system state and disappear once nothing is wrong — no permanently-lit indicators, no "just now" shown when data isn't actually fresh.
- **NFR-7 — Maintainability.** API endpoints stay thin (routing + validation only) and delegate business logic to a service layer, so the codebase stays changeable without regressions in unrelated areas.
- **NFR-8 — Performance** *(qualitative — no formal SLA is documented today)*. Dashboard reads are cached client-side with stale-times aligned to backend sync cadence, and metrics tables are indexed on `(account_id, date)`-style keys for the common query patterns. If specific latency/throughput targets are wanted, they need to be decided and added here.

Current compliance against these isn't 100% — see §9 for the specific, real gaps (e.g. NFR-2 and NFR-5 both have a named open item). See `docs/architecture-spec.md` for how the system is built to support these (async workers, per-platform queues, Postgres constraints, etc.).

## 7. Guardrails

Things dashmet deliberately does not do, because getting them wrong is costly:

- Never converts between currencies — accounts in different currencies are shown separately, never summed or converted.
- Never sums a rate metric (CTR, CPM, etc.) across rows — ratios are computed only after aggregating the underlying counts.
- Never turns a failed request to a platform's API into a fake `0` — a failure has to look like a failure, not a suspiciously quiet number.
- Never drops an all-zero row from a report — a campaign that dropped to zero spend is still a real data point, not noise to filter out.
- Never sends a relative date shortcut (like "last 7 days") straight to a platform's API — it's resolved to explicit calendar dates in the account's own timezone first, so what gets synced and what gets displayed always agree.

## 8. Non-Goals

- **Not a bidding or budget-optimization tool.** dashmet reports on performance; it doesn't manage bids or budgets on the connected platforms.
- **Not a blended cross-platform metric fabricator.** The combined view shows each platform's real numbers side by side — it doesn't invent a single blended CTR/ROAS across platforms that don't share a measurement methodology.
- **Not a custom report builder (yet).** Export today is a fixed-format account overview, not an arbitrary report designer.

## 9. Known Gaps & Risks

Found while documenting the current codebase — real, current state, not hypothetical:

- **Metrics upserts aren't fully windowed by attribution window** (NFR-2, NFR-5). `metrics_daily` stores an `attribution_window` per row, but the database constraint that prevents duplicate/overwritten rows doesn't currently include it. A re-sync under a different attribution-window setting could silently overwrite numbers computed under the previous one.
- **One endpoint bypasses the service layer** (NFR-7). The login endpoint queries the database directly instead of going through the existing auth service — a small inconsistency, but exactly the kind that makes future auth changes error-prone.
- **No automated tests on the core auth flow** (NFR-5). Signup, login, email verification, and password reset have no dedicated test coverage today, despite being the entry point to everything else.
- **Reconciliation isn't built yet** (NFR-1). Periodically checking dashmet's stored numbers against what a platform itself reports, and flagging unexplained drift, is part of how this product is meant to earn trust — it doesn't exist as a feature yet.
- **Two sync-freshness UI pieces are mid-flight** (FR-5.4). The global sync-status badge and per-section empty states are implemented but not yet verified with browser or automated frontend tests.
- **`creatives` sync doesn't report its own status** (FR-4.3). Every other sync type records "did this run and how did it go"; creatives currently don't, so their status always reads as "never synced" even after they have run.
- **Production deployment topology isn't documented** (see `docs/architecture-spec.md` §7) — this repo documents local Docker Compose only.

## 10. Roadmap

Live, granular status lives in `docs/tasks.md` — this is the shape, not the day-to-day state.

**Near-term**
- Finish verifying the sync-freshness UI (global badge + per-section empty states).
- Give `creatives` sync its own status tracking.
- Fix the date-range-preset off-by-one (`last_Nd` currently covers N+1 days instead of N).
- Decide whether TikTok Shop / GMV Max ships — the UI is built and waiting on real shop-conversion data.

**Medium-term**
- Close the attribution-window upsert gap in `metrics_daily`.
- Build the reconciliation feature described in §6 (NFR-1) / §9.
- Route the login endpoint through its service layer; add test coverage for the auth flow.

New platforms or major features aren't listed here because none are currently scoped in this repo — adding one is a scoping decision, not a documentation gap.

## 11. Glossary

- **`entity_type` / `entity_id`** — the polymorphic key pattern the metrics tables use so one schema serves accounts, campaigns, ad groups, and ads without four separate tables.
- **`attribution_window`** — the conversion-attribution setting (e.g. 7-day-click / 1-day-view) a metric was computed under.
- **`sync_jobs`** — the record of every sync attempt: what ran, when, and how it went.
- **Reconciliation** — the not-yet-built feature that checks dashmet's stored numbers against a platform's own reported numbers.
