"""Per-member account access (the membership_accounts allowlist).

Enforces the invariant that a member sees only the accounts an owner granted,
owners are unrestricted, and grant writes stay inside the org. Covers the three
enforcement chokepoints (resolver/assert, list scoping) and the owner grant API.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.exceptions import ConflictError, ForbiddenError
from app.models.auth import MembershipAccount, OrganizationMembership, User
from app.services import accounts as acc_svc
from app.services import org as org_svc
from app.services.auth import create_user_and_org, hash_password
from tests.conftest import make_account, make_connection, make_org


def _owner(db, email="owner@example.com", org_name="Acme"):
    user = create_user_and_org(db, "Owner", email, "password123", org_name)
    db.flush()
    mem = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == user.id)
        .first()
    )
    return str(user.id), str(mem.organization_id), str(mem.id)


def _add_member(db, org_id, email="member@example.com"):
    """An accepted member of an existing org. Returns (user_id, membership_id)."""
    user = User(
        email=email, password_hash=hash_password("password123"),
        name="Member", email_verified=True,
    )
    db.add(user)
    db.flush()
    mem = OrganizationMembership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role="member",
        accepted_at=datetime.now(timezone.utc),
    )
    db.add(mem)
    db.flush()
    return str(user.id), str(mem.id)


def _cu(user_id, org_id, role):
    return {"user_id": user_id, "org_id": org_id, "role": role, "email": "x@x.co"}


def _seed_account(db, org_id):
    conn = make_connection(db, org_id)
    return make_account(db, org_id, conn)


# ── resolver ────────────────────────────────────────────────────────────────

def test_owner_is_unrestricted(db):
    owner_id, org_id, _ = _owner(db)
    assert acc_svc.get_accessible_account_ids(db, _cu(owner_id, org_id, "owner")) is None


def test_member_without_grants_sees_nothing(db):
    _, org_id, _ = _owner(db)
    member_id, _mid = _add_member(db, org_id)
    assert acc_svc.get_accessible_account_ids(db, _cu(member_id, org_id, "member")) == set()


def test_member_with_grant_sees_only_granted(db):
    _, org_id, _ = _owner(db)
    member_id, mid = _add_member(db, org_id)
    acc_a = _seed_account(db, org_id)
    _seed_account(db, org_id)  # a second, ungranted account
    db.flush()

    org_svc.set_member_accounts(db, org_id, mid, [acc_a])
    db.flush()

    allowed = acc_svc.get_accessible_account_ids(db, _cu(member_id, org_id, "member"))
    assert allowed == {uuid.UUID(acc_a)}


# ── assert / list scoping ───────────────────────────────────────────────────

def test_assert_denies_ungranted_account(db):
    _, org_id, _ = _owner(db)
    _member_id, mid = _add_member(db, org_id)
    granted = _seed_account(db, org_id)
    ungranted = _seed_account(db, org_id)
    db.flush()
    org_svc.set_member_accounts(db, org_id, mid, [granted])
    db.flush()

    allowed = {uuid.UUID(granted)}
    # Granted → ok
    acc_svc.assert_account_belongs_to_org(db, granted, org_id, allowed_ids=allowed)
    # Ungranted (still same org) → 403
    with pytest.raises(ForbiddenError):
        acc_svc.assert_account_belongs_to_org(db, ungranted, org_id, allowed_ids=allowed)
    # Owner (allowed_ids=None) → ok for the same account
    acc_svc.assert_account_belongs_to_org(db, ungranted, org_id, allowed_ids=None)


def test_list_accounts_restrict_ids_scopes_rows(db):
    _, org_id, _ = _owner(db)
    granted = _seed_account(db, org_id)
    _seed_account(db, org_id)
    db.flush()

    rows, total = acc_svc.list_accounts(db, org_id, restrict_ids={uuid.UUID(granted)})
    assert total == 1
    assert [str(a.id) for a in rows] == [granted]

    # Empty grant set → no rows.
    rows, total = acc_svc.list_accounts(db, org_id, restrict_ids=set())
    assert total == 0 and rows == []

    # None (owner) → all.
    _, total_all = acc_svc.list_accounts(db, org_id, restrict_ids=None)
    assert total_all == 2


# ── owner grant API ─────────────────────────────────────────────────────────

def test_set_member_accounts_replaces_grant_set(db):
    _, org_id, _ = _owner(db)
    _member_id, mid = _add_member(db, org_id)
    a1, a2, a3 = (_seed_account(db, org_id) for _ in range(3))
    db.flush()

    org_svc.set_member_accounts(db, org_id, mid, [a1, a2])
    db.flush()
    assert set(org_svc.list_member_accounts(db, org_id, mid)) == {a1, a2}

    # Replace, not append.
    org_svc.set_member_accounts(db, org_id, mid, [a3])
    db.flush()
    assert org_svc.list_member_accounts(db, org_id, mid) == [a3]
    assert db.query(MembershipAccount).filter(
        MembershipAccount.membership_id == uuid.UUID(mid)
    ).count() == 1


def test_set_member_accounts_rejects_cross_org_account(db):
    _, org_a, _ = _owner(db, email="a@example.com", org_name="OrgA")
    _member_id, mid = _add_member(db, org_a)
    # An account in a different org.
    other_org = make_org(db, name="OrgB")
    foreign = _seed_account(db, other_org)
    db.flush()

    with pytest.raises(ForbiddenError):
        org_svc.set_member_accounts(db, org_a, mid, [foreign])


def test_cannot_scope_an_owner(db):
    _owner_id, org_id, owner_mid = _owner(db)
    acc = _seed_account(db, org_id)
    db.flush()
    with pytest.raises(ConflictError):
        org_svc.set_member_accounts(db, org_id, owner_mid, [acc])


# ── endpoint chokepoint (insights resolver) ─────────────────────────────────

def test_insights_resolver_enforces_member_grant(db):
    """The shared insights resolver — every insights read endpoint routes
    through it — 403s a member on an ungranted account and resolves after grant."""
    from fastapi import HTTPException

    from app.api.v1.endpoints.insights import _resolve_dates

    _, org_id, _ = _owner(db)
    member_id, mid = _add_member(db, org_id)
    acc = _seed_account(db, org_id)
    db.flush()
    cu = _cu(member_id, org_id, "member")

    with pytest.raises(HTTPException) as ei:
        _resolve_dates(acc, cu, db, "last_30d", None, None)
    assert ei.value.status_code == 403

    org_svc.set_member_accounts(db, org_id, mid, [acc])
    db.flush()
    _ds, _de, account, _preset = _resolve_dates(acc, cu, db, "last_30d", None, None)
    assert str(account.id) == acc
