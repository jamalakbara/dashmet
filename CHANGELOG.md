# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project aims to.

## [Unreleased]

### Added
- **PPTX export of a single-account overview** — new `GET /insights/overview/export.pptx`
  (`backend/app/api/v1/endpoints/insights.py`) returns a 5-slide PowerPoint deck (title+meta,
  KPI summary, native spend-trend chart, top-campaigns table, top-6 ads with 4:5 creative
  thumbnails) as a binary `StreamingResponse`. Deck built by the new
  `backend/app/services/export.py` (`generate_overview_pptx`), which reuses the shared
  `get_overview`/`get_timeseries`/`get_table` read functions — identical numbers by
  construction, no second query path (P-6/P-7). Frontend: `insightsApi.exportOverviewPptx`
  (`frontend/src/lib/api/insights.ts`) plus an **Export PPTX** button shown on single-account
  views (`frontend/src/components/layout/control-strip.tsx`). New backend deps
  `python-pptx==1.0.2` + `Pillow==11.3.0` (`backend/requirements.txt`). Known gap: the
  single-account `get_overview()` read path lacks a freshness/coverage envelope, so the title
  slide stamps only "Data as of <date_stop>" (P-1 follow-up, tracked in `BOARD.md`).
- **Animated lucide icons** across the dashboard via a new reusable `AnimatedIcon` primitive
  (`frontend/src/components/shared/animated-icon.tsx`) that wraps any `lucide-react` glyph in a
  framer-motion `motion.span` — so every animation honors OS reduce-motion through the global
  `<MotionConfig reducedMotion="user">`. Motion presets are centralized in
  `frontend/src/lib/motion.ts` (`ICON_MOTION`: `spin`, `wiggle`, `bounce`, `pop`, `draw`,
  `nudge`, `nudgeRight`, `flip`). Applied to nav/menu/action icons (hover), expand/collapse
  chevrons (rotate on state), and appearing state icons (delta trend arrows, active sort arrow,
  sync/connection status checks + warnings). Touches
  `frontend/src/components/{metrics/delta-pill,metrics/metric-card,metrics/metric-group-card,layout/sidebar,layout/top-bar,layout/filter-popover,shared/date-range-picker,shared/sync-status-badge,shared/sync-aware-empty,shared/user-menu,shared/account-command-list,shared/account-switcher,views/table-view,views/ads-view}.tsx`
  and `frontend/src/app/{(dashboard)/dashboard/page,settings/members/page,settings/connections/page}.tsx`.
  Active-op CSS spinners (`Loader2`/`RefreshCw` `animate-spin`), platform-badge letter marks, and
  chart/data-viz SVGs (`bento/geo-tile.tsx`, `bento/gauge-tile.tsx`) are intentionally left as-is.
- Left nav sidebar can now **collapse to an icon-only rail** (`w-[68px]`) and expand back to
  full width (`w-60`) via a round chevron handle on the rail's right edge (vertically centered,
  same spot in both states). Collapsed, labels/section headers hide, rows center their icon with
  a native `title` tooltip, and the `Platform Data` group flattens to its three platform icons.
  State persists via the existing UI store (`sidebarCollapsed`).
  `frontend/src/components/layout/sidebar.tsx`.
- Shell is now **two inset floating panels** — the indigo sidebar rail and the right content
  panel each render as a `rounded-2xl shadow-xl ring-1` card with a gap between them, replacing
  the flush edge-to-edge layout. `frontend/src/app/(dashboard)/layout.tsx`,
  `frontend/src/app/settings/layout.tsx`.
- Compare-previous delta pills now surface the **previous absolute value** (formatted per metric
  type via `formatMetric`), not just the `%` delta: KPI cards and funnel stages show it inline as
  `vs <prev>`; table cells and ad cards/rows reveal `prev <prev>` on hover. Added `variant`,
  `currency`, and `valueType` props to `DeltaPill` and a new shadcn `Tooltip` primitive.
  `frontend/src/components/metrics/delta-pill.tsx`, `frontend/src/components/ui/tooltip.tsx`,
  `frontend/src/components/metrics/metric-group-card.tsx`,
  `frontend/src/components/views/{overview-view,funnel-view,table-view,ads-view}.tsx`.

