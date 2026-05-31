"""
Meta Graph API v25.0 client.
Uses raw httpx for direct rate-limit header access.
"""
import json
import logging
import re

import httpx


def _parse_attribution_windows(window_str: str) -> list[str]:
    """Convert '7d_click_1d_view' → ['7d_click', '1d_view'] for Meta API."""
    return re.findall(r"\d+d_(?:click|view|engaged_view)", window_str) or [window_str]

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v25.0"
MAX_PAGES = 50


class MetaAPIError(Exception):
    def __init__(self, code: int, subcode: int | None, message: str, fbtrace_id: str | None = None):
        self.code = code
        self.subcode = subcode
        self.fbtrace_id = fbtrace_id
        super().__init__(message)


class MetaClient:
    def __init__(self, access_token: str):
        self.token = access_token
        self._client = httpx.Client(timeout=60.0)

    def _inject_token(self, params: dict | None) -> dict:
        p = params.copy() if params else {}
        p["access_token"] = self.token
        return p

    def _check_error(self, data: dict) -> None:
        if "error" in data:
            err = data["error"]
            raise MetaAPIError(
                code=err.get("code", 0),
                subcode=err.get("error_subcode"),
                message=err.get("message", "Unknown Meta API error"),
                fbtrace_id=err.get("fbtrace_id"),
            )

    def _parse_rate_limits(self, response: httpx.Response) -> dict:
        limits = {}
        for header in [
            "X-FB-Ads-Insights-Throttle",
            "X-Ad-Account-Usage",
            "X-App-Usage",
        ]:
            val = response.headers.get(header)
            if val:
                try:
                    limits[header] = json.loads(val)
                except Exception:
                    pass
        return limits

    def get(self, path: str, params: dict | None = None) -> tuple[dict, dict]:
        """Returns (data, rate_limits)."""
        url = f"{BASE_URL}{path}" if path.startswith("/") else f"{BASE_URL}/{path}"
        resp = self._client.get(url, params=self._inject_token(params))
        resp.raise_for_status()
        data = resp.json()
        self._check_error(data)
        return data, self._parse_rate_limits(resp)

    def paginate(
        self, path: str, params: dict | None = None, max_pages: int = MAX_PAGES
    ) -> list[dict]:
        """Follow paging.next and return flat list of all data items."""
        all_items = []
        data, _ = self.get(path, params)
        all_items.extend(data.get("data", []))

        page_count = 1
        next_url = data.get("paging", {}).get("next")
        while next_url and page_count < max_pages:
            resp = self._client.get(next_url)
            resp.raise_for_status()
            page_data = resp.json()
            self._check_error(page_data)
            all_items.extend(page_data.get("data", []))
            next_url = page_data.get("paging", {}).get("next")
            page_count += 1

        return all_items

    def batch(self, requests: list[dict]) -> list[dict]:
        """POST /v25.0/ with batch param. Each request is {"method", "relative_url"}."""
        resp = self._client.post(
            BASE_URL + "/",
            data={
                "access_token": self.token,
                "batch": json.dumps(requests),
            },
        )
        resp.raise_for_status()
        results = resp.json()
        parsed = []
        for item in results:
            if item is None:
                parsed.append({})
                continue
            body = json.loads(item.get("body", "{}"))
            self._check_error(body)
            parsed.append(body)
        return parsed

    def post_async_job(self, account_external_id: str, params: dict) -> str:
        """Submit async insights job. Returns report_run_id."""
        url = f"{BASE_URL}/act_{account_external_id}/insights"
        p = self._inject_token(params)
        resp = self._client.post(url, data=p)
        resp.raise_for_status()
        data = resp.json()
        self._check_error(data)
        return data["report_run_id"]

    def validate_token(self) -> dict:
        data, _ = self.get("/me", {"fields": "id,name"})
        return data

    def get_insights(
        self,
        entity_id: str,
        fields: str,
        level: str,
        date_preset: str,
        time_increment: int = 1,
        action_attribution_windows: str | None = None,
    ) -> list[dict]:
        """Fetch insights for any entity. Pass 'act_123' for account-level,
        bare campaign/adset/ad ID for entity-level."""
        params = {
            "fields": fields,
            "level": level,
            "date_preset": date_preset,
            "time_increment": time_increment,
            "limit": 200,
        }
        if action_attribution_windows:
            windows = _parse_attribution_windows(action_attribution_windows)
            params["action_attribution_windows"] = json.dumps(windows)
        return self.paginate(f"/{entity_id}/insights", params)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
