from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.exceptions import ForbiddenError, NotFoundError
from app.schemas.common import DataResponse, PaginatedResponse, build_pagination
from app.schemas.insights import (
    BreakdownResponse,
    OverviewResponse,
    TimeSeriesResponse,
)
from app.services import accounts as acc_svc
from app.services import insights as insights_svc

router = APIRouter()


def _resolve_dates(
    account_id: str,
    org_id: str,
    db: Session,
    date_preset: Optional[str],
    date_start: Optional[date],
    date_end: Optional[date],
):
    try:
        account = acc_svc.assert_account_belongs_to_org(db, account_id, org_id)
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


@router.get("/overview")
def overview(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    date_preset: Optional[str] = Query(None),
    date_start: Optional[date] = Query(None),
    date_end: Optional[date] = Query(None),
):
    ds, de, account, preset = _resolve_dates(
        account_id, current_user["org_id"], db, date_preset, date_start, date_end
    )
    data = insights_svc.get_overview(
        db, account_id, current_user["org_id"], ds, de, date_preset=preset
    )
    return DataResponse(data=data)


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
):
    ds, de, account, preset = _resolve_dates(
        account_id, current_user["org_id"], db, date_preset, date_start, date_end
    )
    metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]
    data = insights_svc.get_timeseries(
        db, account_id, current_user["org_id"], ds, de,
        metrics=metrics_list,
        level=level,
        time_increment=time_increment,
        compare_previous=compare_previous,
        date_preset=preset,
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
    sort_by: str = Query("spend"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
):
    ds, de, account, preset = _resolve_dates(
        account_id, current_user["org_id"], db, date_preset, date_start, date_end
    )
    rows, total = insights_svc.get_table(
        db, account_id, current_user["org_id"], ds, de,
        level=level,
        campaign_id=campaign_id,
        adgroup_id=adgroup_id,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
        date_preset=preset,
    )
    return PaginatedResponse(
        data=rows,
        pagination=build_pagination(total, page, per_page),
    )


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
        account_id, current_user["org_id"], db, date_preset, date_start, date_end
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
