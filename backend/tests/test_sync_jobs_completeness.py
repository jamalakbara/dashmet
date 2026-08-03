"""§11 sync_jobs completeness — every tracked job_type must have a producer.

The /sync/status envelope (and the freshness badge / section empty-states that
read it) reports one entry per tracked job_type. If a job_type has no worker
that writes a SyncJob row with that exact string, the UI can never see it reach
"completed" — e.g. the badge sticks on "partially synced" forever (P-2). This
test scans the worker source statically so a missing or misspelled producer
fails here instead of in the browser.
"""
import re
from pathlib import Path

from app.services.sync import JOB_TTLS

WORKERS_DIR = Path(__file__).resolve().parent.parent / "workers"

# job_types produced via a `job_type` *parameter* rather than a string literal
# (tiktok/google insights tasks pass job_type="insights_historical").
DYNAMIC_PRODUCERS = {"insights_daily", "insights_historical"}

# Known gap: creatives are fetched lazily/per-ad and write no SyncJob yet.
# Tracked in BOARD item 4 — remove from here when a producer lands.
LAZY_NO_PRODUCER_YET = {"creatives"}


def _literal_producers() -> set[str]:
    """All job_type string literals passed as the 3rd arg of create_sync_job."""
    found: set[str] = set()
    pat = re.compile(r"create_sync_job\(\s*[^,]+,\s*[^,]+,\s*\"([a-z_]+)\"")
    for path in WORKERS_DIR.rglob("*.py"):
        for m in pat.finditer(path.read_text()):
            found.add(m.group(1))
    return found


def test_every_tracked_job_type_has_a_producer():
    tracked = set(JOB_TTLS)
    producers = _literal_producers() | DYNAMIC_PRODUCERS
    missing = tracked - producers - LAZY_NO_PRODUCER_YET
    assert not missing, f"job_types with no SyncJob producer: {sorted(missing)}"


def test_breakdown_producer_is_singular():
    # Regression guard: endpoint tracks "breakdown"; workers must not write the
    # "breakdowns" plural (which silently never matched → stuck-partial badge).
    literals = _literal_producers()
    assert "breakdown" in literals
    assert "breakdowns" not in literals, "use singular 'breakdown' to match JOB_TTLS/sync status"
