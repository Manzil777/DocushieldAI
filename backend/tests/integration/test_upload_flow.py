from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


def _mock_pipeline_result() -> dict[str, object]:
    return {
        "fields": {
            "uid": "123456789012",
            "dob": "01-01-2000",
        },
        "bounding_boxes": {
            "aadhaar_number": [[2, 2, 18, 18]],
            "dob": [[20, 20, 36, 36]],
        },
        "forgery": {"status": "clear"},
        "qr": {"status": "not_checked"},
    }


@pytest.mark.asyncio
async def test_upload_flow_creates_document_record(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_image_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_db_session: Session,
) -> None:
    from app.api.routes import documents as documents_route

    monkeypatch.setattr(documents_route, "run_pipeline", lambda image: _mock_pipeline_result())
    monkeypatch.setattr(
        documents_route,
        "upload_file",
        lambda file_bytes, path, content_type=None: path,
    )
    monkeypatch.setattr(
        documents_route,
        "_parse_uuid",
        lambda value, detail: str(UUID(value)),
    )

    with sample_image_path.open("rb") as image_file:
        response = await async_client.post(
            "/documents/upload",
            headers=auth_headers,
            files={"file": ("aadhaar_sample.jpg", image_file, "image/jpeg")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"]
    assert payload["fields"] == {"uid": "123456789012", "dob": "01-01-2000"}
    assert payload["forgery"] == {"status": "clear"}
    assert payload["qr"] == {"status": "not_checked"}

    stored_document = test_db_session.scalar(
        select(Document).where(Document.id == payload["document_id"])
    )
    assert stored_document is not None
    assert stored_document.extracted_fields == {"uid": "123456789012", "dob": "01-01-2000"}
    assert stored_document.bounding_boxes == {
        "aadhaar_number": [[2, 2, 18, 18]],
        "dob": [[20, 20, 36, 36]],
    }


@pytest.mark.asyncio
async def test_upload_requires_file(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import documents as documents_route

    monkeypatch.setattr(
        documents_route,
        "upload_file",
        lambda file_bytes, path, content_type=None: path,
    )
    monkeypatch.setattr(
        documents_route,
        "_parse_uuid",
        lambda value, detail: str(UUID(value)),
    )

    response = await async_client.post("/documents/upload", headers=auth_headers)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"][-1] == "file"
