"""E2E test fixtures with a lightweight in-process route client."""

from __future__ import annotations

import json as jsonlib
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPAuthorizationCredentials

from backend.tests.integration.conftest import sample_image_path, test_db_session  # noqa: F401
from app.services import auth_service, share_service


@dataclass
class _ClientResponse:
    status_code: int
    payload: Any

    def json(self) -> Any:
        return self.payload

    @property
    def text(self) -> str:
        return jsonlib.dumps(self.payload)


class _UploadedFile:
    def __init__(self, filename: str, content_type: str, file_bytes: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._file_bytes = file_bytes

    async def read(self) -> bytes:
        return self._file_bytes


class E2EAsyncClient:
    def __init__(self, test_db_session, share_store) -> None:
        self._db = test_db_session
        self._share_store = share_store

    def _response(self, result: Any, status_code: int = 200) -> _ClientResponse:
        return _ClientResponse(status_code=status_code, payload=jsonable_encoder(result))

    def _error_response(self, exc: HTTPException) -> _ClientResponse:
        return _ClientResponse(status_code=exc.status_code, payload={"detail": exc.detail})

    def _current_user(self, headers: dict[str, str] | None) -> str:
        authorization = (headers or {}).get("Authorization")
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        scheme, _, token = authorization.partition(" ")
        credentials = HTTPAuthorizationCredentials(scheme=scheme, credentials=token)
        return auth_service.get_current_user(credentials)

    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        files: dict[str, tuple[str, Any, str]] | None = None,
    ) -> _ClientResponse:
        from app.api.routes import auth as auth_route
        from app.api.routes import documents as documents_route
        from app.schemas.auth import UserCreate, UserLogin
        from app.schemas.document import MaskRequest

        try:
            if path == "/auth/register":
                payload = UserCreate(**(json or {}))
                return self._response(auth_route.register(payload, db=self._db))

            if path == "/auth/login":
                payload = UserLogin(**(json or {}))
                return self._response(auth_route.login(payload, db=self._db))

            if path == "/documents/upload":
                if not files or "file" not in files:
                    raise HTTPException(status_code=400, detail="Missing file")
                filename, file_obj, content_type = files["file"]
                file_bytes = file_obj.read()
                upload = _UploadedFile(filename=filename, content_type=content_type, file_bytes=file_bytes)
                result = await documents_route.upload_document(
                    file=upload,
                    current_user=self._current_user(headers),
                    db=self._db,
                )
                return self._response(result)

            if path.startswith("/documents/") and path.endswith("/mask"):
                document_id = path.removeprefix("/documents/").removesuffix("/mask")
                result = documents_route.mask_document(
                    id=document_id,
                    payload=MaskRequest(**(json or {})),
                    current_user=self._current_user(headers),
                    db=self._db,
                )
                return self._response(result)
        except HTTPException as exc:
            return self._error_response(exc)

        raise AssertionError(f"Unsupported POST path in E2E client: {path}")

    async def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> _ClientResponse:
        from app.api.routes import auth as auth_route
        from app.api.routes import documents as documents_route

        try:
            if path == "/auth/me":
                return self._response(auth_route.me(self._current_user(headers)))

            if path.startswith("/documents/") and path.endswith("/masked-pdf"):
                document_id = path.removeprefix("/documents/").removesuffix("/masked-pdf")
                result = await documents_route.get_masked_pdf(
                    id=document_id,
                    current_user=self._current_user(headers),
                    db=self._db,
                    redis_client=self._share_store,
                )
                return self._response(result)

            if path.startswith("/share/"):
                token = path.removeprefix("/share/")
                result = share_service.get_shared_document_response(
                    token=token,
                    client_ip="127.0.0.1",
                    db=self._db,
                    redis_client=self._share_store,
                )
                return self._response(result)
        except HTTPException as exc:
            return self._error_response(exc)

        raise AssertionError(f"Unsupported GET path in E2E client: {path}")


@pytest_asyncio.fixture()
async def async_client(test_db_session, monkeypatch: pytest.MonkeyPatch) -> E2EAsyncClient:
    from app.main import app

    refresh_store = getattr(app.state, "test_refresh_store")
    share_store = getattr(app.state, "test_share_store")

    monkeypatch.setattr(auth_service, "get_redis_client", lambda: refresh_store)
    return E2EAsyncClient(
        test_db_session=test_db_session,
        share_store=share_store,
    )
