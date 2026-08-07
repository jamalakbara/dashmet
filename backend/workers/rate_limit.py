"""
Redis-backed rate limit state tracker and backoff enforcer.

Backoff is NON-BLOCKING: `apply_backoff` raises `RateLimitBackoff` instead of
sleeping a worker slot. The calling task catches it and re-dispatches itself with
a countdown, freeing the slot immediately.

The Meta app-level throttle (`X-FB-Ads-Insights-Throttle.app_id_util_pct`) is
shared by every account under one `platform_connections` token. So a hard limit
pauses the whole CONNECTION (via a Redis key with TTL), not just one account —
sibling accounts check that key at task entry and reschedule before spending the
shared quota further.
"""
import json
import logging
import uuid as _uuid

import redis as redis_lib

from app.config import settings

logger = logging.getLogger(__name__)

redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

KEY_PREFIX = "rate_limit:"
TTL = 3600  # 1 hour

# Thresholds (percent of Meta's reported utilization)
HARD_PCT = 95
SOFT_PCT = 80

# Backoff durations (seconds) used when Meta doesn't give us a reset hint
HARD_PAUSE_SECONDS = 300
SOFT_BACKOFF_SECONDS = 30
APP_CALL_BACKOFF_SECONDS = 60


class RateLimitBackoff(Exception):
    """Raised to signal a task should reschedule itself instead of blocking.

    `countdown` — seconds to wait before the rescheduled run.
    `scope`     — "connection" (whole token paused) or "account" (this account only).
    """

    def __init__(self, countdown: int, scope: str = "account"):
        self.countdown = int(countdown)
        self.scope = scope
        super().__init__(f"rate limit backoff: {scope} for {self.countdown}s")


