from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.exceptions import ForbiddenError, NotFoundError
from app.models.structure import AdGroup
from app.schemas.campaigns import AdGroupResponse
from app.schemas.common import PaginatedResponse, build_pagination, calculate_offset
from app.services.accounts import assert_account_belongs_to_org

router = APIRouter()


@router.get("")
def list_adgroups(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
    campaign_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
):
    try:
        account = assert_account_belongs_to_org(db, account_id, current_user["org_id"])
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    import uuid
    q = db.query(AdGroup).filter(AdGroup.account_id == account.id)
    if campaign_id:
        q = q.filter(AdGroup.campaign_id == uuid.UUID(campaign_id))
    if status:
        q = q.filter(AdGroup.status == status)

    total = q.count()
    allowed_sort = {"name", "status", "created_at"}
    col = sort_by if sort_by in allowed_sort else "created_at"
    order_col = getattr(AdGroup, col, AdGroup.created_at)
    q = q.order_by(order_col.desc() if sort_order == "desc" else order_col.asc())
    adgroups = q.offset(calculate_offset(page, per_page)).limit(per_page).all()

    return PaginatedResponse(
        data=[AdGroupResponse.from_orm(ag) for ag in adgroups],
        pagination=build_pagination(total, page, per_page),
    )
