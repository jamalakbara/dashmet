from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


def validate_password_strength(value: str) -> str:
    """Enforce a minimum complexity floor: >=8 chars with at least one
    lowercase, one uppercase, and one digit. Length is also declared via
    Field(min_length=8) for a clean 422, but re-checked here so this function
    is a single source of truth reusable by any password field."""
    errors = []
    if len(value) < 8:
        errors.append("at least 8 characters")
    if not any(c.islower() for c in value):
        errors.append("a lowercase letter")
    if not any(c.isupper() for c in value):
        errors.append("an uppercase letter")
    if not any(c.isdigit() for c in value):
        errors.append("a digit")
    if errors:
        raise ValueError("Password must contain " + ", ".join(errors))
    return value


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)
    org_name: str = Field(min_length=1, max_length=255)

    _validate_password = field_validator("password")(validate_password_strength)


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

    _validate_password = field_validator("new_password")(validate_password_strength)


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
