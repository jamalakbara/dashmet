# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project aims to.

## [Unreleased]

### Added
- **Meta token auto-refresh + token-failure alerting (Piece 1 + Piece 2 emission, workers-sync).** New `MetaClient.exchange_long_lived_token(app_id, app_secret, fb_exchange_token)` wraps Meta's `fb_exchange_token` grant (same graph-version + httpx `get` plumbing) — `backend/workers/meta_client.py`. New beat task `refresh_meta_tokens` (`backend/workers/tasks/meta_token_refresh.py`, registered in `celery_app` include list + `meta` queue route, `refresh-meta-tokens` beat entry daily 00:45 UTC, staggered off TikTok's 00:30) — finds active Meta connections with a non-NULL `token_expires_at` inside a 7-day window (NULL expiry = never-expires/unprobed → skipped) and exchanges the still-valid long-lived token for a fresh one while it's alive. Success stores the new encrypted token + recomputed `token_expires_at` and clears health + resolves any open `token_expired`/`token_expiring` alert (P-2). Failure leaves a durable trace (P-8): stamps `last_error`/`last_error_at`, creates a deduped `token_expired` notification (`deep_link=/settings/connections`), emails the org owner once, and — unlike TikTok — does **not** deactivate the connection (recovers on manual re-paste, P-5). `META_APP_ID`/`META_APP_SECRET` unset → task logs and returns early. New shared `backend/workers/token_alerts.py` (`record_token_failure` / `clear_token_failure` / `alert_connection_token_failure` / `send_token_failure_email`) — the single funnel all platforms use so every notification still goes through `app/services/notifications.py` (P-7); email is gated on the notification being newly created (queries for an existing unresolved row first, since `create_notification`'s `ON CONFLICT DO NOTHING` can't signal new-vs-existing) so a repeated failure never re-spams. Dedup key scheme `{type}:{connection_id}`. Tests: `backend/tests/test_meta_token_refresh.py` (success updates token + expiry + resolves alert; failure sets `last_error` + creates `token_expired` + keeps connection active + does not crash; email gated off when an unresolved alert already exists; unset app creds is a no-op). `docs/sync-worker-spec.md`.
- **Notification center + connection health badge (token-expiry alerting, Piece 3 frontend).** New typed API client `frontend/src/lib/api/notifications.ts` (`NotificationItem` mirroring `NotificationOut`, `list(status?)` → `{items, unread_count}`, `markRead(id)` — no `any`, api-contract-parity). Bell + unread-count badge added to both the dashboard top chrome (`frontend/src/components/layout/top-bar.tsx`, replacing the placeholder bell) and the settings header (`frontend/src/components/layout/header.tsx`); clicking opens a Popover inbox (`frontend/src/components/shared/notification-center.tsx`) listing unread notifications with severity icons + relative time — clicking a row marks it read and follows its stored `deep_link`. Live via TanStack Query polling (`refetchInterval` 45s + `refetchOnWindowFocus`, `frontend/src/hooks/use-notifications.ts`, `NOTIFICATIONS_POLL_MS`), never websockets; the badge is hidden entirely at `unread_count === 0` and clears automatically when the backend resolves a notification (P-2 — no permanently-lit badge). Per-connection health chip on the connections page (`frontend/src/components/shared/connection-health-badge.tsx`, integrated in `frontend/src/app/settings/connections/page.tsx`) driven by the backend-derived `health` field — renders nothing when `healthy` (P-2), amber "Token expires soon" (with relative expiry) when `expiring`, red "Token expired — reconnect" when `expired`, red "Connection error" with `last_error`/`last_error_at` in a tooltip when `error`; a Reconnect action (OAuth re-initiate for TikTok/Google, token dialog for Meta) surfaces only when `expired`/`error`, and the connections query now refetches on a 60s interval + window focus so the badge reflects live health. New query keys `notifications` / `connections` (`frontend/src/lib/query-keys.ts`). `docs/frontend-spec.md`, `docs/frontend-ia-spec.md`.
- **Token-expiry alerting service + endpoints (Piece 2 backend).** Single notification writer `backend/app/services/notifications.py` — the one writer for the `notifications` table (P-7), imported by the POST endpoints and (next) worker tasks, never as a side effect of a read. `create_notification` upserts `ON CONFLICT (organization_id, dedup_key) DO NOTHING` (DB dedup, not an app-side time window — anti-req §2.3); `resolve_notification` marks matching rows `resolved` for P-2 auto-clear; `list_notifications` / `unread_count` / `mark_read` (tenant-scoped) are the read helpers. New endpoints `GET /api/v1/notifications?status=` (tenant-scoped list + unread count, emits nothing) and `POST /api/v1/notifications/{id}/read` (mark read, `404` if not in org) — `backend/app/api/v1/endpoints/notifications.py`, `backend/app/schemas/notifications.py`, registered in `backend/app/api/v1/router.py`. `GET /api/v1/connections` now returns `token_expires_at`, `last_error`, `last_error_at`, and a derived `health` (`healthy` / `expiring` / `expired` / `error`) — `backend/app/schemas/accounts.py::ConnectionResponse`, matched in `frontend/src/lib/api/connections.ts` (api-contract-parity). Meta connect flow now probes `/debug_token` after token validation to capture the real `token_expires_at` (never-expiring → NULL; `debug_token` failure logged, does not break connect) — `backend/app/api/v1/endpoints/connections.py`. Added `META_APP_ID` / `META_APP_SECRET` settings — `backend/app/config.py`. Tests: `backend/tests/test_notifications.py` (dedup idempotency, resolve, tenant isolation on list + read, no-emit-from-GET). `docs/backend-api-spec.md`.
- **`notifications` table + connection-health columns (schema for token-expiry alerting, Piece 2).** New `Notification` model (`backend/app/models/notifications.py`) for `token_expiring` / `token_expired` / `refresh_failed` / `sync_failed` alerts — tenant-scoped (`organization_id` FK, `ON DELETE CASCADE`), with a stored `deep_link` column (never inferred from message text) and a composite `UNIQUE (organization_id, dedup_key)` (`uq_notifications_org_dedup`) as the DB-level dedup mechanism (anti-req §2.3: dedup is a DB unique constraint, not an app-side time window — emission upserts `ON CONFLICT DO NOTHING`). Index `ix_notifications_org_status` on `(organization_id, status)` for the unread-count query. Also added `last_error` / `last_error_at` to `platform_connections` (`backend/app/models/platform.py`) for connection health (status derived from `token_expires_at` + `last_error`, no enum column). Migration `backend/migrations/versions/e9f0a1b2c3d4_add_notifications_and_connection_health.py` (head `e9f0a1b2c3d4`, down_revision `d8e9f0a1b2c3`). Schema only — endpoints/service/worker emission land separately. `docs/internal-schema-spec.md`.
- **Login rate limiting (anti-brute-force).** `POST /auth/login` previously had zero throttle on failed attempts. Now redis-backed with two independent gates over a rolling 15-minute window — per-account (default 5 failures for one email) and per-IP (default 20, catches credential spraying across many emails from one source). Either exceeded → `429` *before* the password is checked; a successful login clears the per-account counter, the per-IP counter is left to expire. Source IP from `X-Forwarded-For` first hop (proxied hosts like Railway) else socket peer. Tunables `LOGIN_MAX_ATTEMPTS_PER_ACCOUNT` / `LOGIN_MAX_ATTEMPTS_PER_IP` / `LOGIN_LOCKOUT_WINDOW_SECONDS`. `backend/app/services/auth.py`, `backend/app/api/v1/endpoints/auth.py`, `backend/app/config.py`. Tests: `backend/tests/test_auth_password_and_rate_limit.py`.

### Changed
- **Worker token-alert dedup-key definition centralized (P-7, workers-sync).** `backend/workers/token_alerts.py` no longer declares its own local `token_dedup_key(...)` or a hard-coded alert-type tuple — it now imports `token_dedup_key` and `TOKEN_ALERT_TYPES` from `app/services/notifications.py` (the canonical single source of truth the backend established) and uses `TOKEN_ALERT_TYPES` as the default `notif_types` in `clear_token_failure`. Prevents the emit path and the clear path from drifting out of alignment. No behavior change (values are identical); the local copies were removed. Grep confirmed nothing imported the local `token_dedup_key` from `token_alerts` (tests already use the `app.services.notifications` one).
- **TikTok/Google token failures now emit a durable alert instead of failing silently (Piece 2 emission).** TikTok refresh (`backend/workers/tasks/tiktok_token_refresh.py`) previously set `is_active=False` on refresh failure with no user-facing signal — it now also stamps `last_error`/`last_error_at`, creates a deduped `token_expired` notification, and emails the org owner once (keeping the existing deactivation), and on a successful refresh clears health + resolves the alert (P-2). Google (`backend/workers/google_client.py` + `google_structure`/`google_insights`/`google_breakdowns` tasks) now classifies authentication/authorization failures: `GoogleAdsClientError` gained an `is_auth` flag set in `_wrap` from the gRPC status (`UNAUTHENTICATED`/`PERMISSION_DENIED`) and the typed `AuthenticationError`/`AuthorizationError` GAQL error codes, plus `search` catches google-auth `RefreshError` (invalid_grant: refresh token expired/revoked) and re-raises it as an auth error. Each Google sync task's `except GoogleAdsClientError` block raises a durable token-failure alert (via `workers.token_alerts.alert_connection_token_failure`) when `is_auth` — additive to, not a swallow of, the existing `sync_job` failure + retry. `google_creatives` is a no-op enrichment (no client call) so needs no wiring. All emission goes through the one writer (`app/services/notifications.py`, P-7); dedup key `token_expired:{connection_id}`; email gated on newly-created. `docs/sync-worker-spec.md`.
- **Password complexity now enforced.** Signup, reset-password, and accept-invite previously required only length ≥8. Passwords must now also contain a lowercase letter, an uppercase letter, and a digit — one shared validator (`backend/app/schemas/auth.py::validate_password_strength`) applied across all three schemas (`schemas/auth.py`, `schemas/org.py`), returning `422` on violation. Mirrored client-side for inline feedback (`frontend/src/lib/validation.ts::passwordSchema`) in the signup/reset-password/accept-invite forms. `docs/backend-api-spec.md`.

