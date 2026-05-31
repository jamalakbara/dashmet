"""
Redis-backed rate limit state tracker and backoff enforcer.
"""
import json
import logging
import time

import redis as redis_lib

from app.config import settings

logger = logging.getLogger(__name__)

redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

KEY_PREFIX = "rate_limit:"
TTL = 3600  # 1 hour


class RateLimitState:
    def __init__(self, account_id: str):
        self.account_id = account_id

    def _key(self, field: str) -> str:
        return f"{KEY_PREFIX}{self.account_id}:{field}"

    def _store(self, field: str, value) -> None:
        redis_client.setex(self._key(field), TTL, str(value))

    def _get(self, field: str) -> float:
        val = redis_client.get(self._key(field))
        return float(val) if val else 0.0

    def update_from_headers(self, headers: dict) -> None:
        insights = headers.get("X-FB-Ads-Insights-Throttle")
        if insights:
            try:
                data = json.loads(insights)
                self._store("insights_app_pct", data.get("app_id_util_pct", 0))
                self._store("insights_acc_pct", data.get("acc_id_util_pct", 0))
                tier = data.get("ads_api_access_tier")
                if tier:
                    self._store("access_tier", tier)
            except Exception:
                pass

        usage = headers.get("X-Ad-Account-Usage")
        if usage:
            try:
                data = json.loads(usage)
                self._store("structure_acc_pct", data.get("acc_id_util_pct", 0))
                reset = data.get("reset_time_duration")
                if reset:
                    self._store("quota_reset_seconds", reset)
            except Exception:
                pass

        app_usage = headers.get("X-App-Usage")
        if app_usage:
            try:
                data = json.loads(app_usage)
                self._store("app_call_count", data.get("call_count", 0))
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


def apply_backoff(account_id: str) -> None:
    state = RateLimitState(account_id)

    if state.insights_app_pct > 95:
        logger.warning(f"[{account_id}] Hard rate limit pause (5 min)")
        time.sleep(300)
        return

    if state.insights_app_pct > 80 or state.insights_acc_pct > 80:
        logger.info(f"[{account_id}] Soft rate limit back-off (30s)")
        time.sleep(30)

    if state.structure_acc_pct > 80:
        logger.info(f"[{account_id}] Structure rate limit back-off (30s)")
        time.sleep(30)

    if state.app_call_count > 80:
        logger.info(f"[{account_id}] App call count back-off (60s)")
        time.sleep(60)
