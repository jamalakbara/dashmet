import logging

from sqlalchemy import text

from workers.celery_app import celery_app
from workers.db_helpers import get_worker_db

logger = logging.getLogger(__name__)

SYNC_JOBS_RETENTION_DAYS = 7


@celery_app.task(name="workers.tasks.maintenance.prune_sync_jobs")
def prune_sync_jobs() -> dict:
    with get_worker_db() as db:
        result = db.execute(
            text(
                "DELETE FROM sync_jobs "
                "WHERE created_at < now() - interval '1 day' * :days"
            ),
            {"days": SYNC_JOBS_RETENTION_DAYS},
        )
        deleted = result.rowcount

    logger.info("prune_sync_jobs: deleted %d rows older than %dd", deleted, SYNC_JOBS_RETENTION_DAYS)
    return {"deleted": deleted}
