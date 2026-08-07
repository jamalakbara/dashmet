"""Endpoint tests for the AI diagnosis card: POST /insights/overview/summary
and GET /insights/overview/summary/peek, including the Redis cache.

The insights service is raw-Postgres-specific and the shared `db` fixture needs
a reachable Postgres (see conftest). Rather than gate these behind a live DB,
these tests call the endpoint FUNCTIONS directly and mock the seams the handler
sits between:

  * the three shared read functions (`insights_svc.get_overview`,
    `insights_svc.get_table`, `insights_svc.get_timeseries`),
  * the OpenAI call (`ai_summary_svc.generate_overview_diagnosis`),
  * the Redis client (`insights_ep.redis_client`) — patched to a fake so
    `.get()`/`.setex()` are fully controllable (no live Redis).

That lets us pin the handler's own logic — tenant-error passthrough,
read→diagnose parity (P-6), the cache hit/miss/force/peek paths, the freshness
token in the key (P-1), and AISummaryError→502-never-cached (P-4) — with zero
DB, zero Redis, and zero network.

Each test documents exactly which layer is mocked and why.

Run:
    cd backend && \
    $HOME/.pyenv/versions/3.12.13/bin/python -m pytest tests/test_overview_summary_endpoint.py -v
"""
import types
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from app.api.v1.endpoints import insights as insights_ep
from app.exceptions import ForbiddenError
from app.schemas.insights import OverviewSummaryResponse
from app.services import ai_summary as ai_summary_svc

# The freshness token get_overview returns (MAX fetched_at). Fixed so key
# derivation is deterministic across tests.
_CACHED_AT = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def _overview_payload(cached_at=_CACHED_AT):
    """Shaped like insights_svc.get_overview's return value — now including the
    `cached_at` freshness token (MAX fetched_at, or None for an empty period)."""
    return {
        "period": {"date_start": date(2026, 6, 1), "date_stop": date(2026, 6, 30),
                   "preset": "last_30d"},
        "summary": {"spend": 12345.67, "impressions": 2_500_000, "clicks": 48_000,
                    "ctr": 1.92, "cpm": 4.94, "conversions": 1_234, "roas": 3.75},
        "previous": {"spend": 11000.0},
        "vs_previous": {"spend": 12.3},
        "top_campaigns": [{"name": "Alpha", "spend": 5000.0, "ctr": 2.1,
                           "conversions": 600.0, "roas": 4.0}],
        "cached_at": cached_at,
    }


def _campaigns_payload():
    """Shaped like insights_svc.get_table(level="campaign", compare_previous=True):
    a (rows, total) tuple — the handler unpacks `campaigns, _total`."""
    rows = [
        {"name": "Alpha", "status": "ACTIVE", "objective": "OUTCOME_SALES",
         "metrics": {"spend": 5000.0, "roas": 4.0, "conversions": 600.0, "ctr": 2.1},
         "metrics_previous": {"spend": 4800.0, "roas": 6.0, "conversions": 900.0, "ctr": 2.3}},
    ]
    return rows, len(rows)


def _timeseries_payload():
    """Shaped like insights_svc.get_timeseries(compare_previous=True)."""
    return {
        "series": [{"date": date(2026, 6, 1), "spend": 400.0, "conversions": 42}],
        "previous_series": [{"date": date(2026, 5, 1), "spend": 380.0, "conversions": 60}],
    }


def _card():
    """A valid structured diagnosis the mocked AI service returns."""
    return {
        "headline": "Conversions down on flat spend.",
        "driver": "Alpha (SALES) drove the drop.",
        "watch": "CTR softening.",
        "next_step": "Audit Alpha targeting.",
    }


def _account(currency="USD", tz="UTC"):
    return types.SimpleNamespace(currency=currency, timezone=tz, name="Acct")


def _owner(org_id="org-1"):
    return {"org_id": org_id, "sub": str(uuid.uuid4()), "role": "owner"}