### Fixed
- **Meta insights and structure sync deadlocked on rate-limited accounts — insights burned the app quota structure needed, so structure never populated `campaigns` and every insights run failed (workers-sync).** On a busy shared Meta app, `sync_structure_for_account`'s up-front `apply_backoff` tripped the `SOFT_PCT` (80%) app-usage gate and finalized `skipped`, so `campaigns`/`ad_groups`/`ads` stayed empty — while `sync_insights_for_account` still fetched campaign + per-campaign adset/ad insights (50-sub-request batches) and only *then* raised `RuntimeError` on the empty `adgroup_map`/`ad_map`. That doomed run drained the exact app quota structure needed to complete: a livelock (insights drains quota → structure skips → maps stay empty → insights fails), observed in prod as `structure` = 16 skipped / 0 completed and `insights_daily` = 15 failed with `adgroup_map empty but Meta returned N adset rows`. `sync_insights_for_account` now bails **before constructing `MetaClient` / any API call** when the account has no campaigns: if a `structure` job has already `completed` it returns cleanly (account genuinely has 0 campaigns — nothing to sync, no failed job); otherwise it triggers `sync_structure_for_account.delay(...)` and defers without touching Meta (structure re-kicks insights on completion via `structure.py`, and the 15-min beat is a backstop). The pre-existing `adgroup_map`/`ad_map` empty-guard `RuntimeError`s are kept as a safety net for the rarer campaigns-present-but-adsets-lagging case. `backend/workers/tasks/insights.py`. Tests: `backend/tests/test_insights_structure_guard.py` (no campaigns + structure never done → no Meta call, no insights job, structure triggered; no campaigns + structure done → clean return, structure NOT re-triggered; campaigns present → guard passes through to Phase-2 job creation). `docs/sync-worker-spec.md`.
- **A recurring failure went silent after recovery — a resolved notification was never re-opened (backend).** `create_notification` upserted `ON CONFLICT (organization_id, dedup_key) DO NOTHING`, so once a token alert was resolved (by a reconnect or a successful sync) the row persisted in `status='resolved'` and a genuinely-recurred failure hit the conflict and did nothing — no re-alert, no re-email (P-2 alarm-when-not-fine / P-8 trace-reflects-reality violation, and now reachable precisely because we added resolve-on-recovery paths). Changed to `ON CONFLICT DO UPDATE … WHERE status='resolved'`: a resolved row is re-opened (`status='unread'`, `resolved_at` cleared, title/body/severity/`deep_link`/`created_at` refreshed) while an already-open (`unread`/`read`) row is left untouched — still never dupes, and a `read` row is not bounced back to `unread` on every failing cycle. The return `SELECT` uses `populate_existing=True` so a re-opened identity-map row reflects its new DB state (the email gate's `is_new` check then correctly re-emails on a true recurrence). `backend/app/services/notifications.py`. Tests: `backend/tests/test_notifications.py` (`test_recreate_after_resolve_reopens_same_row`, `test_recreate_while_open_does_not_dupe_or_reset`). `docs/backend-api-spec.md`, `docs/sync-worker-spec.md`.
- **A successful sync did not clear a connection's open token alert — only a nightly refresh or a reconnect did (workers-sync).** The Meta/TikTok/Google sync tasks CREATE a `token_expired` alert on an `is_auth` failure but never resolved it on recovery, so after a transient auth blip (or a reconnect that the refresh task hadn't yet re-probed) the badge/banner stayed lit until the next nightly refresh success — a permanently-lit warning while data was actually flowing again (P-2 violation). Every platform sync task's SUCCESS/completion path now calls the new `workers.token_alerts.clear_connection_token_failure(connection_id)`, which opens its own committed txn, re-fetches the `PlatformConnection`, and — ONLY when `last_error is not None` (guard: a healthy connection skips the resolve query every cycle) — funnels through `clear_token_failure` to resolve the connection's open `token_expired`/`token_expiring`/`refresh_failed` notifications and wipe `last_error`/`last_error_at`. Goes through the one writer (`app/services/notifications.py`, P-7); swallows + logs its own errors so clearing can never fail a sync that otherwise succeeded (mirrors the `alert_connection_token_failure` funnel). Wired at: `backend/workers/tasks/insights.py` (insights_daily + breakdown), `structure.py` (structure + account import), `async_jobs.py` (fetch/finalize); `tiktok_insights.py`, `tiktok_structure.py` (structure + account import), `tiktok_breakdowns.py`; `google_structure.py` (structure + account import), `google_insights.py`, `google_breakdowns.py`. Tests: `backend/tests/test_meta_token_alert_clear.py` (successful sync resolves an open alert + clears `last_error`; healthy connection is a no-op; helper swallows its own errors). `docs/sync-worker-spec.md`.
- **Reconnecting a platform did not clear its token-expiry alert — only a successful refresh did (backend).** A stale/expired token alert stayed lit after the user re-pasted a Meta token or re-ran TikTok/Google OAuth: the alert only cleared when the nightly *refresh* task succeeded, and reconnect INSERTs a brand-new `PlatformConnection` (no unique constraint on `(organization_id, platform_id)`), so the old alert's dedup key (`{type}:{OLD_connection_id}`) never matched the new connection. Reconnect now resolves token alerts at the **org+platform** level (P-2): `resolve_platform_token_alerts(db, org_id, platform)` finds every `PlatformConnection` for that org+platform (old dead rows included), resolves each one's `token_expired`/`token_expiring`/`refresh_failed` notifications, and clears `last_error`/`last_error_at`. Wired into `POST /api/v1/connections` (Meta, after the validated token commits), the TikTok OAuth callback (`platform="tiktok"`), and the Google OAuth callback (`platform="google_ads"` — the stored `platform_id`, not the `"google"` URL label) — only on SUCCESS, never when validation/OAuth failed. The canonical `token_dedup_key(type, connection_id)` and `TOKEN_ALERT_TYPES` now live in `app/services/notifications.py` as the single source of truth (P-7) for the worker path to import. `backend/app/services/notifications.py`, `backend/app/api/v1/endpoints/connections.py`. Tests: `backend/tests/test_notifications.py` (resolve-all-classes; multi-connection org+platform clear; tenant + platform isolation; no-open-alert no-op; dedup-key export). `docs/backend-api-spec.md`.
- **Meta/TikTok sync tasks emitted no token-expiry alert on auth failure — only Google did (workers-sync).** A dead Meta/TikTok access token during a normal *sync* (not refresh) produced failed `sync_jobs` with ZERO notifications and empty `last_error`: the alert funnel was wired into the Google sync tasks + the Meta/TikTok *refresh* tasks, but never the Meta/TikTok *sync* tasks — and the Meta refresh task can't catch a NULL-expiry manual-paste connection (its query filters `token_expires_at IS NOT NULL`), so a dead Meta token fell through every alert path. Added an `is_auth` classifier to `MetaAPIError` (`backend/workers/meta_client.py`: code `190`/`102` or OAuth subcodes `458,459,460,463,464,467,492`) and `TikTokAPIError` (`backend/workers/tiktok_client.py`: code `40100` invalid / `40101` expired / `40200` permission-denied, per `docs/tiktok-api-dashboard-contract.md` §10), mirroring `GoogleAdsClientError.is_auth`. Every Meta sync task's `except MetaAPIError` block (`insights.py` insights_daily + breakdown paths, `structure.py` structure + account-import, `async_jobs.py` submit + poll + fetch paths) and every TikTok sync task's `except TikTokAPIError` block (`tiktok_insights.py`, `tiktok_structure.py` structure + account-import, `tiktok_breakdowns.py`) now calls `workers.token_alerts.alert_connection_token_failure(connection_id, platform_label=..., detail=...)` when `is_auth` — additive to (not a swallow of) the existing `finalize_sync_job(..., "failed")` + retry, and gated on `is_auth` only so rate-limit "skipped"/transient errors never cry wolf (P-2). `connection_id` is the value already resolved from the account's `platform_connection_id` in each task's read phase (hoisted to `None` before the `try` in the TikTok tasks so it's in scope for the `except`). Dedup key stays per-connection (`token_expired:{connection_id}`), so a 15-min failure storm collapses to one notification + one email (P-7). Tests: `backend/tests/test_meta_token_alerts.py` (Meta/TikTok `is_auth` classifier tables; Meta + TikTok account-import auth failure → `token_expired` + `last_error`; non-auth error → no notification). `docs/sync-worker-spec.md`.
- **Google account-import auth failures produced no token alert (workers-sync).** `sync_google_accounts_for_connection` (`backend/workers/tasks/google_structure.py`) only logged/retried on `GoogleAdsClientError`, unlike the other three Google sync paths — yet account import is the *first* Google call to run against a connection, so an expired/revoked grant surfaces here first and left no notification/`last_error`/email. Its `except` now calls `workers.token_alerts.alert_connection_token_failure(...)` when `exc.is_auth` (same args/message style as `google_structure`/`google_insights`/`google_breakdowns`), additive to the existing log + retry. Test: `backend/tests/test_google_sync.py::test_account_import_auth_failure_alerts`.
- **Meta token refresh mislabeled infra errors as token failures and stalled the retry (workers-sync).** `refresh_meta_tokens` (`backend/workers/tasks/meta_token_refresh.py`) caught `(MetaAPIError, Exception)`, so any error (DB down, decrypt misconfig) stamped `last_error`, created a `token_expired` notification, and emailed the owner even though the token was fine (P-2 violation) — and `self.retry` was dead code. Narrowed the token-failure `except` to exchange-shaped errors only (`MetaAPIError`, `httpx.HTTPError`, `ValueError`); genuinely unexpected errors now fall through to `self.retry(exc=...)` so Celery's configured backoff engages and no false warning is lit. TikTok's pre-existing identical pattern left untouched (out of scope). Tests: `backend/tests/test_meta_token_refresh.py::test_infra_error_does_not_stamp_last_error_or_notify`.
- **Meta refresh re-exchanged non-expiring tokens every night (workers-sync).** `token_expires_at` was only updated `if expires_in:`, so a successful `fb_exchange_token` that omits/zeros `expires_in` (Meta treating the token as non-expiring) stored the new token but kept the old near-expiry timestamp — leaving the connection inside the 7-day window and re-exchanging it on every nightly run (unbounded repeat work). A successful exchange with falsy `expires_in` now sets `token_expires_at = None` (never-expires → skipped by the refresh query's `token_expires_at IS NOT NULL` guard), with a dedicated log line. `backend/workers/tasks/meta_token_refresh.py`. Test: `backend/tests/test_meta_token_refresh.py::test_success_no_expires_in_nulls_expiry_and_not_reselected`.
- **Logo (and all `public/` static assets) rendered as a broken image when logged out** — the auth proxy's `matcher` (`frontend/src/proxy.ts`) excluded `_next/*` and `favicon.ico` but not extension-bearing paths, so an unauthenticated request for `/logo.svg` (from `<img>` in `AuthShell`) matched the guard, found no JWT cookie, and 307-redirected to `/login` — returning HTML instead of the SVG. Added `.*\..*` to the matcher exclusions so any path with a file extension is served directly. `frontend/src/proxy.ts`, `docs/frontend-spec.md`.
- **Meta UNSETTLED/pending ad accounts were hidden and never synced** — `META_ACCOUNT_STATUS_MAP` mapped Meta `account_status` 3 (UNSETTLED), 7 (PENDING_RISK_REVIEW), and 8 (PENDING_SETTLEMENT) to `"disabled"`, so these accounts vanished from all reads and were excluded from every sync task. Data for these accounts is still readable on Meta's side. They now map to a new visible-but-flagged `"unsettled"` bucket, and the unknown-status default flipped from `"disabled"` to `"unsettled"` so an unrecognized status never silently hides an account (P-2/P-4). All worker sync gates changed from `account_status == "active"` to `account_status != "disabled"` so `"unsettled"` accounts get insights/breakdowns/structure synced (no-op for TikTok/Google, which only ever store `"active"`/`"disabled"`). `backend/workers/tasks/structure.py`, `backend/workers/tasks/insights.py`, `backend/workers/tasks/async_jobs.py`, `backend/workers/tasks/google_structure.py`, `backend/workers/tasks/google_insights.py`, `backend/workers/tasks/google_breakdowns.py`, `backend/workers/tasks/tiktok_structure.py`, `backend/workers/tasks/tiktok_insights.py`, `backend/workers/tasks/tiktok_breakdowns.py`

### Changed
- **Auth pages redesigned to match the dashboard.** All six `(auth)` pages now share a new `AuthShell` (`frontend/src/components/auth/auth-shell.tsx`) — a single floating rounded card on the light-gray canvas whose left half unfolds the indigo sidebar rail (same `bg-sidebar` surface, logo lockup, iris signature gradient + value highlights), hidden below `lg` in favor of a compact brand lockup above the form. Replaces the old centered-`Card`-with-logo-above layout and drops the per-page `Card`/`CardHeader` boilerplate. Password inputs gained a show/hide eye toggle. `frontend/src/app/(auth)/{login,signup,forgot-password,reset-password,accept-invite,verify-email}/page.tsx`, `docs/frontend-spec.md §5`
- **Meta insights sync: per-campaign batch API** — replaced N×4 sequential `get_insights` calls (one per campaign per level/uniqueness combo) with Meta batch API, capped at 50 sub-requests per round-trip. 50 active campaigns: 200 HTTP calls → 4. `apply_backoff` now fires once per batch chunk instead of once per call (−75% Redis round-trips). Batch sub-request errors (permission denied, deleted campaign, etc.) are now isolated — a bad campaign logs a warning and is skipped instead of aborting the whole task; rate-limit errors in sub-responses still pause the connection and reschedule. `backend/workers/tasks/insights.py`, `backend/workers/meta_client.py`
- **TikTok insights sync: early staleness check** — `_is_stale` now runs before lock acquisition and job creation. Fresh accounts (most accounts, most beat cycles) exit with 1 DB read instead of lock + 2 DB writes + 1 DB read. `backend/workers/tasks/tiktok_insights.py`

### Added
- **TikTok GMV Max (Ads) view — built but PARKED pending requirements.** The view + route
  (`/tiktok/gmv-max`) exist but are **not surfaced** in the tab bar or the `/tiktok` landing (removed
  from `PLATFORM_TABS.tiktok`; `/tiktok` redirects to overview) — most ads accounts lack the
  onsite/shop-conversion data the shop KPIs need, so it waits on real requirements (and likely TikTok
  Shop Open API integration). Re-enable = re-add the tab slug + redirect.
  `frontend/src/components/views/gmv-max-view.tsx` composes five KPI tiles (Cost `spend`,
  Gross Revenue `web_purchase_value`, Orders `web_purchases`, Cost per Order `cost_per_web_purchase`,
  ROAS `roas_shop`, each with a cost-inverted `DeltaPill`), the shared `PeriodicView` trends, and a
  `<TableView platformObjective="PRODUCT_SALES" />` campaign table — all scoped to GMV Max campaigns
  so KPIs and table match by construction (P-6/P-7). A `TikTokModeSwitch`
  (`frontend/src/components/layout/tiktok-mode-switch.tsx`) shows **TikTok Ads · TikTok Shop 🔒 · Ads ×
  Shop 🔒** — Shop/Combined render **locked** (their TikTok Shop Open API data isn't integrated;
  fabricating numbers would violate P-1/P-4). Mockup's "Net cost" / separate "ROI" omitted (no backing
  data, P-4). Docs: `docs/frontend-spec.md`, `docs/tiktok-api-metrics-reference.md`.
