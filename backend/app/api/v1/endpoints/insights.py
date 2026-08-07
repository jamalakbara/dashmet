import hashlib
import io
import json
import re
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, redis_client
from app.config import settings
from app.exceptions import ForbiddenError, NotFoundError
from app.schemas.common import DataResponse, Meta, PaginatedResponse, build_pagination
from app.schemas.insights import (
    BreakdownResponse,
    OverviewResponse,
    OverviewSummaryResponse,
    TimeSeriesResponse,
)
from app.services import accounts as acc_svc
from app.services import ai_summary as ai_summary_svc
from app.services import export as export_svc
from app.services import insights as insights_svc

_PPTX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


def _report_filename(account_name: str, period_start: date) -> str:
    """Human-friendly download name, e.g. "Polki Indonesia - Monthly Report - July 2026.pptx".

    Keeps spaces/dashes readable; strips only characters illegal in filenames or
    that could break the Content-Disposition header.
    """
    month_year = period_start.strftime("%B %Y")
    clean = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", account_name)
    clean = re.sub(r"\s+", " ", clean).strip() or "Report"
    return f"{clean} - Monthly Report - {month_year}.pptx"


def _content_disposition(filename: str) -> str:
    """attachment header with an ASCII fallback + RFC 5987 UTF-8 name (handles
    spaces and non-ASCII account names without breaking the header)."""
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip() or "report.pptx"
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )

router = APIRouter()


def _resolve_dates(
    account_id: str,
    current_user: dict,
    db: Session,
    date_preset: Optional[str],
    date_start: Optional[date],
    date_end: Optional[date],
):
    allowed = acc_svc.get_accessible_account_ids(db, current_user)
    try:
        account = acc_svc.assert_account_belongs_to_org(
            db, account_id, current_user["org_id"], allowed_ids=allowed
        )
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    if date_preset:
        ds, de = insights_svc.resolve_date_range(date_preset, account.timezone)
    elif date_start and date_end:
        ds, de = date_start, date_end
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either date_preset or both date_start and date_end",
        )
    return ds, de, account, date_preset


def _resolve_combined_dates(
    account_ids_raw: str,
    current_user: dict,
    db: Session,
    date_preset: Optional[str],
    date_start: Optional[date],
    date_end: Optional[date],
):
    org_id = current_user["org_id"]
    allowed = acc_svc.get_accessible_account_ids(db, current_user)
    account_ids = [a.strip() for a in account_ids_raw.split(",") if a.strip()]

    if account_ids:
        try:
            accounts = [
                acc_svc.assert_account_belongs_to_org(
                    db, aid, org_id, allowed_ids=allowed
                )
                for aid in account_ids
            ]
        except (NotFoundError, ForbiddenError) as e:
            raise HTTPException(status_code=403, detail=str(e))
    else:
        # Empty selection = all *accessible* accounts: every org account for an
        # owner, the member's grant set for a member.
        ids = allowed if allowed is not None else acc_svc.get_org_account_ids(db, org_id)
        account_ids = [str(i) for i in ids]
        accounts = []

    tz = accounts[0].timezone if accounts else "UTC"
    if date_preset:
        ds, de = insights_svc.resolve_date_range(date_preset, tz)
    elif date_start and date_end:
        ds, de = date_start, date_end
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either date_preset or both date_start and date_end",
        )
    return account_ids, ds, de, date_preset


@router.get("/combined")
def combined(
    account_ids: str = Query(..., description="Comma-separated account ids to combine"),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
):
    ids, ds, de, preset = _resolve_combined_dates(
        account_ids, current_user, db, date_preset, date_start, date_end
    )
    data = insights_svc.get_combined_overview(
        db, ids, current_user["org_id"], ds, de, date_preset=preset
    )
    cached_at = data.pop("cached_at", None)
    return DataResponse(data=data, meta=Meta(cached=cached_at is not None, cached_at=cached_at))


@router.get("/combined-timeseries")
def combined_timeseries(
    account_ids: str = Query(..., description="Comma-separated account ids to combine"),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    time_increment: str = Query("day"),
):
    ids, ds, de, preset = _resolve_combined_dates(
        account_ids, current_user, db, date_preset, date_start, date_end
    )
    data = insights_svc.get_combined_timeseries(
        db, ids, current_user["org_id"], ds, de,
        time_increment=time_increment,
        date_preset=preset,
    )
    return DataResponse(data=data)


