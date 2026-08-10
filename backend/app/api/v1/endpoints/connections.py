import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DbSession, OwnerUser

logger = logging.getLogger(__name__)
from app.config import settings
from app.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.schemas.accounts import ConnectionResponse, CreateConnectionRequest
from app.schemas.common import DataResponse
from app.services import accounts as acc_svc
from app.services.notifications import resolve_platform_token_alerts

router = APIRouter()


def _probe_meta_token_expiry(access_token: str):
    """Read a Meta token's real expiry via /debug_token.

    Returns a tz-aware ``datetime`` when the token has a finite expiry, or
    ``None`` when it never expires (``expires_at == 0``), when META_APP_ID/
    SECRET are unconfigured, or when the debug_token call errors. A failure
    here is logged and swallowed — the token was already validated by the
    /me/adaccounts call, so debug_token must never break the connect flow.

    Called inline via the existing generic MetaClient GET; no methods are added
    to MetaClient (that's workers-sync's file).
    """
    if not settings.META_APP_ID or not settings.META_APP_SECRET:
        logger.info("debug_token skipped: META_APP_ID/SECRET not configured")
        return None

    app_access_token = f"{settings.META_APP_ID}|{settings.META_APP_SECRET}"
    try:
        from workers.meta_client import MetaClient

        data, _ = MetaClient(app_access_token).get(
            "/debug_token", {"input_token": access_token}
        )
        info = data.get("data", {}) if isinstance(data, dict) else {}
        expires_at = info.get("expires_at")
        # 0 (or missing) == never expires → leave token_expires_at NULL.
        if expires_at and int(expires_at) > 0:
            return datetime.fromtimestamp(int(expires_at), tz=timezone.utc)
        return None
    except Exception as e:
        logger.warning("debug_token probe failed (continuing): %s", e)
        return None


@router.get("")
def list_connections(current_user: CurrentUser, db: DbSession):
    conns = acc_svc.list_connections(db, current_user["org_id"])
    return DataResponse(
        data=[ConnectionResponse.from_orm_connection(c) for c in conns]
    )


@router.post("", status_code=201)
def create_connection(
    body: CreateConnectionRequest, current_user: OwnerUser, db: DbSession
):
    try:
        token_expires_at = None
        if body.platform == "meta":
            from workers.meta_client import MetaClient, MetaAPIError
            import httpx
            try:
                MetaClient(body.access_token).get(
                    "/me/adaccounts", {"fields": "id,name", "limit": "1"}
                )
            except MetaAPIError as e:
                raise HTTPException(status_code=400, detail=f"Meta token rejected: {e}")
            except httpx.HTTPStatusError as e:
                raise HTTPException(status_code=400, detail=f"Meta token rejected: {e}")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Could not verify Meta token: {e}")

            # The token is now validated. Probe its real expiry via debug_token
            # so token_expires_at is populated (never-expiring system-user tokens
            # report 0 → stays NULL). A debug_token failure must NOT break the
            # connect flow — the token was already accepted above.
            token_expires_at = _probe_meta_token_expiry(body.access_token)

        conn = acc_svc.create_connection(
            db,
            org_id=current_user["org_id"],
            user_id=current_user["user_id"],
            platform=body.platform,
            access_token=body.access_token,
            token_type=body.token_type,
        )
        if token_expires_at is not None:
            conn.token_expires_at = token_expires_at
        db.commit()
        db.refresh(conn)

        # A validated reconnect clears any open token-expiry alert for this
        # org+platform (P-2). Reconnecting INSERTs a NEW connection row, so the
        # old alert's dedup key points at the dead connection — clear at the
        # org+platform level, not just this new id. Only reached on SUCCESS.
        resolve_platform_token_alerts(
            db, org_id=current_user["org_id"], platform=body.platform
        )
        db.commit()

        from workers.tasks.structure import sync_accounts_for_connection
        sync_accounts_for_connection.delay(str(conn.id), current_user["org_id"])

        return DataResponse(
            data={
                "id": str(conn.id),
                "platform": conn.platform_id,
                "is_active": conn.is_active,
                "scopes": conn.scopes,
                "message": "Connection verified. Ad accounts are being imported.",
            }
        )
    except ConflictError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tiktok/oauth/initiate")
def tiktok_oauth_initiate(current_user: OwnerUser):
    from app.api.deps import redis_client
    if not settings.TIKTOK_APP_ID:
        raise HTTPException(status_code=503, detail="TikTok integration not configured")

    state = secrets.token_urlsafe(32)
    redis_key = f"tiktok_oauth_state:{state}"
    redis_client.setex(
        redis_key,
        600,
        f"{current_user['org_id']}:{current_user['user_id']}",
    )

    auth_url = (
        "https://business-api.tiktok.com/portal/auth"
        f"?app_id={settings.TIKTOK_APP_ID}"
        f"&state={state}"
        f"&redirect_uri={settings.TIKTOK_REDIRECT_URI}"
    )
    return DataResponse(data={"auth_url": auth_url})


