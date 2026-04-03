from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import SECRET_KEY
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
async def test_mask_flow_returns_masked_document(
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
    monkeypatch.setattr(
        documents_route,
        "create_masked_assets",
        lambda source_path, boxes: ("masked/images/test-mask.jpg", "masked/pdfs/test-mask.pdf"),
    )
    monkeypatch.setattr(
        documents_route,
        "generate_presigned_url",
        lambda path, expires_in_seconds=600: f"/local-storage/{path}",
    )

    with sample_image_path.open("rb") as image_file:
        upload_response = await async_client.post(
            "/documents/upload",
            headers=auth_headers,
            files={"file": ("aadhaar_sample.jpg", image_file, "image/jpeg")},
        )

    assert upload_response.status_code == 200
    upload_payload = upload_response.json()

    mask_response = await async_client.post(
        f"/documents/{upload_payload['document_id']}/mask",
        headers=auth_headers,
        json={"mask_fields": ["uid", "dob"]},
    )

    assert mask_response.status_code == 200
    mask_payload = mask_response.json()
    assert mask_payload["masked_document_id"]
    assert mask_payload["preview_url"]

    masked_document = test_db_session.scalar(
        select(Document).where(Document.id == mask_payload["masked_document_id"])
    )
    assert masked_document is not None
    assert masked_document.parent_document_id is not None
    assert masked_document.bounding_boxes == {
        "aadhaar_number": [[2, 2, 18, 18]],
        "dob": [[20, 20, 36, 36]],
    }
    assert masked_document.extracted_fields["uid"] != "XXXX XXXX XXXX"
    assert masked_document.extracted_fields["uid"] == "123456789012"
    assert masked_document.extracted_fields["dob"] == "01-01-2000"


@pytest.mark.asyncio
async def test_mask_requires_valid_document_id(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import documents as documents_route

    def parse_uuid(value: str, detail: str) -> str:
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise documents_route.HTTPException(status_code=400, detail=detail) from exc

    monkeypatch.setattr(documents_route, "_parse_uuid", parse_uuid)

    response = await async_client.post(
        "/documents/not-a-uuid/mask",
        headers=auth_headers,
        json={"mask_fields": ["uid", "dob"]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid document ID"


@pytest.mark.asyncio
async def test_masked_pdf_reuses_existing_asset(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_image_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_db_session: Session,
) -> None:
    from app.api.routes import documents as documents_route

    monkeypatch.setattr(documents_route, "run_pipeline", lambda image: _mock_pipeline_result())
    monkeypatch.setattr(documents_route, "upload_file", lambda file_bytes, path, content_type=None: path)
    monkeypatch.setattr(documents_route, "_parse_uuid", lambda value, detail: str(UUID(value)))
    monkeypatch.setattr(
        documents_route,
        "create_masked_assets",
        lambda source_path, boxes: ("masked/images/test-mask.jpg", "masked/pdfs/test-mask.pdf"),
    )
    monkeypatch.setattr(
        documents_route,
        "generate_presigned_url",
        lambda path, expires_in_seconds=600: f"/local-storage/{path}",
    )

    with sample_image_path.open("rb") as image_file:
        upload_response = await async_client.post(
            "/documents/upload",
            headers=auth_headers,
            files={"file": ("aadhaar_sample.jpg", image_file, "image/jpeg")},
        )

    mask_response = await async_client.post(
        f"/documents/{upload_response.json()['document_id']}/mask",
        headers=auth_headers,
        json={"mask_fields": ["uid"]},
    )
    masked_document_id = mask_response.json()["masked_document_id"]
    masked_document = test_db_session.scalar(
        select(Document).where(Document.id == masked_document_id)
    )
    assert masked_document is not None
    expected_token = hmac.new(
        SECRET_KEY.encode("utf-8"),
        f"masked-pdf:{masked_document.id}:{masked_document.user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    monkeypatch.setattr(documents_route, "file_exists", lambda path: path == f"shares/{expected_token}.pdf")

    async def fail_generate(**kwargs: str) -> bytes:
        raise AssertionError("generate_masked_pdf should not be called when the PDF already exists")

    monkeypatch.setattr(documents_route, "generate_masked_pdf", fail_generate)
    monkeypatch.setattr(
        documents_route,
        "download_file",
        lambda path: (_ for _ in ()).throw(AssertionError("download_file should not be called")),
    )

    response = await async_client.get(
        f"/documents/{masked_document_id}/masked-pdf",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "share_token": expected_token,
        "pdf_url": f"/local-storage/shares/{expected_token}.pdf",
    }


@pytest.mark.asyncio
async def test_masked_pdf_generates_when_missing(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_image_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import documents as documents_route

    monkeypatch.setattr(documents_route, "run_pipeline", lambda image: _mock_pipeline_result())
    monkeypatch.setattr(documents_route, "upload_file", lambda file_bytes, path, content_type=None: path)
    monkeypatch.setattr(documents_route, "_parse_uuid", lambda value, detail: str(UUID(value)))
    monkeypatch.setattr(
        documents_route,
        "create_masked_assets",
        lambda source_path, boxes: ("masked/images/test-mask.jpg", "masked/pdfs/test-mask.pdf"),
    )
    monkeypatch.setattr(
        documents_route,
        "generate_presigned_url",
        lambda path, expires_in_seconds=600: f"/local-storage/{path}",
    )

    with sample_image_path.open("rb") as image_file:
        upload_response = await async_client.post(
            "/documents/upload",
            headers=auth_headers,
            files={"file": ("aadhaar_sample.jpg", image_file, "image/jpeg")},
        )

    mask_response = await async_client.post(
        f"/documents/{upload_response.json()['document_id']}/mask",
        headers=auth_headers,
        json={"mask_fields": ["uid"]},
    )
    masked_document_id = mask_response.json()["masked_document_id"]

    uploads: list[tuple[bytes, str, str | None]] = []

    monkeypatch.setattr(documents_route, "file_exists", lambda path: False)
    monkeypatch.setattr(documents_route, "download_file", lambda path: b"masked-image-bytes")

    async def fake_generate_masked_pdf(image_bytes: bytes, document_id: str, share_token: str) -> bytes:
        assert image_bytes == b"masked-image-bytes"
        assert document_id == masked_document_id
        assert len(share_token) == 32
        return b"%PDF-1.4\n"

    monkeypatch.setattr(documents_route, "generate_masked_pdf", fake_generate_masked_pdf)
    monkeypatch.setattr(
        documents_route,
        "upload_file",
        lambda file_bytes, path, content_type=None: uploads.append((file_bytes, path, content_type)) or path,
    )

    response = await async_client.get(
        f"/documents/{masked_document_id}/masked-pdf",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["share_token"]
    assert payload["pdf_url"] == f"/local-storage/shares/{payload['share_token']}.pdf"
    assert uploads == [
        (b"%PDF-1.4\n", f"shares/{payload['share_token']}.pdf", "application/pdf")
    ]
