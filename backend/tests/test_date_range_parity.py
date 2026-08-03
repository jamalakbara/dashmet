"""Read-vs-write date-range parity (PRD §11, §2.3, P-7).

The write path (Meta sync workers) must resolve a `date_preset` to an explicit
`time_range` using the *same* resolver the read path uses — never send a raw
preset to Meta and let it pick the calendar boundary. These tests pin that:

1. `meta_time_range` produces exactly the dates `resolve_date_range` returns
   (the read path's resolver), across presets × timezones — so synced days ==
   queried days by construction.
2. The output is a Meta-shaped `time_range` JSON string, not a preset.
"""
import json
from datetime import date

import pytest

from app.services.insights import resolve_date_range
from workers.date_range import meta_time_range

PRESETS = [
    "today", "yesterday",
    "last_7d", "last_14d", "last_28d", "last_30d", "last_90d",
    "this_month", "last_month", "this_year", "lifetime",
]
TIMEZONES = ["UTC", "Asia/Jakarta", "America/Los_Angeles", "Pacific/Kiritimati"]


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("tz", TIMEZONES)
def test_write_range_matches_read_resolver(preset, tz):
    """meta_time_range(preset, tz) covers exactly resolve_date_range(preset, tz)."""
    since, until = resolve_date_range(preset, tz)
    tr = json.loads(meta_time_range(preset, tz))
    assert tr == {"since": since.isoformat(), "until": until.isoformat()}


@pytest.mark.parametrize("tz", TIMEZONES)
def test_output_is_time_range_not_preset(tz):
    """Output is a Meta time_range object with ISO dates — never a preset string."""
    tr = json.loads(meta_time_range("last_7d", tz))
    assert set(tr) == {"since", "until"}
    # Parses as real dates (would raise on a preset like "last_7d").
    date.fromisoformat(tr["since"])
    date.fromisoformat(tr["until"])
    assert tr["since"] <= tr["until"]


def test_unknown_preset_rejected():
    """An unknown preset fails loudly rather than leaking to Meta."""
    with pytest.raises(ValueError):
        meta_time_range("last_5000_years", "UTC")
