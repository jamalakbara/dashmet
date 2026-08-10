import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import ConflictError, InvalidTokenError
from app.models.auth import Organization, OrganizationMembership, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: str, org_id: str, role: str, email: str
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "email": email,
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def blacklist_token(jti: str, exp: datetime, redis_client) -> None:
    now = datetime.now(timezone.utc)
    exp_aware = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
    ttl = max(int((exp_aware - now).total_seconds()), 0)
    if ttl > 0:
        redis_client.setex(f"token:blacklist:{jti}", ttl, "1")


def is_token_blacklisted(jti: str, redis_client) -> bool:
    return bool(redis_client.exists(f"token:blacklist:{jti}"))


def _login_keys(email: str, ip: str) -> tuple[str, str]:
    return f"login:fail:acct:{email.lower()}", f"login:fail:ip:{ip}"


def login_rate_limited(redis_client, email: str, ip: str) -> bool:
    """True if the account OR the source IP has already exceeded its failed-login
    budget within the rolling window. Checked BEFORE verifying the password so a
    locked account can't be probed further."""
    acct_key, ip_key = _login_keys(email, ip)
    acct = int(redis_client.get(acct_key) or 0)
    src = int(redis_client.get(ip_key) or 0)
    return (
        acct >= settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT
        or src >= settings.LOGIN_MAX_ATTEMPTS_PER_IP
    )


def record_login_failure(redis_client, email: str, ip: str) -> None:
    """Increment both counters on a failed attempt, setting the window TTL on the
    first failure. TTL is refreshed each failure so sustained probing stays locked."""
    window = settings.LOGIN_LOCKOUT_WINDOW_SECONDS
    for key in _login_keys(email, ip):
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        pipe.execute()


def clear_login_failures(redis_client, email: str, ip: str) -> None:
    """Reset the per-account counter on a successful login. The per-IP counter is
    left to expire on its own so one good login can't unlock a spraying source."""
    acct_key, _ = _login_keys(email, ip)
    redis_client.delete(acct_key)


def encrypt_token(plain_token: str) -> str:
    f = Fernet(settings.ENCRYPTION_KEY.encode())
    return f.encrypt(plain_token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    try:
        f = Fernet(settings.ENCRYPTION_KEY.encode())
        return f.decrypt(encrypted.encode()).decode()
    except (InvalidToken, Exception) as e:
        raise InvalidTokenError(f"Token decryption failed: {e}")


def generate_slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    base = re.sub(r"-+", "-", base).strip("-") or "org"
    slug = base
    suffix = 1
    while db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def create_user_and_org(
    db: Session, name: str, email: str, password: str, org_name: str
) -> User:
    existing = db.query(User).filter(User.email == email.lower()).first()
    if existing:
        raise ConflictError("Email already registered")

    org = Organization(name=org_name, slug=generate_slug(db, org_name))
    db.add(org)
    db.flush()

    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        name=name,
        email_verified=False,
        email_verify_token=secrets.token_urlsafe(32),
    )
    db.add(user)
    db.flush()

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=user.id,
        role="owner",
        accepted_at=datetime.now(timezone.utc),
    )
    db.add(membership)

    return user


def verify_email(db: Session, token: str) -> User:
    user = db.query(User).filter(User.email_verify_token == token).first()
    if not user:
        raise InvalidTokenError("Invalid or expired verification token")
    user.email_verified = True
    user.email_verify_token = None
    return user


def initiate_password_reset(db: Session, email: str):
    """Returns user if found (caller sends email). Never reveals existence."""
    user = db.query(User).filter(User.email == email.lower()).first()
    if user:
        user.reset_password_token = secrets.token_urlsafe(32)
        user.reset_password_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return user


def reset_password(db: Session, token: str, new_password: str) -> User:
    user = db.query(User).filter(User.reset_password_token == token).first()
    if not user:
        raise InvalidTokenError("Invalid or expired reset token")
    now = datetime.now(timezone.utc)
    exp = user.reset_password_expires_at
    if exp:
        exp_aware = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        if now > exp_aware:
            raise InvalidTokenError("Reset token has expired")
    user.password_hash = hash_password(new_password)
    user.reset_password_token = None
    user.reset_password_expires_at = None
    return user


def get_user_org_role(db: Session, user_id: str, org_id: str):
    mem = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.accepted_at.isnot(None),
        )
        .first()
    )
    return mem.role if mem else None
