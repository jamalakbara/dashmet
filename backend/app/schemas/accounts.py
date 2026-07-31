from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


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


class ConnectionResponse(BaseModel):
    id: str
    platform: str
    is_active: bool
    scopes: Optional[list[str]] = None
    token_type: str
    connected_by: Optional[str] = None
    connected_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class CreateConnectionRequest(BaseModel):
    platform: str
    access_token: str
    token_type: str = "system_user"
