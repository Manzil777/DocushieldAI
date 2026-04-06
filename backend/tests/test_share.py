from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Generator
from pathlib import Path
import sqlite3
import sys
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
while "" in sys.path:
    sys.path.remove("")
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sqlite3.register_adapter(UUID, str)

from app.main import app
from app.models import Base
from app.services.auth_service import InMemoryRefreshStore, get_db
from app.services.redis_service import InMemoryRedisStore, get_token, get_token_ttl, get_view_count


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

    def override_test_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_test_db

    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest_asyncio.fixture()
async def async_client(test_db_session: Session, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    del test_db_session

    from app.api.routes import vault as vault_routes
    from app.services import auth_service, redis_service
    from app.services import share_service

    refresh_store = InMemoryRefreshStore()
    share_store = InMemoryRedisStore()
    storage: dict[str, bytes] = {}

    monkeypatch.setattr(auth_service, "get_redis_client", lambda: refresh_store)
    monkeypatch.setattr(redis_service, "get_redis_client", lambda: share_store)
    app.dependency_overrides[redis_service.get_redis_client] = lambda: share_store

    def fake_upload_file(file_bytes: bytes, path: str, content_type: str | None = None) -> str:
        del content_type
        storage[path] = file_bytes
        return path

    def fake_download_file(path: str) -> bytes:
        if path not in storage:
            raise FileNotFoundError(path)
        return storage[path]

    def fake_delete_file(path: str) -> None:
        if path not in storage:
            raise FileNotFoundError(path)
        del storage[path]

    monkeypatch.setattr(vault_routes, "upload_file", fake_upload_file)
    monkeypatch.setattr(vault_routes, "download_file", fake_download_file)
    monkeypatch.setattr(vault_routes, "delete_file", fake_delete_file)
    monkeypatch.setattr(share_service, "download_file", fake_download_file)

    setattr(app.state, "vault_test_storage", storage)
    setattr(app.state, "share_test_store", share_store)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    if hasattr(app.state, "vault_test_storage"):
        delattr(app.state, "vault_test_storage")
    if hasattr(app.state, "share_test_store"):
        delattr(app.state, "share_test_store")
    app.dependency_overrides.pop(redis_service.get_redis_client, None)


async def _register_and_login(async_client: AsyncClient, email: str, password: str) -> dict[str, str]:
    register_response = await async_client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 200

    login_response = await async_client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def _get_current_user_id(async_client: AsyncClient, headers: dict[str, str]) -> str:
    response = await async_client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    return response.json()["user_id"]


async def _create_vault_item(async_client: AsyncClient, headers: dict[str, str], filename: str, data: bytes) -> str:
    response = await async_client.post(
        "/vault/",
        headers=headers,
        files={"file": (filename, data, "application/octet-stream")},
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_share_token_creation_sets_redis_ttl_and_returns_qr(async_client: AsyncClient) -> None:
    headers = await _register_and_login(async_client, "share-owner@example.com", "strongpass123")
    user_id = await _get_current_user_id(async_client, headers)
    vault_id = await _create_vault_item(async_client, headers, "aadhaar.pdf", b"shareable data")

    response = await async_client.post(
        f"/vault/{vault_id}/share",
        headers=headers,
        json={"ttl_hours": 24, "max_views": 10},
    )
    assert response.status_code == 201
    payload = response.json()

    assert payload["share_url"].endswith(f"/share/{payload['token']}")
    assert get_token(payload["token"]) == {
        "vault_item_id": vault_id,
        "user_id": user_id,
        "max_views": 10,
    }
    assert 0 < get_token_ttl(payload["token"]) <= 24 * 3600
    base64.b64decode(payload["qr_code"], validate=True)


@pytest.mark.asyncio
async def test_share_access_decrypts_file_and_increments_views(async_client: AsyncClient) -> None:
    headers = await _register_and_login(async_client, "share-access@example.com", "strongpass123")
    vault_id = await _create_vault_item(async_client, headers, "shared.txt", b"highly confidential")

    create_response = await async_client.post(
        f"/vault/{vault_id}/share",
        headers=headers,
        json={"ttl_hours": 24, "max_views": 3},
    )
    token = create_response.json()["token"]

    first_access = await async_client.get(f"/share/{token}")
    assert first_access.status_code == 200
    assert first_access.content == b"highly confidential"
    assert get_view_count(token) == 1

    second_access = await async_client.get(f"/share/{token}")
    assert second_access.status_code == 200
    assert second_access.content == b"highly confidential"
    assert get_view_count(token) == 2


@pytest.mark.asyncio
async def test_share_max_views_enforced(async_client: AsyncClient) -> None:
    headers = await _register_and_login(async_client, "share-limit@example.com", "strongpass123")
    vault_id = await _create_vault_item(async_client, headers, "limit.txt", b"view once")

    create_response = await async_client.post(
        f"/vault/{vault_id}/share",
        headers=headers,
        json={"ttl_hours": 24, "max_views": 1},
    )
    token = create_response.json()["token"]

    first_access = await async_client.get(f"/share/{token}")
    assert first_access.status_code == 200

    second_access = await async_client.get(f"/share/{token}")
    assert second_access.status_code == 403
    assert second_access.json()["detail"] == "Share token view limit exceeded"
    assert get_view_count(token) == 2


@pytest.mark.asyncio
async def test_expired_share_token_is_denied(async_client: AsyncClient) -> None:
    headers = await _register_and_login(async_client, "share-expired@example.com", "strongpass123")
    vault_id = await _create_vault_item(async_client, headers, "expired.txt", b"expiring soon")

    create_response = await async_client.post(
        f"/vault/{vault_id}/share",
        headers=headers,
        json={"ttl_hours": 24, "max_views": 5},
    )
    token = create_response.json()["token"]

    share_store = app.state.share_test_store
    share_store.force_expire(f"share:{token}", f"share:{token}:views")

    response = await async_client.get(f"/share/{token}")
    assert response.status_code == 410
    assert response.json()["detail"] == "Share token has expired"


@pytest.mark.asyncio
async def test_cross_user_share_creation_is_rejected(async_client: AsyncClient) -> None:
    owner_headers = await _register_and_login(async_client, "share-owner-two@example.com", "strongpass123")
    intruder_headers = await _register_and_login(async_client, "share-intruder@example.com", "strongpass123")
    vault_id = await _create_vault_item(async_client, owner_headers, "private.txt", b"owner only")

    response = await async_client.post(
        f"/vault/{vault_id}/share",
        headers=intruder_headers,
        json={"ttl_hours": 24, "max_views": 5},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to access this vault item"