class RateLimitState:
    def __init__(self, account_id: str, connection_id: str | None = None):
        self.account_id = account_id
        self.connection_id = connection_id

    def _key(self, field: str) -> str:
        return f"{KEY_PREFIX}{self.account_id}:{field}"

    def _store(self, field: str, value) -> None:
        redis_client.setex(self._key(field), TTL, str(value))

    def _get(self, field: str) -> float:
        val = redis_client.get(self._key(field))
        return float(val) if val else 0.0

    @staticmethod
    def _as_dict(value):
        """Header values may arrive already-parsed (MetaClient._parse_rate_limits
        json.loads()es them) or as a raw JSON string. Handle both."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return None

    def update_from_headers(self, headers: dict) -> None:
        insights = self._as_dict(headers.get("X-FB-Ads-Insights-Throttle"))
        if insights:
            try:
                app_pct = insights.get("app_id_util_pct", 0)
                self._store("insights_app_pct", app_pct)
                self._store("insights_acc_pct", insights.get("acc_id_util_pct", 0))
                tier = insights.get("ads_api_access_tier")
                if tier:
                    self._store("access_tier", tier)
                # App-level throttle is shared across the whole token — pause the
                # connection so sibling accounts back off too, not just this one.
                if self.connection_id and float(app_pct or 0) > HARD_PCT:
                    pause_connection(self.connection_id, HARD_PAUSE_SECONDS)
            except Exception:
                pass

        usage = self._as_dict(headers.get("X-Ad-Account-Usage"))
        if usage:
            try:
                self._store("structure_acc_pct", usage.get("acc_id_util_pct", 0))
                reset = usage.get("reset_time_duration")
                if reset:
                    self._store("quota_reset_seconds", reset)
            except Exception:
                pass

        app_usage = self._as_dict(headers.get("X-App-Usage"))
        if app_usage:
            try:
                self._store("app_call_count", app_usage.get("call_count", 0))
            except Exception:
                pass

    @property
    def insights_app_pct(self) -> float:
        return self._get("insights_app_pct")

    @property
    def insights_acc_pct(self) -> float:
        return self._get("insights_acc_pct")

    @property
    def structure_acc_pct(self) -> float:
        return self._get("structure_acc_pct")

    @property
    def app_call_count(self) -> float:
        return self._get("app_call_count")

    @property
    def quota_reset_seconds(self) -> float:
        return self._get("quota_reset_seconds")


# ── Connection-scoped pause (shared-token gate) ───────────────────────────────

def _conn_pause_key(connection_id: str) -> str:
    return f"{KEY_PREFIX}conn:{connection_id}:paused"


def pause_connection(connection_id: str, seconds: int) -> None:
    """Pause all accounts under a connection for `seconds` (Redis key with TTL)."""
    redis_client.setex(_conn_pause_key(connection_id), int(seconds), "1")


def connection_paused_remaining(connection_id: str | None) -> int:
    """Seconds remaining on a connection pause, or 0 if not paused."""
    if not connection_id:
        return 0
    ttl = redis_client.ttl(_conn_pause_key(connection_id))
    return ttl if ttl and ttl > 0 else 0


# ── Per-(account, job_type) in-flight lock ────────────────────────────────────

def _lock_key(job_type: str, account_id: str) -> str:
    return f"{KEY_PREFIX}lock:{job_type}:{account_id}"


def acquire_lock(job_type: str, account_id: str, ttl: int) -> str | None:
    """Atomically acquire an in-flight lock. Returns a token to release with, or
    None if another run already holds it. TTL must be >= the task's hard
    time_limit so a live task never loses its lock and a dead one always frees."""
    token = _uuid.uuid4().hex
    ok = redis_client.set(_lock_key(job_type, account_id), token, nx=True, ex=int(ttl))
    return token if ok else None


_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end"
)


def release_lock(job_type: str, account_id: str, token: str | None) -> None:
    """Release a lock only if we still own it (check-and-delete via Lua)."""
    if not token:
        return
    try:
        redis_client.eval(_RELEASE_LUA, 1, _lock_key(job_type, account_id), token)
    except Exception:
        pass


# ── Meta rate-limit error detection ───────────────────────────────────────────
# Meta enforces rate limits TWO ways: the X-FB-Ads-Insights-Throttle header
# (handled above) AND hard error responses. The header can read ~0% while the API
# still returns "Application request limit reached" — so error codes must also
# trigger a connection pause, or every slot keeps hammering the same token.
# Refs: code 4 (app), 17 (user), 32 (page), 613 (custom-rate), 80000-80004 (ads/insights).
META_RATE_LIMIT_CODES = {4, 17, 32, 613}


def is_meta_rate_limit_error(code, subcode=None) -> bool:
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        return False
    if code in META_RATE_LIMIT_CODES:
        return True
    if code is not None and 80000 <= code <= 80004:
        return True
    return False


# ── Backoff decision (non-blocking) ───────────────────────────────────────────

def apply_backoff(account_id: str, connection_id: str | None = None) -> None:
    """Inspect current rate-limit state and raise RateLimitBackoff if the caller
    should back off. Does NOT sleep — the task reschedules itself on the raise."""
    state = RateLimitState(account_id, connection_id)

    if state.insights_app_pct > HARD_PCT:
        countdown = int(state.quota_reset_seconds) or HARD_PAUSE_SECONDS
        if connection_id:
            pause_connection(connection_id, countdown)
        logger.warning(f"[{account_id}] Hard rate limit — pausing connection {countdown}s")
        raise RateLimitBackoff(countdown, scope="connection")

    soft = 0
    if state.insights_app_pct > SOFT_PCT or state.insights_acc_pct > SOFT_PCT:
        soft = max(soft, SOFT_BACKOFF_SECONDS)
    if state.structure_acc_pct > SOFT_PCT:
        soft = max(soft, SOFT_BACKOFF_SECONDS)
    if state.app_call_count > SOFT_PCT:
        soft = max(soft, APP_CALL_BACKOFF_SECONDS)

    if soft:
        logger.info(f"[{account_id}] Soft rate limit — rescheduling in {soft}s")
        raise RateLimitBackoff(soft, scope="account")