@router.get("/overview")
def overview(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    platform_objective: Optional[str] = Query(
        None,
        description="Scope the overview KPIs to campaigns with this raw platform "
        "objective (e.g. TikTok 'PRODUCT_SALES' for the GMV Max view), so the "
        "cards match the GMV-Max-filtered table.",
    ),
):
    ds, de, account, preset = _resolve_dates(
        account_id, current_user, db, date_preset, date_start, date_end
    )
    data = insights_svc.get_overview(
        db, account_id, current_user["org_id"], ds, de, date_preset=preset,
        status=status, search=search, platform_objective=platform_objective,
    )
    return DataResponse(data=data)


# On-demand AI-summary cache. The narrative costs OpenAI tokens to produce, so
# identical (account + period + filter + data-version) requests replay a stored
# diagnosis instead of re-spending. The freshness token (get_overview's
# cached_at = MAX fetched_at) is IN the key: a re-sync moves it → new key → miss
# → regenerate, so a stale narrative is never served (P-1). The 24h TTL is only a
# backstop for keys that never get re-synced; correctness comes from the token.
_AISUM_KEY_PREFIX = "aisum:v1"
_AISUM_TTL_SECONDS = 86_400  # 24h backstop; real invalidation is the freshness token.


def _aisum_cache_key(
    account_id: str,
    preset: Optional[str],
    date_start: date,
    date_end: date,
    status: Optional[str],
    search: Optional[str],
    cached_at: Optional[datetime],
) -> str:
    """Deterministic cache key for a single AI-overview diagnosis.

    aisum:v1:{account_id}:{period}:{filter_hash}:{cached_at_iso|nodata}
      * period    = preset if given, else {date_start}_{date_end}.
      * filter_hash = short sha1 of canonical json of {status, search} (sorted
        keys) so filters vary the key deterministically without leaking free
        text into it.
      * cached_at = the get_overview freshness token ISO string, or the literal
        'nodata' when the period has no rows. Omitting it would let a stale
        narrative survive a re-sync — do not drop it.
    """
    period = preset if preset else f"{date_start.isoformat()}_{date_end.isoformat()}"
    filter_canonical = json.dumps({"status": status, "search": search}, sort_keys=True)
    filter_hash = hashlib.sha1(filter_canonical.encode()).hexdigest()[:12]
    token = cached_at.isoformat() if cached_at is not None else "nodata"
    return f"{_AISUM_KEY_PREFIX}:{account_id}:{period}:{filter_hash}:{token}"


@router.post("/overview/summary", response_model=OverviewSummaryResponse)
def overview_summary(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    force: bool = Query(False, description="Bypass the cache and regenerate"),
):
    # POST, not GET: generating the narrative spends OpenAI tokens, so the
    # intent must be explicit and off the cacheable read path. The numbers are
    # read via the shared get_overview (tenant check + P-6 parity inside); the
    # AI service only narrates over that dict, it never queries metrics (P-7).
    ds, de, account, preset = _resolve_dates(
        account_id, current_user, db, date_preset, date_start, date_end
    )
    # get_overview does the tenant check and returns the freshness token
    # (cached_at) that keys the cache. We fetch it up front so a cache HIT can
    # short-circuit before any get_table/get_timeseries/OpenAI work.
    overview = insights_svc.get_overview(
        db, account_id, current_user["org_id"], ds, de, date_preset=preset,
        status=status, search=search,
    )
    cached_at = overview.get("cached_at")
    key = _aisum_cache_key(account_id, preset, ds, de, status, search, cached_at)

    if not force:
        stored = redis_client.get(key)
        if stored:
            # Cache hit: replay the stored diagnosis verbatim — zero tokens, and
            # no get_table/get_timeseries/OpenAI work. The stored token in the key
            # guarantees it matches the current data version (P-1).
            resp = OverviewSummaryResponse.model_validate_json(stored)
            resp.cached = True
            return resp

    # Miss (or forced): gather the richer, already-computed bundle via the shared
    # read functions (P-6 parity) — per-campaign period-over-period rows and the
    # daily trajectory — so the diagnosis can name a driver and speak to WHEN a
    # change happened. The AI service only transforms these dicts (P-7).
    campaigns, _total = insights_svc.get_table(
        db, account_id, current_user["org_id"], ds, de,
        level="campaign", compare_previous=True, date_preset=preset,
        status=status, search=search, per_page=10,
        sort_by="spend", sort_order="desc",
    )
    ts = insights_svc.get_timeseries(
        db, account_id, current_user["org_id"], ds, de,
        metrics=["spend", "clicks", "conversions", "ctr", "roas"],
        level="account", time_increment="day", compare_previous=True,
        date_preset=preset, status=status, search=search,
    )
    try:
        card = ai_summary_svc.generate_overview_diagnosis(
            overview, account, campaigns=campaigns, timeseries=ts,
        )
    except ai_summary_svc.AISummaryError as e:
        # Distinguishable error, never a 200 with empty/fake text (P-4) — and
        # never cached, so a transient failure doesn't poison future hits.
        raise HTTPException(status_code=502, detail=str(e))

    resp = OverviewSummaryResponse(
        headline=card["headline"],
        driver=card["driver"],
        watch=card["watch"],
        next_step=card["next_step"],
        period=overview["period"],
        model=settings.OPENAI_MODEL,
        generated_at=datetime.now(timezone.utc),
        data_as_of=cached_at,
        cached=False,
    )
    # Store the freshly-generated diagnosis with cached=False; the model round-
    # trips datetimes as ISO strings so reads are exact. cached=True is set only
    # on the read side. We also cache the 'nodata' key so an empty-period request
    # doesn't re-spend on every call (consistent with the key ending in 'nodata').
    redis_client.setex(key, _AISUM_TTL_SECONDS, resp.model_dump_json())
    return resp