class _FakeRedis:
    """In-process stand-in for the redis client the endpoint imports as
    `redis_client`. Records every `.get()`/`.setex()` call so tests can assert
    on the key, TTL, and stored payload without touching a real server.

    `.get()` returns whatever `store[key]` holds (default: nothing → miss). A
    test can pre-seed a hit via `.seed(key, value)` or by driving `.setex()`."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []

    def seed(self, key: str, value: str) -> None:
        self.store[key] = value

    def get(self, key):
        self.get_calls.append(key)
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value


def _stub_all_reads(monkeypatch, *, account, overview=None, campaigns=None,
                    timeseries=None, redis=None):
    """Stub the tenant guard + resolver + all three shared read functions AND the
    redis client so the handler runs DB-free, Redis-free and network-free.

    Returns (overview, campaigns, timeseries, redis) — the objects used, for
    identity assertions. `redis` defaults to a fresh `_FakeRedis` whose `.get()`
    misses (returns None) so callers exercise the generate-and-store path unless
    they seed it."""
    overview = overview if overview is not None else _overview_payload()
    campaigns = campaigns if campaigns is not None else _campaigns_payload()
    timeseries = timeseries if timeseries is not None else _timeseries_payload()
    redis = redis if redis is not None else _FakeRedis()

    monkeypatch.setattr(
        insights_ep.acc_svc, "assert_account_belongs_to_org",
        lambda db, account_id, org_id, allowed_ids=None: account,
    )
    monkeypatch.setattr(
        insights_ep.insights_svc, "resolve_date_range",
        lambda preset, tz: (date(2026, 6, 1), date(2026, 6, 30)),
    )
    monkeypatch.setattr(
        insights_ep.insights_svc, "get_overview", lambda *a, **k: overview,
    )
    monkeypatch.setattr(
        insights_ep.insights_svc, "get_table", lambda *a, **k: campaigns,
    )
    monkeypatch.setattr(
        insights_ep.insights_svc, "get_timeseries", lambda *a, **k: timeseries,
    )
    monkeypatch.setattr(insights_ep, "redis_client", redis)
    return overview, campaigns, timeseries, redis


def _stored_response(*, headline="Cached headline.", driver="Cached driver.",
                     watch="Cached watch.", next_step="Cached next.",
                     cached_at=_CACHED_AT):
    """Build the exact JSON a prior POST would have stored: an
    OverviewSummaryResponse with cached=False (cached=True is only set on read).
    Returns (response_obj, json_str)."""
    resp = OverviewSummaryResponse(
        headline=headline, driver=driver, watch=watch, next_step=next_step,
        period={"date_start": date(2026, 6, 1), "date_stop": date(2026, 6, 30),
                "preset": "last_30d"},
        model="gpt-4o-mini",
        generated_at=datetime(2026, 7, 1, 12, 30, 0, tzinfo=timezone.utc),
        data_as_of=cached_at,
        cached=False,
    )
    return resp, resp.model_dump_json()


# ─── 2a. Tenant isolation: cross-org account_id → 403 ────────────────────────


def test_summary_cross_org_returns_403(monkeypatch):
    """A caller whose org doesn't own account_id gets 403.

    MOCKED: `acc_svc.assert_account_belongs_to_org` — the real tenant guard that
    _resolve_dates calls. We make it raise ForbiddenError exactly as the real
    function does for a cross-org id; the handler must translate that to
    HTTPException(403). The guard runs first (inside _resolve_dates), before any
    read or AI call.

    generate_overview_diagnosis must NEVER be reached for a forbidden account
    (no tokens spent on an unauthorized read) — we assert that too."""
    def _forbidden(db, account_id, org_id, allowed_ids=None):
        raise ForbiddenError("Account does not belong to your organization")

    monkeypatch.setattr(insights_ep.acc_svc, "assert_account_belongs_to_org", _forbidden)

    called = {"diagnose": False}

    def _diagnose(*a, **k):
        called["diagnose"] = True
        return _card()

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _diagnose)
    # Guard runs (inside _resolve_dates) BEFORE any redis touch — assert Redis
    # is never consulted for a forbidden account.
    redis = _FakeRedis()
    monkeypatch.setattr(insights_ep, "redis_client", redis)

    with pytest.raises(HTTPException) as ei:
        insights_ep.overview_summary(
            account_id=str(uuid.uuid4()),
            current_user=_owner("intruder-org"),
            db=object(),  # never touched: the guard raises before any query
            date_preset="last_30d",
            date_start=None, date_end=None, status=None, search=None,
        )
    assert ei.value.status_code == 403
    assert called["diagnose"] is False, "diagnosis generated for a forbidden account"
    assert redis.get_calls == [], "redis consulted for a forbidden account"
    assert redis.setex_calls == [], "redis written for a forbidden account"


def test_peek_cross_org_returns_403(monkeypatch):
    """Tenant isolation on GET peek: the get_overview guard (inside
    _resolve_dates) raises ForbiddenError → 403, BEFORE any redis.get. peek must
    not leak whether a cached summary exists for another org's account."""
    def _forbidden(db, account_id, org_id, allowed_ids=None):
        raise ForbiddenError("Account does not belong to your organization")

    monkeypatch.setattr(insights_ep.acc_svc, "assert_account_belongs_to_org", _forbidden)
    redis = _FakeRedis()
    monkeypatch.setattr(insights_ep, "redis_client", redis)

    with pytest.raises(HTTPException) as ei:
        insights_ep.overview_summary_peek(
            account_id=str(uuid.uuid4()),
            current_user=_owner("intruder-org"),
            db=object(),
            date_preset="last_30d",
            date_start=None, date_end=None, status=None, search=None,
        )
    assert ei.value.status_code == 403
    assert redis.get_calls == [], "peek consulted redis for a forbidden account"


