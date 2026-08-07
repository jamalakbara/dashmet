"""
Single date resolver for the Meta sync workers.

PRD P-7 / §2.3: never send `date_preset` to a platform API — resolve it to an
explicit `time_range` in the account's timezone *first*, using the same resolver
the read path uses (`app.services.insights.resolve_date_range`). Sending a raw
preset lets Meta pick the calendar-day boundary with its own clock, so synced
rows and queried rows could cover different days. Resolving here guarantees
read-vs-write parity by construction.
"""
import json

from app.services.insights import resolve_date_range


def meta_time_range(date_preset: str, account_timezone: str) -> str:
    """Resolve a preset to a Meta `time_range` JSON string, e.g.
    '{"since": "2026-07-27", "until": "2026-08-03"}', in the account's timezone."""
    since, until = resolve_date_range(date_preset, account_timezone)
    return json.dumps({"since": since.isoformat(), "until": until.isoformat()})
