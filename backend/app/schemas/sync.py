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
    # Optional: when omitted, the service picks a platform-appropriate default
    # set (see services.sync.DEFAULT_JOB_TYPES). Only job_types that have a
    # producer for the account's platform are dispatched.
    job_types: Optional[list[str]] = None


class TriggerSyncResponse(BaseModel):
    message: str
    job_ids: list[str]