# ─── 2b. P-6 parity: diagnoser gets exactly what the read fns returned ───────


def test_summary_diagnoses_exact_read_dicts(monkeypatch):
    """P-6: the objects handed to generate_overview_diagnosis are byte-for-byte
    the ones the shared read functions returned for the same params — the
    handler must not recompute or mutate the numbers between read and diagnose.

    MOCKED:
      * the tenant guard → returns a fake account (no DB).
      * resolve_date_range → fixed range (no dependence on 'today').
      * get_overview / get_table / get_timeseries → return known objects.
      * generate_overview_diagnosis → captures the args it was passed.
    """
    account = _account()
    overview_obj, campaigns_obj, ts_obj, redis = _stub_all_reads(
        monkeypatch, account=account
    )  # redis default: .get() misses → generate path
    campaign_rows, _ = campaigns_obj  # get_table returns (rows, total)

    captured = {}

    def _diagnose(overview, acct, *, campaigns, timeseries):
        captured["overview"] = overview
        captured["account"] = acct
        captured["campaigns"] = campaigns
        captured["timeseries"] = timeseries
        return _card()

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _diagnose)

    resp = insights_ep.overview_summary(
        account_id="acct-1",
        current_user=_owner(),
        db=object(),
        date_preset="last_30d",
        date_start=None, date_end=None, status=None, search=None,
    )

    # Same object identity → provably no copy/recompute/mutation in between (P-6).
    assert captured["overview"] is overview_obj
    assert captured["overview"]["summary"] == overview_obj["summary"]
    assert captured["account"] is account
    # Campaigns passed are the ROWS from get_table (handler unpacks the tuple).
    assert captured["campaigns"] is campaign_rows
    # Timeseries passed is exactly what get_timeseries returned.
    assert captured["timeseries"] is ts_obj

    # Response carries all four structured fields (no more `narrative` blob).
    assert resp.headline == _card()["headline"]
    assert resp.driver == _card()["driver"]
    assert resp.watch == _card()["watch"]
    assert resp.next_step == _card()["next_step"]
    # P-1 envelope: the SAME period the numbers came from, plus model stamp.
    assert resp.period.date_start == overview_obj["period"]["date_start"]
    assert resp.period.date_stop == overview_obj["period"]["date_stop"]
    assert resp.model  # non-empty model identifier
    assert resp.generated_at is not None
    # Freshly generated → cached=False and the freshness token echoed as data_as_of.
    assert resp.cached is False
    assert resp.data_as_of == overview_obj["cached_at"]


# ─── 2c. AISummaryError → HTTP 502 (never a 200 with empty text) ─────────────


