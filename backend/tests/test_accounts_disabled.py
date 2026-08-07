"""Unit tests for disabled-account read filtering in the accounts service.

`get_account_with_config` backs selected-account resolution (and the
`GET /accounts/{id}` endpoint). A disabled account must read as gone (404),
same as `list_accounts` already hides it — otherwise a stale client selection
(an `account_id` kept from before a disconnect+reconnect) resolves a dead
account instead of falling back to a live one.

The DB test harness is not built yet (PRD §11); these use a fake session that
returns a canned Account, matching the pattern in test_insights_filter.py.
"""
import uuid
import types

import pytest

from app.exceptions import ForbiddenError, NotFoundError
from app.services.accounts import get_account_with_config

ORG_ID = str(uuid.uuid4())
ACCOUNT_ID = str(uuid.uuid4())


def _account(status="active", org_id=ORG_ID):
    return types.SimpleNamespace(
        id=uuid.UUID(ACCOUNT_ID),
        organization_id=uuid.UUID(org_id),
        account_status=status,
    )


class _FakeSession:
    def __init__(self, account):
        self._account = account

    def get(self, _model, _pk):
        return self._account


def test_active_account_is_returned():
    db = _FakeSession(_account(status="active"))
    out = get_account_with_config(db, ACCOUNT_ID, ORG_ID)
    assert out.account_status == "active"


def test_disabled_account_reads_as_not_found():
    db = _FakeSession(_account(status="disabled"))
    with pytest.raises(NotFoundError):
        get_account_with_config(db, ACCOUNT_ID, ORG_ID)


def test_missing_account_is_not_found():
    db = _FakeSession(None)
    with pytest.raises(NotFoundError):
        get_account_with_config(db, ACCOUNT_ID, ORG_ID)


def test_cross_org_account_is_forbidden_before_status_check():
    # Tenant isolation still takes precedence — a foreign org's account is 403,
    # not a status-leaking 404, even if it happens to be disabled.
    db = _FakeSession(_account(status="disabled", org_id=str(uuid.uuid4())))
    with pytest.raises(ForbiddenError):
        get_account_with_config(db, ACCOUNT_ID, ORG_ID)