- **`platform_objective` on the insights table + GMV Max filter.** `GET /insights/table` now returns
  each campaign row's raw `platform_objective` (e.g. `PRODUCT_SALES`) alongside the normalized
  `objective`, and accepts an optional `platform_objective` filter (campaign level; neutralized at
  ad-group/ad). `GET /insights/overview` accepts the same filter so its KPIs scope to the same
  GMV-Max campaigns (P-6). Backend: `backend/app/schemas/insights.py` (`TableRow.platform_objective`),
  `backend/app/services/insights.py` (`get_table`, `get_overview`, `_resolve_campaign_ids`),
  `backend/app/api/v1/endpoints/insights.py`. Frontend: `frontend/src/lib/api/insights.ts`,
  `frontend/src/lib/query-keys.ts`. Tests: `backend/tests/test_insights_table_gmv_max.py` (filter
  scoping on table + overview, `platform_objective` surfaced, tenant-isolation 403). Docs:
  `docs/backend-api-spec.md`.
- **TikTok engagement / interactive / LIVE metrics synced + surfaced.** The four
  previously-deferred TikTok metrics now land end-to-end. The sync worker stores them in
  `metric_action_stats` under internal `(field_name, action_type)` keys: `engagements` →
  (`engagement`), `ix_product_click_count` → (`product_click`), `live_effective_views` →
  (`live_view`), `live_product_clicks` → (`product_click`). The read layer
  (`backend/app/services/insights.py`) pivots four new summable-count columns out of
  `metric_action_stats` — `total_engagement`, `product_clicks_ix`, `live_views_10s`,
  `live_product_clicks` (all registered in `_ACTION_INT_KEYS`; raw counts, no derived ratio). The
  four fields are exposed on `MetricsSummary`, `TimeSeriesPoint`, and `TableMetrics` in
  `backend/app/schemas/insights.py`. No DB migration (`metric_action_stats` is generic). Frontend
  registry + `insights.ts` and read-layer tests pending (hand off to frontend + testing).
