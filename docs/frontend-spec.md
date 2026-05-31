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
│   │   ├── layout.tsx            # Sidebar + header shell
│   │   ├── overview/page.tsx
│   │   ├── periodic/page.tsx
│   │   ├── table/page.tsx
│   │   └── ads/page.tsx
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
│   ├── layout/                   # Sidebar, Header, AccountSwitcher
│   ├── charts/                   # Recharts wrappers
│   ├── metrics/                  # MetricCard, MetricTable, etc.
│   ├── ads/                      # AdCard, CreativePreview, etc.
│   └── shared/                   # DateRangePicker, StatusBadge, etc.
│
├── hooks/
│   ├── use-account.ts            # Current selected account
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
│   └── constants.ts              # Date presets, metric labels, colors
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

| Route | Page | Auth required | Role |
|---|---|---|---|
| `/` | Redirect → `/overview` | ✅ | any |
| `/login` | Login | ❌ | — |
| `/signup` | Signup | ❌ | — |
| `/verify-email` | Email verification | ❌ | — |
| `/forgot-password` | Request reset | ❌ | — |
| `/reset-password` | Set new password | ❌ | — |
| `/overview` | Overview dashboard | ✅ | any |
| `/periodic` | Time series dashboard | ✅ | any |
| `/table` | Metrics table | ✅ | any |
| `/ads` | Ads content | ✅ | any |
| `/settings/org` | Org settings | ✅ | owner |
| `/settings/members` | Member management | ✅ | owner |
| `/settings/connections` | Platform connections | ✅ | owner |

Auth guard is a middleware (`middleware.ts`) that checks for a valid JWT cookie. Unauthenticated users are redirected to `/login`. Members trying to access owner-only settings pages see a `403` page.

---

## 4. Global Layout

The dashboard layout (`(dashboard)/layout.tsx`) renders a fixed sidebar on the left and a top header. Main content scrolls independently.

```
┌──────────────────────────────────────────────────────────────┐
│  HEADER                                                       │
│  [AccountSwitcher]     [DateRangePicker]    [SyncStatus] [👤] │
├───────────┬──────────────────────────────────────────────────┤
│           │                                                   │
│  SIDEBAR  │   PAGE CONTENT                                    │
│           │                                                   │
│  Overview │                                                   │
│  Periodic │                                                   │
│  Table    │                                                   │
│  Ads      │                                                   │
│           │                                                   │
│  ───────  │                                                   │
│  Settings │                                                   │
│           │                                                   │
└───────────┴───────────────────────────────────────────────────┘
```

### Header — components

**`AccountSwitcher`**
- shadcn `Popover` + `Command` (combobox pattern)
- Lists all accounts for the current org
- Selecting updates `account_id` in URL state and triggers data refetch
- Shows account name + platform icon badge (Meta logo, etc.)
- Shows "No accounts connected" state with link to `/settings/connections` if empty

**`DateRangePicker`**
- shadcn `Popover` + `Calendar`
- Left panel: preset buttons (`Last 7 days`, `Last 30 days`, `Last 90 days`, `This month`, `Last month`, `Custom range`)
- Right panel: calendar appears only for custom range
- Selection stored in URL params: `?date_preset=last_30d` or `?date_start=2026-05-01&date_end=2026-05-30`
- Default: `last_30d`

**`SyncStatusBadge`**
- Small indicator in the top-right area
- Green dot: all syncs current
- Yellow dot + "Syncing…" spinner: a job is currently running
- Red dot: a sync has failed — click to see detail modal
- "Last updated X min ago" tooltip on hover
- "Refresh" button triggers `POST /sync/trigger` (owner only)
- Polls `GET /sync/status` every 60 seconds

**User menu** — shadcn `DropdownMenu`
- Shows user name + email
- Links: Profile, Settings, Sign out

### Sidebar — items

```
[Logo / DashMet wordmark]

Navigation
  📊  Overview
  📈  Periodic
  📋  Table
  🖼️  Ads Content

─────────────
  ⚙️  Settings
```

Active item highlighted. Sidebar collapses to icon-only at medium viewports (still desktop-first — no hamburger menu).

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

```
┌──────────────────────────────────────────────────────────────┐
│  KPI CARDS (2 rows × 4 cards)                                │
│  [Spend] [Impressions] [Reach]  [Clicks]                     │
│  [CTR]   [CPM]         [Conv.]  [ROAS]                       │
├──────────────────────────────┬───────────────────────────────┤
│  SPEND TREND (line chart)    │  CONVERSIONS TREND (line)     │
│  Last 30 days, daily         │  Last 30 days, daily          │
├──────────────────────────────┴───────────────────────────────┤
│  TOP CAMPAIGNS TABLE                                          │
│  Name | Spend | Impressions | CTR | Conversions | ROAS       │
│  (5 rows, no pagination — link to /table for full view)      │
└──────────────────────────────────────────────────────────────┘
```