def test_summary_ai_failure_returns_502(monkeypatch):
    """P-4: if the OpenAI call fails, the endpoint returns a distinguishable 502
    with a detail — never a 200 carrying empty/fake diagnosis text.

    MOCKED: tenant guard + all three reads (no DB); generate_overview_diagnosis
    raises AISummaryError exactly as it does on any real OpenAI failure.

    A transient failure must NOT be cached — otherwise the next identical request
    would replay the error state as if it were a diagnosis. We assert redis.setex
    was never called."""
    _, _, _, redis = _stub_all_reads(monkeypatch, account=_account())

    def _boom(*a, **k):
        raise ai_summary_svc.AISummaryError("AI summary generation failed: upstream 500")

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _boom)

    with pytest.raises(HTTPException) as ei:
        insights_ep.overview_summary(
            account_id="acct-1",
            current_user=_owner(),
            db=object(),
            date_preset="last_30d",
            date_start=None, date_end=None, status=None, search=None,
        )
    assert ei.value.status_code == 502
    assert ei.value.detail, "502 must carry a distinguishable detail, not be empty"
    assert ei.value.status_code != 200  # explicit: never a fake-success 200
    assert redis.setex_calls == [], "a failed diagnosis must never be cached"


# ─── 3. Cache miss → generates + stores with the 24h TTL and freshness key ───


def test_summary_cache_miss_generates_and_stores(monkeypatch):
    """redis.get → None (miss). The handler must:
      * call generate_overview_diagnosis (miss ⇒ real generation),
      * return cached=False with data_as_of == the get_overview freshness token,
      * store the result via redis.setex EXACTLY once, at the 24h TTL (86400),
        under the freshness-token key, with the serialized response body.
    """
    overview_obj, _campaigns, _ts, redis = _stub_all_reads(
        monkeypatch, account=_account()
    )

    calls = {"n": 0}

    def _diagnose(*a, **k):
        calls["n"] += 1
        return _card()

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _diagnose)

    resp = insights_ep.overview_summary(
        account_id="acct-1", current_user=_owner(), db=object(),
        date_preset="last_30d", date_start=None, date_end=None,
        status=None, search=None,
    )

    assert calls["n"] == 1, "miss must trigger exactly one generation"
    assert resp.cached is False
    assert resp.data_as_of == overview_obj["cached_at"]

    # Stored exactly once, 24h TTL, under the derived key, with this body.
    assert len(redis.setex_calls) == 1
    stored_key, ttl, body = redis.setex_calls[0]
    assert ttl == 86_400
    expected_key = insights_ep._aisum_cache_key(
        "acct-1", "last_30d", date(2026, 6, 1), date(2026, 6, 30),
        None, None, overview_obj["cached_at"],
    )
    assert stored_key == expected_key
    # The stored body round-trips to a diagnosis with cached=False.
    round_tripped = OverviewSummaryResponse.model_validate_json(body)
    assert round_tripped.headline == _card()["headline"]
    assert round_tripped.cached is False


# ─── 4. Cache hit → replays stored, zero generation / zero extra reads ───────


def test_summary_cache_hit_replays_without_generation(monkeypatch):
    """redis.get → a previously-stored OverviewSummaryResponse JSON (hit). With
    force=false the handler must short-circuit:
      * response cached=True and its fields equal the stored ones,
      * generate_overview_diagnosis is NOT called (zero OpenAI tokens),
      * get_table / get_timeseries are NOT called (zero extra DB work),
      * redis.setex is NOT called (nothing to re-store).
    """
    overview_obj = _overview_payload()
    stored_resp, stored_json = _stored_response()

    # Pre-seed the fake so .get() at the derived key returns the stored JSON.
    redis = _FakeRedis()
    key = insights_ep._aisum_cache_key(
        "acct-1", "last_30d", date(2026, 6, 1), date(2026, 6, 30),
        None, None, overview_obj["cached_at"],
    )
    redis.seed(key, stored_json)

    # get_table / get_timeseries must NOT run on a hit — wire them to blow up.
    def _must_not_run(*a, **k):
        raise AssertionError("read fn called on a cache hit")

    _stub_all_reads(monkeypatch, account=_account(), overview=overview_obj,
                    redis=redis)
    monkeypatch.setattr(insights_ep.insights_svc, "get_table", _must_not_run)
    monkeypatch.setattr(insights_ep.insights_svc, "get_timeseries", _must_not_run)

    gen_called = {"n": 0}

    def _diagnose(*a, **k):
        gen_called["n"] += 1
        return _card()

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _diagnose)

    resp = insights_ep.overview_summary(
        account_id="acct-1", current_user=_owner(), db=object(),
        date_preset="last_30d", date_start=None, date_end=None,
        status=None, search=None, force=False,
    )

    assert resp.cached is True, "a replayed diagnosis must be marked cached"
    assert resp.headline == stored_resp.headline
    assert resp.driver == stored_resp.driver
    assert resp.watch == stored_resp.watch
    assert resp.next_step == stored_resp.next_step
    assert resp.data_as_of == stored_resp.data_as_of
    assert gen_called["n"] == 0, "cache hit spent OpenAI tokens"
    assert redis.setex_calls == [], "cache hit re-stored the value"


