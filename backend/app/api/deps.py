from typing import Annotated

import redis as redis_lib
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.auth import User
from app.services.auth import is_token_blacklisted

security = HTTPBearer()

redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id: str = payload.get("sub")
        org_id: str = payload.get("org_id")
        role: str = payload.get("role")
        jti: str = payload.get("jti")

        if user_id is None or org_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    if jti and is_token_blacklisted(jti, redis_client):
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None or not user.email_verified:
        raise credentials_exception

    return {
        "user_id": user_id,
        "org_id": org_id,
        "role": role,
        "email": user.email,
        "jti": jti,
    }


def require_owner(current_user: Annotated[dict, Depends(get_current_user)]):
    if current_user["role"] != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required",
        )
    return current_user


CurrentUser = Annotated[dict, Depends(get_current_user)]
OwnerUser = Annotated[dict, Depends(require_owner)]
DbSession = Annotated[Session, Depends(get_db)]