- **TikTok onsite/shop insights — onsite-family metrics synced.**
  `backend/workers/tasks/tiktok_insights.py` requests TikTok's ONSITE family
  (`onsite_*`, `total_onsite_*`, `ix_*`) — the correct "(Shop)"/"(Onsite)" fields, **not** the
  pixel-web `page_event_*` family — in the graceful-fallback `EVENT_METRICS` tier (dropped
  automatically if the advertiser has no TikTok Shop / onsite tracking, so a rejected field can't
  break the core request), plus `average_video_play_per_user` (video tier, next to
  `average_video_play`). `TIKTOK_ACTION_MAP` stores each into `metric_action_stats` under
  unchanged internal `(field_name, action_type)` keys: `ix_page_view_count` →
  (`page_events`, `page_view`), `onsite_on_web_cart` → (`page_events`, `add_to_cart`),
  `total_onsite_on_web_cart_value` → (`page_event_values`, `add_to_cart`),
  `onsite_initiate_checkout_count` → (`page_events`, `checkout`),
  `total_onsite_initiate_checkout_count_value` → (`page_event_values`, `checkout`),
  `onsite_shopping` → (`page_events`, `purchase`),
  `total_onsite_shopping_value` → (`page_event_values`, `purchase`),
  `average_video_play_per_user` → (`average_video_play_per_user`, `video_view`).
  No DB migration (`metric_action_stats` is generic). Read-layer pivot + tests pending.
  Docs: `docs/sync-worker-spec.md`, `docs/tiktok-api-metrics-reference.md`.
  Deferred: `clicks_all`, `interactive_addon_destination_clicks`, `live_views`, `live_product_clicks`
  — exact TikTok API field names unverified, pending validation against a live account.
- **TikTok onsite/shop insights — read layer surfaces the synced page-event / video metrics.**
  `backend/app/services/insights.py` pivots four new columns out of `metric_action_stats`:
  `page_view_onsite` (`page_events`/`page_view`, count), `web_add_to_cart_value`
  (`page_event_values`/`add_to_cart`), `web_checkout_value` (`page_event_values`/`checkout`), and
  `avg_watch_time_per_user` (`average_video_play_per_user`, AVG — averaged not summed, P-4). Two
  computed ratios derived after aggregation (never stored, P-7): `roas_shop`
  (`web_purchase_value` ÷ spend) and `cost_per_web_checkout` (spend ÷ `web_checkout`). The six new
  fields are exposed on `MetricsSummary`, `TimeSeriesPoint`, and `TableMetrics` in
  `backend/app/schemas/insights.py`. Frontend registry + `insights.ts` and read-layer tests pending
  (hand off to frontend + testing).
- **TikTok onsite/shop metrics wired into the frontend.** `METRIC_REGISTRY`
  (`frontend/src/lib/metrics.ts`) gains 6 TikTok rows (`page_view_onsite`, `web_add_to_cart_value`,
  `web_checkout_value`, `avg_watch_time_per_user`, `roas_shop`, `cost_per_web_checkout`) and relabels
  the existing web-event rows to "(Shop)" naming. Overview cards are now platform-aware
  (`frontend/src/components/views/overview-view.tsx`): `OVERVIEW_CARDS` is keyed by platform then
  account type with a `getOverviewCards(platform, accountType)` resolver that falls back to Meta —
  TikTok renders two cards (Cost + ROAS (Shop)); Meta standard/cpas layouts unchanged. The TikTok
  funnel (`frontend/src/lib/constants.ts`) switches to the onsite/shop path (page views → ATC →
  checkout init → purchase). `CardSpec` gains an optional per-card `labels` override map
  (`buildSubMetrics` uses `labels?.[k] ?? metricLabel(k)`); the TikTok Cost + ROAS (Shop) cards use it
  to match the reference dashboard's exact wording (e.g. "Clicks (destination)", "(Shop)" conversions)
  without changing the shared global registry labels. `CardSpec` also gains an opt-in `fillAbsent`
  flag — an **intentional per-card deviation from P-2** used only by the two TikTok cards — so they
  render their full metric grid with `0` placeholders (`IDR 0`/`0`/`0%`/`0.00x`) instead of collapsing
  to a "No data" state when values are absent; Meta/CPAS cards keep hiding absent metrics. The funnel
  (`frontend/src/components/views/funnel-view.tsx`) now renders every configured step as a labeled
  zero-height bar when values are absent (divide-by-zero guarded → `—`) instead of a "No funnel data"
  message — a fallback message shows only when no steps are defined at all. Docs: `docs/frontend-spec.md`.
- **Per-member account access (frontend) — owner assignment UI + member empty states.** Settings →
  Members gains an owner-only **Manage access** action per member row
  (`frontend/src/components/settings/manage-access-dialog.tsx`): a modal listing all org accounts
  grouped by platform with checkboxes, pre-seeded from `GET /org/members/:id/accounts`, saving the
  full set via `PUT`. Owner rows show "All accounts". Members with no grants now see role-aware "No
  accounts assigned to you" copy in the account switcher
  (`frontend/src/components/shared/account-switcher.tsx`) and overview
  (`frontend/src/components/views/overview-view.tsx`) instead of the owner's "connect an account"
  prompt. `memberAccounts`/`setMemberAccounts` added to `frontend/src/lib/api/org.ts`. No switcher/
  dashboard fetch changes needed — backend scoping filters automatically. Docs: `docs/frontend-spec.md`.