# ─── 5. Freshness token in the key: a re-sync changes cached_at → new key ────


def test_cache_key_varies_with_cached_at_and_filters():
    """The freshness token (get_overview cached_at) is IN the key: identical
    inputs are stable, and a re-sync (different cached_at) yields a DIFFERENT key
    so a stale narrative is never replayed (P-1). status/search also vary it;
    None (empty period) folds to the literal 'nodata'."""
    args = ("acct-1", "last_30d", date(2026, 6, 1), date(2026, 6, 30), None, None)

    t1 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 7, 2, 9, 30, 0, tzinfo=timezone.utc)

    k1 = insights_ep._aisum_cache_key(*args, t1)
    k1_again = insights_ep._aisum_cache_key(*args, t1)
    k2 = insights_ep._aisum_cache_key(*args, t2)

    # Deterministic for identical inputs.
    assert k1 == k1_again
    # A re-sync (new MAX fetched_at) moves the key → forces a miss → regenerate.
    assert k1 != k2

    # No data (cached_at=None) folds to a distinct 'nodata' token, not a crash.
    k_nodata = insights_ep._aisum_cache_key(*args, None)
    assert k_nodata.endswith(":nodata")
    assert k_nodata != k1

    # status / search vary the filter hash deterministically.
    k_status = insights_ep._aisum_cache_key(
        "acct-1", "last_30d", date(2026, 6, 1), date(2026, 6, 30),
        "ACTIVE", None, t1,
    )
    k_search = insights_ep._aisum_cache_key(
        "acct-1", "last_30d", date(2026, 6, 1), date(2026, 6, 30),
        None, "brand", t1,
    )
    assert k_status != k1
    assert k_search != k1
    assert k_status != k_search


def test_new_cached_at_is_a_miss_even_after_prior_store(monkeypatch):
    """End-to-end freshness invalidation: a first request stores under
    cached_at=t1; a second request whose get_overview now reports cached_at=t2
    (a re-sync happened) derives a DIFFERENT key, so .get() misses and it
    regenerates — the stale t1 narrative is never served."""
    account = _account()

    # ── First request: cached_at = t1, miss → generate → store under key(t1).
    ov1 = _overview_payload(cached_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    redis = _FakeRedis()
    _stub_all_reads(monkeypatch, account=account, overview=ov1, redis=redis)

    gen = {"n": 0}

    def _diagnose(*a, **k):
        gen["n"] += 1
        return _card()

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _diagnose)

    insights_ep.overview_summary(
        account_id="acct-1", current_user=_owner(), db=object(),
        date_preset="last_30d", date_start=None, date_end=None,
        status=None, search=None, force=False,
    )
    assert gen["n"] == 1
    assert len(redis.setex_calls) == 1
    key_t1 = redis.setex_calls[0][0]

    # ── Second request: SAME redis (so the t1 value is present), but a re-sync
    # moved cached_at to t2. Key differs → miss → regenerate under key(t2).
    ov2 = _overview_payload(cached_at=datetime(2026, 7, 2, tzinfo=timezone.utc))
    monkeypatch.setattr(insights_ep.insights_svc, "get_overview", lambda *a, **k: ov2)

    insights_ep.overview_summary(
        account_id="acct-1", current_user=_owner(), db=object(),
        date_preset="last_30d", date_start=None, date_end=None,
        status=None, search=None, force=False,
    )
    assert gen["n"] == 2, "a moved freshness token must force regeneration"
    key_t2 = redis.setex_calls[-1][0]
    assert key_t2 != key_t1, "re-sync must land under a different cache key"
    # The last .get() looked up the NEW key (a miss), never the stale one.
    assert redis.get_calls[-1] == key_t2


