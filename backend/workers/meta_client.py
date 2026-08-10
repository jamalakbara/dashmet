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


# Meta OAuth error codes that mean "the token is dead/insufficient", not
# "transient / rate-limited". Code 190 = access token expired/invalid/revoked;
# code 102 = session/API auth failure. These are the codes a sync task should
# turn into a durable token-failure alert rather than retry forever.
META_AUTH_ERROR_CODES = frozenset({190, 102})
# OAuth error_subcodes under code 190/102 that specifically flag an
# expired/revoked/invalidated session (vs. e.g. a generic app-level issue).
META_AUTH_ERROR_SUBCODES = frozenset({458, 459, 460, 463, 464, 467, 492})


class MetaAPIError(Exception):
    def __init__(self, code: int, subcode: int | None, message: str, fbtrace_id: str | None = None):
        self.code = code
        self.subcode = subcode
        self.fbtrace_id = fbtrace_id
        super().__init__(message)

    @property
    def is_auth(self) -> bool:
        """True for token/permission failures (expired/invalid/revoked session).

        Mirrors ``GoogleAdsClientError.is_auth`` so sync-task ``except`` blocks
        read the same across platforms: a dead OAuth token must raise a durable
        token-failure alert (P-8) instead of retrying a dead grant forever.
        Matches Meta code 190/102 or any of the OAuth auth subcodes."""
        return (
            self.code in META_AUTH_ERROR_CODES
            or (self.subcode in META_AUTH_ERROR_SUBCODES if self.subcode else False)
        )


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
        data = resp.json()
        self._check_error(data)  # parse Meta error body before raising HTTP status
        resp.raise_for_status()
        return data, self._parse_rate_limits(resp)

    def _record_rate_limits(self, rate_limits: dict, account_id, connection_id) -> None:
        """Feed rate-limit headers into Redis so apply_backoff sees live data.
        No-op unless an account_id is supplied (keeps non-sync callers cheap)."""
        if not account_id:
            return
        from workers.rate_limit import RateLimitState
        RateLimitState(str(account_id), str(connection_id) if connection_id else None).update_from_headers(rate_limits)

    def paginate(
        self,
        path: str,
        params: dict | None = None,
        max_pages: int = MAX_PAGES,
        account_id=None,
        connection_id=None,
    ) -> list[dict]:
        """Follow paging cursors and return flat list of all data items.

        Pass account_id/connection_id to record rate-limit headers per page —
        otherwise the throttle headers are discarded and backoff reads stale data."""
        all_items = []
        current_params = dict(params) if params else {}
        data, rate_limits = self.get(path, current_params)
        self._record_rate_limits(rate_limits, account_id, connection_id)
        all_items.extend(data.get("data", []))

        page_count = 1
        paging = data.get("paging", {})
        after_cursor = paging.get("cursors", {}).get("after")
        # Fall back to parsing the cursor from paging.next if cursors object absent
        if not after_cursor and paging.get("next"):
            import urllib.parse as _up
            qs = _up.parse_qs(_up.urlparse(paging["next"]).query)
            after_cursor = (qs.get("after") or [None])[0]

        while after_cursor and page_count < max_pages:
            next_params = dict(current_params)
            next_params["after"] = after_cursor
            data, rate_limits = self.get(path, next_params)
            self._record_rate_limits(rate_limits, account_id, connection_id)
            all_items.extend(data.get("data", []))
            paging = data.get("paging", {})
            after_cursor = paging.get("cursors", {}).get("after")
            if not after_cursor and paging.get("next"):
                import urllib.parse as _up
                qs = _up.parse_qs(_up.urlparse(paging["next"]).query)
                after_cursor = (qs.get("after") or [None])[0]
            page_count += 1

        return all_items

    def batch(self, requests: list[dict], account_id=None, connection_id=None) -> list[dict]:
        """POST /v25.0/ with batch param. Each request is {"method", "relative_url"}.
        Pass account_id/connection_id to record rate-limit headers from the response."""
        resp = self._client.post(
            BASE_URL + "/",
            data={
                "access_token": self.token,
                "batch": json.dumps(requests),
            },
        )
        resp.raise_for_status()
        self._record_rate_limits(self._parse_rate_limits(resp), account_id, connection_id)
        results = resp.json()
        parsed = []
        for item in results:
            if item is None:
                parsed.append({})
                continue
            body = json.loads(item.get("body", "{}"))
            # Don't raise on sub-request errors — a single bad campaign must not
            # abort the whole batch. Caller inspects "error" per result.
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

    def exchange_long_lived_token(
        self, app_id: str, app_secret: str, fb_exchange_token: str
    ) -> dict:
        """Exchange a still-valid long-lived token for a fresh one via the
        `fb_exchange_token` grant. Returns {"access_token", "expires_in", ...}.

        Must run while the current token is still alive — a dead token cannot be
        exchanged, which is why the refresh task fires proactively before expiry.
        `app_id`/`app_secret` must be the same Meta app that minted the token,
        or Meta rejects the exchange. Uses the same graph version + httpx get
        plumbing as every other call; `_check_error` raises MetaAPIError on a
        Meta error body."""
        data, _ = self.get(
            "/oauth/access_token",
            {
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": fb_exchange_token,
            },
        )
        return data

    def get_insights(
        self,
        entity_id: str,
        fields: str,
        level: str,
        time_range: str,
        time_increment: int = 1,
        action_attribution_windows: str | None = None,
        account_id=None,
        connection_id=None,
    ) -> list[dict]:
        """Fetch insights for any entity. Pass 'act_123' for account-level,
        bare campaign/adset/ad ID for entity-level.

        `time_range` is a Meta time_range JSON string (see workers.date_range) —
        never a `date_preset`. Sending an explicit range in the account timezone
        is a hard requirement (PRD §2.3)."""
        params = {
            "fields": fields,
            "level": level,
            "time_range": time_range,
            "time_increment": time_increment,
            "limit": 200,
        }
        if action_attribution_windows:
            windows = _parse_attribution_windows(action_attribution_windows)
            params["action_attribution_windows"] = json.dumps(windows)
        return self.paginate(
            f"/{entity_id}/insights", params,
            account_id=account_id, connection_id=connection_id,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
