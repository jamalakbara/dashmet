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
        if not self._redis:
            return
        minute_key = f"tiktok_req_count:{int(time.time() // 60)}"
        count = self._redis.incr(minute_key)
        self._redis.expire(minute_key, 120)
        if count >= 800:
            logger.warning("TikTok rate limit approaching (%s/min), sleeping 5s", count)
            time.sleep(5)

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
            "ad_id", "adgroup_id", "campaign_id", "ad_name", "status",
            "ad_text", "call_to_action", "landing_page_url", "video_id",
            "ad_format", "create_time", "modify_time", "review_status",
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
    ) -> list[dict]:
        import json
        params = {
            "advertiser_id": advertiser_id,
            "report_type": "BASIC",
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
