from celery import Celery
from celery.schedules import crontab
from app.config import settings

# ── Task time limits ──────────────────────────────────────────────────────────
# Global defaults are a backstop against hung tasks (e.g. a network stall pinning
# a worker slot forever). Heavy per-account sync loops override these much higher
# since a large account legitimately takes many minutes. Tune from observed p99.
DEFAULT_SOFT_TIME_LIMIT = 900    # 15 min
DEFAULT_TIME_LIMIT = 1200        # 20 min
HEAVY_SOFT_TIME_LIMIT = 3000     # 50 min — large-account insights/structure loops
HEAVY_TIME_LIMIT = 3300          # 55 min hard kill
# In-flight lock TTL must be >= the heavy hard limit so a still-running task never
# loses its lock, and a SIGKILLed task's lock always expires (no permanent block).
LOCK_TTL = HEAVY_TIME_LIMIT + 120

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
        "workers.tasks.tiktok_breakdowns",
        "workers.tasks.tiktok_creatives",
        "workers.tasks.tiktok_token_refresh",
        "workers.tasks.google_structure",
        "workers.tasks.google_insights",
        "workers.tasks.google_breakdowns",
        "workers.tasks.google_creatives",
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
    task_soft_time_limit=DEFAULT_SOFT_TIME_LIMIT,
    task_time_limit=DEFAULT_TIME_LIMIT,
    task_queues={
        "default": {},
        "meta": {},
        "tiktok": {},
        "google": {},
        "poll": {},
    },
    task_default_queue="default",
    task_routes={
        # Poll tasks — must be before the async_jobs wildcard
        "workers.tasks.async_jobs.poll_async_jobs": {"queue": "poll"},
        "workers.tasks.async_jobs.fetch_async_results": {"queue": "poll"},
        # Meta
        "workers.tasks.structure.*": {"queue": "meta"},
        "workers.tasks.insights.*": {"queue": "meta"},
        "workers.tasks.creatives.*": {"queue": "meta"},
        "workers.tasks.async_jobs.*": {"queue": "meta"},
        # TikTok
        "workers.tasks.tiktok_structure.*": {"queue": "tiktok"},
        "workers.tasks.tiktok_insights.*": {"queue": "tiktok"},
        "workers.tasks.tiktok_breakdowns.*": {"queue": "tiktok"},
        "workers.tasks.tiktok_creatives.*": {"queue": "tiktok"},
        "workers.tasks.tiktok_token_refresh.*": {"queue": "tiktok"},
        # Google
        "workers.tasks.google_structure.*": {"queue": "google"},
        "workers.tasks.google_insights.*": {"queue": "google"},
        "workers.tasks.google_breakdowns.*": {"queue": "google"},
        "workers.tasks.google_creatives.*": {"queue": "google"},
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
        "sync-tiktok-breakdowns": {
            "task": "workers.tasks.tiktok_breakdowns.sync_tiktok_breakdowns_all",
            "schedule": 60 * 60,  # every 1 hour
        },
        "refresh-tiktok-tokens": {
            "task": "workers.tasks.tiktok_token_refresh.refresh_tiktok_tokens",
            "schedule": crontab(hour=0, minute=30),  # daily at 00:30 UTC
        },
        # Google (SDK auto-refreshes the access token from the stored refresh
        # token, so there is no token-refresh task; no async-report jobs either).
        "sync-google-structure-all": {
            "task": "workers.tasks.google_structure.sync_google_structure_all",
            "schedule": 30 * 60,  # every 30 min
        },
        "sync-google-insights-daily": {
            "task": "workers.tasks.google_insights.sync_google_insights_daily_all",
            "schedule": 15 * 60,  # every 15 min
        },
        "sync-google-breakdowns": {
            "task": "workers.tasks.google_breakdowns.sync_google_breakdowns_all",
            "schedule": 60 * 60,  # every 1 hour
        },
    },
)
