from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    severity: str
    title: str
    body: str
    deep_link: Optional[str] = None
    dedup_key: str
    status: str
    resolved_at: Optional[datetime] = None
    created_at: datetime

    @classmethod
    def from_orm_notification(cls, n) -> "NotificationOut":
        return cls(
            id=str(n.id),
            type=n.type,
            severity=n.severity,
            title=n.title,
            body=n.body,
            deep_link=n.deep_link,
            dedup_key=n.dedup_key,
            status=n.status,
            resolved_at=n.resolved_at,
            created_at=n.created_at,
        )


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]
    unread_count: int
