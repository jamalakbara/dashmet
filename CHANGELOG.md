# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project aims to.

## [Unreleased]

### Changed
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
- Sync-aware empty states — breakdown and ads sections read their own `jobs_status[job_type]`
  from `/sync/status` and show "Syncing…" instead of "No data"/"No ads found" when the relevant
  job hasn't completed yet (P-1). New `frontend/src/hooks/use-sync-jobs.ts` +
  `frontend/src/components/shared/sync-aware-empty.tsx`; wired into `breakdown-section.tsx`
  (keys on `breakdown`) and `ads-view.tsx` (keys on `insights_daily`, i.e. ad rows).
- Read-vs-write date-range parity test — `backend/tests/test_date_range_parity.py`
  (presets × timezones; asserts worker `time_range` == read resolver; rejects unknown presets). PRD §11.
