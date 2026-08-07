"""TikTok historical backfill must reach the prior-period compare range.

Bug: `insights_historical` dispatched `last_30d`, so on any given day the
backfill covered only ~30 days. "Last month" + its compare (prior period =
the month before) needs ~2 full months of history. June (compare of July)
fell outside the 30-day window → compare came back empty while Meta (90-day
async backfill) worked. Fix adds a `last_90d` preset and uses it for the
TikTok historical job.
"""
from datetime import date, timedelta

from workers.tasks.tiktok_insights import _resolve_dates, _date_chunks, TIKTOK_MAX_REPORT_DAYS
from app.services.insights import resolve_date_range, resolve_prior_period


def test_last_90d_preset_exists_and_spans_90_days():
    start_s, end_s = _resolve_dates("last_90d")
    start, end = date.fromisoformat(start_s), date.fromisoformat(end_s)
    today = date.today()
    assert end == today - timedelta(1)
    assert start == today - timedelta(90)


def test_historical_window_covers_last_month_and_its_compare():
    """The 90-day TikTok backfill must fully contain both `last_month` and the
    prior period it compares against — the exact range the dashboard reads."""
    lm_start, lm_end = resolve_date_range("last_month")
    prior_start, prior_end = resolve_prior_period(lm_start, lm_end)

    hist_start_s, hist_end_s = _resolve_dates("last_90d")
    hist_start = date.fromisoformat(hist_start_s)
    hist_end = date.fromisoformat(hist_end_s)

    # Compare (earliest) start must be inside the backfill window...
    assert hist_start <= prior_start, (
        f"backfill starts {hist_start}, but compare needs data from {prior_start}"
    )
    # ...through the end of last month.
    assert hist_end >= lm_end, (
        f"backfill ends {hist_end}, but last month runs through {lm_end}"
    )


def test_90d_window_splits_into_le_30_day_chunks():
    """TikTok rejects any stat_time_day report wider than 30 days
    ("max time span is 30 days"). The 90-day backfill must be chunked."""
    start, end = _resolve_dates("last_90d")
    chunks = _date_chunks(start, end)

    # Every chunk within the API limit.
    for c_start, c_end in chunks:
        span_days = (date.fromisoformat(c_end) - date.fromisoformat(c_start)).days + 1
        assert span_days <= TIKTOK_MAX_REPORT_DAYS, f"chunk {c_start}..{c_end} spans {span_days}d"

    # Contiguous, no gaps or overlaps, covering the full range end-to-end.
    assert chunks[0][0] == start
    assert chunks[-1][1] == end
    for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:]):
        assert date.fromisoformat(next_start) == date.fromisoformat(prev_end) + timedelta(1)


def test_single_short_range_is_one_chunk():
    chunks = _date_chunks("2026-07-01", "2026-07-15")
    assert chunks == [("2026-07-01", "2026-07-15")]


def test_old_30d_window_would_have_missed_the_compare():
    """Regression guard: the previous `last_30d` window did NOT reach the
    compare range — proving the bug and locking in the fix."""
    lm_start, _ = resolve_date_range("last_month")
    prior_start, _ = resolve_prior_period(lm_start, resolve_date_range("last_month")[1])

    old_start = date.fromisoformat(_resolve_dates("last_30d")[0])
    assert old_start > prior_start, "30-day window unexpectedly reached the compare range"