### Changed
- **Sidebar nav slimmed: Account Binding removed, Settings pinned to bottom.** Dropped the
  standalone "Account Binding" rail link (and the now-empty USER section label); account
  connection is reached via **Settings → Connections** tab (`settings-nav.tsx` unchanged, route
  `/settings/connections` kept). Settings moved out of the scrollable nav into a bottom-pinned
  footer with a top divider, in both expanded and collapsed states. Touches
  `frontend/src/components/layout/sidebar.tsx`.
- **Brand + platform logos now use real SVG assets.** Sidebar brand swapped from the `Sparkles`
  lucide glyph to `/logo.svg`; `PlatformBadge` renders `/meta-logo.svg`, `/tiktok-logo.svg`, and
  `/gads-logo.svg` for meta/tiktok/google_ads (colored letter tile kept as fallback for any other
  platform). Assets added under `frontend/public/`. Touches
  `frontend/src/components/layout/sidebar.tsx`,
  `frontend/src/components/shared/platform-badge.tsx`.
- **Icon hover animations now trigger on the whole container, not the icon itself.** `AnimatedIcon`
  with `trigger="hover"` switched from framer-motion `whileHover` (icon-only) to CSS `group-hover:`,
  so hovering the enclosing `<Link>`/`<button>`/row/card animates the icon. Added
  `ICON_HOVER_CLASS` (Tailwind `group-hover:` + `motion-reduce:` guards) to
  `frontend/src/lib/motion.ts` and an `@keyframes icon-wiggle` to `frontend/src/app/globals.css`;
  `frontend/src/components/shared/animated-icon.tsx` now renders hover icons as a plain `<span>`.
  Every hover call site's nearest interactive container gained the `group` class
  (`layout/sidebar` [shared `ITEM`], `layout/top-bar`, `layout/filter-popover`,
  `shared/date-range-picker`, `shared/user-menu`, `shared/account-command-list`,
  `shared/account-switcher` [shared `TRIGGER_CLASS`], `metrics/metric-group-card`, `views/table-view`,
  `views/ads-view`, `settings/members/page`, `settings/connections/page`). `trigger="state"`/`appear`
  paths (framer-motion) are unchanged.
- Compare-previous is now a **global** toggle in the top bar (URL `?compare=true`) instead of a
  Trends-local switch. It drives the Trends prior-period overlay plus period-over-period delta pills
  across every Overview section. `frontend/src/components/layout/top-bar.tsx`,
  `frontend/src/components/views/periodic-view.tsx` (Trends switch removed, now reads `?compare` read-only).
- `GET /insights/overview` response `data` gained a `previous` object (full prior-period summary,
  same keys as `summary`; always present). `GET /insights/table` gained a `compare_previous` query
  param; when true each row also carries `metrics_previous`. `backend/app/schemas/insights.py`,
  `backend/app/services/insights.py`, `backend/app/api/v1/endpoints/insights.py`.
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
- Period-over-period delta pills across the Overview — KPI cards (headline + sub-metrics), funnel
  stages, table cells, and ad cards/rows. New shared `frontend/src/components/metrics/delta-pill.tsx`
  (`DeltaPill` + `DeltaBadge`) + `metricDelta`/`COST_METRICS` helper in `frontend/src/lib/formatters.ts`;
  cost metrics (`cpa`/`cpc`/`cpm`/`cpp`/`frequency`, `cost_per_*`) are color-inverted so a drop reads
  green. Pills stay silent when no usable comparison exists (P-2). Wired into `metric-group-card.tsx`,
  `overview-view.tsx`, `funnel-view.tsx`, `table-view.tsx`, `ads-view.tsx`.
- Prior-period metrics on read endpoints backing the delta pills — `previous` on the overview response
  and `metrics_previous` per table/ad row (opt-in via `compare_previous`), both reusing the same
  aggregate-then-ratio path as the current period. `frontend/src/lib/api/insights.ts` gained the
  `compare_previous` param + `MetricsPrevious` type. `backend/app/services/insights.py`.
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
