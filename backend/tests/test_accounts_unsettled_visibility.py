"""DB-backed tests: "unsettled" Meta accounts are visible and readable.

The bug: an ad account whose Meta status is UNSETTLED (resolved to
account_status "unsettled") was previously hidden. The read side now filters
`account_status != "disabled"`, so "active" *and* "unsettled" appear in lists
and are readable via get_account_with_config; only "disabled" is hidden.

Uses the throwaway-schema `db` fixture from conftest.py.
"""
import uuid

import pytest
from sqlalchemy import text

from app.exceptions import NotFoundError
from app.services.accounts import get_account_with_config, list_accounts
from tests.conftest import make_connection, make_org


def _make_account(db, org_id, conn_id, name, status):
    """Insert one account with an explicit account_status (conftest.make_account
    hardcodes 'active', so we inline the insert to vary status)."""
    acct_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO accounts "
            "(id, organization_id, platform_connection_id, platform_id, "
            " external_id, name, currency, timezone, account_status) "
            "VALUES (:id, :org, :conn, 'meta', :ext, :name, 'USD', 'UTC', :status)"
        ),
        {
            "id": acct_id, "org": uuid.UUID(org_id), "conn": uuid.UUID(conn_id),
            "ext": f"act_{acct_id.hex[:8]}", "name": name, "status": status,
        },
    )
    return str(acct_id)


@pytest.fixture
def accounts_by_status(db):
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    ids = {
        "active": _make_account(db, org_id, conn_id, "Active Co", "active"),
        "unsettled": _make_account(db, org_id, conn_id, "Persebaya", "unsettled"),
        "disabled": _make_account(db, org_id, conn_id, "Dead Co", "disabled"),
    }
    db.flush()
    return {"db": db, "org_id": org_id, "ids": ids}


def test_list_accounts_shows_active_and_unsettled_hides_disabled(accounts_by_status):
    db = accounts_by_status["db"]
    org_id = accounts_by_status["org_id"]
    ids = accounts_by_status["ids"]

    accounts, total = list_accounts(db=db, org_id=org_id)

    returned = {str(a.id) for a in accounts}
    assert ids["active"] in returned
    assert ids["unsettled"] in returned
    assert ids["disabled"] not in returned
    assert total == 2


def test_get_account_with_config_returns_unsettled(accounts_by_status):
    db = accounts_by_status["db"]
    org_id = accounts_by_status["org_id"]
    unsettled_id = accounts_by_status["ids"]["unsettled"]

    acct = get_account_with_config(db, unsettled_id, org_id)
    assert acct.account_status == "unsettled"


def test_get_account_with_config_hides_disabled(accounts_by_status):
    db = accounts_by_status["db"]
    org_id = accounts_by_status["org_id"]
    disabled_id = accounts_by_status["ids"]["disabled"]

    with pytest.raises(NotFoundError):
        get_account_with_config(db, disabled_id, org_id)
