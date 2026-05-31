from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.exceptions import ForbiddenError, NotFoundError
from app.schemas.accounts import AccountConfigUpdateRequest, AccountResponse
from app.schemas.common import DataResponse, PaginatedResponse, build_pagination
from app.services import accounts as acc_svc

router = APIRouter()


@router.get("")
def list_accounts(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
):
    accounts, total = acc_svc.list_accounts(
        db, current_user["org_id"], page=page, per_page=per_page
    )
    return PaginatedResponse(
        data=[AccountResponse.from_orm_account(a) for a in accounts],
        pagination=build_pagination(total, page, per_page),
    )


@router.get("/{account_id}")
def get_account(account_id: str, current_user: CurrentUser, db: DbSession):
    try:
        account = acc_svc.get_account_with_config(db, account_id, current_user["org_id"])
        return DataResponse(data=AccountResponse.from_orm_account(account))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/{account_id}/config")
def update_account_config(
    account_id: str,
    body: AccountConfigUpdateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    try:
        acc_svc.update_account_config(
            db,
            account_id=account_id,
            org_id=current_user["org_id"],
            primary_conversion_action=body.primary_conversion_action,
            attribution_window=body.attribution_window,
            roas_action_type=body.roas_action_type,
        )
        db.commit()
        account = acc_svc.get_account_with_config(db, account_id, current_user["org_id"])
        return DataResponse(data=AccountResponse.from_orm_account(account))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
