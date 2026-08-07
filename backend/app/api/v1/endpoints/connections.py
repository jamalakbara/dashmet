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

router = APIRouter()


@router.get("")
def list_connections(current_user: CurrentUser, db: DbSession):
    conns = acc_svc.list_connections(db, current_user["org_id"])
    return DataResponse(
        data=[
            ConnectionResponse(
                id=str(c.id),
                platform=c.platform_id,
                is_active=c.is_active,
                scopes=c.scopes,
                token_type=c.token_type,
                connected_by=c.connected_by.name if c.connected_by else None,
                connected_at=c.created_at,
                last_used_at=c.last_used_at,
            )
            for c in conns
        ]
    )


@router.post("", status_code=201)
def create_connection(
    body: CreateConnectionRequest, current_user: OwnerUser, db: DbSession
):
    try:
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

        conn = acc_svc.create_connection(
            db,
            org_id=current_user["org_id"],
            user_id=current_user["user_id"],
            platform=body.platform,
            access_token=body.access_token,
            token_type=body.token_type,
        )
        db.commit()
        db.refresh(conn)

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
