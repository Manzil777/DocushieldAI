from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
while "" in sys.path:
    sys.path.remove("")
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sqlite3.register_adapter(UUID, str)

from app.core.config import ALGORITHM, SECRET_KEY
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.models import Base, User
from app.services import auth_service
from app.services.auth_service import (
    InMemoryRefreshStore,
    get_current_user,
    register_user,
    verify_refresh_token,
)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_registered_password_is_hashed_in_storage(db_session: Session) -> None:
    password = "strongpass123"
    user = register_user(db_session, "security@example.com", password)

    stored_user = db_session.scalar(select(User).where(User.id == user.id))
    assert stored_user is not None
    assert stored_user.hashed_password != password
    assert stored_user.hashed_password.startswith("$2")
    assert verify_password(password, stored_user.hashed_password) is True


def test_access_token_is_generated_with_expiry_and_validates_current_user() -> None:
    user_id = str(uuid4())
    token = create_access_token({"sub": user_id})

    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == user_id
    assert payload["type"] == "access"
    assert payload["jti"]
    assert payload["exp"] > payload["iat"]

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert get_current_user(credentials) == user_id


def test_invalid_access_token_is_rejected() -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-valid-jwt")

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


def test_expired_refresh_token_is_rejected_even_when_present_in_store(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = str(uuid4())
    refresh_store = InMemoryRefreshStore()
    monkeypatch.setattr(auth_service, "get_redis_client", lambda: refresh_store)

    fresh_token = create_refresh_token({"sub": user_id})
    fresh_payload = jwt.decode(
        fresh_token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_exp": False},
    )
    fresh_payload["iat"] = datetime.now(timezone.utc) - timedelta(minutes=10)
    fresh_payload["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired_token = jwt.encode(fresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    refresh_store.setex(expired_token, 60, user_id)

    with pytest.raises(HTTPException) as exc_info:
        verify_refresh_token(expired_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token has expired"
