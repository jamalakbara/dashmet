"""Org membership: invite / list / remove.

Regression coverage for the members bug — pending invites (no user account
yet, user_id NULL) were unaddressable: they showed no email and couldn't be
removed. Fix stores the invited email on the membership, dedups repeat
invites, and keys removal on the membership PK instead of user_id.
"""
import uuid

import pytest

from app.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.auth import OrganizationMembership, User
from app.services import org as org_svc
from app.services.auth import create_user_and_org


def _owner(db, email="owner@example.com", org_name="Acme"):
    """Create an owner user + org, return (user_id, org_id)."""
    user = create_user_and_org(db, "Owner", email, "password123", org_name)
    db.flush()
    mem = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == user.id)
        .first()
    )
    return str(user.id), str(mem.organization_id)


def test_invite_new_email_creates_pending_with_email(db):
    _, org_id = _owner(db)

    mem = org_svc.invite_member(db, org_id, _owner_id(db, org_id), "new@example.com")
    db.flush()

    assert mem.user_id is None
    assert mem.invite_email == "new@example.com"
    assert mem.accepted_at is None
    assert mem.invite_token is not None


def test_invite_lowercases_email(db):
    owner_id, org_id = _owner(db)
    mem = org_svc.invite_member(db, org_id, owner_id, "MixedCase@Example.com")
    db.flush()
    assert mem.invite_email == "mixedcase@example.com"


def test_repeat_invite_same_email_dedups(db):
    owner_id, org_id = _owner(db)

    m1 = org_svc.invite_member(db, org_id, owner_id, "dup@example.com")
    db.flush()
    m2 = org_svc.invite_member(db, org_id, owner_id, "dup@example.com")
    db.flush()

    assert m1.id == m2.id  # same row reused, token rotated
    pending = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.invite_email == "dup@example.com")
        .count()
    )
    assert pending == 1


def test_list_members_exposes_pending_email_and_membership_id(db):
    owner_id, org_id = _owner(db)
    org_svc.invite_member(db, org_id, owner_id, "pending@example.com")
    db.flush()

    members = org_svc.list_members(db, org_id)
    pending = next(m for m in members if m["invite_pending"])

    assert pending["membership_id"]  # always present
    assert pending["id"] is None      # no user account yet
    assert pending["email"] == "pending@example.com"


def test_remove_pending_member_by_membership_id(db):
    owner_id, org_id = _owner(db)
    mem = org_svc.invite_member(db, org_id, owner_id, "gone@example.com")
    db.flush()
    membership_id = str(mem.id)

    org_svc.remove_member(db, org_id, membership_id, owner_id)
    db.flush()

    assert db.get(OrganizationMembership, uuid.UUID(membership_id)) is None


def test_cannot_remove_self(db):
    owner_id, org_id = _owner(db)
    own_mem = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == uuid.UUID(owner_id))
        .first()
    )
    with pytest.raises(ForbiddenError):
        org_svc.remove_member(db, org_id, str(own_mem.id), owner_id)


def test_remove_unknown_membership_raises_not_found(db):
    owner_id, org_id = _owner(db)
    with pytest.raises(NotFoundError):
        org_svc.remove_member(db, org_id, str(uuid.uuid4()), owner_id)


def test_tenant_isolation_cannot_remove_other_orgs_member(db):
    owner_a, org_a = _owner(db, email="a@example.com", org_name="OrgA")
    owner_b, org_b = _owner(db, email="b@example.com", org_name="OrgB")

    mem_b = org_svc.invite_member(db, org_b, owner_b, "member@orgb.com")
    db.flush()

    # Owner A scopes the delete to org_a; membership belongs to org_b → not found.
    with pytest.raises(NotFoundError):
        org_svc.remove_member(db, org_a, str(mem_b.id), owner_a)

    assert db.get(OrganizationMembership, mem_b.id) is not None


def test_invite_existing_member_conflicts(db):
    owner_id, org_id = _owner(db)
    # Owner is already an accepted member of their own org.
    with pytest.raises(ConflictError):
        org_svc.invite_member(db, org_id, owner_id, "owner@example.com")


def test_accept_invite_uses_real_invited_email(db):
    owner_id, org_id = _owner(db)
    mem = org_svc.invite_member(db, org_id, owner_id, "real@example.com")
    db.flush()

    user, accepted = org_svc.accept_invite(
        db, mem.invite_token, "Real Person", "password123"
    )
    db.flush()

    # The account is created with the invited address, not a pending_* stub.
    assert user.email == "real@example.com"
    assert "pending" not in user.email
    assert accepted.user_id == user.id
    assert accepted.accepted_at is not None
    assert accepted.invite_token is None
    assert accepted.invite_email is None  # cleared on accept


def test_accept_invite_attaches_to_existing_account(db):
    # Same email already has an account (invited to a second org).
    owner_a, org_a = _owner(db, email="a@example.com", org_name="OrgA")
    existing = create_user_and_org(
        db, "Existing", "shared@example.com", "origpassword", "TheirOrg"
    )
    db.flush()

    mem = org_svc.invite_member(db, org_a, owner_a, "shared@example.com")
    db.flush()
    user, accepted = org_svc.accept_invite(
        db, mem.invite_token, "Ignored", "newpassword"
    )
    db.flush()

    # Reuses the existing account — no duplicate user, password untouched.
    assert user.id == existing.id
    assert accepted.user_id == existing.id
    assert (
        db.query(User).filter(User.email == "shared@example.com").count() == 1
    )


def _owner_id(db, org_id: str) -> str:
    mem = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == uuid.UUID(org_id),
            OrganizationMembership.role == "owner",
        )
        .first()
    )
    return str(mem.user_id)
