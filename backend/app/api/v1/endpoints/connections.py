import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DbSession, OwnerUser
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
    auth_code: str = Query(...),
    state: str = Query(...),
    db: DbSession = None,
):
    from app.api.deps import redis_client
    from workers.tiktok_client import TikTokClient, TikTokAPIError

    error_url = f"{settings.FRONTEND_URL}/settings/connections?tiktok=error"

    redis_key = f"tiktok_oauth_state:{state}"
    stored = redis_client.get(redis_key)
    if not stored:
        return RedirectResponse(url=error_url)
    redis_client.delete(redis_key)

    org_id, user_id = stored.decode().split(":", 1)

    try:
        client = TikTokClient(access_token="")
        token_data = client.exchange_auth_code(
            settings.TIKTOK_APP_ID, settings.TIKTOK_APP_SECRET, auth_code
        )
    except (TikTokAPIError, Exception):
        return RedirectResponse(url=error_url)

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 86400)
    advertiser_ids = token_data.get("advertiser_ids", [])

    if not access_token or not advertiser_ids:
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


@router.delete("/{connection_id}", status_code=204)
def delete_connection(connection_id: str, current_user: OwnerUser, db: DbSession):
    try:
        acc_svc.disconnect_connection(db, connection_id, current_user["org_id"])
        db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
