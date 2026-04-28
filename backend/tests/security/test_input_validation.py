from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
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


@pytest.fixture()
def client(test_db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    del test_db_session

    from app.services import auth_service

    refresh_store = InMemoryRefreshStore()
    monkeypatch.setattr(auth_service, "get_redis_client", lambda: refresh_store)

    with TestClient(app) as test_client:
        yield test_client


def _auth_headers(client: TestClient) -> dict[str, str]:
    register_response = client.post(
        "/auth/register",
        json={"email": "security-input@example.com", "password": "strongpass123"},
    )
    assert register_response.status_code == 200

    login_response = client.post(
        "/auth/login",
        json={"email": "security-input@example.com", "password": "strongpass123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def test_invalid_file_type_upload_is_rejected(client: TestClient) -> None:
    headers = _auth_headers(client)

    response = client.post(
        "/documents/upload",
        headers=headers,
        files={"file": ("payload.exe", b"MZ", "application/x-msdownload")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type"


def test_large_malformed_upload_returns_client_error_without_crashing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import documents as documents_route

    headers = _auth_headers(client)
    monkeypatch.setattr(
        documents_route,
        "upload_file",
        lambda file_bytes, path, content_type=None: path,
    )

    large_invalid_image = b"\x00" * (2 * 1024 * 1024)
    response = client.post(
        "/documents/upload",
        headers=headers,
        files={"file": ("large.jpg", large_invalid_image, "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image file"


def test_malformed_json_request_returns_validation_error(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        content=b'{"email":"user@example.com","password":}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["type"] == "json_invalid"