#### `MetricCard` component

```
┌─────────────────────────┐
│  Spend                  │
│  $1,234.56              │
│  ▲ 12.3%  vs prev. period│
│  ▁▂▃▄▅▆ (sparkline)    │
└─────────────────────────┘
```

Props:
- `label` — metric display name
- `value` — formatted value (currency, %, number)
- `change` — % change vs previous period (null if unavailable)
- `sparkline` — array of daily values for the mini chart
- `trend` — `up` | `down` | `neutral` — controls arrow color (green/red/gray)
- `loading` — shows skeleton

KPI cards in order: Spend, Impressions, Reach, Clicks, CTR, CPM, Conversions, ROAS. Cards for Conversions and ROAS only render if the account has `primary_conversion_action` configured — otherwise show a "Set up conversion tracking" prompt card in their place.

#### Spend & Conversions trend charts

- Recharts `LineChart` with `ResponsiveContainer`
- X-axis: date labels (abbreviated: "May 1", "May 15", "May 30")
- Y-axis: formatted values (currency for spend, integer for conversions)
- Tooltip: formatted date + value
- No legend (single series each)
- Height: `240px`

#### Top Campaigns table

- shadcn `Table` — 5 rows, no pagination
- Columns: Campaign name, Status badge, Spend, Impressions, CTR, Conversions, ROAS
- "View all campaigns →" link routes to `/table?level=campaign`
- Shows skeleton rows while loading

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
│  [Level ▾] [Metrics ▾] [Time ▾ Day/Week/Month] [Compare ○]  │
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

**Time increment** — segmented control (shadcn `ToggleGroup`)
- Options: Day · Week · Month
- Default: Day

**Compare previous period** — shadcn `Switch`
- When on: overlays the prior period as a dashed line on the same chart
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

Four tabs — each fetches `GET /insights/breakdown` with the corresponding breakdown param on tab activation (lazy fetch, cached).

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
│   thumbnail 16:9]      │
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

- Image ads: show `image_url` directly
- Video ads: show `thumbnail_url` with a play icon overlay
- Carousel ads: show first image with a carousel indicator badge
- Missing creative (not yet fetched): show gray placeholder with animated pulse
- Clicking any card opens the `AdDetailSheet`

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

---

## 8. Shared Components

### `MetricCard`
KPI display card with value, label, % change badge, and optional sparkline. Used in Overview.

### `SparklineChart`
Tiny inline Recharts `LineChart` (no axes, no tooltip) for KPI card trends.

### `DateRangePicker`
Popover with preset buttons + optional calendar for custom range. Syncs to URL.

### `AccountSwitcher`
Combobox dropdown listing all org accounts. Syncs selected account to URL + Zustand store.

### `SyncStatusBadge`
Polls sync status every 60 seconds. Shows dot indicator + last updated time. Triggers manual sync on click (owner only).

### `StatusBadge`
Color-coded badge for entity status. Props: `status: 'active' | 'paused' | 'archived' | 'deleted'`

### `PlatformBadge`
Small logo + name badge for platform. Props: `platform: 'meta' | 'google_ads' | 'tiktok'`

### `MetricValue`
Formatted metric display. Handles currency, percentage, multiplier (ROAS), and large number abbreviation (1.2M, 45K). Props: `value`, `type: 'currency' | 'percent' | 'number' | 'roas'`, `currency?: string`

### `EmptyState`
Centered illustration + title + description + optional CTA button. Used when: no accounts connected, no campaigns in date range, no creatives loaded.

### `LoadingSkeleton`
Animated pulse placeholder. Variants: card, table-row, chart.

### `ConfirmDialog`
shadcn `AlertDialog` wrapper for destructive actions (disconnect, remove member, delete org). Requires typing a confirmation phrase for high-risk actions.

---

## 9. State Management

Two layers of state:

### URL state (via `nuqs`)

Primary state for all dashboard filters — ensures shareable, bookmarkable URLs and browser back/forward navigation.

| URL param | Used by | Example |
|---|---|---|
| `account_id` | All dashboard views | `?account_id=uuid` |
| `date_preset` | All dashboard views | `?date_preset=last_30d` |
| `date_start` | All dashboard views | `?date_start=2026-05-01` |
| `date_end` | All dashboard views | `?date_end=2026-05-30` |
| `level` | Periodic, Table | `?level=campaign` |
| `metrics` | Periodic | `?metrics=spend,ctr` |
| `time_increment` | Periodic | `?time_increment=day` |
| `compare` | Periodic | `?compare=true` |
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

- When `date_preset` is set, `date_start` and `date_end` are ignored (preset takes precedence)
- When `account_id` is absent from the URL, default to the first account in the list
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
