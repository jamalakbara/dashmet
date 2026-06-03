from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "dashmet",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "workers.tasks.structure",
        "workers.tasks.insights",
        "workers.tasks.async_jobs",
        "workers.tasks.creatives",
        "workers.tasks.tiktok_structure",
        "workers.tasks.tiktok_insights",
        "workers.tasks.tiktok_creatives",
        "workers.tasks.tiktok_token_refresh",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,          # re-queue task if worker crashes
    worker_prefetch_multiplier=1, # one task at a time per worker (rate limit safe)
    task_queues={
        "default": {},
        "poll": {},   # dedicated queue — prevents poll tasks being starved by long insight syncs
    },
    task_default_queue="default",
    task_routes={
        "workers.tasks.async_jobs.poll_async_jobs": {"queue": "poll"},
        "workers.tasks.async_jobs.fetch_async_results": {"queue": "poll"},
    },
    beat_schedule={
        # Meta
        "sync-meta-structure-all": {
            "task": "workers.tasks.structure.sync_structure_all",
            "schedule": 30 * 60,  # every 30 min
        },
        "sync-meta-insights-daily": {
            "task": "workers.tasks.insights.sync_insights_daily_all",
            "schedule": 15 * 60,  # every 15 min
        },
        "sync-meta-breakdowns": {
            "task": "workers.tasks.insights.sync_breakdowns_all",
            "schedule": 60 * 60,  # every 1 hour
        },
        "sync-meta-insights-async-submit": {
            "task": "workers.tasks.async_jobs.submit_async_jobs",
            "schedule": 6 * 60 * 60,  # every 6 hours
        },
        "poll-async-jobs": {
            "task": "workers.tasks.async_jobs.poll_async_jobs",
            "schedule": 2 * 60,  # every 2 min
        },
        # TikTok
        "sync-tiktok-structure-all": {
            "task": "workers.tasks.tiktok_structure.sync_tiktok_structure_all",
            "schedule": 30 * 60,  # every 30 min
        },
        "sync-tiktok-insights-daily": {
            "task": "workers.tasks.tiktok_insights.sync_tiktok_insights_daily_all",
            "schedule": 15 * 60,  # every 15 min
        },
        "refresh-tiktok-tokens": {
            "task": "workers.tasks.tiktok_token_refresh.refresh_tiktok_tokens",
            "schedule": crontab(hour=0, minute=30),  # daily at 00:30 UTC
        },
    },
)
