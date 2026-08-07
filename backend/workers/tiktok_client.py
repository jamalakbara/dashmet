"""
TikTok Business API v1.3 client.
Auth: Access-Token header (OAuth 2.0 access token).
"""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"
MAX_PAGES = 50
VIDEO_BATCH_SIZE = 100

# TikTok enforces an app-level 10 QPS limit shared across every worker. We cap
# below that (8 QPS) for headroom so bursts from concurrent backfill fan-out
# don't trip "reaches the QPS limit 10" (HTTP 200 with code != 0 -> failed job).
TIKTOK_APP_QPS_CAP = 8


class TikTokAPIError(Exception):
    def __init__(self, code: int, message: str, request_id: str | None = None):
        self.code = code
        self.request_id = request_id
        super().__init__(message)


class TikTokClient:
    def __init__(self, access_token: str, redis_client=None):
        self.token = access_token
        self._redis = redis_client
        self._client = httpx.Client(timeout=60.0)

    def _headers(self) -> dict:
        return {"Access-Token": self.token, "Content-Type": "application/json"}

    def _check(self, data: dict) -> None:
        code = data.get("code", 0)
        if code != 0:
            raise TikTokAPIError(
                code=code,
                message=data.get("message", "Unknown TikTok API error"),
                request_id=data.get("request_id"),
            )

    def _rate_limit_check(self) -> None:
        """App-wide per-second token bucket shared across all workers via Redis.

        TikTok's real limit is 10 QPS at the *app* level; the previous per-minute
        counter never enforced it, so concurrent backfill fan-out burst past 10
        req/sec and every job failed with "reaches the QPS limit 10". We cap at
        TIKTOK_APP_QPS_CAP (8) per one-second window: each request claims a slot
        in that second's key; if the window is full we sleep to the next second
        and re-check. No-op when Redis is absent (unit tests without a broker).
        """
        if not self._redis:
            return
        while True:
            second = int(time.time())
            key = f"tiktok_qps:{second}"
            count = self._redis.incr(key)
            # Expire well past the window so a claimed slot is never double-counted
            # by a clock that lingers on the same second; harmless if it re-sets.
            self._redis.expire(key, 2)
            if count <= TIKTOK_APP_QPS_CAP:
                return
            # Window is full: give back the slot we claimed and wait out the second.
            self._redis.decr(key)
            sleep_for = 1.0 - (time.time() - second)
            if sleep_for < 0:
                sleep_for = 0.0
            logger.warning(
                "TikTok app QPS cap %s reached in window %s; sleeping %.3fs",
                TIKTOK_APP_QPS_CAP, second, sleep_for,
            )
            time.sleep(sleep_for)

    def get(self, path: str, params: dict | None = None) -> dict:
        self._rate_limit_check()
        url = f"{BASE_URL}{path}"
        resp = self._client.get(url, params=params or {}, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        self._check(data)
        return data

    def post(self, path: str, body: dict) -> dict:
        self._rate_limit_check()
        url = f"{BASE_URL}{path}"
        resp = self._client.post(url, json=body, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        self._check(data)
        return data

    def paginate(self, path: str, params: dict, page_size: int = 1000) -> list[dict]:
        all_items: list[dict] = []
        page = 1
        while True:
            p = {**params, "page": page, "page_size": page_size}
            data = self.get(path, p)
            items = data.get("data", {}).get("list", [])
            all_items.extend(items)
            page_info = data.get("data", {}).get("page_info", {})
            total = page_info.get("total_number", 0)
            if len(all_items) >= total or not items:
                break
            page += 1
            if page > MAX_PAGES:
                logger.warning("Hit MAX_PAGES (%s) on %s", MAX_PAGES, path)
                break
        return all_items

    def get_advertiser_info(self, advertiser_ids: list[str]) -> list[dict]:
        import json
        data = self.get(
            "/advertiser/info/",
            {"advertiser_ids": json.dumps(advertiser_ids)},
        )
        return data.get("data", {}).get("list", [])

    def get_campaigns(self, advertiser_id: str) -> list[dict]:
        return self.paginate(
            "/campaign/get/",
            {"advertiser_id": advertiser_id},
        )

    def get_adgroups(self, advertiser_id: str) -> list[dict]:
        return self.paginate(
            "/adgroup/get/",
            {"advertiser_id": advertiser_id},
        )

    def get_ads(self, advertiser_id: str) -> list[dict]:
        import json
        fields = json.dumps([
            "ad_id", "adgroup_id", "campaign_id", "ad_name", "operation_status",
            "ad_text", "call_to_action", "landing_page_url", "video_id",
            "tiktok_item_id", "ad_format", "create_time", "modify_time",
        ])
        return self.paginate(
            "/ad/get/",
            {"advertiser_id": advertiser_id, "fields": fields},
        )

    def get_video_info(self, advertiser_id: str, video_ids: list[str]) -> list[dict]:
        """Batch in groups of 100 (POST endpoint, despite being a read)."""
        results: list[dict] = []
        for i in range(0, len(video_ids), VIDEO_BATCH_SIZE):
            batch = video_ids[i : i + VIDEO_BATCH_SIZE]
            data = self.post(
                "/file/video/ad/info/",
                {"advertiser_id": advertiser_id, "video_ids": batch},
            )
            results.extend(data.get("data", {}).get("list", []))
        return results

    def get_report(
        self,
        advertiser_id: str,
        data_level: str,
        dimensions: list[str],
        metrics: list[str],
        start_date: str,
        end_date: str,
        page_size: int = 1000,
        report_type: str = "BASIC",
    ) -> list[dict]:
        import json
        params = {
            "advertiser_id": advertiser_id,
            "report_type": report_type,
            "data_level": data_level,
            "dimensions": json.dumps(dimensions),
            "metrics": json.dumps(metrics),
            "start_date": start_date,
            "end_date": end_date,
        }
        return self.paginate("/report/integrated/get/", params, page_size=page_size)

    def exchange_auth_code(self, app_id: str, app_secret: str, auth_code: str) -> dict:
        data = self.post(
            "/oauth2/access_token/",
            {"app_id": app_id, "secret": app_secret, "auth_code": auth_code},
        )
        return data.get("data", {})

    def refresh_access_token(self, app_id: str, app_secret: str, refresh_token: str) -> dict:
        data = self.post(
            "/oauth2/refresh_token/",
            {"app_id": app_id, "secret": app_secret, "refresh_token": refresh_token},
        )
        return data.get("data", {})

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
