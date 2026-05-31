from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class JobStatus(BaseModel):
    status: str
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    is_stale: bool = False
    percent_complete: Optional[int] = None


class RateLimitStatus(BaseModel):
    insights_app_pct: float = 0
    insights_acc_pct: float = 0
    structure_acc_pct: float = 0
    access_tier: str = "standard_access"


class SyncStatusResponse(BaseModel):
    account_id: str
    jobs: dict[str, JobStatus]
    rate_limit: RateLimitStatus
    has_warning: bool


class TriggerSyncRequest(BaseModel):
    account_id: str
    job_types: list[str]


class TriggerSyncResponse(BaseModel):
    message: str
    job_ids: list[str]
