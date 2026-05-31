from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession, OwnerUser, redis_client
from app.exceptions import ForbiddenError, NotFoundError
from app.schemas.common import DataResponse
from app.schemas.sync import SyncStatusResponse, TriggerSyncRequest, TriggerSyncResponse
from app.services import sync as sync_svc

router = APIRouter()


@router.get("/status")
def sync_status(
    account_id: str = Query(...),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
):
    try:
        data = sync_svc.get_sync_status(
            db, redis_client, account_id, current_user["org_id"]
        )
        return DataResponse(data=data)
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/trigger", status_code=202)
def trigger_sync(body: TriggerSyncRequest, current_user: OwnerUser, db: DbSession):
    try:
        job_ids = sync_svc.trigger_sync(
            db, body.account_id, current_user["org_id"], body.job_types
        )
        db.commit()
        return DataResponse(
            data=TriggerSyncResponse(
                message="Sync jobs queued",
                job_ids=job_ids,
            )
        )
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))
