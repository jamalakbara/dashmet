import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.exceptions import ConflictError, ForbiddenError, InvalidTokenError, NotFoundError
from app.models.auth import Organization, OrganizationMembership, User
from app.services.auth import create_user_and_org, hash_password


def get_org(db: Session, org_id: str) -> Organization:
    org = db.get(Organization, uuid.UUID(org_id))
    if not org:
        raise NotFoundError("Organization not found")
    return org


def update_org(db: Session, org_id: str, name: str) -> Organization:
    org = get_org(db, org_id)
    org.name = name
    return org


def list_members(db: Session, org_id: str) -> list[dict]:
    memberships = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == uuid.UUID(org_id))
        .all()
    )
    result = []
    for mem in memberships:
        user = mem.user
        is_pending = mem.accepted_at is None
        result.append({
            "id": str(user.id) if user else None,
            "name": user.name if user else None,
            "email": user.email if user else (mem.invite_token and "pending"),
            "role": mem.role,
            "joined_at": mem.accepted_at,
            "invite_pending": is_pending,
        })
    return result


def invite_member(
    db: Session,
    org_id: str,
    invited_by_user_id: str,
    email: str,
    role: str = "member",
) -> OrganizationMembership:
    email = email.lower()
    org_uuid = uuid.UUID(org_id)

    existing_user = db.query(User).filter(User.email == email).first()

    if existing_user:
        existing_mem = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == org_uuid,
                OrganizationMembership.user_id == existing_user.id,
                OrganizationMembership.accepted_at.isnot(None),
            )
            .first()
        )
        if existing_mem:
            raise ConflictError(f"{email} is already a member of this organization")

        pending = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == org_uuid,
                OrganizationMembership.user_id == existing_user.id,
            )
            .first()
        )
        if pending:
            pending.invite_token = secrets.token_urlsafe(32)
            pending.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            return pending

    invite_token = secrets.token_urlsafe(32)
    mem = OrganizationMembership(
        organization_id=org_uuid,
        user_id=existing_user.id if existing_user else None,
        role=role,
        invited_by_user_id=uuid.UUID(invited_by_user_id),
        invite_token=invite_token,
        invite_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(mem)
    return mem


def accept_invite(
    db: Session,
    token: str,
    name: str,
    password: str,
) -> tuple[User, OrganizationMembership]:
    mem = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.invite_token == token)
        .first()
    )
    if not mem:
        raise InvalidTokenError("Invalid invite token")

    now = datetime.now(timezone.utc)
    if mem.invite_expires_at:
        exp = mem.invite_expires_at
        exp_aware = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        if now > exp_aware:
            raise InvalidTokenError("Invite token has expired")

    if mem.user_id is None:
        existing_mem_email = None
        user = User(
            email=f"pending_{token[:8]}@pending.dashmet",
            password_hash=hash_password(password),
            name=name,
            email_verified=True,
        )
        db.add(user)
        db.flush()
        mem.user_id = user.id
    else:
        user = db.get(User, mem.user_id)
        if not user:
            raise InvalidTokenError("User account not found")
        user.name = name
        user.password_hash = hash_password(password)
        user.email_verified = True

    mem.accepted_at = now
    mem.invite_token = None
    return user, mem


def remove_member(
    db: Session,
    org_id: str,
    target_user_id: str,
    requesting_user_id: str,
) -> None:
    if target_user_id == requesting_user_id:
        raise ForbiddenError("Cannot remove yourself from the organization")

    mem = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == uuid.UUID(org_id),
            OrganizationMembership.user_id == uuid.UUID(target_user_id),
        )
        .first()
    )
    if not mem:
        raise NotFoundError("Member not found")

    db.delete(mem)
