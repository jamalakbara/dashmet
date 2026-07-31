"""
Google Ads API client wrapper (official google-ads SDK, gRPC).

Unlike the Meta/TikTok clients (raw httpx), Google's API is gRPC, so we wrap the
official ``GoogleAdsClient`` + ``GoogleAdsService.search_stream``. Each instance is
built per ``platform_connections`` row from the decrypted OAuth refresh token; the
SDK auto-refreshes the short-lived access token, so there is no token-refresh task.

``search`` flattens each proto ``GoogleAdsRow`` into a plain dict keyed by GAQL
field path (e.g. ``"campaign.id"``, ``"metrics.cost_micros"``) so the downstream
parsers stay SDK-agnostic. int64 fields come back as strings and enums as their
name (e.g. ``"ENABLED"``) — callers coerce as needed.
"""
import logging

from google.ads.googleads.client import GoogleAdsClient as _SDKClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.json_format import MessageToDict

from app.config import settings

logger = logging.getLogger(__name__)


class GoogleAdsClientError(Exception):
    """Wraps GoogleAdsException with a flat message + quota flag for backoff."""

    def __init__(self, message: str, request_id: str | None = None, is_quota: bool = False):
        self.request_id = request_id
        self.is_quota = is_quota
        super().__init__(message)


def _flatten(d: dict, prefix: str = "") -> dict:
    """Flatten a nested MessageToDict result to dotted keys. Lists (repeated
    fields like final_urls / headlines) are kept as-is for the caller to handle."""
    out: dict = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


class GoogleClient:
    def __init__(self, refresh_token: str):
        login_cid = (settings.GOOGLE_ADS_LOGIN_CUSTOMER_ID or "").replace("-", "").strip()
        config = {
            "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
            "client_id": settings.GOOGLE_ADS_CLIENT_ID,
            "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "use_proto_plus": True,
        }
        if login_cid:
            config["login_customer_id"] = login_cid
        # Omit the version arg → SDK uses the latest API version it ships (v24-era
        # for google-ads 31.x). GAQL in docs/ is written for v24.1.
        self._client = _SDKClient.load_from_dict(config)

    @staticmethod
    def _cid(customer_id: str) -> str:
        return str(customer_id).replace("-", "").strip()

    def _wrap(self, ex: GoogleAdsException) -> GoogleAdsClientError:
        try:
            msg = "; ".join(e.message for e in ex.failure.errors)
        except Exception:
            msg = str(ex)
        is_quota = False
        try:
            import grpc
            if ex.error.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                is_quota = True
        except Exception:
            pass
        if not is_quota and "quota" in (msg or "").lower():
            is_quota = True
        return GoogleAdsClientError(msg, request_id=getattr(ex, "request_id", None), is_quota=is_quota)

    def search(self, customer_id: str, query: str) -> list[dict]:
        """Run a GAQL query via search_stream and return flattened row dicts."""
        service = self._client.get_service("GoogleAdsService")
        rows: list[dict] = []
        try:
            stream = service.search_stream(customer_id=self._cid(customer_id), query=query)
            for batch in stream:
                for row in batch.results:
                    pb = type(row).pb(row)
                    d = MessageToDict(pb, preserving_proto_field_name=True)
                    rows.append(_flatten(d))
        except GoogleAdsException as ex:
            raise self._wrap(ex)
        return rows

    def list_accessible_customers(self) -> list[str]:
        """Customer IDs (digits only) the authenticated user can access directly."""
        try:
            service = self._client.get_service("CustomerService")
            resp = service.list_accessible_customers()
            return [rn.split("/")[-1] for rn in resp.resource_names]
        except GoogleAdsException as ex:
            raise self._wrap(ex)

    def list_customer_clients(self, manager_customer_id: str) -> list[dict]:
        """Walk the manager (MCC) hierarchy → child customers with metadata.
        Returns flattened rows keyed by `customer_client.*`."""
        query = (
            "SELECT customer_client.id, customer_client.descriptive_name, "
            "customer_client.currency_code, customer_client.time_zone, "
            "customer_client.manager, customer_client.status, customer_client.level "
            "FROM customer_client "
            "WHERE customer_client.status = 'ENABLED'"
        )
        return self.search(manager_customer_id, query)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
