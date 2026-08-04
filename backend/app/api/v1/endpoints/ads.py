import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession
from app.exceptions import ForbiddenError, NotFoundError
from app.models.platform import Account
from app.models.structure import Ad
from app.schemas.campaigns import AdResponse, CreativeResponse
from app.schemas.common import DataResponse, PaginatedResponse, build_pagination, calculate_offset
from app.services.accounts import (
    assert_account_belongs_to_org,
    get_accessible_account_ids,
)

router = APIRouter()


@router.get("")
def list_ads(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    campaign_id: Optional[str] = Query(None),
    adgroup_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
):
    try:
        allowed = get_accessible_account_ids(db, current_user)
        account = assert_account_belongs_to_org(
            db, account_id, current_user["org_id"], allowed_ids=allowed
        )
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    q = (
        db.query(Ad)
        .options(joinedload(Ad.creative))
        .filter(Ad.account_id == account.id)
    )
    if campaign_id:
        q = q.filter(Ad.campaign_id == uuid.UUID(campaign_id))
    if adgroup_id:
        q = q.filter(Ad.ad_group_id == uuid.UUID(adgroup_id))
    if status:
        q = q.filter(Ad.status == status)

    total = q.count()
    allowed_sort = {"name", "status", "created_at"}
    col = sort_by if sort_by in allowed_sort else "created_at"
    order_col = getattr(Ad, col, Ad.created_at)
    q = q.order_by(order_col.desc() if sort_order == "desc" else order_col.asc())
    ads = q.offset(calculate_offset(page, per_page)).limit(per_page).all()

    return PaginatedResponse(
        data=[AdResponse.from_orm(a) for a in ads],
        pagination=build_pagination(total, page, per_page),
    )


@router.get("/{ad_id}/creative")
def get_creative(ad_id: str, current_user: CurrentUser, db: DbSession):
    ad = db.query(Ad).options(joinedload(Ad.creative)).filter(
        Ad.id == uuid.UUID(ad_id)
    ).first()

    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    try:
        allowed = get_accessible_account_ids(db, current_user)
        assert_account_belongs_to_org(
            db, str(ad.account_id), current_user["org_id"], allowed_ids=allowed
        )
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    if ad.creative and ad.creative.thumbnail_url:
        return DataResponse(
            data={
                "ad_id": str(ad.id),
                "creative": CreativeResponse.from_orm(ad.creative).model_dump(),
            }
        )

    account = db.get(Account, ad.account_id)
    # Google ads are text creatives (no thumbnail) and fully populated at structure
    # sync — serve whatever exists rather than blocking on an async fetch.
    if account and account.platform_id == "google_ads":
        if ad.creative:
            return DataResponse(
                data={
                    "ad_id": str(ad.id),
                    "creative": CreativeResponse.from_orm(ad.creative).model_dump(),
                }
            )
        from workers.tasks.google_creatives import sync_google_creative
        sync_google_creative.delay(ad_id)
    elif account and account.platform_id == "tiktok":
        from workers.tasks.tiktok_creatives import sync_tiktok_creative
        sync_tiktok_creative.delay(ad_id)
    else:
        from workers.tasks.creatives import sync_creative
        sync_creative.delay(ad_id)

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=202,
        content={
            "data": None,
            "meta": {
                "status": "fetching",
                "message": "Creative is being fetched. Retry in a few seconds.",
            },
        },
    )