# ─── 6. force=true bypasses a hit and overwrites ─────────────────────────────


def test_summary_force_bypasses_cache_hit(monkeypatch):
    """redis.get has a stored value, but force=true → the handler must skip the
    read path entirely, regenerate, return cached=False, and overwrite via setex.
    (Manual regeneration is the recovery path, P-5.)"""
    overview_obj = _overview_payload()
    _stored_resp, stored_json = _stored_response(headline="STALE cached headline.")

    redis = _FakeRedis()
    key = insights_ep._aisum_cache_key(
        "acct-1", "last_30d", date(2026, 6, 1), date(2026, 6, 30),
        None, None, overview_obj["cached_at"],
    )
    redis.seed(key, stored_json)

    _stub_all_reads(monkeypatch, account=_account(), overview=overview_obj,
                    redis=redis)

    gen = {"n": 0}

    def _diagnose(*a, **k):
        gen["n"] += 1
        return _card()

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _diagnose)

    resp = insights_ep.overview_summary(
        account_id="acct-1", current_user=_owner(), db=object(),
        date_preset="last_30d", date_start=None, date_end=None,
        status=None, search=None, force=True,
    )

    assert gen["n"] == 1, "force=true must regenerate even on a hit"
    assert resp.cached is False
    # The fresh diagnosis, not the seeded stale one.
    assert resp.headline == _card()["headline"]
    # setex overwrote the stored value.
    assert len(redis.setex_calls) == 1
    assert redis.setex_calls[0][0] == key
    assert OverviewSummaryResponse.model_validate_json(
        redis.store[key]
    ).headline == _card()["headline"]


# ─── 7. peek: hit replays, miss → 204, never generates ───────────────────────


def test_peek_cache_hit_returns_cached(monkeypatch):
    """GET peek with a stored value → 200 with cached=True, replaying the stored
    fields. It must NEVER call generate_overview_diagnosis / get_table /
    get_timeseries (strictly cache-only, zero tokens)."""
    overview_obj = _overview_payload()
    stored_resp, stored_json = _stored_response()

    redis = _FakeRedis()
    key = insights_ep._aisum_cache_key(
        "acct-1", "last_30d", date(2026, 6, 1), date(2026, 6, 30),
        None, None, overview_obj["cached_at"],
    )
    redis.seed(key, stored_json)

    def _must_not_run(*a, **k):
        raise AssertionError("peek called a read/generate fn")

    _stub_all_reads(monkeypatch, account=_account(), overview=overview_obj,
                    redis=redis)
    monkeypatch.setattr(insights_ep.insights_svc, "get_table", _must_not_run)
    monkeypatch.setattr(insights_ep.insights_svc, "get_timeseries", _must_not_run)
    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _must_not_run)

    resp = insights_ep.overview_summary_peek(
        account_id="acct-1", current_user=_owner(), db=object(),
        date_preset="last_30d", date_start=None, date_end=None,
        status=None, search=None,
    )

    assert isinstance(resp, OverviewSummaryResponse)
    assert resp.cached is True
    assert resp.headline == stored_resp.headline
    assert resp.next_step == stored_resp.next_step
    assert redis.setex_calls == [], "peek must never write"


def test_peek_cache_miss_returns_204(monkeypatch):
    """GET peek with no stored value → HTTP 204, empty body, and NEVER touches
    OpenAI / get_table / get_timeseries. The client renders an idle state without
    spending a token (P-5)."""
    def _must_not_run(*a, **k):
        raise AssertionError("peek called a read/generate fn on a miss")

    # Fresh fake → .get() misses.
    _stub_all_reads(monkeypatch, account=_account())  # redis default misses
    monkeypatch.setattr(insights_ep.insights_svc, "get_table", _must_not_run)
    monkeypatch.setattr(insights_ep.insights_svc, "get_timeseries", _must_not_run)
    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _must_not_run)

    resp = insights_ep.overview_summary_peek(
        account_id="acct-1", current_user=_owner(), db=object(),
        date_preset="last_30d", date_start=None, date_end=None,
        status=None, search=None,
    )

    assert isinstance(resp, Response)
    assert resp.status_code == 204
    assert resp.body == b"", "204 must carry an empty body"
