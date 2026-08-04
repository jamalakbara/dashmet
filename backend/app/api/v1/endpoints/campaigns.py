import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.exceptions import ForbiddenError, NotFoundError
from app.models.structure import Campaign
from app.schemas.campaigns import CampaignResponse
from app.schemas.common import PaginatedResponse, build_pagination, calculate_offset
from app.services.accounts import (
    assert_account_belongs_to_org,
    get_accessible_account_ids,
)

router = APIRouter()


@router.get("")
def list_campaigns(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
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

    q = db.query(Campaign).filter(Campaign.account_id == account.id)
    if status:
        q = q.filter(Campaign.status == status)

    total = q.count()
    allowed_sort = {"name", "status", "created_at", "daily_budget"}
    col = sort_by if sort_by in allowed_sort else "created_at"
    order_col = getattr(Campaign, col, Campaign.created_at)
    q = q.order_by(order_col.desc() if sort_order == "desc" else order_col.asc())
    campaigns = q.offset(calculate_offset(page, per_page)).limit(per_page).all()

    return PaginatedResponse(
        data=[CampaignResponse.from_orm(c) for c in campaigns],
        pagination=build_pagination(total, page, per_page),
    )
