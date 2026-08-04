"""DB-backed tests for get_table drill-down scoping.

Gates the fix for the Overview→campaign click bug: clicking a campaign drilled
into the Ad Groups level but the ad-group query ignored campaign_id entirely, so
it returned EVERY ad group in the account (ad groups from other campaigns too).

What's pinned here:
  * level="adgroup" + campaign_id → only that campaign's ad groups.
  * level="ad" + campaign_id → only that campaign's ads.
  * level="ad" + adgroup_id → only that ad group's ads.
  * No filter (campaign_id/adgroup_id=None) stays a no-op: all rows returned.
  * Filter is applied to total_count too (pagination reflects the scope).
"""
from datetime import date

from app.services.insights import get_table

from tests.conftest import (
    insert_metrics_daily,
    make_account,
    make_ad,
    make_adgroup,
    make_campaign,
    make_connection,
    make_org,
)

CUR_START = date(2026, 6, 8)
CUR_END = date(2026, 6, 14)


def _seed_two_campaigns(db):
    """Two campaigns, each with its own ad group + ad, all with current-window
    metrics so every level returns rows."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)

    camp_a = make_campaign(db, account_id, name="Alpha")
    camp_b = make_campaign(db, account_id, name="Beta")

    ag_a = make_adgroup(db, account_id, camp_a, name="Alpha-AG")
    ag_b = make_adgroup(db, account_id, camp_b, name="Beta-AG")

    ad_a = make_ad(db, account_id, camp_a, ag_a, name="Alpha-Ad")
    ad_b = make_ad(db, account_id, camp_b, ag_b, name="Beta-Ad")

    for eid, et in [
        (camp_a, "campaign"), (camp_b, "campaign"),
        (ag_a, "adgroup"), (ag_b, "adgroup"),
        (ad_a, "ad"), (ad_b, "ad"),
    ]:
        insert_metrics_daily(db, account_id, eid, CUR_START,
                             entity_type=et, impressions=100, clicks=5, spend=10)
    db.flush()
    return {
        "org_id": org_id, "account_id": account_id,
        "camp_a": camp_a, "camp_b": camp_b,
        "ag_a": ag_a, "ag_b": ag_b, "ad_a": ad_a, "ad_b": ad_b,
    }


def test_adgroup_level_scoped_to_campaign(db):
    ctx = _seed_two_campaigns(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        level="adgroup", campaign_id=ctx["camp_a"],
    )
    assert total == 1
    assert [r["id"] for r in rows] == [ctx["ag_a"]]
    assert rows[0]["campaign_id"] == ctx["camp_a"]


def test_adgroup_level_no_filter_returns_all(db):
    ctx = _seed_two_campaigns(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        level="adgroup",
    )
    assert total == 2
    assert {r["id"] for r in rows} == {ctx["ag_a"], ctx["ag_b"]}


def test_ad_level_scoped_to_campaign(db):
    ctx = _seed_two_campaigns(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        level="ad", campaign_id=ctx["camp_b"],
    )
    assert total == 1
    assert [r["id"] for r in rows] == [ctx["ad_b"]]


def test_ad_level_scoped_to_adgroup(db):
    ctx = _seed_two_campaigns(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        level="ad", adgroup_id=ctx["ag_a"],
    )
    assert total == 1
    assert [r["id"] for r in rows] == [ctx["ad_a"]]


def test_campaign_level_ignores_drilldown_params(db):
    """Campaign level has no parent to scope to — passing campaign_id must not
    filter (or error); both campaigns still returned."""
    ctx = _seed_two_campaigns(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        level="campaign", campaign_id=ctx["camp_a"],
    )
    assert total == 2
    assert {r["id"] for r in rows} == {ctx["camp_a"], ctx["camp_b"]}
