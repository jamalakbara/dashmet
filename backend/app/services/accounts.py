import json
import uuid
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.platform import Account, AccountConfig, PlatformConnection
from app.schemas.common import calculate_offset
from app.services.auth import decrypt_token, encrypt_token


def get_org_account_ids(db: Session, org_id: str, redis_client=None) -> set[uuid.UUID]:
    cache_key = f"org_account_ids:{org_id}"
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            ids = json.loads(cached)
            return {uuid.UUID(i) for i in ids}

    rows = (
        db.query(Account.id)
        .filter(Account.organization_id == uuid.UUID(org_id))
        .all()
    )
    result = {row.id for row in rows}

    if redis_client and result:
        redis_client.setex(cache_key, 60, json.dumps([str(i) for i in result]))

    return result


def assert_account_belongs_to_org(
    db: Session, account_id: str, org_id: str
) -> Account:
    account = db.get(Account, uuid.UUID(account_id))
    if not account:
        raise NotFoundError("Account not found")
    if str(account.organization_id) != org_id:
        raise ForbiddenError("Account does not belong to your organization")
    return account


def list_accounts(
    db: Session, org_id: str, page: int = 1, per_page: int = 25
) -> tuple[list[Account], int]:
    org_uuid = uuid.UUID(org_id)
    q = db.query(Account).filter(Account.organization_id == org_uuid)
    total = q.count()
    accounts = q.offset(calculate_offset(page, per_page)).limit(per_page).all()
    return accounts, total


def get_account_with_config(
    db: Session, account_id: str, org_id: str
) -> Account:
    account = assert_account_belongs_to_org(db, account_id, org_id)
    return account


def update_account_config(
    db: Session,
    account_id: str,
    org_id: str,
    primary_conversion_action: Optional[str] = None,
    attribution_window: Optional[str] = None,
    roas_action_type: Optional[str] = None,
) -> AccountConfig:
    account = assert_account_belongs_to_org(db, account_id, org_id)
    config = account.config
    if not config:
        config = AccountConfig(account_id=account.id)
        db.add(config)
        db.flush()

    if primary_conversion_action is not None:
        config.primary_conversion_action = primary_conversion_action
    if attribution_window is not None:
        config.attribution_window = attribution_window
    if roas_action_type is not None:
        config.roas_action_type = roas_action_type

    return config


def list_connections(db: Session, org_id: str) -> list[PlatformConnection]:
    return (
        db.query(PlatformConnection)
        .filter(
            PlatformConnection.organization_id == uuid.UUID(org_id),
        )
        .all()
    )


def _validate_meta_token(access_token: str) -> dict:
    try:
        resp = httpx.get(
            "https://graph.facebook.com/v25.0/me",
            params={"access_token": access_token, "fields": "id,name"},
            timeout=10.0,
        )
        data = resp.json()
        if "error" in data:
            raise ConflictError(
                f"Token validation failed: {data['error'].get('message', 'Unknown error')}"
            )
        return data
    except httpx.RequestError as e:
        raise ConflictError(f"Could not reach Meta API: {e}")


def create_connection(
    db: Session,
    org_id: str,
    user_id: str,
    platform: str,
    access_token: str,
    token_type: str = "system_user",
) -> PlatformConnection:
    if platform == "meta":
        token_info = _validate_meta_token(access_token)
    else:
        raise ConflictError(f"Platform '{platform}' not yet supported")

    encrypted = encrypt_token(access_token)
    conn = PlatformConnection(
        organization_id=uuid.UUID(org_id),
        platform_id=platform,
        access_token=encrypted,
        token_type=token_type,
        scopes=["ads_read", "read_insights"],
        connected_by_user_id=uuid.UUID(user_id),
        is_active=True,
    )
    db.add(conn)
    return conn


def create_tiktok_connection(
    db: Session,
    org_id: str,
    user_id: str,
    access_token: str,
    refresh_token: str,
    token_expires_at,
) -> PlatformConnection:
    from datetime import datetime, timezone
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token)
    conn = PlatformConnection(
        organization_id=uuid.UUID(org_id),
        platform_id="tiktok",
        access_token=encrypted_access,
        refresh_token=encrypted_refresh,
        token_expires_at=token_expires_at,
        token_type="oauth2",
        scopes=["ads_read", "reporting"],
        connected_by_user_id=uuid.UUID(user_id),
        is_active=True,
    )
    db.add(conn)
    return conn


def disconnect_connection(
    db: Session, connection_id: str, org_id: str
) -> None:
    conn = db.get(PlatformConnection, uuid.UUID(connection_id))
    if not conn:
        raise NotFoundError("Connection not found")
    if str(conn.organization_id) != org_id:
        raise ForbiddenError("Connection does not belong to your organization")
    conn.is_active = False
    db.query(Account).filter(
        Account.platform_connection_id == conn.id
    ).update({"account_status": "disabled"})
