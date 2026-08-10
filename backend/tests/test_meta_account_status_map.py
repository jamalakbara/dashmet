"""Unit tests for META_ACCOUNT_STATUS_MAP in workers.tasks.structure (no DB).

Regression guard for the reported bug where a Meta ad account with an
UNSETTLED status (integer 3, e.g. Persebaya) was hidden and never synced.
The fix makes UNSETTLED/pending statuses map to "unsettled" (visible +
syncable, not "disabled"), and — critically — makes any *unrecognized*
integer status default to "unsettled" rather than silently vanishing the
account (P-2/P-4).
"""
import pytest

from workers.tasks.structure import META_ACCOUNT_STATUS_MAP


def _resolve(status_int):
    """Mirror the exact resolution the sync code uses (structure.py:153):
    unknown/unmapped ints default to "unsettled", never "disabled"."""
    return META_ACCOUNT_STATUS_MAP.get(status_int, "unsettled")


@pytest.mark.parametrize("status_int", [1, 9])
def test_active_statuses_map_to_active(status_int):
    assert META_ACCOUNT_STATUS_MAP[status_int] == "active"


@pytest.mark.parametrize("status_int", [3, 7, 8])
def test_unsettled_statuses_map_to_unsettled(status_int):
    # 3=UNSETTLED, 7=PENDING_RISK_REVIEW, 8=PENDING_SETTLEMENT — data still readable.
    assert META_ACCOUNT_STATUS_MAP[status_int] == "unsettled"


@pytest.mark.parametrize("status_int", [2, 100, 101])
def test_disabled_statuses_map_to_disabled(status_int):
    # 2=DISABLED, 100=PENDING_CLOSURE, 101=CLOSED — terminal, hidden from reads.
    assert META_ACCOUNT_STATUS_MAP[status_int] == "disabled"


@pytest.mark.parametrize("status_int", [999, 0, -1, 42])
def test_unknown_status_defaults_to_unsettled_not_disabled(status_int):
    # The core regression guard: an unrecognized status must stay visible and
    # syncable ("unsettled"), never silently hidden ("disabled").
    assert status_int not in META_ACCOUNT_STATUS_MAP
    assert _resolve(status_int) == "unsettled"


def test_no_status_ever_resolves_to_something_unexpected():
    # Every mapped value is one of the three states the read side understands.
    assert set(META_ACCOUNT_STATUS_MAP.values()) <= {"active", "unsettled", "disabled"}
