# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project aims to.

## [Unreleased]

### Changed
- Ad creative thumbnails now use a 4:5 portrait frame with `object-contain` (zero crop)
  instead of a 16:9 `object-cover` frame that cropped heads/text off Meta feed creatives.
  Applies to grid `AdCard`s and the detail sheet; skeletons match. Added a `fit` prop to
  `CreativeThumbnail` (list-view row thumb stays `cover`).
  `frontend/src/components/views/ads-view.tsx`.
- Sync status badge no longer reports a blanket "Updated Xm ago" when only the primary
  (`insights_daily`) job is fresh — if the secondary `breakdown` job is still pending/running
  it shows "Partially synced — breakdowns pending" (P-2). Creatives excluded (no sync_job
  producer yet). `frontend/src/components/shared/sync-status-badge.tsx`.
- Meta sync workers now resolve `date_preset` → explicit `time_range` in the account's
  timezone before calling the Graph API, instead of sending the raw preset (PRD §2.3 / P-7).
  Uses the same resolver as the read path (`app.services.insights.resolve_date_range`) via a
  new `workers/date_range.py::meta_time_range`, so synced days == queried days by construction.
  Affects `workers/tasks/insights.py` (daily + breakdowns), `workers/tasks/async_jobs.py`,
  `workers/meta_client.py` (`get_insights` now requires `time_range`, no longer accepts `date_preset`).

### Added
- Eager first sync on connect — `sync_accounts_for_connection` now enqueues `insights_daily`
  + `breakdown` for the just-connected connection's accounts (scoped, via `stagger_dispatch`)
  instead of leaving them for the next 15-min/hourly Beat. Breakdowns are no longer empty for
  up to an hour after connect. `backend/workers/tasks/structure.py`. Test:
  `backend/tests/test_stagger_dispatch.py` (dispatch mechanism).
- Sync-aware empty states — breakdown and ads sections read their own `jobs_status[job_type]`
  from `/sync/status` and show "Syncing…" instead of "No data"/"No ads found" when the relevant
  job hasn't completed yet (P-1). New `frontend/src/hooks/use-sync-jobs.ts` +
  `frontend/src/components/shared/sync-aware-empty.tsx`; wired into `breakdown-section.tsx`
  (keys on `breakdown`) and `ads-view.tsx` (keys on `insights_daily`, i.e. ad rows).
- Read-vs-write date-range parity test — `backend/tests/test_date_range_parity.py`
  (presets × timezones; asserts worker `time_range` == read resolver; rejects unknown presets). PRD §11.

### Fixed
- Dashboard sections now auto-refresh as a sync lands, instead of only the Overview KPI cards.
  Previously Trends, Breakdown, campaigns Table, and Ads mounted empty, cached for 15–30 min,
  and never refetched when the background sync wrote data — so after "Updated Xm ago" they stayed
  blank until a manual refresh. Added `useSyncActive()` (derived from real `sync_jobs` state, not a
  blind 5-min timer) and gave every section `refetchInterval: syncActive ? 5000 : false`. Replaces
  the Overview-only 5-min poll timer. `frontend/src/hooks/use-sync-jobs.ts`,
  `overview-view.tsx`, `periodic-view.tsx`, `table-view.tsx`, `ads-view.tsx`, `breakdown-section.tsx`.
- Breakdown sync now records a `sync_jobs` row (`job_type = "breakdown"`, committed running
  before the first API call, finalized on every exit path) — previously it had no producer, so
  the freshness badge was permanently stuck on "Partially synced — breakdowns pending" and the
  breakdown section's empty state permanently showed "Syncing…" (P-2/P-8).
  `backend/workers/tasks/insights.py`. Also normalized TikTok/Google breakdown producers from
  the plural `"breakdowns"` to `"breakdown"` to match the `/sync/status` envelope —
  `backend/workers/tasks/tiktok_breakdowns.py`, `backend/workers/tasks/google_breakdowns.py`.
  Test: `backend/tests/test_sync_jobs_completeness.py` (§11 sync_jobs completeness).
