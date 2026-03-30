from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import AsyncIterator, Generator
from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
sqlite3.register_adapter(UUID, str)

from app.main import app
from app.models import Base
from app.services.auth_service import InMemoryRefreshStore, get_db


@pytest.fixture()
def test_db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = testing_session_local()
    refresh_store = InMemoryRefreshStore()

    def override_test_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_test_db
    setattr(app.state, "test_refresh_store", refresh_store)

    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        if hasattr(app.state, "test_refresh_store"):
            delattr(app.state, "test_refresh_store")
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest_asyncio.fixture()
async def async_client(test_db_session: Session, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    del test_db_session

    from app.services import auth_service

    refresh_store = app.state.test_refresh_store
    monkeypatch.setattr(auth_service, "get_redis_client", lambda: refresh_store)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture()
async def auth_headers(async_client: AsyncClient) -> dict[str, str]:
    register_response = await async_client.post(
        "/auth/register",
        json={"email": "integration@example.com", "password": "strongpass123"},
    )
    assert register_response.status_code == 200

    login_response = await async_client.post(
        "/auth/login",
        json={"email": "integration@example.com", "password": "strongpass123"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()

    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture()
def sample_image_path() -> Path:
    return ROOT / "backend" / "tests" / "fixtures" / "aadhaar_sample.jpg"