@router.get("/overview/summary/peek", response_model=OverviewSummaryResponse)
def overview_summary_peek(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    # GET, and strictly cache-only: peeking must NEVER spend tokens or touch
    # get_table/get_timeseries/OpenAI. It resolves the same numbers + freshness
    # token (via get_overview, which also does the tenant check), rebuilds the
    # same key, and either replays a cached diagnosis or reports "no cached
    # summary" via 204 so the client can render an idle state token-free (P-5).
    ds, de, account, preset = _resolve_dates(
        account_id, current_user, db, date_preset, date_start, date_end
    )
    overview = insights_svc.get_overview(
        db, account_id, current_user["org_id"], ds, de, date_preset=preset,
        status=status, search=search,
    )
    cached_at = overview.get("cached_at")
    key = _aisum_cache_key(account_id, preset, ds, de, status, search, cached_at)

    stored = redis_client.get(key)
    if not stored:
        return Response(status_code=204)
    resp = OverviewSummaryResponse.model_validate_json(stored)
    resp.cached = True
    return resp


@router.get("/overview/export.pptx")
def overview_export_pptx(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    include_ai_summary: bool = Query(False),
):
    # Same date/tenant resolution as GET /overview → identical numbers by
    # construction (P-6). All three reads go through the shared insights
    # functions; no second query path to the metrics tables (P-7).
    ds, de, account, preset = _resolve_dates(
        account_id, current_user, db, date_preset, date_start, date_end
    )
    overview = insights_svc.get_overview(
        db, account_id, current_user["org_id"], ds, de, date_preset=preset,
        status=status, search=search,
    )
    ts = insights_svc.get_timeseries(
        db, account_id, current_user["org_id"], ds, de,
        metrics=["spend"], time_increment="day", date_preset=preset,
        status=status, search=search, compare_previous=True,
    )
    rows, _total = insights_svc.get_table(
        db, account_id, current_user["org_id"], ds, de,
        level="ad", sort_by="spend", sort_order="desc", page=1, per_page=6,
        date_preset=preset, status=status, search=search,
    )

    # Only spend tokens when the user explicitly opts in; default deck is
    # token-free and renders the original placeholders (no regression).
    # NOTE: the PPTX AI path is intentionally left UNCACHED — it produces a
    # different artifact (multi-section deck prose) than the on-screen card, so
    # it doesn't share the aisum:v1 cache. Caching it is a possible follow-up.
    insights_text: Optional[dict[str, str]] = None
    if include_ai_summary:
        # Ground the narrative in the same enriched bundle the on-screen card
        # uses: per-campaign period-over-period rows (with objectives) and a
        # daily trajectory with conversions — so the deck's "trend" slide speaks
        # to real day-by-day data instead of a trajectory it never saw. Same
        # shared read functions (P-6/P-7).
        ai_campaigns, _ = insights_svc.get_table(
            db, account_id, current_user["org_id"], ds, de,
            level="campaign", compare_previous=True, date_preset=preset,
            status=status, search=search, per_page=10,
            sort_by="spend", sort_order="desc",
        )
        ai_ts = insights_svc.get_timeseries(
            db, account_id, current_user["org_id"], ds, de,
            metrics=["spend", "clicks", "conversions", "ctr", "roas"],
            level="account", time_increment="day", compare_previous=True,
            date_preset=preset, status=status, search=search,
        )
        try:
            insights_text = ai_summary_svc.generate_narrative(
                overview, account, sections=["performance", "trend", "campaigns"],
                campaigns=ai_campaigns, timeseries=ai_ts,
            )
        except ai_summary_svc.AISummaryError as e:
            # The user asked for the summary; don't silently export without it.
            raise HTTPException(status_code=502, detail=str(e))

    pptx_bytes = export_svc.generate_overview_pptx(
        account=account, overview=overview, series=ts["series"],
        previous_series=ts.get("previous_series"), ads=rows,
        insights=insights_text,
    )

    filename = _report_filename(account.name, ds)
    return StreamingResponse(
        io.BytesIO(pptx_bytes),
        media_type=_PPTX_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/timeseries")
def timeseries(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    level: str = Query("account"),
    metrics: str = Query("spend,impressions,clicks,ctr"),
    time_increment: str = Query("day"),
    compare_previous: bool = Query(False),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    ds, de, account, preset = _resolve_dates(
        account_id, current_user, db, date_preset, date_start, date_end
    )
    metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]
    data = insights_svc.get_timeseries(
        db, account_id, current_user["org_id"], ds, de,
        metrics=metrics_list,
        level=level,
        time_increment=time_increment,
        compare_previous=compare_previous,
        date_preset=preset,
        status=status,
        search=search,
    )
    return DataResponse(data=data)


@router.get("/table")
def table(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    level: str = Query("campaign"),
    campaign_id: Optional[str] = Query(None),
    adgroup_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    platform_objective: Optional[str] = Query(
        None,
        description="Filter campaigns by raw platform objective (e.g. TikTok "
        "'PRODUCT_SALES' for the GMV Max view). Campaign level only.",
    ),
    sort_by: str = Query("spend"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
    compare_previous: bool = Query(False),
):
    ds, de, account, preset = _resolve_dates(
        account_id, current_user, db, date_preset, date_start, date_end
    )
    rows, total = insights_svc.get_table(
        db, account_id, current_user["org_id"], ds, de,
        level=level,
        campaign_id=campaign_id,
        adgroup_id=adgroup_id,
        status=status,
        search=search,
        platform_objective=platform_objective,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
        date_preset=preset,
        compare_previous=compare_previous,
    )

    if level == "ad":
        from workers.tasks.creatives import sync_creative
        for row in rows:
            if not row.get("creative_preview"):
                sync_creative.delay(row["id"])

    return PaginatedResponse(
        data=rows,
        pagination=build_pagination(total, page, per_page),
    )


@router.get("/engagement")
def engagement(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
):
    ds, de, account, preset = _resolve_dates(
        account_id, current_user, db, date_preset, date_start, date_end
    )
    data = insights_svc.get_engagement(
        db, account_id, current_user["org_id"], ds, de, date_preset=preset
    )
    cached_at = data.pop("cached_at", None)
    return DataResponse(data=data, meta=Meta(cached=cached_at is not None, cached_at=cached_at))


@router.get("/breakdown")
def breakdown(
    account_id: str = Query(...),
    breakdown_type: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
    level: str = Query("account"),
    campaign_id: Optional[str] = Query(None),
    adgroup_id: Optional[str] = Query(None),
):
    valid_breakdowns = {"age_gender", "country", "platform_position", "device"}
    if breakdown_type not in valid_breakdowns:
        raise HTTPException(
            status_code=400,
            detail=f"breakdown must be one of: {', '.join(valid_breakdowns)}",
        )

    ds, de, account, preset = _resolve_dates(
        account_id, current_user, db, date_preset, date_start, date_end
    )
    data = insights_svc.get_breakdown(
        db, account_id, current_user["org_id"], ds, de,
        breakdown_type=breakdown_type,
        level=level,
        campaign_id=campaign_id,
        adgroup_id=adgroup_id,
        date_preset=preset,
    )
    return DataResponse(data=data)
