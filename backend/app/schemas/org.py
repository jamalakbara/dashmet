from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime


class OrgUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MemberResponse(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    email: str
    role: str
    joined_at: Optional[datetime] = None
    invite_pending: bool = False


class InviteRequest(BaseModel):
    email: EmailStr
    role: Literal["member"] = "member"


class AcceptInviteRequest(BaseModel):
    token: str
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)
