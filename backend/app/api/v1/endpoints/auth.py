import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, redis_client
from app.config import settings
from app.database import get_db
from app.exceptions import ConflictError, InvalidTokenError, UnverifiedEmailError
from app.models.auth import OrganizationMembership, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    OrgPublic,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserPublic,
    VerifyEmailRequest,
)
from app.schemas.common import DataResponse
from app.services import auth as auth_svc
from app.services import email as email_svc
from app.services.email import EmailError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/signup", status_code=201)
def signup(body: SignupRequest, db: DbSession):
    try:
        user = auth_svc.create_user_and_org(
            db, body.name, body.email, body.password, body.org_name
        )
        db.commit()
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Send AFTER commit: the account exists regardless of delivery outcome.
    try:
        email_svc.send_verification_email(
            user.email, user.email_verify_token, user.name
        )
    except EmailError as e:
        logger.error("Verification email to %s failed: %s", user.email, e)

    return DataResponse(data={"message": "Account created. Check your email to verify."})


@router.post("/verify-email")
def verify_email(body: VerifyEmailRequest, db: DbSession):
    try:
        user = auth_svc.verify_email(db, body.token)
        db.flush()

        mem = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.accepted_at.isnot(None),
            )
            .first()
        )
        if not mem:
            raise HTTPException(status_code=400, detail="No active membership found")

        token = auth_svc.create_access_token(
            str(user.id), str(mem.organization_id), mem.role, user.email
        )
        db.commit()

        return DataResponse(
            data=TokenResponse(
                access_token=token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            )
        )
    except InvalidTokenError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _client_ip(request: Request) -> str:
    # Railway/other proxies set X-Forwarded-For; trust the first hop. Falls back
    # to the socket peer for direct connections.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login")
def login(body: LoginRequest, request: Request, db: DbSession):
    ip = _client_ip(request)

    if auth_svc.login_rate_limited(redis_client, body.email, ip):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
        )

    user = db.query(User).filter(User.email == body.email.lower()).first()

    if not user or not auth_svc.verify_password(body.password, user.password_hash):
        auth_svc.record_login_failure(redis_client, body.email, ip)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.email_verified:
        raise HTTPException(
            status_code=401,
            detail="Email not verified. Check your inbox.",
        )

    mem = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.accepted_at.isnot(None),
        )
        .first()
    )
    if not mem:
        raise HTTPException(status_code=403, detail="No active organization membership")

    from app.models.auth import Organization
    org = db.get(Organization, mem.organization_id)

    token = auth_svc.create_access_token(
        str(user.id), str(mem.organization_id), mem.role, user.email
    )

    from datetime import datetime, timezone
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    auth_svc.clear_login_failures(redis_client, body.email, ip)

    return DataResponse(
        data=LoginResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserPublic(id=str(user.id), name=user.name, email=user.email),
            org=OrgPublic(
                id=str(org.id),
                name=org.name,
                slug=org.slug,
                role=mem.role,
            ),
        )
    )


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: DbSession):
    user = auth_svc.initiate_password_reset(db, body.email)
    if user:
        db.commit()
        # Send AFTER commit; never reveal whether the email exists to the caller.
        try:
            email_svc.send_password_reset_email(user.email, user.reset_password_token)
        except EmailError as e:
            logger.error("Password reset email to %s failed: %s", user.email, e)
    return DataResponse(
        data={"message": "If that email exists, a reset link has been sent."}
    )


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: DbSession):
    try:
        auth_svc.reset_password(db, body.token, body.new_password)
        db.commit()
        return DataResponse(data={"message": "Password updated. You can now log in."})
    except InvalidTokenError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/logout", status_code=204)
def logout(current_user: CurrentUser):
    jti = current_user.get("jti")
    if jti:
        from jose import jwt as jose_jwt
        from app.config import settings as cfg

        auth_svc.blacklist_token(
            jti,
            __import__("datetime").datetime.utcnow()
            + __import__("datetime").timedelta(
                minutes=cfg.ACCESS_TOKEN_EXPIRE_MINUTES
            ),
            redis_client,
        )


@router.get("/me")
def me(current_user: CurrentUser, db: DbSession):
    from app.models.auth import Organization, OrganizationMembership, User

    user = db.get(User, current_user["user_id"])
    org = db.get(Organization, current_user["org_id"])

    return DataResponse(
        data=MeResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            org=OrgPublic(
                id=str(org.id),
                name=org.name,
                slug=org.slug,
                role=current_user["role"],
            ),
        )
    )
