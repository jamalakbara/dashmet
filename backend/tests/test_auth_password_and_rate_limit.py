"""Password-strength validation + login rate limiting.

Security guards added because the app previously enforced only min-length-8 and
had zero throttle on failed logins (unlimited brute force). Both are pure/redis
units — no DB fixture needed.
"""
import pytest
from pydantic import ValidationError

from app.config import settings
from app.schemas.auth import ResetPasswordRequest, SignupRequest
from app.services import auth as auth_svc


# ─── Password complexity ─────────────────────────────────────────────────────

VALID = "Str0ngPass"  # 8+, lower, upper, digit


def _signup(pw):
    return SignupRequest(name="A", email="a@b.co", password=pw, org_name="Org")


def test_valid_password_accepted():
    assert _signup(VALID).password == VALID


@pytest.mark.parametrize(
    "pw",
    [
        "short1A",        # < 8 chars
        "alllower123",    # no uppercase
        "ALLUPPER123",    # no lowercase
        "NoDigitsHere",   # no digit
        "password",       # the classic — fails multiple rules
    ],
)
def test_weak_passwords_rejected(pw):
    with pytest.raises(ValidationError):
        _signup(pw)


def test_reset_password_uses_same_rules():
    with pytest.raises(ValidationError):
        ResetPasswordRequest(token="t", new_password="weakpass")
    assert ResetPasswordRequest(token="t", new_password=VALID).new_password == VALID


# ─── Login rate limiting ─────────────────────────────────────────────────────

class FakeRedis:
    """Minimal redis stand-in: get/incr/delete + a pipeline that queues
    incr/expire. expire is a no-op (tests exercise counts, not TTL expiry)."""

    def __init__(self):
        self.store = {}

    def get(self, k):
        v = self.store.get(k)
        return None if v is None else str(v)

    def delete(self, k):
        self.store.pop(k, None)

    def _incr(self, k):
        self.store[k] = self.store.get(k, 0) + 1

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, r):
        self.r = r
        self.ops = []

    def incr(self, k):
        self.ops.append(("incr", k))
        return self

    def expire(self, k, _ttl):
        self.ops.append(("expire", k))
        return self

    def execute(self):
        for op, k in self.ops:
            if op == "incr":
                self.r._incr(k)
        self.ops = []


def test_not_limited_below_threshold():
    r = FakeRedis()
    for _ in range(settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT - 1):
        auth_svc.record_login_failure(r, "u@x.co", "1.2.3.4")
    assert auth_svc.login_rate_limited(r, "u@x.co", "1.2.3.4") is False


def test_account_locks_at_threshold():
    r = FakeRedis()
    for _ in range(settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT):
        auth_svc.record_login_failure(r, "u@x.co", "1.2.3.4")
    assert auth_svc.login_rate_limited(r, "u@x.co", "1.2.3.4") is True


def test_ip_locks_across_distinct_accounts():
    """Credential spraying: many emails, one IP → per-IP gate trips even though
    no single account hit its own limit."""
    r = FakeRedis()
    for i in range(settings.LOGIN_MAX_ATTEMPTS_PER_IP):
        auth_svc.record_login_failure(r, f"user{i}@x.co", "9.9.9.9")
    # A fresh account from that IP is already blocked.
    assert auth_svc.login_rate_limited(r, "brandnew@x.co", "9.9.9.9") is True


def test_clear_resets_account_but_not_ip():
    r = FakeRedis()
    for _ in range(settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT):
        auth_svc.record_login_failure(r, "u@x.co", "1.2.3.4")
    auth_svc.clear_login_failures(r, "u@x.co", "1.2.3.4")
    # Account counter cleared; from the same IP alone it's under the IP cap.
    assert auth_svc.login_rate_limited(r, "u@x.co", "1.2.3.4") is False
    # But the per-IP counter survives (one good login can't unlock a sprayer).
    assert int(r.get("login:fail:ip:1.2.3.4")) == settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT


def test_email_case_insensitive_key():
    r = FakeRedis()
    for _ in range(settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT):
        auth_svc.record_login_failure(r, "USER@x.co", "1.2.3.4")
    # Lookup with different casing hits the same lowercased key.
    assert auth_svc.login_rate_limited(r, "user@x.co", "1.2.3.4") is True
