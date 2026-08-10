# Plan: Meta Token Auto-Refresh + Token-Expiry Alerting

Status: **IMPLEMENTED (2026-08-10).** Retained as the design record; the "as-shipped" locations are noted inline where they differ from the original plan. For the live behavior see `docs/sync-worker-spec.md` (refresh task + emission), `docs/backend-api-spec.md` §6.15 (notifications endpoints + `/connections` health fields), `docs/internal-schema-spec.md` (`notifications` table + connection health columns), and `docs/frontend-spec.md` (`NotificationCenter` + connection health badge).
Maps to `.claude/rules/product-principles.md` (P-1, P-2, P-5, P-7, P-8; §2.3 anti-reqs). No `docs/prd-parity.md` exists yet — identifiers point at the principles doc, per `BOARD.md`.

## Problem

Worker sync fails when a platform token expires. Today:

- **Meta** — connected by manual long-lived-token paste. `token_type` defaults to `"system_user"`, `token_expires_at` is left **NULL**. No refresh path. When the token expires, every Meta sync errors indefinitely with no auto-recovery and no alert.
- **TikTok** — has a refresh task (`workers/tasks/tiktok_token_refresh.py`, daily 00:30 UTC), but on failure it silently sets `is_active=False` with no user-facing signal.
- **Google** — SDK auto-refreshes from the stored refresh token; on `GoogleAdsException` the sync errors with no alert.

> **As shipped (2026-08-10):** the below described the pre-build state. A notification system now exists — the `notifications` table (with `dedup_key`/`deep_link`), a single writer `app/services/notifications.py`, and the worker-side alerting funnel `workers/token_alerts.py`. Before this change, failures lived only in `sync_jobs.error_message` + the `/sync/status` `has_warning` flag.

## Meta token mechanics (confirmed)

- The `fb_exchange_token` grant takes the **current valid long-lived token** (the one pasted at connect) and returns a fresh one, expiry reset ~60d:
  ```
  GET https://graph.facebook.com/oauth/access_token
    ?grant_type=fb_exchange_token
    &client_id=<META_APP_ID>
    &client_secret=<META_APP_SECRET>
    &fb_exchange_token=<current long-lived access_token>
  ```
- **Must run while the token is still alive.** A dead token cannot be exchanged — hence refresh fires proactively before expiry, not after.
- `client_id`/`client_secret` **must be the same Meta app that minted the token**, else exchange fails. (User has these.)
- **Hard ceiling — auto-refresh is not sufficient alone (P-5):**
  - `fb_exchange_token` extends the 60d token but does **NOT** reset Meta's ~90d **data-access expiration** → periodic manual re-auth/re-paste is unavoidable.
  - A true system-user token isn't refreshable this way (regenerated in Business Manager).
  - Revoked / permission-changed tokens can't self-heal.
  - → These are exactly the cases the alerting piece is the recovery path for. Auto-refresh + alert-when-can't-refresh = complete.

---

## Piece 1 — Meta token refresh (source fix)

**Config**
- Add `META_APP_ID`, `META_APP_SECRET` to settings + `.env`.

**Connect flow** (`workers/meta_client.py`, `app/services/accounts.py`, `app/api/v1/endpoints/connections.py`)
- On Meta connect, call Meta `/debug_token` → read `expires_at`, `data_access_expires_at`, token type.
- Populate `token_expires_at` (currently NULL). Auto-detects never-expiring system-user vs 60d long-lived — no guessing.

**Refresh** (`workers/meta_client.py` + new `workers/tasks/meta_token_refresh.py`)
- `MetaClient.exchange_long_lived_token()` wraps `fb_exchange_token`.
- Beat task `refresh_meta_tokens` — mirror `tiktok_token_refresh`: active Meta connections with `token_expires_at < now + 7d` → exchange → store new encrypted token + expiry. Schedule daily (add to `workers/celery_app.py` beat_schedule).
- On success → resolve any matching unresolved notification (P-2).
- On failure → set `last_error` + create notification + email (Piece 2).

**Ownership:** workers-sync (client + task + beat), backend (settings + connect-flow expiry capture).

---

## Piece 2 — Notifications system (dashboard center + in-app health + email)

Built per the §2.3 anti-requirements. (As shipped: migration `e9f0a1b2c3d4_add_notifications_and_connection_health.py`.)

