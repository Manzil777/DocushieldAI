from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from pathlib import Path
import sqlite3
import sys
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
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
from app.models import Base, VaultItem
from app.services.auth_service import InMemoryRefreshStore, get_db


@pytest.fixture()
def test_db_session(monkeypatch: pytest.MonkeyPatch) -> Generator[Session, None, None]:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")

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

    from app.api.routes import vault as vault_routes
    from app.services import auth_service

    refresh_store = app.state.test_refresh_store
    monkeypatch.setattr(auth_service, "get_redis_client", lambda: refresh_store)

    storage: dict[str, bytes] = {}

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
    setattr(app.state, "vault_test_storage", storage)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    if hasattr(app.state, "vault_test_storage"):
        delattr(app.state, "vault_test_storage")


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


@pytest.mark.asyncio
async def test_vault_round_trip_encrypts_and_decrypts(
    async_client: AsyncClient,
) -> None:
    auth_headers = await _register_and_login(async_client, "vault-owner@example.com", "strongpass123")
    plaintext = b"top secret aadhaar payload"

    upload_response = await async_client.post(
        "/vault/",
        headers=auth_headers,
        files={"file": ("aadhaar.pdf", plaintext, "application/pdf")},
    )
    assert upload_response.status_code == 201
    payload = upload_response.json()
    vault_id = payload["id"]

    stored_ciphertext = app.state.vault_test_storage[payload["storage_path"]]
    assert stored_ciphertext != plaintext

    list_response = await async_client.get("/vault/", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["filename"] == "aadhaar.pdf"

    download_response = await async_client.get(f"/vault/{vault_id}", headers=auth_headers)
    assert download_response.status_code == 200
    assert download_response.content == plaintext
    assert download_response.headers["content-disposition"] == 'attachment; filename="aadhaar.pdf"'


@pytest.mark.asyncio
async def test_wrong_user_cannot_access_vault_item(
    async_client: AsyncClient,
) -> None:
    owner_headers = await _register_and_login(async_client, "owner@example.com", "strongpass123")
    intruder_headers = await _register_and_login(async_client, "intruder@example.com", "strongpass123")

    upload_response = await async_client.post(
        "/vault/",
        headers=owner_headers,
        files={"file": ("secret.txt", b"classified", "text/plain")},
    )
    vault_id = upload_response.json()["id"]

    fetch_response = await async_client.get(f"/vault/{vault_id}", headers=intruder_headers)
    assert fetch_response.status_code == 403
    assert fetch_response.json()["detail"] == "Not authorized to access this vault item"

    delete_response = await async_client.delete(f"/vault/{vault_id}", headers=intruder_headers)
    assert delete_response.status_code == 403
    assert delete_response.json()["detail"] == "Not authorized to access this vault item"


@pytest.mark.asyncio
async def test_delete_removes_db_record_and_stored_file(
    async_client: AsyncClient,
    test_db_session: Session,
) -> None:
    auth_headers = await _register_and_login(async_client, "delete-owner@example.com", "strongpass123")

    upload_response = await async_client.post(
        "/vault/",
        headers=auth_headers,
        files={"file": ("delete-me.txt", b"erase me", "text/plain")},
    )
    payload = upload_response.json()
    vault_id = payload["id"]
    storage_path = payload["storage_path"]

    assert storage_path in app.state.vault_test_storage

    delete_response = await async_client.delete(f"/vault/{vault_id}", headers=auth_headers)
    assert delete_response.status_code == 200
    assert delete_response.json() == {"message": "Vault item deleted successfully"}
    assert storage_path not in app.state.vault_test_storage

    db_item = test_db_session.scalar(select(VaultItem).where(VaultItem.id == UUID(vault_id)))
    assert db_item is None


@pytest.mark.asyncio
async def test_tampered_ciphertext_fails_decryption(
    async_client: AsyncClient,
) -> None:
    auth_headers = await _register_and_login(async_client, "tamper-owner@example.com", "strongpass123")

    upload_response = await async_client.post(
        "/vault/",
        headers=auth_headers,
        files={"file": ("tamper.txt", b"do not alter", "text/plain")},
    )
    payload = upload_response.json()
    storage_path = payload["storage_path"]

    ciphertext = bytearray(app.state.vault_test_storage[storage_path])
    ciphertext[-1] ^= 0x01
    app.state.vault_test_storage[storage_path] = bytes(ciphertext)

    download_response = await async_client.get(f"/vault/{payload['id']}", headers=auth_headers)
    assert download_response.status_code == 500
    assert download_response.json()["detail"] == "Failed to decrypt file"