- **Per-member account access (backend) — members see only owner-granted accounts.** New
  `membership_accounts` allowlist table (migration `d8e9f0a1b2c3`, model in
  `backend/app/models/auth.py`): one row grants a membership access to one account; owners are
  unrestricted (no rows), members see only granted accounts, **no row = no access** (new members and
  newly-synced accounts are not auto-granted). Single resolver
  `accounts.get_accessible_account_ids(db, current_user)` (owner → `None` sentinel = unrestricted;
  member → grant set) drives all three enforcement chokepoints:
  `assert_account_belongs_to_org(..., allowed_ids=)` (single-account reads: `/insights/*` via the
  shared `_resolve_dates`/`_resolve_combined_dates`, `/ads`, `/adgroups`, `/campaigns`,
  `GET /accounts/:id`), `list_accounts(..., restrict_ids=)` (the account switcher), and the combined
  dashboard's "all accounts" default. Ungranted account → `403`. `PATCH /accounts/:id/config` is now
  **owner-only** (`OwnerUser`). Owner grant API: `GET /org/members/:membership_id/accounts` and
  idempotent `PUT` (validates ids belong to the org → `403` otherwise; owner target → `409`). Refs:
  `backend/app/services/accounts.py`, `backend/app/services/org.py`, `backend/app/schemas/org.py`,
  `backend/app/api/v1/endpoints/{org,accounts,insights,ads,adgroups,campaigns}.py`. Tests:
  `backend/tests/test_account_access.py` (10 — resolver, assert/list scoping, grant replace,
  cross-org rejection, owner-can't-be-scoped, insights-resolver enforcement). Frontend
  (manage-access UI + member empty states) handled separately. Docs: `docs/backend-api-spec.md`,
  `docs/internal-schema-spec.md`.

### Changed
- **Accounts settings paginate on mobile.** Page size is now viewport-aware (8 rows on phones vs 20
  on desktop) via a new `useIsMobile` hook (`frontend/src/hooks/use-is-mobile.ts`), so the list
  actually paginates on a narrow screen instead of scrolling one long page; `page` resets on a
  breakpoint cross. `PaginationBar` also collapses its numbered pages to a compact `page / total` +
  arrows below `sm`. `frontend/src/app/settings/accounts/page.tsx`,
  `frontend/src/components/shared/pagination-bar.tsx`, `frontend/src/lib/query-keys.ts`
  (`accountsList` key now includes `perPage`).
- **Sync/freshness badge surfaced on mobile.** The top-bar `SyncStatusBadge` is `hidden md:block`, so
  on phones it vanished entirely — dropping the freshness signal every number must carry (P-1). Added an
  opt-in `freshness` prop to the shared `SectionHeading` that renders a `md:hidden` `SyncStatusBadge`
  beneath the subtitle; enabled on `OverviewView`'s primary heading so freshness shows under the page
  title on mobile. `frontend/src/components/shared/section-heading.tsx`,
  `frontend/src/components/views/overview-view.tsx`. Docs: `docs/frontend-spec.md`.
- **Dashboard shell is now responsive on narrow screens.** Below `md` the indigo sidebar rail
  (previously always in-flow, squeezing the content canvas to a sliver on phones) is `hidden md:flex`
  and replaced by `MobileSidebar` — an off-canvas drawer (shadcn `Sheet`, `side="left"`, backed by a
  new ephemeral `mobileNavOpen` UI-store flag) opened from a `md:hidden` hamburger in the top bar and
  closed on backdrop tap / route change / nav tap. The drawer borrows the ad-detail drawer's
  detached-card shape (inset + rounded + own close button) while keeping the indigo rail background;
  both drawers use a near-full-width `w-[calc(100%-1.5rem)]` on mobile. The content column drops its left margin below `md` so it spans full width. Top bar collapses
  redundant chrome on mobile (platform badge/title, freshness, notification bell hide `<sm`; account
  switcher `w-40 sm:w-56`); the control-strip view tabs scroll horizontally instead of hiding.
  The date-range picker moves from the top bar into the control strip below `sm` so the account
  name no longer collides with it. Overview content de-clipped on narrow screens: `SegmentControl`
  scrolls horizontally when it overflows (Breakdown tabs), funnel rows use responsive label/value
  widths + wrapping connectors, KPI sub-metric grid tightens its gap/padding and truncates long
  currency, and the Trends chart's Y-axis ticks use a new compact currency formatter
  (`formatMetricCompact` / `formatCurrencyCompact` — "IDR 280K") so long currency labels aren't cut
  (tooltips keep full precision).
  `frontend/src/components/layout/{sidebar,top-bar,control-strip}.tsx`,
  `frontend/src/app/(dashboard)/layout.tsx`, `frontend/src/stores/ui-store.ts`,
  `frontend/src/components/shared/account-switcher.tsx`,
  `frontend/src/components/ui/segment-control.tsx`,
  `frontend/src/components/views/funnel-view.tsx`,
  `frontend/src/components/metrics/metric-group-card.tsx`,
  `frontend/src/components/views/periodic-view.tsx`. Docs: `docs/frontend-spec.md`.
- **Combined summary (`/dashboard`) restyled to match the platform Overview.** Replaced the
  legacy bento canvas (giant greeting hero + per-KPI sparkline tiles) with the shared section
  structure: a `SectionHeading` lead per section, a full-width Combined spend chart, and a grouped
  **Combined KPIs** card. Added `frontend/src/components/shared/section-heading.tsx` (extracted from
  `overview-view.tsx`) and `frontend/src/components/summary/combined-kpi-card.tsx`. Combined KPI delta
  badges now gate on the Compare toggle (`?compare=true`, P-2) instead of always showing.
  Docs: `docs/frontend-spec.md`.
- **Unified every dashboard card onto one primitive; removed card hover motion.** Added
  `frontend/src/components/shared/dash-card.tsx` (`DashCard`) and
  `frontend/src/components/shared/card-chip-header.tsx` (`CardChipHeader`) as the single card surface +
  header used everywhere. `DashCard` has **no hover lift / shadow swap** (matching the platform cards —
  the old behavior read as noisy); `MetricGroupCard` and `CombinedKpiCard` are now built on it. Deleted
  the legacy `BentoTile` (`bento/bento-tile.tsx`), `MetricCard` (`metrics/metric-card.tsx`), and the
  orphaned `bento/greeting-tile.tsx` + `bento/metric-tile.tsx`; removed the unused `hoverLift` motion
  (`lib/motion.ts`); moved `geo-tile.tsx` into `components/shared/` (the `bento/` dir is gone). Migrated
  the TikTok **Engagement** page (`app/(dashboard)/tiktok/engagement/page.tsx`) off `MetricCard` — its 8
  KPI sparkline tiles are now one grouped `MetricGroupCard` + a `DashCard` trend chart, matching the
  platform Overview. Docs: `docs/frontend-spec.md`.

### Fixed
- **TikTok "Last month" + compare came back empty while Meta worked — historical backfill only reached 30 days.**
  The TikTok `insights_historical` job was dispatched `last_30d`, so on any given day the backfill covered
  ~30 days back. "Last month" plus its prior-period compare (the month before) needs ~2 full months of
  history — the compare month (e.g. June when viewing July) fell entirely outside the window, so compare
  data was missing. Meta's 90-day async backfill covered it, hence the platform asymmetry. Added a
  `last_90d` preset to the TikTok resolver and switched the historical job to it, matching Meta's window.
  TikTok rejects any `stat_time_day` report wider than 30 days ("max time span is 30 days when use
  stat_time_day"), so the 90-day backfill is split into contiguous ≤30-day chunks (`_date_chunks`) and
  fetched per window, merging the rows (`backend/workers/tasks/tiktok_insights.py`,
  `backend/workers/tasks/tiktok_structure.py`, `backend/app/services/sync.py`). Also added
  `insights_historical` to `DEFAULT_JOB_TYPES["tiktok"]` so a manual `/sync/trigger` (bare `{account_id}`)
  backfills history, not just the 7-day daily window.
  Tests: `backend/tests/test_tiktok_historical_window.py` (window spans compare range; chunks ≤30d,
  contiguous, full-cover; 30d regression guard).
  Docs: `docs/sync-worker-spec.md`.
- **Combined spend chart on `/dashboard` looked broken — clipped Y-axis + rainbow stroke.** The hero
  chart bled to the card edge (`px-1` body) so its Y-axis tick labels were cut off, used a 3-stop iris
  rainbow stroke, and a cramped 180px height. Rebuilt it from the shared chart theme to match the
  platform trend charts: `seriesColor(0)` solid stroke + single-hue `gradientDef` fill, 64px Y-axis,
  padded body, 300px height (`frontend/src/app/(dashboard)/dashboard/page.tsx`). Docs:
  `docs/frontend-spec.md`.
- **TikTok `PRODUCT_SALES` objective mislabeled as `awareness`.** `TIKTOK_OBJECTIVE_MAP`
  (`backend/workers/tasks/tiktok_structure.py`) had no entry for `PRODUCT_SALES` — the raw
  objective_type TikTok's Business API returns for the Product GMV Max / Shop-sales family — so it
  fell through to the `"awareness"` default, normalizing every shop campaign to `awareness`. Added
  `PRODUCT_SALES` → `sales` (and an explicit `BRAND_CONSIDERATION` → `awareness`). Takes effect on the
  next structure sync; the raw `platform_objective` (used by the GMV Max view's filter) was already
  correct.
- **Table drill-down ignored `campaign_id`/`adgroup_id` — showed the whole account.**
  `get_table` accepted both params but never bound them, and `TABLE_SQL_ADGROUP`/`TABLE_SQL_AD` had
  no campaign/ad-group predicate, so clicking a campaign in Overview drilled into the Ad Groups level
  but returned *every* ad group in the account (other campaigns' rows included). Added the scoping
  clauses (`c.campaign_id = CAST(:campaign_id AS uuid)`, `c.ad_group_id = CAST(:adgroup_id AS uuid)`,
  NULL = no-op) and bound the params at the matching levels. Also wired the Overview preview
  campaign-name click (previously a no-op `() => {}` callback) to navigate to
  `/{platform}/table?level=adgroup&campaign_id=…`. Refs: `backend/app/services/insights.py`,
  `frontend/src/components/views/table-view.tsx`,
  `backend/tests/test_insights_drilldown_filter.py`.
- **Navbar user name/email silently blanked to "—".** Six components read the `queryKeys.me()` cache
  entry with two different `queryFn` shapes — some cached the full axios response, some the parsed
  `.data.data` body. TanStack keys one cache entry per key, so the value that won depended on mount
  order; when a full-response consumer (members page / the new `useIsOwner`) populated the cache
  first, the parsed consumers (`top-bar`, `header`, `greeting-tile`, `user-menu`) read `.name` off the
  wrong shape and got `undefined`. Introduced a single canonical `useMe()` hook
  (`frontend/src/hooks/use-me.ts`, one parsed shape) and routed all six consumers through it. Refs:
  `frontend/src/components/layout/{top-bar,header}.tsx`,
  `frontend/src/components/{shared/user-menu,bento/greeting-tile}.tsx`,
  `frontend/src/hooks/use-role.ts`, `frontend/src/app/settings/members/page.tsx`.
- **Accepted invitees got a synthetic `pending_*@pending.dashmet` email instead of their real
  address.** `accept_invite` created the user account with a `pending_{token}@pending.dashmet` stub
  (written before the invited email was stored anywhere). Now it uses the membership's `invite_email`
  (the synthetic form remains only as a fallback for legacy pre-`invite_email` invites); if an account
  with that email already exists (invited to a second org), the membership attaches to it rather than
  hitting the `users.email` unique constraint, leaving the existing name/password untouched. Refs:
  `backend/app/services/org.py`. Tests: `backend/tests/test_org_members.py`
  (`test_accept_invite_uses_real_invited_email`, `test_accept_invite_attaches_to_existing_account`).
- **Members saw owner-only settings controls as if they could use them.** The `/settings/*` pages
  rendered Save org / Delete organization / Invite member / remove-member / Connect / Disconnect with
  no role gating (the backend `403`s the mutations, but the UI gave no signal). Added `useIsOwner()`
  (`frontend/src/hooks/use-role.ts`, reads `GET /auth/me` → `org.role`); owner-only controls on the
  org, members, and connections settings pages are now **disabled** for members (locked, not hidden —
  visibility preserved) with an "Owner only" title, plus a `SettingsReadonlyBanner`
  (`frontend/src/components/shared/settings-readonly-banner.tsx`) under the settings nav. Backend
  authorization is unchanged — this is the matching UX. The `Sync now` recovery action on the sync
  status badge (`frontend/src/components/shared/sync-status-badge.tsx`) is locked the same way, since
  `POST /sync/trigger` is owner-only. Refs:
  `frontend/src/app/settings/{org,members,connections}/page.tsx`, `frontend/src/app/settings/layout.tsx`.

### Removed
- **"Delete organization" stub UI dropped from `/settings/org`.** The Danger-zone button was a no-op
  (no `DELETE /org` endpoint; `onClick` only closed the dialog) — misleading for owners and members
  alike. Removed the button, confirm dialog, and dead state rather than leaving a fake control. Refs:
  `frontend/src/app/settings/org/page.tsx`, `docs/frontend-spec.md`.

### Added
- **Member invites are now emailed (SMTP), with an accept-invite landing page** — previously an
  invite only wrote a token to the server log; the invitee had no way to receive or accept it.
  New `backend/app/services/email.py` (stdlib `smtplib`, no new dependency) sends the invite with a
  link to `{FRONTEND_URL}/accept-invite?token=…`. Delivery never gates the invite (P-8): the
  membership row is committed first, then the email is sent *after* commit — if SMTP is unconfigured
  (`SMTP_HOST` empty) the link is logged as a dev fallback, and if a configured server fails the error
  is logged; either way the invite exists and the `201` response now carries `email_sent: false` with
  honest message text (never a fake "sent"). SMTP config added to `backend/app/config.py` /
  `.env.example` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`,
  `SMTP_FROM_NAME`, `SMTP_USE_TLS`, `SMTP_USE_SSL`). `POST /org/members/invite` wires the send
  (`backend/app/api/v1/endpoints/org.py`). New public frontend page
  `frontend/src/app/(auth)/accept-invite/page.tsx` (name + password → `orgApi.acceptInvite` → sets
  auth cookie → `/dashboard`); `acceptInvite` added to `frontend/src/lib/api/org.ts`. Tests:
  `backend/tests/test_email_service.py` (dev fallback, STARTTLS+login send, configured-failure →
  `EmailError`). Docs: `docs/backend-api-spec.md`, `docs/frontend-spec.md`.

### Changed
- **Overview cards and funnel are now account-type-aware, with strict standard/CPAS separation.**
  `overview-view.tsx` replaces the flat `DELIVERY_KEYS`/`RESULT_KEYS`/`RESULT_HEADLINE` arrays with an
  `OVERVIEW_CARDS: Record<AccountType, CardSpec[]>` config keyed on the selected account's
  `accountType`: standard renders **three** cards (Spend / ROAS / a title-only **Post & Media** card),
  CPAS renders **two** (Spend / **ROAS Shared Item**). The config is keyed on account type so a
  standard account renders zero `*_shared` metrics and a CPAS account renders none of the standard
  ROAS/Post & Media set. `buildSubMetrics` presence-filtering, the `compare`/`previous` delta pills,
  and `See Detail → table` links are unchanged. `MetricGroupCard` (`metric-group-card.tsx`) now takes
  an optional `headline` — omitting it drops the big-number block (and its top border) for the
  title-only Post & Media card, so no fake headline number is forced (P-1/P-2). The standard
  **Post & Media** card is now **full-width** (`CardSpec.span: 2` → `lg:col-span-2`) with a 4-column
  inner sub-metric grid (`CardSpec.cols: 4` → `MetricGroupCard` `columns` prop →
  `grid-cols-2 lg:grid-cols-4`), so its 8 metrics form two rows of four and fill the row left empty
  by the odd third card (Spend + ROAS stay 2-up, CPAS layout unchanged). The funnel
  (`funnel-view.tsx`) resolves steps via the new `getFunnelSteps(platform, accountType)` in
  `constants.ts` (`META_FUNNEL_STEPS` keyed by account type): Meta standard uses
  `landing_page_views → add_to_cart → initiate_checkout → purchase`, Meta CPAS uses
  `content_view_shared → add_to_cart_shared → purchase_shared`; tiktok / google_ads funnels are
  unchanged. Refs: `frontend/src/components/views/overview-view.tsx`,
  `frontend/src/components/views/funnel-view.tsx`, `frontend/src/lib/constants.ts`,
  `frontend/src/components/metrics/metric-group-card.tsx`.
- **Ads detail sheet metric list is now registry-driven and account-type-aware.** `ads-view.tsx`'s
  `AdDetailSheet` replaces its hardcoded 11-row `metricRows` array with rows built from
  `usePlatformMetrics().tableMetricDefs` (the account-type-filtered ad-level `METRIC_REGISTRY` set),
  presence-filtered to the keys actually non-null in the ad's `metrics` (P-1/P-2 — no forced zeros)
  and formatted via the shared `metricLabel`/`metricType`/`formatMetric`. A standard account now shows
  standard metrics (incl. `add_to_cart_value`, `avg_basket_price`, `post_reactions`, `post_saves`,
  `comments`), a CPAS account shows the `*_shared` set — no cross-leak by construction. `AdMetrics`
  widened to an index signature (`[key: string]: number | null | undefined`, keys read directly in the
  card/row summaries kept explicit) — no `any` on the response type. Refs:
  `frontend/src/components/views/ads-view.tsx`.

### Fixed
- **Pending member invites were unaddressable — no email shown, couldn't be removed, and piled up
  as duplicates.** A pending invite creates a membership row with `user_id = NULL` (no account yet),
  but the invited email was never stored, `list_members` keyed the row id off the (missing) user, and
  `DELETE /org/members/{…}` + `remove_member` filtered on `user_id` — so pending rows surfaced with a
  null id (React key collision, dead remove button) and were impossible to delete. Added
  `organization_memberships.invite_email` (+ partial unique index
  `uq_membership_org_invite_email` on `(organization_id, invite_email) WHERE invite_email IS NOT NULL`)
  so pending invites store/display their address, dedup on repeat invite, and are removable by
  membership PK. `list_members` now returns `membership_id` (stable row id, always present) alongside
  the nullable user `id`; the delete route is keyed on `membership_id` with self-removal still guarded
  via the row's `user_id`. Refs: `backend/app/models/auth.py`,
  `backend/migrations/versions/c7d8e9f0a1b2_add_invite_email_to_memberships.py`,
  `backend/app/services/org.py`, `backend/app/schemas/org.py`,
  `backend/app/api/v1/endpoints/org.py`, `frontend/src/lib/api/org.ts`,
  `frontend/src/app/settings/members/page.tsx`. Test: `backend/tests/test_org_members.py`.

### Added
- **Meta CPAS shared-item (catalog-segment) metrics surfaced in the insights read layer** — the
  raw catalog-segment data already stored generically in `metric_action_stats` by the sync worker
  is now returned by the insights API (no worker change). `_ACTION_PIVOT_COLS` gained five FILTER
  columns — `purchase_shared`/`add_to_cart_shared`/`content_view_shared`
  (`catalog_segment_actions` × purchase/add_to_cart/view_content) and
  `purchase_value_shared`/`add_to_cart_value_shared` (`catalog_segment_value` × purchase/add_to_cart)
  — registered in `_ACTION_INT_KEYS`/`_ACTION_FLOAT_KEYS`; `_finalize_metrics` derives
  `cost_per_purchase_shared`, `cost_per_add_to_cart_shared`, `cost_per_content_view_shared`
  (spend ÷ count) and `roas_shared` (purchase_value_shared ÷ spend) after aggregation, never stored
  (same rule as ROAS/CPA, P-7) (`backend/app/services/insights.py`). The nine fields
  (`purchase_shared`, `add_to_cart_shared`, `content_view_shared`, `purchase_value_shared`,
  `add_to_cart_value_shared`, `cost_per_purchase_shared`, `cost_per_add_to_cart_shared`,
  `cost_per_content_view_shared`, `roas_shared`) added to `MetricsSummary`, `TimeSeriesPoint`, and
  `TableMetrics` (`backend/app/schemas/insights.py`). Frontend registry
  (`frontend/src/lib/metrics.ts`) + `insights.ts` types gain the same fields (handled separately).
  Test coverage pending (hand off to testing).
- **Insights metric registry surfaces the new Meta metrics in the overview/table/trends grids**
  (`frontend/src/lib/metrics.ts`). Standard: `add_to_cart_value`, `avg_basket_price`,
  `post_reactions` (Post Reaction), `post_saves` (Post Save), and `comments` (Post Comment, now
  rendered for Meta — previously TikTok-only). CPAS: the nine catalog-segment "Shared Item" rows
  (`purchase_shared` … `roas_shared`, `accountTypes:["cpas"]`), and `inline_link_clicks` (Link
  Clicks) extended to CPAS as well as standard. Registry-driven — cards adapt per platform/account
  type with no per-view wiring. Docs: `docs/frontend-spec.md`.
- **Meta CPAS shared-item (catalog-segment) conversions synced** — the insights worker now
  requests `catalog_segment_actions` and `catalog_segment_value` for all Meta accounts across
  campaign/adset/ad non-unique fetches (added to `_METRIC_FIELDS`), the only conversion source for
  Collaborative Ads accounts where the retailer owns the pixel and regular
  `actions`/`action_values`/`purchase_roas` return empty. Both stored into `metric_action_stats`
  via `ACTION_STAT_FIELDS` (no migration — table is generic). `parse_insight_row` normalizes each
  catalog-segment `action_type` to canonical `purchase`/`add_to_cart`/`view_content` via
  `_normalize_catalog_segment_action` (unknown types kept verbatim; normalization scoped to
  catalog_segment fields only) so the read layer has a stable pivot contract
  (`backend/workers/tasks/insights.py`). Read-layer surfacing handled separately.
- **Four Meta metrics surfaced in the insights read layer** — Post Reactions, Post Saves,
  Add to Cart Value, and Avg. Basket Price are now returned by the insights API. The raw data
  was already stored generically in `metric_action_stats` by the sync worker (`parse_insight_row`);
  only the read pivot + schemas needed to surface it (no worker change). `_ACTION_PIVOT_COLS`
  gained three FILTER columns — `post_reactions` (`actions`/`post_reaction`), `post_saves`
  (`actions`/`onsite_conversion.post_save`), `add_to_cart_value` (`action_values`/`add_to_cart`) —
  registered in `_ACTION_INT_KEYS`/`_ACTION_FLOAT_KEYS`; `_finalize_metrics` derives
  `avg_basket_price` = conversion_value ÷ purchase after aggregation, never stored (same rule as
  ROAS/CPA), None-guarded for timeseries points lacking conversion_value (P-4/P-7)
  (`backend/app/services/insights.py`). The four fields added to `MetricsSummary`,
  `TimeSeriesPoint`, and `TableMetrics` (`backend/app/schemas/insights.py`). Frontend
  `frontend/src/lib/api/insights.ts` types gain the same four fields (handled separately).
- **On-demand AI overview diagnosis** — a grounded LLM diagnosis over the single-account overview
  numbers. New service `backend/app/services/ai_summary.py` diagnoses over dicts from the shared
  read path (`insights.get_overview` + `get_table` + `get_timeseries`) — it computes nothing, states
  no figure not in its input, imports no repository and runs no SQL (P-6/P-7); any failure raises
  `AISummaryError` rather than fabricating text (P-4). New `POST /insights/overview/summary`
  (`backend/app/api/v1/endpoints/insights.py`) returns `OverviewSummaryResponse`
  (`{ headline, driver, watch, next_step, period, model, generated_at }`,
  `backend/app/schemas/insights.py`) at the top level (not `{ data }`-wrapped): a structured
  diagnosis — a headline finding, its likely driver, a watch signal, a next step — rather than one
  prose blob. The endpoint feeds the service a richer bundle via the shared read fns (P-6/P-7):
  per-campaign period-over-period rows with objectives (`get_table(level="campaign",
  compare_previous=True)`, top 10 by spend) and the current+previous daily trajectory
  (`get_timeseries(compare_previous=True)`), alongside the account rollup. The senior-analyst prompt
  (`generate_overview_diagnosis`) judges each metric against the campaign objective and SELECTS (does
  not compute/rank) the driver campaign from pre-computed deltas — no LLM arithmetic (P-7). Errors
  `403` cross-org, `400` missing dates, `502 { detail }` on any AI failure. The diagnosis is
  Redis-cached (`app.api.deps.redis_client`), keyed on
  `aisum:v1:{account}:{period}:{sha1(status,search)[:12]}:{cached_at|"nodata"}` with a 24h backstop
  TTL: without the new `force` query param a cache hit is replayed verbatim (`cached=true`, zero
  tokens); `force=true` regenerates and overwrites. The final key segment is `get_overview`'s new
  `cached_at` freshness token (`MAX(fetched_at)`, `backend/app/services/insights.py`), so a re-sync
  moves the key → miss → regenerate and a stale narrative is never served (P-1); AI failures are
  never cached (P-4). `OverviewSummaryResponse` gained `data_as_of` (the freshness token) and
  `cached`. New cache-only `GET /insights/overview/summary/peek` returns the cached diagnosis
  (`200`, `cached=true`) or `204` on a miss and **never** spends tokens. `GET
  /insights/overview/export.pptx` gained an opt-in `include_ai_summary` flag that auto-fills the
  deck's insight boxes via `generate_narrative` + `generate_overview_pptx(insights=…)`
  (`backend/app/services/export.py`), now fed the same campaign/trajectory bundle so the "trend"
  slide is grounded in real daily data; default off = the original placeholder, token-free deck. New
  config `OPENAI_API_KEY` + `OPENAI_MODEL` (default `gpt-4o-mini`) in `backend/app/config.py` /
  `backend/.env.example`; `openai` added to `backend/requirements.txt`. Frontend: typed
  `insightsApi.generateSummary` (now taking `force`; `OverviewSummary` gained `data_as_of` + `cached`)
  and cache-only `insightsApi.peekSummary` (maps `204` → `null`), plus `include_ai_summary` on
  `exportOverviewPptx` (`frontend/src/lib/api/insights.ts`), an **AI Summary** card rendering the
  four labeled sections with idle/loading/success/error states — it peeks the cache on mount
  (token-free) so an existing diagnosis shows instantly, Regenerate sends `force=true`, and the
  footnote shows `Data as of <relative time>` from `data_as_of` (P-1) — keyed on account + period +
  filter so a context change remounts it and a summary is never shown stale against
  numbers it wasn't generated for (P-1) (`frontend/src/components/views/overview-view.tsx`), and an
  **Include AI summary** toggle next to
  Export PPTX (`frontend/src/components/layout/control-strip.tsx`). Tests:
  `backend/tests/test_ai_summary.py`, `backend/tests/test_overview_summary_endpoint.py`,
  `backend/tests/test_export_overview.py`.
- **PPTX export of a single-account overview** — new `GET /insights/overview/export.pptx`
  (`backend/app/api/v1/endpoints/insights.py`) returns a branded 6-slide PowerPoint deck as a
  binary `StreamingResponse`: a dark gradient-blob **cover**, a **Monthly Performance** slide
  (Current-vs-Previous hero + metric cards with coloured period-over-period deltas and prior
  values), a **daily spend trend** with a native current-vs-previous overlay chart (thinned
  date axis), a styled **Top Campaigns** table, a **Top Ads** grid with 4:5 creative thumbnails,
  and a closing slide. Each content slide carries an editable purple "insight" placeholder box.
  Visual language mirrors a monthly-report agency template with dashmet branding: the dashmet
  logo (top-right of every slide + closing) and the platform logo beside the cover's "<PLATFORM>
  ADS" tag, rasterized from `frontend/public/*.svg` to bundled PNGs under
  `backend/app/services/assets/` (PowerPoint can't embed SVG; a missing asset degrades to a text
  mark). Deck built by the new `backend/app/services/export.py`
  (`generate_overview_pptx`), which reuses the shared `get_overview`/`get_timeseries`
  (`compare_previous=True`)/`get_table` read functions — identical numbers by construction, no
  second query path (P-6/P-7). Frontend: `insightsApi.exportOverviewPptx`
  (`frontend/src/lib/api/insights.ts`) plus an **Export PPTX** button shown on single-account
  views (`frontend/src/components/layout/control-strip.tsx`). Downloads with a human-readable
  name `"<Account> - Monthly Report - <Month Year>.pptx"` (RFC 5987 `Content-Disposition`,
  exposed via CORS in `app/main.py`; the frontend parses it for the download). New backend deps
  `python-pptx==1.0.2` + `Pillow==11.3.0` (`backend/requirements.txt`). Known gap: the
  single-account `get_overview()` read path lacks a freshness/coverage envelope, so the cover
  stamps only "Data as of <date_stop>" (P-1 follow-up, tracked in `BOARD.md`).
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
  full width (`w-60`) via a chevron toggle in the brand block next to the logo. Collapsed, labels/
  section headers hide, rows center their icon with a native `title` tooltip, and the `Platform
  Data` group flattens to its three platform icons. State persists via the existing UI store
  (`sidebarCollapsed`). `frontend/src/components/layout/sidebar.tsx`.
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
- **Conversion funnel redesign (UI-only, no data/behavior change)** — replaced the proportional
  horizontal bars (deep steps collapsed to ~2% slivers) with uniform left-aligned rows: label,
  power-scaled bar fill (`^0.4`, 6% floor) so every step stays visible, a fixed-width value +
  `DeltaPill` block, and a muted `% of top · vs <prev>` line. Step-to-step conversion (`↳ X%
  continue · cost/ea`) now renders as a thin indented connector between rows. Fixes the
  compare-on overlap where the delta pill collided with the value
  (`frontend/src/components/views/funnel-view.tsx`).
- **App font switched to Rubik.** Replaced Inter/Geist/Manrope with Rubik as the sans + display
  family (`--font-sans`, `--font-display`); Geist Mono retained for `--font-mono`
  (`frontend/src/app/layout.tsx`, `frontend/src/app/globals.css`).
- **Design-system unification pass — one accent, one segmented-control, coherent cards/tables.**
  Collapsed the frontend's competing visual languages into a single system (UI-only; no data or
  behavior change). (a) **Single accent = sidebar indigo.** `--primary`/`--ring`/`--accent`
  retuned from blue (~262°) to the sidebar indigo (~273°) in `frontend/src/app/globals.css`, and
  dark-mode `--primary`/`--ring` moved off the disconnected orange (45°) into the same indigo
  family — so buttons, active toggles, links and focus rings all match the rail. (b) **One
  filled-pill segmented control** — new shared `SegmentControl`
  (`frontend/src/components/ui/segment-control.tsx`): muted-bg pill container, active segment gets
  a solid `bg-primary`/`text-primary-foreground` fill; supports both state-based (`onValueChange`)
  and route-based (`href` → Next `<Link>`) segments. Every bespoke segmented/tab control now uses
  it: `layout/platform-tabs.tsx`, `shared/settings-nav.tsx` (was a border-b underline),
  `views/periodic-view.tsx` (Day/Week/Month + Line/Bar, hand-rolled control deleted),
  `views/ads-view.tsx` (Grid/List), `views/table-view.tsx` (Campaigns/Ad Groups/Ads),
  `metrics/breakdown-section.tsx` (Age/Country/Platform/Device), and
  `app/settings/accounts/page.tsx` (platform filter) — the last four dropped shadcn `Tabs` for
  the shared pill. (c) **Cards** — `metrics/metric-group-card.tsx` and the `ads-view` grid cards
  switched to the standard card surface (`ring-1 ring-foreground/10` + `--shadow-soft`/`--shadow-lift`)
  matching shadcn `Card`. (d) **Dashboard (bento) tiles re-skinned to match platform cards** —
  `components/bento/bento-tile.tsx` dropped its near-black hairline/mono-uppercase-label look for
  the standard card surface + sans `text-muted-foreground` labels; `bento/greeting-tile.tsx`
  dropped the terminal/typewriter/mono status line for a plain greeting; the `(dashboard)/dashboard`
  "By account" rows de-mono'd. (e) **Table spacing** refined in `components/ui/table.tsx`
  (header `h-11`, cells `px-3 py-2.5`). Platform brand colors (Meta/TikTok/Google badges), semantic
  status colors, and chart-series/data-encoding colors were deliberately left unchanged.
- **Toolbar reorganized into a tidy two-row layout; permanent "Sync Data" button removed.**
  The always-lit blue Sync Data button is gone — manual sync is now a contextual **Sync now**
  action inside the freshness chip, shown only when data is stale or a job failed (P-5). The
  `SyncStatusBadge` fresh state is muted from emerald to neutral grey so fresh data reads calm,
  not lit (P-2), and its pill icon is vertically centered. `AccountSwitcher` moved up beside the
  platform title (TopBar); the **Compare prev.** toggle moved down beside the view tabs
  (ControlStrip). Touches `frontend/src/components/layout/top-bar.tsx`,
  `frontend/src/components/layout/control-strip.tsx`,
  `frontend/src/components/shared/sync-status-badge.tsx`, `docs/frontend-spec.md`.
- **Sidebar nav slimmed: Account Binding removed, Settings pinned to bottom.** Dropped the
  standalone "Account Binding" rail link (and the now-empty USER section label); account
  connection is reached via **Settings → Connections** tab (`settings-nav.tsx` unchanged, route
  `/settings/connections` kept). Settings moved out of the scrollable nav into a bottom-pinned
  footer with a top divider, in both expanded and collapsed states. Touches
  `frontend/src/components/layout/sidebar.tsx`.
- **Brand + platform logos now use real SVG assets.** Sidebar brand swapped from the `Sparkles`
  lucide glyph to `/logo.svg`; `PlatformBadge` renders `/meta-logo.svg`, `/tiktok-logo.svg`, and
  `/gads-logo.svg` for meta/tiktok/google_ads (colored letter tile kept as fallback for any other
  platform). Assets added under `frontend/public/`. The Connections settings page's own
  `PlatformIcon` tiles render the same brand SVGs too. Touches
  `frontend/src/components/layout/sidebar.tsx`,
  `frontend/src/components/shared/platform-badge.tsx`,
  `frontend/src/app/settings/connections/page.tsx`.
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

### Fixed
- **"Sync now" button broken for TikTok and Google accounts** — two bugs. (A) The frontend posted
  `{ account_id }` only, but `TriggerSyncRequest.job_types` was required with no default, so the
  request failed validation → HTTP 400 "VALIDATION_ERROR". Made `job_types` optional
  (`job_types: list[str] | None = None`, `backend/app/schemas/sync.py`); when omitted the service
  picks a platform-appropriate default set. (B) `trigger_sync` dispatch was Meta-only — it created a
  `SyncJob` row per requested job_type but only branched to Meta tasks, so a TikTok/Google account
  either ran the wrong task or left `pending` rows with no producer (violates P-8: sync_jobs
  completeness). Replaced with a platform-aware `DISPATCH_TABLE`
  (`meta`/`tiktok`/`google_ads` → per-platform per-account tasks) plus `DEFAULT_JOB_TYPES`; a
  (platform, job_type) pair with no producer is skipped entirely rather than creating a stuck
  `pending` row (`backend/app/services/sync.py`). Tenant isolation
  (`assert_account_belongs_to_org`) unchanged. Frontend `sync.ts` typed to reflect the now-optional
  field (`frontend/src/lib/api/sync.ts`). Covered by `backend/tests/test_trigger_sync_dispatch.py`.
- TikTok sync jobs failing with "App … reaches the QPS limit 10, current QPS is 11" during
  connect-time backfill fan-out. `TikTokClient._rate_limit_check()` only enforced a per-*minute*
  counter and never the real app-wide 10 QPS limit, so concurrent tasks burst past it (TikTok
  returns HTTP 200 with `code != 0`, finalizing the job "failed"). Replaced with an app-level
  per-second token bucket in Redis, shared across all workers and capped at 8 QPS for headroom
  (`backend/workers/tiktok_client.py`); overflow requests sleep to the next one-second window and
  re-check. Still a no-op without Redis. The bucket alone was inert because every task call site
  constructed `TikTokClient(access_token)` with no Redis client — wired the shared
  `workers.rate_limit.redis_client` into all six constructions so the bucket is genuinely app-wide
  (`backend/workers/tasks/tiktok_structure.py`, `tiktok_insights.py`, `tiktok_breakdowns.py`,
  `tiktok_creatives.py`, `tiktok_token_refresh.py`). Guarded by
  `backend/tests/test_tiktok_limiter.py`, including a source-level assertion that no task call site
  omits `redis_client`.
- Laggy sidebar collapse/expand animation. The rail animated its `width` as a
  `shrink-0` flex sibling, so the content panel (charts/tables) recomputed layout
  every frame — heavy reflow. The rail is now an **absolute overlay** over an
  in-flow spacer (`w-[264px]`/`w-[92px]`, no transition) that reserves its column
  (`frontend/src/components/layout/sidebar.tsx`,
  `frontend/src/app/(dashboard)/layout.tsx`): the content panel sizes off the
  spacer and reflows once per toggle, while `[contain:layout_paint]` scopes the
  remaining reflow/paint to the rail, content column, and `<main>`. The rail's
  inner content is keyed on `collapsed` and replays a `sidebar-swap-in` opacity
  fade (`frontend/src/app/globals.css`, `motion-safe:` only) so the discrete
  layout swap fades in while the animated width settles — no more flash of labels
  clipped in the narrow rail / icons floating in the wide rail mid-animation.
- Disabled accounts read as gone from single-account resolution. `get_account_with_config`
  (`backend/app/services/accounts.py`) now raises `NotFoundError` for `account_status="disabled"`,
  so `GET /accounts/{id}` returns `404` like `GET /accounts` already hides them — a stale client
  selection (an `account_id` kept from before a disconnect+reconnect) resolves to gone and the UI
  falls back to a live account. Cross-org access stays `403`, checked before the status filter so
  status never leaks. Covered by `backend/tests/test_accounts_disabled.py`.
- Account picker no longer keeps a dead selection alive from a stale localStorage snapshot.
  `useSelectedAccount` (`frontend/src/hooks/use-account.ts`) now validates any selected id absent
  from the live first page even when a snapshot exists (`retry: false` GET; a 404 drops the
  selection), and only trusts the snapshot optimistically while that fetch is in flight.
  `AccountCommandList` (`frontend/src/components/shared/account-command-list.tsx`) prunes
  Pinned/Recent snapshots absent from the live list, but only when absence is conclusive (idle,
  non-truncated page); `PICKER_PAGE_SIZE` is now exported for the truncation check. — KPI cards (headline + sub-metrics), funnel
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
