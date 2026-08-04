# BOARD

Kanban for PARITY work. One line per item, referencing its PRD identifier
(§/P-/F-). See `.claude/rules/task-tracker.md`.

> Note: `docs/prd-parity.md` referenced by the rules does not exist yet — identifiers
> below point at `.claude/rules/product-principles.md` (§2.3 anti-reqs, P-1…P-9) until it lands.

## Todo

Sync-freshness UX (fresh-connect "data gone?" confusion) — ordered:
4. §9.2/§11 — `creatives` job_type still has no producer → `jobs_status["creatives"]` permanently "never synced" (P-2 lit-warning). Make `sync_creatives_for_account` write a sync_job, or drop `creatives` from `sync.py:48` list. (Breakdown half done — see Done.)
5. Ads image row-level UX — render ad row immediately + placeholder/shimmer thumbnail + auto-refetch after lazy `sync_creative`; never hide a row for a missing `creative_preview`.

- §2.3 date resolver off-by-one — `last_Nd` spans N+1 days (`today-N..today`); make it exactly N (`today-(N-1)..today`). Shared resolver → shifts read + write together.

## In Progress

- [A] P-1/P-2 — section empty states read own `jobs_status[jt]`: no completed job → "Syncing…"; completed+0 rows → "No data". Ads-empty keys on `insights_daily` (ad rows), not creatives. Code-complete (tsc+build green); NOT Done — no frontend test harness, needs browser verify or vitest for `jobState`.
- [C] P-2 — global badge = worst of primary(`insights_daily`)+secondary(`breakdown`); primary fresh + breakdown pending → "Partially synced — breakdowns pending". Excludes creatives (item 4).
- [D-lite] P-5 — on connect, eager-enqueue `insights_daily` + `breakdown` for this connection's accounts via `stagger_dispatch` (scoped, not global — breakdown has no stale guard). No banner, creatives stay lazy. Dispatch mechanism tested (`test_stagger_dispatch.py`); connect-integration needs DB/worker harness (not built) for full Done.

## Done

- 2026-08-04 (net-new) P-6/P-1/P-4/P-7 — AI narrative summary: on-demand grounded narrative over `get_overview()` (LLM narrates, computes nothing). Landed `app/services/ai_summary.py` + `POST /insights/overview/summary` + Overview "AI Summary" card + opt-in PPTX insight-box auto-fill (`include_ai_summary`). Tests: `test_ai_summary.py`, `test_overview_summary_endpoint.py`, `test_export_overview.py` (25 passing).
  - 2026-08-04 follow-up: deepened to a structured objective-aware DIAGNOSIS — response now `{headline, driver, watch, next_step}` (was single `narrative`), fed per-campaign compare-previous rows + daily timeseries (all shared read fns, P-6/P-7); driver SELECTED not computed. Frontend 4-section card. Tests: `test_ai_summary.py`, `test_overview_summary_endpoint.py`.
  - 2026-08-04 follow-up: Redis-cached (P-1 freshness-token key `aisum:v1:…:{cached_at}`, 24h TTL) — `force` regenerates, AI failures never cached (P-4); new cache-only `GET /overview/summary/peek` (200 hit / 204 miss, never spends tokens); response gained `data_as_of`+`cached`; card peeks on mount + "Data as of …" footnote. Test: `test_overview_summary_endpoint.py`.
- 2026-08-04 P-1 (follow-up from PPTX export) — `get_overview()` now returns a `cached_at` freshness token via `MAX(fetched_at)` over the period (`app/services/insights.py`); consumed by the AI-summary Redis cache key + card "Data as of …" footnote. Test: `test_overview_summary_endpoint.py`.
- 2026-08-04 (net-new, not a PRD item) P-6 "deliverable, not just a dashboard" — PPTX export of single-account overview (`GET /insights/overview/export.pptx` + `app/services/export.py`; reuses shared read fns, one query path). Export PPTX button in control-strip. Deps python-pptx + Pillow.
- 2026-08-03 P-2 (auto-refresh) — all dashboard sections poll while sync active (`useSyncActive` from real sync_jobs state) so Trends/Breakdown/Table/Ads fill in as data lands, not just Overview KPIs. Replaces blind 5-min timer. Verified in browser (badge green + sections filled).
- 2026-08-03 §9.2/§11 (breakdown) — breakdown sync writes a `sync_jobs` row (`job_type="breakdown"`, finalized on every exit path); fixes badge stuck "partially synced" + section stuck "Syncing…". Normalized TikTok/Google `"breakdowns"`→`"breakdown"`. Test: `test_sync_jobs_completeness.py`.
- 2026-08-03 §2.3 / P-7 — Meta workers resolve `date_preset`→`time_range` in account tz (one resolver, read==write). Test: `backend/tests/test_date_range_parity.py`.
