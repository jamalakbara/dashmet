from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import DataResponse
from app.schemas.notifications import NotificationListResponse, NotificationOut
from app.services import notifications as notif_svc

router = APIRouter()


@router.get("")
def list_notifications(
    current_user: CurrentUser,
    db: DbSession,
    status: Optional[str] = Query(default=None),
):
    """Tenant-scoped notification list + unread count.

    Read-only: this endpoint calls only the read helpers and emits nothing
    (no notification is ever created as a side effect of a GET — anti-req).
    """
    org_id = current_user["org_id"]
    items = notif_svc.list_notifications(db, org_id=org_id, status=status)
    count = notif_svc.unread_count(db, org_id=org_id)
    return DataResponse(
        data=NotificationListResponse(
            items=[NotificationOut.from_orm_notification(n) for n in items],
            unread_count=count,
        )
    )


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: str, current_user: CurrentUser, db: DbSession
):
    """Mark a notification read. Tenant-scoped: a notification that is not in
    the caller's org yields 404 (never mutates another org's row)."""
    notif = notif_svc.mark_read(
        db, org_id=current_user["org_id"], notification_id=notification_id
    )
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.commit()
    return DataResponse(data=NotificationOut.from_orm_notification(notif))
