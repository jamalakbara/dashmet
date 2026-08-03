# BOARD

Kanban for PARITY work. One line per item, referencing its PRD identifier
(§/P-/F-). See `.claude/rules/task-tracker.md`.

> Note: `docs/prd-parity.md` referenced by the rules does not exist yet — identifiers
> below point at `.claude/rules/product-principles.md` (§2.3 anti-reqs, P-1…P-9) until it lands.

## Todo

Sync-freshness UX (fresh-connect "data gone?" confusion) — ordered:
1. [A] P-1/P-2 — section empty states read own `jobs_status[jt]`: no completed job → "Syncing…"; completed+0 rows → "No data". Ads-empty keys on `insights_daily` (ad rows), not creatives.
2. [C] P-2 — global freshness badge = worst/oldest of relevant job_types, not just `insights_daily` (e.g. "Partially synced — breakdowns pending").
3. [D-lite] P-5 — on connect, eager-enqueue `insights_daily` + `breakdown` via `stagger_dispatch` (not raw `.delay`); mirror existing structure dispatch. No banner, creatives stay lazy.
4. §9.2/§11 — `creatives` job_type has no producer → `jobs_status["creatives"]` permanently "never synced" (P-2 lit-warning). Make `sync_creatives_for_account` write a sync_job, or drop `creatives` from `sync.py:48` list.
5. Ads image row-level UX — render ad row immediately + placeholder/shimmer thumbnail + auto-refetch after lazy `sync_creative`; never hide a row for a missing `creative_preview`.

- §2.3 date resolver off-by-one — `last_Nd` spans N+1 days (`today-N..today`); make it exactly N (`today-(N-1)..today`). Shared resolver → shifts read + write together.

## In Progress

## Done

- 2026-08-03 §2.3 / P-7 — Meta workers resolve `date_preset`→`time_range` in account tz (one resolver, read==write). Test: `backend/tests/test_date_range_parity.py`.
