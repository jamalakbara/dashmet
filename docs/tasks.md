# dashmet — Task Board

> Whole-product backlog, organized against `docs/prd.md`. Three columns: `Todo`, `In Progress`, `Done`.
>
> This repo also has `BOARD.md` at the root, which tracks a narrower, ongoing reliability/trust-focused workstream (branch `feat/parity`) in more technical detail. The two will overlap on some items — that's expected, they're different-grained views of the same codebase, not two competing sources of truth. This file is the product-wide one.

---

## Todo

- **Attribution-window upsert gap** — `metrics_daily`'s unique constraint doesn't include `attribution_window`, so a re-sync under a different window could silently overwrite the prior window's numbers. Needs a migration plus a backfill plan for existing rows.
- **Auth endpoint layering fix** — the login endpoint queries the database directly instead of going through the existing auth service. Route it through the service layer.
- **Auth flow test coverage** — signup, login, email verification, and password reset currently have no dedicated tests.
- **Reconciliation feature** — periodically check dashmet's stored numbers against what a platform itself reports, and surface unexplained drift. Not started; see `docs/prd.md` §6/§9.
- **Date-range-preset off-by-one** — `last_Nd` currently spans N+1 days (`today-N..today`) instead of exactly N (`today-(N-1)..today`). Fix in the shared resolver so read and write shift together.
- **`creatives` sync status tracking** — every other sync type records a run (pending/running/completed/failed); `creatives` doesn't yet, so it always reads "never synced" even after running.
- **Ads image row-level UX** — render an ad's row immediately with a placeholder/shimmer thumbnail and auto-refetch once its creative sync completes, instead of hiding the row until the image is ready.
- **TikTok Shop / GMV Max — ship or drop decision** — the view and route are built but intentionally hidden; blocked on real shop-conversion data (and likely a TikTok Shop API integration) rather than on UI work.

## In Progress

- **Global sync-status badge** — reflects the worst of primary/secondary sync status (e.g. "Partially synced — breakdowns pending"). Code complete; needs browser verification.
- **Per-section empty states** — each dashboard section reads its own sync status instead of a blanket "No data" message. Code complete; needs browser or automated frontend tests.
- **Eager first sync on connect** — a newly connected account's first sync is dispatched immediately rather than waiting for the next scheduled run. The dispatch mechanism itself is tested; the connect-time integration still needs a DB/worker test harness before this is fully verified end to end.

## Done (recent highlights)

- Per-member account access control — owners unrestricted, members scoped to explicitly granted accounts.
- TikTok onsite/shop, engagement, and LIVE metrics synced and surfaced.
- Meta CPAS shared-item metrics synced and surfaced.
- AI-generated narrative diagnosis of account performance — on-demand, freshness-cached, optionally embedded in PPTX export.
- PPTX export of a single account's overview, built from the same functions as the live API.
- Dashboard sections auto-refresh while a sync is active, instead of only the Overview KPIs.
- Breakdown sync now records its own status, fixing a badge that used to get stuck on "partially synced."
- Meta workers resolve relative date presets to explicit date ranges in the account's timezone, matching what the read side queries.

---

For the detailed, line-by-line history behind each of these, see `CHANGELOG.md`.
