# DashMet — Frontend Specification

> **Version:** 0.1  
> **Status:** Draft  
> **Stack:** Next.js 16 (App Router) · shadcn/ui 4 · Tailwind CSS 4 · Recharts 3 · TanStack Query 5

---

## Table of Contents

1. [Stack & Dependencies](#1-stack--dependencies)
2. [Project Structure](#2-project-structure)
3. [Routing](#3-routing)
4. [Global Layout](#4-global-layout)
5. [Auth Pages](#5-auth-pages)
6. [Dashboard Views](#6-dashboard-views)
   - [6.1 Overview](#61-overview)
   - [6.2 Periodic (Time Series)](#62-periodic-time-series)
   - [6.3 Table](#63-table)
   - [6.4 Ads Content](#64-ads-content)
7. [Settings & Org Pages](#7-settings--org-pages)
8. [Shared Components](#8-shared-components)
9. [State Management](#9-state-management)
10. [Data Fetching Patterns](#10-data-fetching-patterns)
11. [URL State Conventions](#11-url-state-conventions)

---

## 1. Stack & Dependencies

| Package | Version | Purpose |
|---|---|---|
| `next` | 16 | Framework (App Router) |
| `react` | 19 | UI library |
| `typescript` | 5 | Type safety |
| `tailwindcss` | 4 | Utility-first CSS |
| `shadcn` | 4 | Component library |
| `@tanstack/react-query` | 5 | Server state / data fetching |
| `recharts` | 3 | Charts |
| `zustand` | 5 | Lightweight client state |
| `nuqs` | 2 | URL search param state |
| `date-fns` | 4 | Date manipulation |
| `zod` | 3 | Schema validation (forms + API responses) |
| `react-hook-form` | 7 | Form management |
| `axios` | 1 | HTTP client |
| `lucide-react` | 0.468 | Icons |

---

## 2. Project Structure

```
src/
├── app/                          # Next.js App Router
│   ├── (auth)/                   # Auth route group — no sidebar
│   │   ├── login/page.tsx
│   │   ├── signup/page.tsx
│   │   ├── verify-email/page.tsx
│   │   ├── forgot-password/page.tsx
│   │   └── reset-password/page.tsx
│   │
│   ├── (dashboard)/              # Dashboard route group — with sidebar
│   │   ├── layout.tsx            # Sidebar + header + PlatformTabs shell
│   │   ├── dashboard/page.tsx    # Combined cross-platform summary
│   │   ├── meta/                 # Meta section — views render as tabs
│   │   │   ├── page.tsx          #   bare /meta → redirect to overview
│   │   │   ├── overview/page.tsx
│   │   │   ├── periodic/page.tsx #   includes breakdowns (no separate route)
│   │   │   ├── table/page.tsx
│   │   │   └── ads/page.tsx
│   │   └── tiktok/               # TikTok section — views render as tabs
│   │       ├── page.tsx          #   bare /tiktok → redirect to overview
│   │       ├── overview/page.tsx
│   │       ├── periodic/page.tsx
│   │       ├── table/page.tsx
│   │       ├── ads/page.tsx
│   │       └── engagement/page.tsx
│   │
│   ├── settings/
│   │   ├── org/page.tsx          # Org name, general settings
│   │   ├── members/page.tsx      # Member list + invite
│   │   └── connections/page.tsx  # Platform connections (Meta, etc.)
│   │
│   └── layout.tsx                # Root layout — providers
│
├── components/
│   ├── ui/                       # shadcn/ui primitives (auto-generated)
│   ├── layout/                   # Sidebar, Header, PlatformTabs
│   ├── views/                    # Per-platform view bodies (Overview/Periodic/Table/Ads)
│   ├── charts/                   # Recharts wrappers
│   ├── metrics/                  # MetricCard, MetricTable, BreakdownSection, etc.
│   ├── ads/                      # AdCard, CreativePreview, etc.
│   └── shared/                   # AccountSwitcher, AccountCommandList, DateRangePicker, StatusBadge, etc.
│
├── hooks/
│   ├── use-account.ts            # Selected account + server-side account search (useAccountSearch / useAccountsCount / useSelectedAccount)
│   ├── use-platform.ts           # Active platform from route (/meta → "meta", etc.)
│   ├── use-platform-metrics.ts   # Platform/account-type-aware metric sets
│   ├── use-shared-query.ts       # Carry account_id + date params across nav
│   ├── use-date-range.ts         # Date range from URL state
│   ├── use-insights-*.ts         # Per-view data fetching hooks
│   └── use-sync-status.ts        # Sync status polling
│
├── lib/
│   ├── api/                      # API client functions (axios)
│   │   ├── client.ts             # Axios instance + interceptors
│   │   ├── auth.ts
│   │   ├── accounts.ts
│   │   ├── insights.ts
│   │   ├── campaigns.ts
│   │   └── sync.ts
│   ├── query-keys.ts             # TanStack Query key factory
│   ├── formatters.ts             # Currency, %, number formatters
│   ├── metrics.ts                # Platform/account-type metric registry
│   └── constants.ts              # Date presets, metric labels, colors, PLATFORM_TABS
│
├── stores/
│   └── ui-store.ts               # Zustand — sidebar state, active account
│
└── types/
    ├── api.ts                    # API response types (from backend spec)
    ├── metrics.ts                # Metric field types
    └── enums.ts                  # Status, level, breakdown, platform enums
```

---

## 3. Routing

`{platform}` ∈ `{meta, tiktok}`.

| Route | Page | Auth required | Role |
|---|---|---|---|
| `/` | Redirect → `/dashboard` | ✅ | any |
| `/login` | Login | ❌ | — |
| `/signup` | Signup | ❌ | — |
| `/verify-email` | Email verification | ❌ | — |
| `/forgot-password` | Request reset | ❌ | — |
| `/reset-password` | Set new password | ❌ | — |
| `/dashboard` | Combined cross-platform summary | ✅ | any |
| `/meta`, `/tiktok` | Redirect → `…/overview` | ✅ | any |
| `/{platform}/overview` | Platform overview (summary) | ✅ | any |
| `/{platform}/periodic` | Time series **+ breakdowns** | ✅ | any |
| `/{platform}/table` | Metrics table | ✅ | any |
| `/{platform}/ads` | Ads content | ✅ | any |
| `/tiktok/engagement` | TikTok engagement metrics | ✅ | any |
| `/settings/org` | Org settings | ✅ | owner |
| `/settings/members` | Member management | ✅ | owner |
| `/settings/connections` | Platform connections | ✅ | owner |

The per-platform tab bar is **Overview · Table · Ads** (plus TikTok's Engagement) — `PLATFORM_TABS` in `lib/constants.ts`. Each tab is its own route so deep links stay shareable. **Overview is a composed scroll** (Base Data reference style): grouped metric cards → `PeriodicView` (trends) → `FunnelView` → a **Table preview** (`<TableView preview />`) → an **Ads preview** (`<AdsView preview />`). Periodic and Funnel therefore no longer have their own tabs; their routes (`/periodic`, `/funnel`) still exist for deep-links but aren't surfaced in the bar. Table and Ads keep full tabs — their previews on Overview show the top rows/creatives with a **See All →** link to the full view. **Breakdowns are part of the Periodic view** (`BreakdownSection` at the bottom of `periodic-view.tsx`).

Auth guard is a middleware (`middleware.ts`) that checks for a valid JWT cookie. Unauthenticated users are redirected to `/login`. Members trying to access owner-only settings pages see a `403` page.

---

## 4. Global Layout

The dashboard layout (`(dashboard)/layout.tsx`) renders two inset floating panels (both `m-3 rounded-2xl shadow-xl ring-1 ring-black/5`): the indigo **sidebar rail** on the left, and a right **content panel** holding a light **top bar** (`TopBar`) that carries the platform identity + freshness chip + account picker (left) and DateRange / notifications / user (right), a **control strip** (`ControlStrip`) that carries `PlatformTabs` + Compare toggle + Filter + Export, and the scrollable content canvas. There is **no permanent "Sync Data" button** — manual sync is a recovery path surfaced contextually inside the freshness chip (P-5). Base Data light-SaaS theme (white cards floating on a light-gray canvas); the near-black bento "OS-window" chrome was retired.

```
┌───────────┬──────────────────────────────────────────────────┐
│  DASH·MET │  TOP BAR                                          │
│ (indigo)  │ [MetaAds·fresh·Account▾]   [DateRange][🔔][👤]    │
│           ├──────────────────────────────────────────────────┤
│ DATA      │  CONTROL STRIP                                    │
│  Summary  │  [Overview…Ads] [Compare◑]      [Filter][Export] │
│  Platform ├──────────────────────────────────────────────────┤
│   Meta    │                                                   │
│   TikTok  │   PAGE CONTENT (active tab)                       │
│   Google  │                                                   │
│ USER      │                                                   │
│  Binding  │                                                   │
│  Settings │                                                   │
└───────────┴──────────────────────────────────────────────────┘
  (PlatformTabs self-hides on the combined /dashboard)
```

### Top bar — components

**`AccountSwitcher`**
- shadcn `Popover` + `Command` (cmdk combobox), **server-side searched** — never loads the whole org (200–1000+ accounts). Search hits `GET /accounts?search=&platform=`; the picker sets `shouldFilter={false}` (the server is the filter).
- Two modes via a shared `AccountCommandList` (`components/shared/`):
  - **Platform route** (`/meta`, `/tiktok`) → single-select, scoped to that platform. Updates `account_id`.
  - **Combined dashboard** (`/dashboard`) → multi-select, results grouped by platform. Updates `accounts` (comma-separated). `null` param = **All accounts**, `""` = none.
- **Pinned + Recent** groups at the top, persisted in `ui-store` (localStorage) as denormalized `accountSnapshots` so they render without re-fetching. Star icon toggles pin. Stale snapshots (accounts the API no longer returns after a disconnect/reconnect, e.g. `account_status="disabled"`) are pruned against the live list — but only when absence is conclusive (idle, non-truncated page); a capped or still-loading page never drops an account that merely sits beyond the first page.
- Rows: platform badge, **account name (primary)**, business name / external id (secondary muted line), currency, star. Name always takes priority width (`flex-1` + truncate) so long ids never squeeze it out.
- "No accounts connected" empty state (via `useAccountsCount`); brief on-connect polling.

**`DateRangePicker`**
- shadcn `Popover` + `Calendar` (`react-day-picker`). **Single popover, two views** — not split panels.
  - **Presets view**: preset buttons + a `Custom range…` item.
  - **Custom view**: clicking `Custom range…` swaps in a range `Calendar` (future dates disabled) with a `‹ Presets` back link and a footer showing the selected range + `Cancel`/`Apply`.
- Mutually exclusive: choosing a preset clears `date_start`/`date_end`; `Apply` sets `date_start`/`date_end` and clears `date_preset` (backend rejects both).
- A 30-day note appears in the custom view **only when** the chosen range reaches back past 30 days (breakdowns cover ~30d; see breakdown sync).
- Selection stored in URL: `?date_preset=last_30d` or `?date_start=2026-05-01&date_end=2026-05-30`. Default: `last_30d`. Survives nav via `useSharedFilterQuery`.

**Compare-previous toggle** — shadcn `Switch` labeled "Compare prev.", lives in the **control strip** next to `PlatformTabs` (it's a view control, so it sits with the tabs rather than in the top bar).
- **Global** period-over-period switch driven by URL state `?compare=true` (via `useQueryState("compare")`); absence = off (no `compare=false` in the URL).
- Drives every Overview section at once: the Trends prior-period overlay plus the period-over-period **delta pills** on KPI cards, funnel stages, table cells, and ad cards/rows. Trends no longer owns its own compare switch — it reads the same URL param read-only (see §6.2).
- Delta pills stay **silent** when a comparison can't be made (missing current/previous or a zero baseline) per P-2 — no permanently-lit neutral badge.
- Delta pills also surface the **previous absolute value** (formatted per metric type via `formatMetric`): KPI cards and funnel stages show it inline as `vs <prev>` next to the `%` pill (`variant="inline"`); table cells and ad cards/rows keep the compact pill and reveal `prev <prev>` on hover (`variant="tooltip"`).

**`SyncStatusBadge`**
- The **single** sync indicator, rendered as a labeled pill in the `TopBar` (the old full-width `SyncStatusBar` freshness banner was removed to avoid a redundant second indicator; its per-preset job-resolution logic was folded into this badge).
- Resolves the jobs relevant to the active `date_preset` + platform (`RANGE_JOBS` / `insights_historical_or_async` → `insights_historical` for TikTok else `insights_async`) and reports inline, color-coded:
  - **fresh** (neutral grey — same treatment as idle): `Updated Xm ago` — stays visible so the navbar always reports freshness, but reads as calm rather than lit-green (P-2)
  - **syncing** (amber, spinner): `Syncing last 30d — ready in ~2–8 min` (or account/structure ETA)
  - **stale** (amber): `last 30d may be outdated · synced Xh ago`
  - **failed** (red): `Sync failed · last 30d`
  - **idle** (gray): `Last updated —` / `No account`
- **Contextual manual sync (P-5):** on the **stale** and **failed** variants only — where there's a real reason — the pill renders an inline `Sync now` action (`RefreshCw` icon, spinner while pending) that fires `POST /sync/trigger` for the resolved account, toasts on success/error, and invalidates `queryKeys.syncStatus`. Fresh / syncing / idle show no sync action. This replaces the old permanent "Sync Data" button.
- Polls `GET /sync/status` every 30 seconds.

**User menu** — shadcn `DropdownMenu`
- Shows user name + email
- Links: Profile, Settings, Sign out

### Sidebar — items

```
[✦ Base Data Dashboard]

DATA
  ▦  Summary              → /dashboard (combined cross-platform)
  ▦  Platform Data ▾      (expandable group)
       Meta Ads           → /meta/overview
       TikTok Ads         → /tiktok/overview
       Google Ads         → /google_ads/overview

  ⚙️  Settings            → /settings/org   (pinned to rail bottom)
```

Sidebar (`components/layout/sidebar.tsx`) is an **indigo rail** with a single `DATA` section. `Platform Data` is a collapsible group (open by default); each platform lands on its first tab (`PLATFORM_TABS[platform][0]`, i.e. Overview) and is highlighted whenever any of its tabs is active (`pathname.startsWith('/{platform}')`). **Settings** sits in a bottom-pinned footer (top divider), below the scrollable nav, in both expanded and collapsed states. There is no standalone `Account Binding` rail link — account connection is reached via **Settings → Connections** tab (route `/settings/connections` still exists). Filter params (account_id, date range) are carried across sidebar + tab navigation by `useSharedFilterQuery()`. The rail renders as a **detached floating card** (`m-3 rounded-2xl shadow-xl`), sitting inset from the viewport edges rather than flush. It is an **absolute overlay** (`absolute inset-y-0 left-0`) paired with an in-flow **spacer** (`w-[264px]` expanded / `w-[92px]` collapsed, no transition) that reserves its column: the content panel sizes off the spacer, so it reflows **once** per toggle instead of every frame, while only the rail's own (`[contain:layout_paint]`) subtree reflows during the 200ms width animation. The rail's inner content is **keyed on `collapsed`** so it remounts and replays a `sidebar-swap-in` opacity fade (`globals.css`, `motion-safe:` only) on every toggle: the collapsed/expanded layout is discrete but the width is animated, so the new layout fades in from 0 while the width settles — masking the frames where content geometry doesn't yet match the animating width (otherwise labels clip in the narrow rail / icons float in the wide one). It collapses to an icon-only strip (`w-[68px]`) and expands back to full width (`w-60`) via a chevron toggle in the brand block next to the logo (ChatGPT-style): expanded, it's a ghost button right-aligned in the brand row; collapsed, the logo alone shows and hovering it swaps the logo for the expand button. The choice lives in the persisted UI store (`ui-store.ts` → `sidebarCollapsed`, key `dashmet-ui`). Collapsed, labels/section headers/chevrons hide, each row centers its icon with a native `title` tooltip, and the `Platform Data` group flattens to its three platform icons (no toggle). Desktop-first — no hamburger.

### Control strip — `ControlStrip`

`components/layout/control-strip.tsx` — sits directly under the top bar. Holds the view controls left→right: the `PlatformTabs`, the **Compare prev.** toggle, then a right-aligned group with the **Filter** popover (`FilterPopover`) and — on single-account views only — the **Export PPTX** button. It carries **no Sync Data button** (removed): manual sync is a recovery path surfaced contextually in the freshness chip (`SyncStatusBadge`) per P-5, not a permanent strip fixture. The `AccountSwitcher` moved up to the `TopBar`.

**Export PPTX** — an outline button (`FileDown` icon) shown only on **single-account** (platform-scoped) views, hidden on the combined `/dashboard` where `usePlatform()` is `null` (there's no single-account overview to render). Calls `insightsApi.exportOverviewPptx({ account_id, ...dateRange, ...filter, include_ai_summary })` — same params as the overview read plus the toggle below — then downloads the returned `Blob` client-side (creates an object URL + a temporary `<a download="overview.pptx">`). Pending state pulses the icon; a failure toasts and downloads nothing. Backend endpoint: `GET /insights/overview/export.pptx` (see `docs/backend-api-spec.md`).

**Include AI summary** — a `Switch` (default **off**, local `useState`) shown next to Export PPTX on single-account views. When on, sets `include_ai_summary: true` on the export call so the deck's insight boxes are auto-filled with AI narrative; default-off keeps the standard export token-free (P-5: gated, not automatic).

**Filter popover** — `components/layout/filter-popover.tsx`. A campaign filter (status dropdown + campaign-name search, debounced 300ms) that writes the shared `status` + `search` URL params. Read back by `useOverviewFilter()` (status `"all"` → omitted) and threaded into the Overview cards, funnel (`insightsApi.overview`), trends (`insightsApi.timeseries`), and the Table/Ads tabs — one filter scopes every view. Trigger shows an active-count badge; a Clear action resets both params. Backend enforces it via `status`/`search` on `GET /insights/overview` + `/insights/timeseries`.

### Platform tab bar — `PlatformTabs`

`components/layout/platform-tabs.tsx` — a route-driven (not shadcn `Tabs`) tab bar mounted in the control strip, rendered via the shared `SegmentControl` in route-based mode (each item carries an `href`, so tabs are real `<Link>`s). Reads the active platform via `usePlatform()`, looks up `PLATFORM_TABS[platform]`, and renders one filled-pill segment per view. Returns `null` on `/dashboard` (no platform). Active tab = exact `pathname` match.

---

## 5. Auth Pages

All auth pages share a centered card layout — no sidebar, no header. Logo centered above the card.

### Login (`/login`)

**Fields:** Email, Password  
**Actions:** Submit → `POST /auth/login`, "Forgot password?" link → `/forgot-password`  
**On success:** Store JWT in httpOnly cookie, redirect to `/overview`  
**Errors:** Show inline under the field (invalid credentials as a form-level error)

### Signup (`/signup`)

**Fields:** Name, Email, Password, Organization name  
**Actions:** Submit → `POST /auth/signup`  
**On success:** Show "Check your email to verify your account" message — do not auto-login yet  
**Validation (client-side via Zod):** Email format, password min 8 chars, org name required

### Verify Email (`/verify-email?token=...`)

On page load, auto-calls `POST /auth/verify-email` with the token from the URL.  
- Loading state while verifying  
- Success: "Email verified! Logging you in…" → redirect to `/overview`  
- Error: "This link has expired or is invalid" with a "Resend verification email" button

### Forgot Password (`/forgot-password`)

**Fields:** Email  
**On submit:** `POST /auth/forgot-password`  
**Always shows:** "If that email exists, a reset link has been sent." (no email enumeration)

### Reset Password (`/reset-password?token=...`)

**Fields:** New password, Confirm password  
**On submit:** `POST /auth/reset-password`  
**On success:** "Password updated. Redirecting to login…" → redirect to `/login`

---

## 6. Dashboard Views

All four dashboard views share the global layout. They all react to changes in `AccountSwitcher` and `DateRangePicker` — no "Apply" button, changes trigger immediate refetch via TanStack Query.

---

### 6.1 Overview

**Purpose:** At-a-glance account health for the selected period. The "homepage" of the dashboard.

**Composed scroll** — Overview stacks the platform's whole story on one page (Base Data reference), rather than splitting it across tabs:

```
┌──────────────────────────────────────────────────────────────┐
│  GROUPED METRIC CARDS (Base Data style)                      │
│  ┌ 🟠 Spend  IDR 6.0M ── See Detail ┐ ┌ 🟢 ROAS 23.08 ─────┐ │
│  │ Reach     Impressions            │ │ Purchase  Purch.Val │ │
│  │        [ See More ▾ ]            │ │    [ See More ▾ ]   │ │
│  └──────────────────────────────────┘ └─────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  TRENDS   → <PeriodicView />  (metric-tab charts + breakdowns)│
├──────────────────────────────────────────────────────────────┤
│  FUNNEL   → <FunnelView />    (bar chart + step table)        │
├──────────────────────────────────────────────────────────────┤
│  DATA BASED ON  → <TableView preview />   [ See All → /table ]│
├──────────────────────────────────────────────────────────────┤
│  ADS      → <AdsView preview />           [ See All → /ads ]  │
└──────────────────────────────────────────────────────────────┘
```

The embedded sub-views are self-contained (own data hooks off the shared URL params). The Table/Ads **previews** are read-only (no toolbar, pagination, or param writes) — they show the top rows/creatives with a **See All →** link into the full tab.

#### `MetricGroupCard` component

`components/metrics/metric-group-card.tsx` — one card per metric family. A colored icon chip + title + big headline number, an optional **See Detail** link, then a two-column grid of sub-metrics with a **See More/See Less** expander for the overflow (default `previewCount = 4`).

```
┌──────────────────────────────────────┐
│ 🟠 Spend            [↗ See Detail]   │
│ IDR 6.026.558,00                     │
│ ───────────────────────────────────  │
│ Reach       Impressions              │
│ 191.534     872.666                  │
│ Frequency   CTR                      │
│ 4,56        2,03%                     │
│            [ See More ▾ ]            │
└──────────────────────────────────────┘
```

Props: `title`, `headline` (formatted), `icon` (Lucide), `accent` (chip bg class), `subMetrics` (`{key,label,value,raw?}[]`), `previewCount?`, `detailHref?`, `loading?`, plus period-over-period props `compare?`, `previous?` (raw prior values keyed by metric), `headlineKey?`, `headlineValue?`, `currency?`. When `compare` is on and `previous` is present, an inline `DeltaPill` renders next to the headline and each sub-metric (using each `SubMetric.raw` vs `previous[key]`), including a muted `vs <prev>` absolute value; `currency` is threaded through so currency metrics format correctly.

`overview-view.tsx` builds two cards: **Spend** (delivery family — Reach, Impressions, Frequency, CTR, CPM, CPC, Clicks, Link Clicks…) headlined by spend, and a **Results** card headlined by the first present of `roas → conversions → web_purchases → result → engagement_rate → outbound_clicks` (title = that metric's label). Sub-metrics are filtered to keys present in the overview `summary`; labels/format come from `METRIC_REGISTRY` (`metricLabel`/`metricType`), so the grid adapts per platform and account type. `See Detail` links to the platform's Table view. Both cards receive the global `compare` flag (from `?compare`) plus the overview response's `previous` summary, so the headline and sub-metric delta pills light up when compare is on.

**AI Summary card** — `AiSummaryCard` (in `overview-view.tsx`), rendered between the metric-group cards and Trends. An on-demand grounded diagnosis of the overview, generation is **opt-in** so token spend is always intentional (P-5). On mount the card **peeks** the cache — a token-free `GET /insights/overview/summary/peek` (`insightsApi.peekSummary`, `useQuery`) — so an already-generated diagnosis renders instantly; it only falls to Idle when there's no cached summary. Display precedence is freshest-first: a just-generated mutation result wins over the peeked cache, both fall back to Idle. States:

- **Idle** — a "Generate AI summary" button (`Sparkles`) with a "Uses AI · counts toward token usage" hint. Shown only when the peek returned no cached summary.
- **Loading** — animated skeleton lines (mutation pending, or the peek still loading with no mutation result yet).
- **Success** — the structured diagnosis rendered as four labeled sections: the **headline** as a bold lead paragraph, then **Likely driver** (`driver`), **Watch** (`watch`), and **Next** (`next_step`) each under a small uppercase label — plus a footnote showing `period.date_start – date_stop · model` and, when present, `· Data as of <relative time>` derived from `data_as_of` (`formatDistanceToNow`) as a freshness marker (P-1) — and a **Regenerate** action.
- **Error** — a destructive `Alert` showing the backend's `detail` verbatim (falling back to a generic message) plus a **Retry** button — never a silent/empty card or fabricated text (P-4).

Generate/Regenerate/Retry call `insightsApi.generateSummary({ account_id, ...dateRange, ...filter, force })` → `POST /insights/overview/summary` (top-level response, not `{ data }`-wrapped; typed `OverviewSummary` with the four `headline`/`driver`/`watch`/`next_step` fields plus `data_as_of` and `cached`). Idle **Generate** sends the default (no `force`) so a cached result is replayed token-free; **Regenerate** sends `force=true` to bypass the cache and spend tokens for a fresh diagnosis, then writes the result back into the peek query cache (`queryClient.setQueryData`) so a remount stays consistent. A failure surfaces as a `502` whose `detail` is shown to the user.

The card is **keyed on account + period + filter**, so changing any of them remounts it back to the Idle state rather than leaving a previous period's diagnosis displayed against the new numbers (P-1: a summary is only ever shown against the numbers it was generated for). Regeneration stays an explicit click — the reset never auto-spends tokens.

#### Embedded sub-views

- **Trends** — `<PeriodicView />` (see §6.2): metric-tab time-series charts + `BreakdownSection`.
- **Funnel** — `<FunnelView />`: step bar chart + conversion-rate table. When the global `?compare` toggle is on, each step shows an inline `DeltaPill` (step value vs the overview response's `previous[step.key]`) with a muted `vs <prev>` absolute value.
- **Table preview** — `<TableView preview />`: a "Data Based On" card with the top campaigns by spend (visible columns only, no expand/pagination) + **See All →** `/table`.
- **Ads preview** — `<AdsView preview />`: top 3 creatives as `AdCard`s (click opens the shared `AdDetailSheet`) + **See All →** `/ads`.

#### Data fetching

```ts
// hooks/use-insights-overview.ts
const { data, isLoading } = useQuery({
  queryKey: queryKeys.overview(accountId, dateRange),
  queryFn:  () => api.insights.getOverview({ account_id: accountId, ...dateRange }),
  staleTime: 15 * 60 * 1000,  // 15 min — matches backend cache TTL
})
```

---

### 6.2 Periodic (Time Series)

**Purpose:** Trend analysis over time with metric and dimension controls.

```
┌──────────────────────────────────────────────────────────────┐
│  CONTROLS BAR                                                 │
│  [Level ▾] [Metrics ▾] [Time ▾ Day/Week/Month]              │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  MAIN CHART (line or bar, switchable)                         │
│  Height: 360px                                                │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│  BREAKDOWN SECTION                                            │
│  [Age & Gender] [Country] [Platform] [Device]  ← tabs        │
│                                                               │
│  BREAKDOWN CHART (bar chart, horizontal)                      │
│  Height: 280px                                                │
└──────────────────────────────────────────────────────────────┘
```

#### Controls bar

**Level selector** — shadcn `Select`
- Options: Account, Campaign, Ad Group, Ad
- Default: Campaign
- Changing level updates the chart grouping

**Metrics selector** — shadcn `Popover` with checkboxes
- Up to 2 metrics can be selected simultaneously (left Y-axis and right Y-axis)
- Available: Spend, Impressions, Reach, Clicks, CTR, CPM, CPC, Conversions, ROAS, CPA
- Default selection: Spend + Clicks
- Selected metrics shown as chips next to the button

**Time increment** — filled-pill `SegmentControl` (state-based), alongside a matching Line/Bar chart-type toggle
- Options: Day · Week · Month
- Default: Day

**Compare previous period** — no longer a Trends-local control. The toggle moved to a **global** `Switch` in the `ControlStrip` (see §4), driven by `?compare=true`. Trends reads that URL param **read-only** (`useQueryState("compare")` without a setter) and still renders the prior-period dashed-line overlay when it's on:
- When on: overlays the prior period as a dashed line on the same chart (fetched via `compare_previous=true` on `timeseries`)
- Period label shown in the chart legend (e.g. "May 2026" vs "Apr 2026")

#### Main chart

- Recharts `ComposedChart` — allows mixing line + bar types
- Left Y-axis: primary metric
- Right Y-axis: secondary metric (if selected) — different scale
- X-axis: dates
- When level = Campaign/Ad Group/Ad: renders one `Line` per entity (up to 10 entities — show top 10 by spend if more)
- Legend below the chart (click to toggle individual series)
- Chart type toggle: Line / Bar (shadcn `ToggleGroup`, top-right of chart)
- Loading state: animated skeleton at chart height

#### Breakdown section

Lives at the bottom of the Periodic view (`BreakdownSection`, `components/metrics/breakdown-section.tsx`) — there is **no standalone breakdowns route**. Four tabs — each fetches `GET /insights/breakdown` with the corresponding breakdown param on tab activation (lazy fetch, cached).

- **Age & Gender** — grouped horizontal bar chart, grouped by age range, colored by gender
- **Country** — horizontal bar chart sorted by spend (top 10 countries)
- **Platform & Placement** — stacked bar chart (facebook feed, instagram feed, instagram story, etc.)
- **Device** — donut chart (mobile vs desktop)

Each breakdown tab shows: Impressions, Spend, CTR. Metric selector for breakdowns is its own smaller control.

#### Data fetching

```ts
// Main chart — refetches on any control change
useQuery({
  queryKey: queryKeys.timeseries(accountId, dateRange, level, metrics, timeIncrement),
  queryFn:  () => api.insights.getTimeseries({ ... }),
  staleTime: 15 * 60 * 1000,
})

// Breakdown — fetched lazily on tab activation
useQuery({
  queryKey: queryKeys.breakdown(accountId, dateRange, activeBreakdown),
  queryFn:  () => api.insights.getBreakdown({ breakdown: activeBreakdown, ... }),
  staleTime: 30 * 60 * 1000,
  enabled:  !!activeBreakdown,
})
```

---

### 6.3 Table

**Purpose:** Sortable, filterable metrics table for campaigns, ad groups, or ads.

```
┌──────────────────────────────────────────────────────────────┐
│  LEVEL TABS: [Campaigns] [Ad Groups] [Ads]                   │
├──────────────────────────────────────────────────────────────┤
│  TOOLBAR: [🔍 Search...] [Status ▾] [Columns ▾]   [Export]  │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  DATA TABLE                                                   │
│  (sortable columns, sticky first column, paginated)          │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│  Showing 1–25 of 47    [← 1  2  →]                          │
└──────────────────────────────────────────────────────────────┘
```

#### Level tabs

shadcn `Tabs` — Campaigns · Ad Groups · Ads. Switching resets sort, keeps date range and search.

#### Toolbar

- **Search** — shadcn `Input` with search icon. Debounced (300ms) — filters by entity name client-side if data is fully loaded, or via `search` API param if paginating server-side.
- **Status filter** — shadcn `Select` with multi-select support: All · Active · Paused · Archived
- **Columns** — shadcn `Popover` with checkboxes to show/hide metric columns. Persisted in `localStorage`.
- **Export** — downloads current view as CSV (client-side, from loaded data)

#### Table columns

**Campaigns level:**

| Column | Type | Default | Sortable |
|---|---|---|---|
| Name | text | ✅ visible | ✅ |
| Status | badge | ✅ visible | ✅ |
| Objective | text | ✅ visible | ❌ |
| Daily budget | currency | ✅ visible | ✅ |
| Spend | currency | ✅ visible | ✅ |
| Impressions | number | ✅ visible | ✅ |
| Reach | number | optional | ✅ |
| Clicks | number | ✅ visible | ✅ |
| CTR | percent | ✅ visible | ✅ |
| CPM | currency | optional | ✅ |
| CPC | currency | optional | ✅ |
| Conversions | number | ✅ visible | ✅ |
| Conv. Value | currency | optional | ✅ |
| ROAS | multiplier | ✅ visible | ✅ |
| CPA | currency | optional | ✅ |

**Ad Groups level:** same as campaigns, plus Optimization Goal, Bid Amount; minus Objective.

**Ads level:** same as campaigns, plus a **Creative preview** column (thumbnail + headline, leftmost after Name), minus Budget columns.

**Compare deltas:** when the global `?compare` toggle is on, `TableView` sends `compare_previous=true` and every numeric metric cell (currency/number/percent/roas) renders a `DeltaPill` beneath the value using `row.metrics_previous[col.metricKey]` — cost metrics color-inverted per `metricDelta`, with the previous absolute value shown on hover (`variant="tooltip"`). The `compare` flag is part of the query key so cached results split by compare on/off.

#### Row interactions

- Click row → expand inline detail panel (not a new page) showing:
  - For campaign: list of ad groups in that campaign with their spend (mini table)
  - For ad group: list of ads with creative thumbnails
  - For ad: full creative preview (calls `GET /ads/:id/creative`)
- Clicking the entity name navigates down a level with the parent pre-filtered:
  - Campaign name → `/table?level=adgroup&campaign_id=...`
  - Ad Group name → `/table?level=ad&adgroup_id=...`

#### Status badge

- **Active** — green dot + "Active"
- **Paused** — yellow dot + "Paused"
- **Archived** — gray dot + "Archived"
- **Deleted** — red dot + "Deleted" (shown only if explicitly filtering for deleted)

#### Pagination

Server-side. 25 rows per page default. shadcn `Pagination` component at the bottom.

---

### 6.4 Ads Content

**Purpose:** Visual view of ad creatives paired with their performance. Lets the team quickly identify winning and underperforming creatives.

```
┌──────────────────────────────────────────────────────────────┐
│  TOOLBAR: [Format ▾] [Sort by ▾] [🔍 Search] [Grid / List]  │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  AD GRID (3 columns)                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ AdCard   │  │ AdCard   │  │ AdCard   │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ AdCard   │  │ AdCard   │  │ AdCard   │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│  Load more (infinite scroll or "Load 25 more" button)        │
└──────────────────────────────────────────────────────────────┘
```

#### `AdCard` component

```
┌────────────────────────┐
│  [Creative image/video │
│   thumbnail 4:5]       │
│                        │
│  Format badge (video)  │
├────────────────────────┤
│  "Shop Summer Deals"   │  ← title
│  "Enjoy up to 50% off" │  ← body (truncated, 2 lines)
│  [SHOP NOW]            │  ← CTA badge
├────────────────────────┤
│  📊 Spend: $780        │
│     CTR: 1.87%         │
│     Conv: 150  ROAS:7x │
├────────────────────────┤
│  Status: ● Active      │
│  Campaign: Summer Sale │
└────────────────────────┘
```

- Creative thumbnails use a 4:5 portrait frame with `object-contain` (zero crop) — full asset shown, letterboxed on a muted background rather than cropped to fill
- Image ads: show `image_url` directly
- Video ads: show `thumbnail_url` with a play icon overlay
- Carousel ads: show first image with a carousel indicator badge
- Missing creative (not yet fetched): show gray placeholder with animated pulse
- Clicking any card opens the `AdDetailSheet`
- **Compare deltas:** when the global `?compare` toggle is on, `AdsView` requests `compare_previous=true` (via `level=ad` on `/insights/table`); `AdCard` and `AdRow` render a `DeltaPill` next to Spend/CTR/Conv./ROAS using `ad.metrics_previous`, with the previous absolute value shown on hover (`variant="tooltip"`). The `compare` flag is part of the infinite-query key.

#### `AdDetailSheet` (shadcn `Sheet` — slides in from right)

Full-width side panel showing:

**Left panel (creative):**
- Full-size image or video thumbnail
- All creative text: title, body, CTA, destination URL
- Format, platform

**Right panel (metrics):**
- Full metrics for the selected date range
- Video retention funnel (if video ad) — horizontal bar chart: plays → 25% → 50% → 75% → 100%
- Placement breakdown (facebook feed vs instagram story, etc.)
- Campaign and ad group hierarchy breadcrumb

#### Toolbar

- **Format filter** — `All · Image · Video · Carousel`
- **Sort by** — `Spend (high to low) · CTR · Conversions · ROAS · Impressions`
- **Search** — by ad name or creative headline
- **Grid / List toggle** — grid (default) shows visual cards; list shows compact rows with a small thumbnail

#### Creative loading

Creatives are loaded lazily. The page first loads ad metadata + metrics from `GET /insights/table?level=ad`. For each ad in the grid, the creative data is fetched from `GET /ads/:id/creative` only when the card is in or near the viewport (Intersection Observer). If the creative returns `202` (still fetching), the card shows a skeleton and retries after 3 seconds.

---

## 7. Settings & Org Pages

### `/settings/org`

Simple form page. **Owner only.**

- Org name (text input, editable)
- Org slug (read-only display)
- "Save changes" button → `PATCH /org`
- Danger zone: "Delete organization" (confirmation dialog — owner must type org name to confirm)

### `/settings/members`

**Owner only.**

Layout: header with "Invite member" button → opens shadcn `Dialog`.

**Invite dialog:**
- Email input + Role selector (Member only — role is always member in current model)
- Submit → `POST /org/members/invite`
- Shows success message with the invited email

**Members table:**

| Column | Description |
|---|---|
| Name / Email | Name if joined, email if pending |
| Role | Badge: Owner / Member |
| Status | Joined / Pending invite |
| Joined | Date |
| Actions | Remove button (owner can't remove themselves) |

### `/settings/connections`

**Owner only.**

List of platform connections. One card per platform.

```
┌────────────────────────────────────────────────────┐
│  [Meta logo]  Meta Ads                             │
│  Status: ● Connected                               │
│  Token type: System User                           │
│  Connected by: Akbar · Feb 1, 2026                │
│  Last used: 5 min ago                              │
│  Ad accounts imported: 3                          │
│  [Disconnect]                                      │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│  [Google logo]  Google Ads               [Connect] │
│  Status: Not connected                             │
└────────────────────────────────────────────────────┘
```

Clicking "Connect" for Meta opens a dialog with:
- Instructions to create a System User token in Meta Business Manager
- Text input for the token
- Submit → `POST /connections` (validates token server-side before saving)
- On success: "Connection verified. Importing ad accounts…" → closes dialog, page refreshes

### `/settings/accounts`

Per-account configuration list. Orgs can have 200–1000+ accounts, so the list is **server-paginated** — never the full org at once.

```
Account Type
CPAS (Collaborative Ads) accounts show traffic metrics only — ROAS/conversions
owned by the retailer. CPAS applies to Meta accounts only.

[ 🔍 Search accounts… ]            [ All | Meta | TikTok ]
┌──────────────────────────────────────────────────────┐
│  ▣ Meta   Acme Ads      USD          [ Standard ▾ ]  │
│  ▣ TikTok Beta Co       EUR                    —     │
└──────────────────────────────────────────────────────┘
Showing 1–20 of 123        ←  1  2  3  …  7  →
```

- **Data:** `useQuery` on `accountsApi.list({ search, platform, page, per_page: 20 })`, keyed by `queryKeys.accountsList(platform, search, page)`. `placeholderData:(prev)=>prev` keeps the list stable while typing/paging. `PAGE_SIZE = 20`.
- **Search:** local input → `useDebounced(…, 250)` (from `hooks/use-account.ts`) → server `search` param.
- **Platform filter:** `Tabs` (All / Meta / TikTok), single-select, value `all`/`meta`/`tiktok` → server `platform` param. `all` sends no filter.
- Changing search or platform resets `page` to 1.
- **Account type control is Meta-only:** Meta rows render the Standard/CPAS `Select`; non-Meta (TikTok) rows render a muted `—` (CPAS is a Meta concept; backend rejects `cpas` on non-Meta with `409`).
- **Mutation:** `accountsApi.updateConfig(id, { account_type })`; on success invalidates the `["accounts"]` prefix (refreshes this list, picker search, and count together).
- Footer: `PaginationBar` (shown only when `total_pages > 1`).
- Empty state reflects filters: "No accounts match your filters." vs "No ad accounts connected yet."

---

## 8. Shared Components

### Design language (single-accent rule)

The UI runs on **one accent family**: the sidebar indigo (`--primary`/`--ring`/`--accent`, hue ~273° in `globals.css`, matching the rail in both light and dark mode). Every interactive-accent surface — primary buttons, active toggles/segments, links, focus rings — resolves to this token; there is no second (blue/orange) accent. Deliberately **exempt** and left brand/semantic-correct: platform **brand** colors (Meta blue, TikTok black, Google multicolor — `platform-badge.tsx`, `settings/connections`), **status** colors (green active / yellow paused / red error — `status-badge.tsx`), and **chart-series / data-encoding** colors (`--chart-*`, `--tint-*`, iris palette). Cards share one surface (`rounded-xl bg-card ring-1 ring-foreground/10` + `--shadow-soft`, lifting to `--shadow-lift` on hover) — the same for platform overview cards **and** dashboard (bento) tiles, which no longer use a bespoke near-black/mono-terminal look.

### `SegmentControl`
`components/ui/segment-control.tsx` — the single **filled-pill** segmented control used app-wide. Presentational only (owns no state): a muted-bg pill container (`bg-muted rounded-lg p-0.5`); the active segment gets a solid `bg-primary`/`text-primary-foreground` fill with `shadow-sm`, inactive segments are `text-muted-foreground` → `hover:text-foreground`. Props: `items: {value,label,icon?,href?}[]`, `value`, `onValueChange?(value)`, `ariaLabel?`, `className?`, `segmentClassName?`. Interaction is per-item: an item with `href` renders a Next `<Link>` (route-based tabs), otherwise a `<button>` calling `onValueChange` (state-based toggles). Typed generically over the value union (no `any`). Used by the platform tab bar (`PlatformTabs`), settings nav (`SettingsNav`), Periodic (Day/Week/Month + Line/Bar), Ads (Grid/List), Table (Campaigns/Ad Groups/Ads), Breakdown (Age/Country/Platform/Device), and the `/settings/accounts` platform filter — replacing all previously bespoke segment/tab implementations and most in-view shadcn `Tabs` usages.

### `MetricCard`
KPI display card with value, label, % change badge, and optional sparkline. Used in Overview.

### `SparklineChart`
Tiny inline Recharts `LineChart` (no axes, no tooltip) for KPI card trends.

### `DateRangePicker`
Single popover, two views: preset buttons and a `Custom range…` reveal that swaps in a `react-day-picker` range calendar (future dates disabled). Apply sets `date_start`/`date_end` and clears `date_preset`. Syncs to URL.

### `AccountSwitcher` / `AccountCommandList`
Server-side searched `cmdk` combobox (`?search=&platform=`) — single-select on platform routes, multi-select (grouped by platform) on the combined dashboard. Pinned + Recent groups persisted in `ui-store` via `accountSnapshots`, pruned against the live account list when a snapshot is conclusively gone (idle, non-truncated page). Syncs `account_id` (or `accounts`) to URL. `useSelectedAccount` validates a selected `account_id` that isn't on the live first page via `GET /accounts/:id` (a snapshot alone is not trusted); a `404` (disabled/removed account) drops the dead selection and falls back to the first live remembered/first-page account, which the switcher then writes back to the URL.

### `PaginationBar`
Server-pagination footer: "Showing X–Y of N" + numbered page buttons (collapses to first/last with `…` past 7 pages) and prev/next. Props: `page`, `totalPages`, `total`, `perPage`, `onPage`. Used by `TableView` and `/settings/accounts`.

### `SyncStatusBadge`
Polls sync status every 60 seconds. Shows dot indicator + last updated time. Triggers manual sync on click (owner only).

### `DeltaPill`
`components/metrics/delta-pill.tsx` — period-over-period delta badge (`▲ +12%`) used by KPI cards, funnel stages, table cells, and ad cards/rows. Computes the delta via the `metricDelta` helper (`lib/formatters.ts`), whose `direction` is **semantic (good/bad)**, not raw sign: for cost/efficiency metrics (`COST_METRICS` = `cpa`/`cpc`/`cpm`/`cpp`/`frequency`, plus any `cost_per_*` key) the direction is inverted so a decrease reads green ("up"). Props: `current`, `previous`, `metricKey`, `className?`, `variant?` (`"inline" | "tooltip"`, default `"tooltip"`), `currency?` (default `"USD"`), `valueType?` (overrides the type otherwise derived from `metricKey` via `metricType`). Renders **nothing** when there's no usable comparison (missing current/previous or a zero baseline) — stays silent per P-2. When a comparison exists it also shows the **previous absolute value**, formatted via `formatMetric(previous, type, currency)`: `variant="inline"` appends a muted `vs <prev>` after the pill (KPI cards, funnel); `variant="tooltip"` reveals `prev <prev>` on hover via the shadcn `Tooltip` (`components/ui/tooltip.tsx`, table cells + ad cards/rows). `DeltaBadge` (the raw visual, given a pre-computed `label`+`direction`) is exported for callers that already have a formatted change, e.g. `metric-tile.tsx`.

### `StatusBadge`
Color-coded badge for entity status. Props: `status: 'active' | 'paused' | 'archived' | 'deleted'`

### `PlatformBadge`
Small platform icon. `meta`/`tiktok`/`google_ads` render their brand SVG (`/meta-logo.svg`, `/tiktok-logo.svg`, `/gads-logo.svg`); any other platform falls back to a colored letter tile. Props: `platform: 'meta' | 'google_ads' | 'tiktok'`, `size?: 'sm' | 'md'`

### `MetricValue`
Formatted metric display. Handles currency, percentage, multiplier (ROAS), and large number abbreviation (1.2M, 45K). Props: `value`, `type: 'currency' | 'percent' | 'number' | 'roas'`, `currency?: string`

### `EmptyState`
Centered illustration + title + description + optional CTA button. Used when: no accounts connected, no campaigns in date range, no creatives loaded.

### `LoadingSkeleton`
Animated pulse placeholder. Variants: card, table-row, chart.

### `ConfirmDialog`
shadcn `AlertDialog` wrapper for destructive actions (disconnect, remove member, delete org). Requires typing a confirmation phrase for high-risk actions.

### `AnimatedIcon`
`components/shared/animated-icon.tsx` — the single wrapper for giving any `lucide-react` glyph a tasteful micro-animation. Both modes honor the OS "reduce motion" preference. Props: `icon: LucideIcon`, `motionPreset` (name of a preset in `lib/motion.ts`), `trigger?: "hover" | "state"` (default `"hover"`), `active?` + `activeVariant?` + `appear?` (for `trigger="state"`), `iconClassName?`, `size?`, `className?`.

Two modes:
- `trigger="hover"` (default): **CSS `group-hover` drives the animation**, so the whole containing element (a `<Link>`, `<button>`, row `<div>`, card, etc.) fires it on hover — not just the icon itself. The icon renders as a plain `<span>` carrying `group-hover:` transform classes (`ICON_HOVER_CLASS` in `lib/motion.ts`), so the parent can be any element type without becoming a motion component. **Requirement:** the nearest interactive/hover ancestor of the icon **must carry the Tailwind `group` class**, or the animation is inert. reduce-motion is honored via `motion-reduce:` variant guards on each class. Used for nav/menu/action glyphs (Summary, Settings, Bell, Filter, Trash, Export, Star, "See All"/drill chevrons, external-link/plug).
- `trigger="state"`: framer-motion (`motion.span`) drives the animation from a boolean `active` — used for expand/collapse chevrons (rotate on open) and for `appear` "pop-in" of state icons (delta trend arrows, active sort arrow, sync CheckCircle2/AlertTriangle, connection-stage checks). This path respects reduce-motion via the global `<MotionConfig reducedMotion="user">` in `components/shared/providers.tsx`.

Animation presets live **only** in `lib/motion.ts` (single source): `ICON_MOTION` (framer-motion variants, used by `trigger="state"`/`appear`) and `ICON_HOVER_CLASS` (Tailwind `group-hover:` class strings, used by `trigger="hover"`). The `wiggle` hover shake uses an `@keyframes icon-wiggle` defined in `app/globals.css`. Do not scatter inline motion objects in components — add a new preset in both maps and reference it by name. Current presets: `spin` (90° tip — settings/sliders), `wiggle` (shake — bell/alert/dismiss), `bounce` (vertical hop — download/export, up-down chevrons), `pop` (scale pop; also the mount `hidden→show` for appearing state icons), `draw` (scale+rotate — external-link/plug), `nudge` (subtle lift — generic nav glyphs), `nudgeRight` (slide right — "go/navigate" chevrons), `flip` (180° — expand/collapse chevrons). Platform-badge letter marks (M/T/G) and chart/data-viz inline SVGs (`bento/geo-tile.tsx`, `bento/gauge-tile.tsx`) are **not** routed through `AnimatedIcon` — they animate on their own terms. Active-op spinners (`Loader2`, `RefreshCw` with `animate-spin`) stay as CSS spins since they only run during a live async op.

---

## 9. State Management

Two layers of state:

### URL state (via `nuqs`)

Primary state for all dashboard filters — ensures shareable, bookmarkable URLs and browser back/forward navigation.

| URL param | Used by | Example |
|---|---|---|
| `account_id` | Platform views (Meta, TikTok) | `?account_id=uuid` |
| `accounts` | Combined dashboard (multi-select; absent = all) | `?accounts=uuid1,uuid2` |
| `date_preset` | All dashboard views | `?date_preset=last_30d` |
| `date_start` | All dashboard views | `?date_start=2026-05-01` |
| `date_end` | All dashboard views | `?date_end=2026-05-30` |
| `level` | Table | `?level=campaign` (Table only) |
| `trend_level` | Trends/Periodic | `?trend_level=account` (default `account`; separate key from `level` so both can co-mount on Overview) |
| `metrics` | Periodic | `?metrics=spend,ctr` |
| `time_increment` | Periodic | `?time_increment=day` |
| `compare` | Global (ControlStrip) | `?compare=true` — drives Trends overlay + delta pills on cards/funnel/table/ads |
| `breakdown` | Periodic | `?breakdown=age_gender` |
| `status` | Table | `?status=active` |
| `sort_by` | Table | `?sort_by=spend` |
| `sort_order` | Table | `?sort_order=desc` |
| `page` | Table | `?page=2` |
| `campaign_id` | Table (drill-down) | `?campaign_id=uuid` |
| `adgroup_id` | Table (drill-down) | `?adgroup_id=uuid` |
| `format` | Ads Content | `?format=video` |
| `ad_sort` | Ads Content | `?ad_sort=ctr` |

### Zustand store (`ui-store.ts`)

For UI state that should NOT be in the URL:

```ts
interface UIStore {
  sidebarCollapsed: boolean
  setSidebarCollapsed: (v: boolean) => void

  visibleColumns: Record<string, string[]>   // per level — persisted to localStorage
  setVisibleColumns: (level: string, cols: string[]) => void
}
```

### TanStack Query

All server data. No Redux, no Context for API data. Query keys are centralized in `query-keys.ts` to ensure consistent cache invalidation.

```ts
// lib/query-keys.ts
export const queryKeys = {
  accounts:    (orgId: string) => ['accounts', orgId],
  overview:    (accountId: string, dateRange: DateRange) => ['overview', accountId, dateRange],
  timeseries:  (accountId: string, dateRange: DateRange, level: string, metrics: string[], increment: string) =>
                 ['timeseries', accountId, dateRange, level, metrics, increment],
  table:       (accountId: string, dateRange: DateRange, level: string, filters: TableFilters) =>
                 ['table', accountId, dateRange, level, filters],
  breakdown:   (accountId: string, dateRange: DateRange, type: string) =>
                 ['breakdown', accountId, dateRange, type],
  creative:    (adId: string) => ['creative', adId],
  syncStatus:  (accountId: string) => ['sync-status', accountId],
}
```

---

## 10. Data Fetching Patterns

### Stale times (match backend cache TTL)

| Query | `staleTime` |
|---|---|
| Overview, timeseries, table | 15 min |
| Breakdown | 30 min |
| Campaigns / Ad groups / Ads (structure) | 30 min |
| Creatives | 60 min |
| Sync status | 1 min (polled) |
| Accounts list | 60 min |

### Error handling

All API calls go through the Axios instance in `lib/api/client.ts`. The interceptor handles:
- `401` → clear JWT cookie, redirect to `/login`
- `403` → show `ForbiddenError` page
- `429` → show toast: "Data is temporarily delayed — showing cached results"
- `503` with `sync_pending` → show inline "Loading data for the first time…" state instead of an error

### Creative polling (202 pattern)

```ts
// hooks/use-creative.ts
function useCreative(adId: string) {
  return useQuery({
    queryKey: queryKeys.creative(adId),
    queryFn:  () => api.ads.getCreative(adId),
    refetchInterval: (data) =>
      data?.meta?.status === 'fetching' ? 3000 : false,  // poll every 3s until ready
    staleTime: 60 * 60 * 1000,
  })
}
```

### Sync status polling

```ts
// hooks/use-sync-status.ts
function useSyncStatus(accountId: string) {
  return useQuery({
    queryKey:       queryKeys.syncStatus(accountId),
    queryFn:        () => api.sync.getStatus(accountId),
    refetchInterval: 60_000,   // every 60 seconds
    refetchIntervalInBackground: false,  // only poll when tab is active
  })
}
```

---

## 11. URL State Conventions

- `date_preset` and `date_start`/`date_end` are mutually exclusive; the picker clears one when the other is chosen. If both somehow appear, a custom range (`date_start`+`date_end`) wins (`useDateRange`).
- When `account_id` is absent, `useSelectedAccount` resolves a default: first pinned/recent account for the platform, else the first row of the platform's first page.
- Combined dashboard: `accounts` absent = all org accounts (sent as empty `account_ids`); `accounts=""` = none selected (empty state).
- Changing `level` in the table resets `page` to 1 and clears `campaign_id` / `adgroup_id`
- All URL params use snake_case (consistent with API params)
- Boolean params: `compare=true` — absence means `false` (no `compare=false` in URL)
- Array params: `metrics=spend,ctr` — comma-separated in a single param

### Default URL state on first visit

```
/overview?account_id={first_account}&date_preset=last_30d
/periodic?account_id={first_account}&date_preset=last_30d&level=campaign&metrics=spend,clicks&time_increment=day
/table?account_id={first_account}&date_preset=last_30d&level=campaign&sort_by=spend&sort_order=desc
/ads?account_id={first_account}&date_preset=last_30d&ad_sort=spend
```
