from celery import Celery
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
    beat_schedule={
        "sync-structure-all-accounts": {
            "task": "workers.tasks.structure.sync_structure_all",
            "schedule": 30 * 60,  # every 30 min
        },
        "sync-insights-daily": {
            "task": "workers.tasks.insights.sync_insights_daily_all",
            "schedule": 15 * 60,  # every 15 min
        },
        "sync-insights-async-submit": {
            "task": "workers.tasks.async_jobs.submit_async_jobs",
            "schedule": 6 * 60 * 60,  # every 6 hours
        },
        "poll-async-jobs": {
            "task": "workers.tasks.async_jobs.poll_async_jobs",
            "schedule": 2 * 60,  # every 2 min
        },
    },
)