@router.get("/tiktok/oauth/callback")
def tiktok_oauth_callback(
    db: DbSession,
    auth_code: str = Query(...),
    state: str = Query(...),
):
    from app.api.deps import redis_client
    from workers.tiktok_client import TikTokClient, TikTokAPIError

    error_url = f"{settings.FRONTEND_URL}/settings/connections?tiktok=error"

    redis_key = f"tiktok_oauth_state:{state}"
    stored = redis_client.get(redis_key)
    if not stored:
        logger.error("TikTok OAuth: state not found in Redis: %s", state)
        return RedirectResponse(url=error_url)
    redis_client.delete(redis_key)

    org_id, user_id = stored.split(":", 1)

    try:
        client = TikTokClient(access_token="")
        token_data = client.exchange_auth_code(
            settings.TIKTOK_APP_ID, settings.TIKTOK_APP_SECRET, auth_code
        )
    except (TikTokAPIError, Exception) as e:
        logger.error("TikTok token exchange failed: %s", e, exc_info=True)
        return RedirectResponse(url=error_url)

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 86400)
    advertiser_ids = token_data.get("advertiser_ids", [])

    if not access_token or not advertiser_ids:
        logger.error("TikTok OAuth: missing token or advertiser_ids. token_data=%s", token_data)
        return RedirectResponse(url=error_url)

    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    conn = acc_svc.create_tiktok_connection(
        db,
        org_id=org_id,
        user_id=user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
    )
    db.commit()
    db.refresh(conn)

    # Successful OAuth reconnect clears any open TikTok token-expiry alert for
    # the org (org+platform level — the old dead connection lingers). P-2.
    resolve_platform_token_alerts(db, org_id=org_id, platform="tiktok")
    db.commit()

    from workers.tasks.tiktok_structure import sync_tiktok_accounts_for_connection
    sync_tiktok_accounts_for_connection.delay(str(conn.id), org_id, advertiser_ids)

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/settings/connections?tiktok=connected"
    )


@router.get("/google/oauth/initiate")
def google_oauth_initiate(current_user: OwnerUser):
    from urllib.parse import urlencode
    from app.api.deps import redis_client
    if not settings.GOOGLE_ADS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google Ads integration not configured")

    state = secrets.token_urlsafe(32)
    redis_client.setex(
        f"google_oauth_state:{state}",
        600,
        f"{current_user['org_id']}:{current_user['user_id']}",
    )

    params = {
        "client_id": settings.GOOGLE_ADS_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_ADS_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/adwords",
        "access_type": "offline",   # ask for a refresh token
        "prompt": "consent",        # force refresh_token even on reconnect
        "include_granted_scopes": "true",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return DataResponse(data={"auth_url": auth_url})


@router.get("/google/oauth/callback")
def google_oauth_callback(
    db: DbSession,
    code: str = Query(...),
    state: str = Query(...),
):
    import httpx
    from app.api.deps import redis_client

    error_url = f"{settings.FRONTEND_URL}/settings/connections?google=error"

    redis_key = f"google_oauth_state:{state}"
    stored = redis_client.get(redis_key)
    if not stored:
        logger.error("Google OAuth: state not found in Redis: %s", state)
        return RedirectResponse(url=error_url)
    redis_client.delete(redis_key)

    org_id, user_id = stored.split(":", 1)

    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_ADS_CLIENT_ID,
                "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_ADS_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=20.0,
        )
        token_data = resp.json()
    except Exception as e:
        logger.error("Google token exchange failed: %s", e, exc_info=True)
        return RedirectResponse(url=error_url)

    refresh_token = token_data.get("refresh_token")
    access_token = token_data.get("access_token")
    # refresh_token is only returned with access_type=offline + prompt=consent.
    if not refresh_token or not access_token:
        logger.error("Google OAuth: missing tokens in response: %s", token_data)
        return RedirectResponse(url=error_url)

    expires_in = token_data.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    conn = acc_svc.create_google_connection(
        db,
        org_id=org_id,
        user_id=user_id,
        refresh_token=refresh_token,
        access_token=access_token,
        token_expires_at=token_expires_at,
    )
    db.commit()
    db.refresh(conn)

    # Successful OAuth reconnect clears any open Google token-expiry alert for
    # the org. NOTE: create_google_connection stores platform_id="google_ads",
    # so the org+platform clear must match that stored id, not the "google"
    # display label used in the callback URL. P-2.
    resolve_platform_token_alerts(db, org_id=org_id, platform="google_ads")
    db.commit()

    from workers.tasks.google_structure import sync_google_accounts_for_connection
    sync_google_accounts_for_connection.delay(str(conn.id), org_id)

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/settings/connections?google=connected"
    )


@router.delete("/{connection_id}", status_code=204)
def delete_connection(connection_id: str, current_user: OwnerUser, db: DbSession):
    try:
        acc_svc.disconnect_connection(db, connection_id, current_user["org_id"])
        db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
