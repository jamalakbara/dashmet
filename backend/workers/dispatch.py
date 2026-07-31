"""
Staggered fan-out for per-account sync tasks.

Beat dispatchers used to enqueue every account at the same instant — a thundering
herd that hits the shared Meta token simultaneously and trips the app-level
throttle. `stagger_dispatch` spreads enqueues across the sync interval, interleaves
accounts that share a connection (so one org's accounts don't burst against one
token), and skips connections that are currently rate-limit paused.
"""
import logging
import random

from workers.rate_limit import connection_paused_remaining

logger = logging.getLogger(__name__)


def stagger_dispatch(task, account_conn_pairs, extra_args=(), spread_seconds: int = 600) -> int:
    """Enqueue `task` once per account, spread over `spread_seconds`.

    account_conn_pairs — iterable of (account_id: str, connection_id: str | None).
    extra_args         — positional args appended after account_id on every call.
    Returns the number of tasks enqueued (paused connections are skipped).
    """
    # Group by connection, dropping any connection that's currently paused.
    by_conn: dict = {}
    skipped_conns = 0
    for account_id, connection_id in account_conn_pairs:
        if connection_id and connection_paused_remaining(connection_id) > 0:
            skipped_conns += 1
            continue
        by_conn.setdefault(connection_id, []).append(account_id)

    # Round-robin across connections so siblings land far apart in the schedule.
    buckets = [list(v) for v in by_conn.values()]
    ordered: list = []
    while any(buckets):
        for b in buckets:
            if b:
                ordered.append(b.pop(0))

    if not ordered:
        if skipped_conns:
            logger.info("stagger_dispatch: all %s connection(s) paused — nothing enqueued", skipped_conns)
        return 0

    step = spread_seconds / len(ordered)
    for i, account_id in enumerate(ordered):
        countdown = int(i * step + random.uniform(0, step))
        task.apply_async(args=[account_id, *extra_args], countdown=countdown)

    if skipped_conns:
        logger.info("stagger_dispatch: skipped %s paused connection(s)", skipped_conns)
    return len(ordered)
