from fastapi import APIRouter

from app.api.v1.endpoints import (
    accounts,
    adgroups,
    ads,
    auth,
    campaigns,
    connections,
    insights,
    org,
    sync,
)

router = APIRouter()

router.include_router(auth.router,        prefix="/auth",        tags=["auth"])
router.include_router(org.router,         prefix="/org",         tags=["org"])
router.include_router(connections.router, prefix="/connections", tags=["connections"])
router.include_router(accounts.router,    prefix="/accounts",    tags=["accounts"])
router.include_router(campaigns.router,   prefix="/campaigns",   tags=["campaigns"])
router.include_router(adgroups.router,    prefix="/adgroups",    tags=["adgroups"])
router.include_router(ads.router,         prefix="/ads",         tags=["ads"])
router.include_router(insights.router,    prefix="/insights",    tags=["insights"])
router.include_router(sync.router,        prefix="/sync",        tags=["sync"])


@router.get("/ping", tags=["health"])
def ping():
    return {"message": "pong"}
