from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict

# A token within this window of expiry is "expiring" (warn before it dies so a
# proactive refresh/re-paste can happen — the connect flow captures the real
# expiry from Meta debug_token).
TOKEN_EXPIRING_WINDOW = timedelta(days=7)


class AccountConfigPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    primary_conversion_action: Optional[str] = None
    attribution_window: Optional[str] = None
    roas_action_type: Optional[str] = None


class AccountConfigUpdateRequest(BaseModel):
    primary_conversion_action: Optional[str] = None
    attribution_window: Optional[str] = None
    roas_action_type: Optional[str] = None
    account_type: Optional[Literal["standard", "cpas"]] = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    external_id: str
    name: str
    currency: str
    timezone: str
    account_status: str
    account_type: str
    business_name: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    config: Optional[AccountConfigPublic] = None

    @classmethod
    def from_orm_account(cls, account) -> "AccountResponse":
        return cls(
            id=str(account.id),
            platform=account.platform_id,
            external_id=account.external_id,
            name=account.name,
            currency=account.currency,
            timezone=account.timezone,
            account_status=account.account_status,
            account_type=account.account_type,
            business_name=account.business_name,
            last_synced_at=account.synced_at,
            config=AccountConfigPublic.model_validate(account.config) if account.config else None,
        )


def _derive_health(
    token_expires_at: Optional[datetime], last_error: Optional[str]
) -> str:
    """Derived connection health (pure read, no stored enum column).

    Precedence: a live ``last_error`` is the strongest signal ("error"); then
    an expired token ("expired"); then a token expiring within the window
    ("expiring"); otherwise "healthy". A NULL ``token_expires_at`` (e.g. a true
    never-expiring system-user token, or an un-probed connection) is treated as
    not-expiring for the expiry checks.
    """
    if last_error:
        return "error"
    if token_expires_at is not None:
        now = datetime.now(timezone.utc)
        # token_expires_at is stored tz-aware (DateTime(timezone=True)).
        if token_expires_at <= now:
            return "expired"
        if token_expires_at <= now + TOKEN_EXPIRING_WINDOW:
            return "expiring"
    return "healthy"


class ConnectionResponse(BaseModel):
    id: str
    platform: str
    is_active: bool
    scopes: Optional[list[str]] = None
    token_type: str
    connected_by: Optional[str] = None
    connected_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    health: str = "healthy"

    @classmethod
    def from_orm_connection(cls, c) -> "ConnectionResponse":
        return cls(
            id=str(c.id),
            platform=c.platform_id,
            is_active=c.is_active,
            scopes=c.scopes,
            token_type=c.token_type,
            connected_by=c.connected_by.name if c.connected_by else None,
            connected_at=c.created_at,
            last_used_at=c.last_used_at,
            token_expires_at=c.token_expires_at,
            last_error=c.last_error,
            last_error_at=c.last_error_at,
            health=_derive_health(c.token_expires_at, c.last_error),
        )


class CreateConnectionRequest(BaseModel):
    platform: str
    access_token: str
    token_type: str = "system_user"
