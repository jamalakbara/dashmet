from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)
    org_name: str = Field(min_length=1, max_length=255)


class VerifyEmailRequest(BaseModel):
    token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserPublic(BaseModel):
    id: str
    name: str
    email: str


class OrgPublic(BaseModel):
    id: str
    name: str
    slug: str
    role: str


class LoginResponse(TokenResponse):
    user: UserPublic
    org: OrgPublic


class MeResponse(BaseModel):
    id: str
    email: str
    name: str
    org: OrgPublic
