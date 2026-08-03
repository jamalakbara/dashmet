"""Unit tests for stagger_dispatch — the staggered fan-out used by every
per-account sync beat task and by the eager first-sync on connect (D-lite).

No broker/DB needed: a fake task records apply_async calls, and the paused-
connection check is monkeypatched.
"""
import workers.dispatch as dispatch
from workers.dispatch import stagger_dispatch


class _FakeTask:
    def __init__(self):
        self.calls = []

    def apply_async(self, args=None, countdown=None):
        self.calls.append({"args": list(args or []), "countdown": countdown})


def _no_pause(_connection_id):
    return 0


def test_one_enqueue_per_account(monkeypatch):
    monkeypatch.setattr(dispatch, "connection_paused_remaining", _no_pause)
    task = _FakeTask()
    pairs = [("a1", "c1"), ("a2", "c1"), ("a3", "c2")]

    n = stagger_dispatch(task, pairs, spread_seconds=60)

    assert n == 3
    assert len(task.calls) == 3
    assert {c["args"][0] for c in task.calls} == {"a1", "a2", "a3"}


def test_extra_args_appended_after_account(monkeypatch):
    monkeypatch.setattr(dispatch, "connection_paused_remaining", _no_pause)
    task = _FakeTask()

    stagger_dispatch(task, [("a1", "c1")], extra_args=("last_30d",), spread_seconds=10)

    assert task.calls[0]["args"] == ["a1", "last_30d"]


def test_paused_connection_skipped(monkeypatch):
    # c2 is paused → its accounts are not enqueued; c1's still are.
    monkeypatch.setattr(
        dispatch,
        "connection_paused_remaining",
        lambda cid: 300 if cid == "c2" else 0,
    )
    task = _FakeTask()
    pairs = [("a1", "c1"), ("a2", "c2"), ("a3", "c2")]

    n = stagger_dispatch(task, pairs, spread_seconds=60)

    assert n == 1
    assert [c["args"][0] for c in task.calls] == ["a1"]


def test_countdowns_within_spread(monkeypatch):
    monkeypatch.setattr(dispatch, "connection_paused_remaining", _no_pause)
    task = _FakeTask()
    pairs = [(f"a{i}", "c1") for i in range(10)]

    stagger_dispatch(task, pairs, spread_seconds=100)

    # Every enqueue is spread within [0, spread_seconds); none fire all at once.
    countdowns = [c["countdown"] for c in task.calls]
    assert all(0 <= cd < 100 for cd in countdowns)
    assert len(set(countdowns)) > 1  # genuinely staggered, not a thundering herd


def test_empty_pairs_enqueues_nothing(monkeypatch):
    monkeypatch.setattr(dispatch, "connection_paused_remaining", _no_pause)
    task = _FakeTask()

    assert stagger_dispatch(task, []) == 0
    assert task.calls == []
