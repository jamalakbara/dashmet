"""Shared fixtures for DB-backed insights tests.

The insights service is raw-Postgres-specific (uuid[] arrays, date_trunc,
FILTER (WHERE ...)), so its queries can only be exercised against a real
Postgres 16 instance — a fake session can't. Rather than mutate the shared
`dashmet` database, every DB-backed test runs inside its own throwaway
Postgres *schema* on the same server: created fresh per test session,
`search_path` scoped to it, tables built from `Base.metadata`, dropped at
teardown. Nothing outside the schema is touched.

Only tests that request the `db` fixture pull this in; the existing fake-session
unit tests are unaffected.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base

# Import every model module so Base.metadata is fully populated before create_all.
import app.models.auth          # noqa: F401
import app.models.platform      # noqa: F401
import app.models.structure     # noqa: F401
import app.models.metrics       # noqa: F401
import app.models.notifications # noqa: F401

TEST_SCHEMA = "test_compare_prev"


@pytest.fixture(scope="session")
def _engine():
    """Engine whose every connection defaults into an isolated test schema."""
    engine = create_engine(settings.DATABASE_URL, poolclass=None)

    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{TEST_SCHEMA}"'))

    # Force search_path on every checkout so create_all and the service SQL
    # (which uses unqualified table names) both land in the test schema.
    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute(f'SET search_path TO "{TEST_SCHEMA}"')
        cur.close()

    Base.metadata.create_all(engine)
    # The service joins account_configs; every account needs a platform row for
    # the FK on accounts.platform_id.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO platforms (id, name) VALUES ('meta', 'Meta') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )

    yield engine

    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE'))
    engine.dispose()


@pytest.fixture
def db(_engine):
    """A Session in a transaction rolled back after each test (full isolation)."""
    connection = _engine.connect()
    trans = connection.begin()
    Session = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


# ─── Seeding helpers ────────────────────────────────────────────────────────

def make_org(db, name="Org") -> str:
    org_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": org_id, "name": name, "slug": f"{name}-{org_id.hex[:8]}"},
    )
    return str(org_id)


def make_connection(db, org_id: str) -> str:
    conn_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO platform_connections "
            "(id, organization_id, platform_id, access_token, token_type, is_active) "
            "VALUES (:id, :org, 'meta', 'tok', 'system_user', true)"
        ),
        {"id": conn_id, "org": uuid.UUID(org_id)},
    )
    return str(conn_id)


def make_account(db, org_id: str, conn_id: str, name="Acct", tz="UTC") -> str:
    acct_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO accounts "
            "(id, organization_id, platform_connection_id, platform_id, "
            " external_id, name, currency, timezone, account_status) "
            "VALUES (:id, :org, :conn, 'meta', :ext, :name, 'USD', :tz, 'active')"
        ),
        {
            "id": acct_id, "org": uuid.UUID(org_id), "conn": uuid.UUID(conn_id),
            "ext": f"act_{acct_id.hex[:8]}", "name": name, "tz": tz,
        },
    )
    return str(acct_id)


def make_campaign(db, account_id: str, name="Camp", status="active") -> str:
    camp_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO campaigns "
            "(id, account_id, platform_id, platform_campaign_id, name, status, effective_status, objective) "
            "VALUES (:id, :acct, 'meta', :pcid, :name, :status, :status, 'OUTCOME_SALES')"
        ),
        {
            "id": camp_id, "acct": uuid.UUID(account_id),
            "pcid": f"c_{camp_id.hex[:8]}", "name": name, "status": status,
        },
    )
    return str(camp_id)


def make_adgroup(db, account_id: str, campaign_id: str, name="AdGroup", status="active") -> str:
    ag_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO ad_groups "
            "(id, campaign_id, account_id, platform_id, platform_adgroup_id, name, status, effective_status) "
            "VALUES (:id, :camp, :acct, 'meta', :pgid, :name, :status, :status)"
        ),
        {
            "id": ag_id, "camp": uuid.UUID(campaign_id), "acct": uuid.UUID(account_id),
            "pgid": f"ag_{ag_id.hex[:8]}", "name": name, "status": status,
        },
    )
    return str(ag_id)


def make_ad(db, account_id: str, campaign_id: str, adgroup_id: str, name="Ad", status="active") -> str:
    ad_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO ads "
            "(id, ad_group_id, campaign_id, account_id, platform_id, platform_ad_id, name, status, effective_status) "
            "VALUES (:id, :ag, :camp, :acct, 'meta', :paid, :name, :status, :status)"
        ),
        {
            "id": ad_id, "ag": uuid.UUID(adgroup_id), "camp": uuid.UUID(campaign_id),
            "acct": uuid.UUID(account_id), "paid": f"ad_{ad_id.hex[:8]}",
            "name": name, "status": status,
        },
    )
    return str(ad_id)


def insert_metrics_daily(
    db, account_id: str, entity_id: str, d: date,
    *, entity_type="campaign", impressions=0, clicks=0, spend=0,
    reach=0, inline_link_clicks=0,
):
    """One metrics_daily row. Base metrics only; ratios are computed by the
    service AFTER aggregation, so we deliberately do NOT store ctr/cpm/etc."""
    db.execute(
        text(
            "INSERT INTO metrics_daily "
            "(id, entity_type, entity_id, platform_id, account_id, date, "
            " impressions, reach, clicks, spend, inline_link_clicks) "
            "VALUES (:id, :et, :eid, 'meta', :acct, :d, "
            " :impr, :reach, :clicks, :spend, :ilc)"
        ),
        {
            "id": uuid.uuid4(), "et": entity_type, "eid": uuid.UUID(entity_id),
            "acct": uuid.UUID(account_id), "d": d, "impr": impressions,
            "reach": reach, "clicks": clicks, "spend": spend, "ilc": inline_link_clicks,
        },
    )


def insert_action_stat(
    db, account_id: str, entity_id: str, d: date, field_name: str,
    action_type: str, value, *, entity_type="campaign",
):
    db.execute(
        text(
            "INSERT INTO metric_action_stats "
            "(id, entity_type, entity_id, platform_id, account_id, date, "
            " field_name, action_type, value) "
            "VALUES (:id, :et, :eid, 'meta', :acct, :d, :fn, :at, :val)"
        ),
        {
            "id": uuid.uuid4(), "et": entity_type, "eid": uuid.UUID(entity_id),
            "acct": uuid.UUID(account_id), "d": d, "fn": field_name,
            "at": action_type, "val": value,
        },
    )


@pytest.fixture
def seeded_account(db):
    """An org + connection + account, all committed to the test transaction."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    db.flush()
    return {"org_id": org_id, "account_id": account_id}
