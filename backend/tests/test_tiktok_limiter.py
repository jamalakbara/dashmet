"""Unit tests for TikTokClient._rate_limit_check — the app-level per-second
token bucket that enforces TikTok's 10 QPS app-wide limit (capped at 8 for
headroom).

Regression guard for the sync-failure bug: concurrent backfill fan-out burst
past 10 req/sec, TikTok returned HTTP 200 with code != 0 ("reaches the QPS
limit 10"), and every sync_jobs row finalized "failed". The old limiter only
counted per *minute* and never enforced the per-second app cap.

No broker/DB needed: a fake Redis provides atomic incr/decr/expire against an
in-memory dict, and a fake clock advances only when the bucket sleeps — so the
test is deterministic and never waits on a real wall-clock second.
"""
import ast
import pathlib

import workers.tiktok_client as tiktok_client
from workers.tiktok_client import TIKTOK_APP_QPS_CAP, TikTokClient


class _FakeRedis:
    """Minimal atomic incr/decr/expire over an in-memory dict (single-thread)."""

    def __init__(self):
        self.store: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def decr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) - 1
        return self.store[key]

    def expire(self, key: str, ttl: int) -> None:  # no-op for the test clock
        pass


class _FakeClock:
    """Monotonic clock that only moves forward when the bucket calls sleep(),
    so the 'wait until the next second' path is exercised without real delay."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _make_client(monkeypatch, redis, clock):
    monkeypatch.setattr(tiktok_client.time, "time", clock.time)
    monkeypatch.setattr(tiktok_client.time, "sleep", clock.sleep)
    # __init__ builds an httpx.Client but we never issue a request here.
    return TikTokClient(access_token="tok", redis_client=redis)


def test_cap_lets_exactly_cap_requests_through_per_second(monkeypatch):
    redis = _FakeRedis()
    clock = _FakeClock()
    client = _make_client(monkeypatch, redis, clock)

    start_second = int(clock.now)
    # Fire cap+1 checks back-to-back. The clock does NOT advance on its own; only
    # a bucket-induced sleep moves it. So the first `cap` land in the same second
    # and the (cap+1)th must be forced into the next second.
    for _ in range(TIKTOK_APP_QPS_CAP + 1):
        client._rate_limit_check()

    # The first window holds no more than the cap.
    assert redis.store[f"tiktok_qps:{start_second}"] == TIKTOK_APP_QPS_CAP
    # The overflow request was pushed into a later second (the clock advanced).
    assert int(clock.now) > start_second
    assert redis.store.get(f"tiktok_qps:{int(clock.now)}") == 1


def test_no_window_ever_exceeds_cap_under_burst(monkeypatch):
    redis = _FakeRedis()
    clock = _FakeClock()
    client = _make_client(monkeypatch, redis, clock)

    # A burst well beyond a single second's capacity (11 * cap requests).
    for _ in range(TIKTOK_APP_QPS_CAP * 11):
        client._rate_limit_check()

    # The invariant: NO one-second window ever passed more than the cap. This is
    # the actual guard against TikTok's app-wide 10 QPS limit being exceeded.
    per_window = {k: v for k, v in redis.store.items() if k.startswith("tiktok_qps:")}
    assert per_window, "expected the bucket to record per-second windows"
    assert max(per_window.values()) <= TIKTOK_APP_QPS_CAP
    assert TIKTOK_APP_QPS_CAP < 10  # headroom below the real app limit


def test_noop_without_redis(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(tiktok_client.time, "time", clock.time)
    monkeypatch.setattr(tiktok_client.time, "sleep", clock.sleep)
    client = TikTokClient(access_token="tok", redis_client=None)

    # Must not raise and must never sleep when there's no shared bucket.
    for _ in range(100):
        client._rate_limit_check()
    assert clock.now == 1000.0


def test_client_constructed_with_redis_enforces_cap(monkeypatch):
    """The bucket only works if a real redis_client is passed at construction.
    This exercises the wired-in path (not None) end-to-end from the constructor,
    guarding the 'bucket exists but self._redis is None so it no-ops' failure."""
    redis = _FakeRedis()
    clock = _FakeClock()
    monkeypatch.setattr(tiktok_client.time, "time", clock.time)
    monkeypatch.setattr(tiktok_client.time, "sleep", clock.sleep)

    client = TikTokClient(access_token="tok", redis_client=redis)
    assert client._redis is redis  # constructor actually stored it

    for _ in range(TIKTOK_APP_QPS_CAP * 5):
        client._rate_limit_check()

    per_window = {k: v for k, v in redis.store.items() if k.startswith("tiktok_qps:")}
    assert max(per_window.values()) <= TIKTOK_APP_QPS_CAP  # cap enforced, not inert


# ─── Structural guard: every task call site must WIRE IN a redis client ──────
# The QPS bucket was landed but every `TikTokClient(...)` in the task files was
# constructed bare, so the bucket no-op'd and the live QPS-limit failure came
# right back. This asserts, at the source level, that no TikTokClient(...) call
# in workers/tasks/ is missing a redis_client keyword — so the fix can't silently
# regress by someone adding a new bare construction.

_TASKS_DIR = pathlib.Path(tiktok_client.__file__).parent / "tasks"


def _tiktok_client_calls_missing_redis() -> list[str]:
    offenders: list[str] = []
    for path in sorted(_TASKS_DIR.glob("tiktok_*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "TikTokClient":
                kwargs = {kw.arg for kw in node.keywords}
                if "redis_client" not in kwargs:
                    offenders.append(f"{path.name}:{node.lineno}")
    return offenders


def test_every_task_call_site_passes_redis_client():
    offenders = _tiktok_client_calls_missing_redis()
    assert offenders == [], (
        "TikTokClient constructed without redis_client (bucket would no-op): "
        + ", ".join(offenders)
    )