### `notifications` table (db-migration)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `organization_id` | uuid fk | tenant isolation |
| `type` | str | `token_expiring` \| `token_expired` \| `refresh_failed` \| `sync_failed` |
| `severity` | str | `info` \| `warning` \| `error` |
| `title`, `body` | str | |
| `deep_link` | str | **stored column, never inferred from message text** (anti-req) |
| `dedup_key` | str | e.g. `token_expired:{connection_id}` |
| `status` | str | `unread` \| `read` \| `resolved` |
| `resolved_at` | datetime? | |
| `created_at` | datetime | |

- **`UNIQUE (organization_id, dedup_key)`** — DB dedup, not an app-side time window (anti-req). Insert = upsert `ON CONFLICT DO NOTHING` → re-running a check never dupes.
- **Auto-resolve (P-2):** successful refresh / recovered sync marks the matching row `resolved` → badge and banner disappear. No permanently-lit warning.

### Connection health (add to `PlatformConnection`)
- `last_error text?`, `last_error_at datetime?`. Health status derived from `token_expires_at` + `last_error` (no separate enum column needed).

### Emission (workers only)
- Notifications are created only by worker/refresh/sync-failure code paths — **never as a side effect of a GET** (anti-req).
- One shared writer `app/services/notifications.py`; worker paths reach it through the shared funnel `workers/token_alerts.py` (`record_token_failure` / `clear_token_failure` / `alert_connection_token_failure`), used by all platforms (P-7):
  - Meta refresh task — fail → create + email + `last_error`; success → resolve.
  - TikTok refresh task — currently deactivates silently; add notification on fail.
  - Google sync tasks — catch `GoogleAdsException` → create notification (SDK can't pre-check).

### Backend endpoints (backend agent)
- `GET /notifications` — tenant-scoped list + unread count. Read-only, emits nothing.
- `POST /notifications/{id}/read` — mark read.
- Extend `GET /connections` — include `health`, `token_expires_at`, `last_error` (update `frontend/src/lib/api/connections.ts` in the same PR — api-contract-parity rule).

### Email (`app/services/email.py`)
- Send on `token_expired` / `refresh_failed`. Gated by the same `dedup_key` — if an unresolved notification already exists, don't re-send. No per-sync-cycle spam.

> **As shipped:** `app/services/email.py` is a **live transport** — Resend HTTP API (preferred, port 443) with an SMTP fallback; when neither is configured it logs instead of sending. Token-failure email goes to the org **owner(s)** via `workers/token_alerts.send_token_failure_email`, gated by the same dedup (only when the notification was newly created, so a repeated failure never re-emails).

---

## Piece 3 — Frontend (frontend agent)

- **Notification center:** bell icon + unread badge + dropdown/inbox. New `frontend/src/lib/api/notifications.ts`.
- **Connection health badge** on the connections/settings page. Update `connections.ts` types for the new fields.
- **Auto-update via polling** (no websockets/SSE):
  - TanStack Query `refetchInterval` ~30–60s on the notifications query → bell/count refresh automatically.
  - `refetchOnWindowFocus` → updates on tab focus.
  - Worker-generated events are minute-scale, so polling matches the data cadence — cheaper than a socket. Same poll auto-clears the badge when a notif resolves (P-2).

---

## Tests (test-required-for-done, §11)

- `dedup_key` idempotency — run the check twice → exactly one row (DB unique constraint).
- Notification auto-resolves on successful refresh (P-2).
- Tenant isolation — `GET /notifications` cross-org → 403.
- No-emit-from-GET — structural: `GET /notifications` inserts zero rows.
- Meta refresh — exchange updates token + expiry; failure creates notification + sets `last_error` and does **not** crash the sync task.

## Docs updated (docs-sync) — done

`internal-schema-spec.md` (table + connection columns), `backend-api-spec.md` (§6.15 endpoints + `/connections` health fields), `sync-worker-spec.md` (refresh task + emission), `frontend-spec.md` (`NotificationCenter` + health badge), `meta-ads-dashboard-api-reference.md` (§1 debug_token / fb_exchange_token usage).

## Build order & ownership

db-migration (table + connection columns) → backend (endpoints + notif service + settings + connect-flow expiry) → workers-sync (meta_client, refresh task, beat, notif wiring) → frontend (center + badge + api types) → testing → docs.

## Open items before build (resolved)

1. ~~Meta App ID/Secret available~~ — resolved: `META_APP_ID` / `META_APP_SECRET` are in `app/config.py` (default `""`; the refresh task no-ops and the connect-flow `debug_token` probe is skipped when unset).
2. ~~Is `app/services/email.py` a live transport or a stub?~~ — resolved: it is live (Resend HTTP API + SMTP fallback), used by `workers/token_alerts.send_token_failure_email`.
