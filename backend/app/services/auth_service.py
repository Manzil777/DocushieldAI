from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from typing import Any
from uuid import UUID

import redis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, ExpiredSignatureError, jwt
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import (
    ALGORITHM,
    DATABASE_URL,
    REDIS_URL,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import Base, User


engine_kwargs: dict[str, Any] = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}


engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base.metadata.create_all(bind=engine)

http_bearer = HTTPBearer(auto_error=False)


class InMemoryRefreshStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def setex(self, key: str, ttl: timedelta | int, value: str) -> bool:
        self._store[key] = str(value)
        return True

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


_fallback_store = InMemoryRefreshStore()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis_client() -> redis.Redis | InMemoryRefreshStore:
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        client.ping()
        return client
    except redis.RedisError:
        return _fallback_store


def register_user(db: Session, email: str, password: str) -> User:
    user = User(email=email.strip().lower(), hashed_password=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        ) from exc
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    stmt = select(User).where(User.email == email.strip().lower())
    user = db.scalar(stmt)
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return user


def create_tokens(user_id: UUID | str) -> dict[str, str]:
    subject = {"sub": str(user_id)}
    return {
        "access_token": create_access_token(subject),
        "refresh_token": create_refresh_token(subject),
        "token_type": "bearer",
    }


def store_refresh_token(token: str, user_id: UUID | str) -> None:
    ttl_seconds = int(timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS).total_seconds())
    client = get_redis_client()
    client.setex(token, ttl_seconds, str(user_id))


def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from exc
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc


def verify_refresh_token(token: str) -> str:
    payload = _decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    stored_user_id = get_redis_client().get(token)
    if stored_user_id is None or str(stored_user_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is not active",
        )
    return str(user_id)


def revoke_refresh_token(token: str) -> None:
    get_redis_client().delete(token)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    return str(user_id)
