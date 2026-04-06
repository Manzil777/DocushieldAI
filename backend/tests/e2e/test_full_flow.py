"""Task D-01: Full E2E smoke test — upload → mask → share → view."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, ShareToken


EXPECTED_FIELDS = {
    "uid": "123456789012",
    "dob": "01-01-2000",
}
EXPECTED_BOXES = {
    "aadhaar_number": [[2, 2, 18, 18]],
    "dob": [[20, 20, 36, 36]],
}
EXPECTED_MASKED_FIELDS = {
    "uid": "XXXX XXXX 9012",
    "dob": "XX/XX/XXXX",
}


def _mock_pipeline_result() -> dict[str, object]:
    return {
        "fields": EXPECTED_FIELDS,
        "bounding_boxes": EXPECTED_BOXES,
        "forgery": {"status": "clear"},
        "qr": {"status": "not_checked"},
    }


def _apply_monkeypatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply all external-service stubs needed for the full flow."""
    from app.api.routes import documents as documents_route
    from app.services import share_service

    monkeypatch.setattr(documents_route, "_bytes_to_image", lambda file_bytes, content_type: object())
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
    monkeypatch.setattr(documents_route, "download_file", lambda path: b"masked-image-bytes")
    monkeypatch.setattr(documents_route, "file_exists", lambda path: True)
    monkeypatch.setattr(share_service, "download_file", lambda path: b"masked-image-bytes")
    monkeypatch.setattr(
        share_service,
        "generate_presigned_url",
        lambda path, expires_in_seconds=600: f"/local-storage/{path}",
    )


async def _register_and_login(async_client: AsyncClient) -> dict[str, str]:
    register_response = await async_client.post(
        "/auth/register",
        json={"email": "e2e@example.com", "password": "strongpass123"},
    )
    assert register_response.status_code == 200
    assert register_response.json() == {"message": "User registered successfully"}

    login_response = await async_client.post(
        "/auth/login",
        json={"email": "e2e@example.com", "password": "strongpass123"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _upload_document(
    async_client: AsyncClient,
    sample_image_path: Path,
    headers: dict[str, str],
) -> dict[str, Any]:
    with sample_image_path.open("rb") as file_obj:
        response = await async_client.post(
            "/documents/upload",
            headers=headers,
            files={"file": ("aadhaar_sample.jpg", file_obj, "image/jpeg")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"]
    assert payload["fields"] == EXPECTED_FIELDS
    assert payload["forgery"] == {"status": "clear"}
    assert payload["qr"] == {"status": "not_checked"}
    return payload


async def _wait_for_processing_completion(
    async_client: AsyncClient,
    document_id: str,
    headers: dict[str, str],
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    deadline = monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None

    while monotonic() <= deadline:
        response = await async_client.get(f"/documents/{document_id}/status", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        last_payload = payload

        if payload["status"] == "completed":
            return payload
        if payload["status"] == "failed":
            pytest.fail(f"AI processing failed for document {document_id}: {payload}")

        await asyncio.sleep(poll_interval_seconds)

    pytest.fail(f"Timed out waiting for document {document_id} to complete processing: {last_payload}")


async def _list_vault_documents(
    async_client: AsyncClient,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    response = await async_client.get("/vault/", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    return payload


@pytest.mark.asyncio
async def test_upload_mask_share_flow(
    async_client: AsyncClient,
    sample_image_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_db_session: Session,
) -> None:
    """Happy-path E2E: upload → AI processing → masking → vault → share → public view."""

    _apply_monkeypatches(monkeypatch)

    headers = await _register_and_login(async_client)

    # ── 1. Upload ────────────────────────────────────────────────
    upload_payload = await _upload_document(async_client, sample_image_path, headers)
    document_id = upload_payload["document_id"]
    uploaded_document = test_db_session.scalar(select(Document).where(Document.id == document_id))
    assert uploaded_document is not None
    assert uploaded_document.parent_document_id is None
    assert uploaded_document.file_path.startswith("documents/")
    assert uploaded_document.file_path.endswith(f"{document_id}.jpg")
    assert uploaded_document.preview_file_path == uploaded_document.file_path
    assert uploaded_document.extracted_fields == EXPECTED_FIELDS
    assert uploaded_document.bounding_boxes == EXPECTED_BOXES

    # ── 2. AI processing status ──────────────────────────────────
    status_payload = await _wait_for_processing_completion(async_client, document_id, headers)
    assert status_payload["document_id"] == document_id
    assert status_payload["status"] == "completed"
    assert status_payload["fields"] == EXPECTED_FIELDS
    assert status_payload["detections"] == EXPECTED_BOXES
    assert status_payload["detection_metadata"]["field_count"] == 2
    assert status_payload["detection_metadata"]["bounding_box_count"] == 2
    assert status_payload["detection_metadata"]["forgery_status"] == "clear"
    assert status_payload["detection_metadata"]["qr_status"] == "not_checked"

    # ── 3. Mask (uid + dob) ──────────────────────────────────────
    mask = await async_client.post(
        f"/documents/{document_id}/mask",
        headers=headers,
        json={"mask_fields": ["uid", "dob"]},
    )
    assert mask.status_code == 200
    mask_payload = mask.json()
    masked_document_id = mask_payload["masked_document_id"]
    assert masked_document_id != document_id
    assert mask_payload["preview_url"] == "/local-storage/masked/images/test-mask.jpg"

    masked_document = test_db_session.scalar(select(Document).where(Document.id == masked_document_id))
    assert masked_document is not None
    assert str(masked_document.parent_document_id) == document_id
    assert masked_document.file_path == "masked/pdfs/test-mask.pdf"
    assert masked_document.preview_file_path == "masked/images/test-mask.jpg"
    assert masked_document.preview_file_path != uploaded_document.preview_file_path
    assert masked_document.bounding_boxes == EXPECTED_BOXES

    # ── 4. Vault persistence view ────────────────────────────────
    vault_documents = await _list_vault_documents(async_client, headers)
    original_vault_entry = next(item for item in vault_documents if item["id"] == document_id)
    masked_vault_entry = next(item for item in vault_documents if item["id"] == masked_document_id)
    assert original_vault_entry["masked"] is False
    assert original_vault_entry["parent_document_id"] is None
    assert original_vault_entry["file_path"].endswith(f"{document_id}.jpg")
    assert masked_vault_entry["masked"] is True
    assert masked_vault_entry["parent_document_id"] == document_id
    assert masked_vault_entry["file_path"] == "masked/pdfs/test-mask.pdf"
    assert masked_vault_entry["preview_file_path"] == "masked/images/test-mask.jpg"

    # ── 5. Generate share token ──────────────────────────────────
    pdf = await async_client.get(
        f"/documents/{masked_document_id}/masked-pdf",
        headers=headers,
    )
    assert pdf.status_code == 200
    pdf_payload = pdf.json()
    share_token = pdf_payload["share_token"]
    assert len(share_token) == 32
    assert pdf_payload["pdf_url"] == f"/local-storage/shares/{share_token}.pdf"

    share_record = test_db_session.scalar(select(ShareToken).where(ShareToken.token == share_token))
    assert share_record is not None
    assert str(share_record.document_id) == masked_document_id
    assert share_record.masked_fields == EXPECTED_MASKED_FIELDS
    assert share_record.expires_at is not None

    # ── 6. Public share view (NO auth) ───────────────────────────
    share = await async_client.get(f"/share/{share_token}")
    assert share.status_code == 200
    share_payload = share.json()
    assert base64.b64decode(share_payload["document"]) == b"masked-image-bytes"
    assert share_payload["fields"] == EXPECTED_MASKED_FIELDS
    assert share_payload["pdf_url"] == "/local-storage/masked/pdfs/test-mask.pdf"
    assert share_payload["expires_at"]

    # ── 7. Verify access count incremented ───────────────────────
    share2 = await async_client.get(f"/share/{share_token}")
    assert share2.status_code == 200
    assert share2.json()["fields"] == EXPECTED_MASKED_FIELDS
    assert base64.b64decode(share2.json()["document"]) == b"masked-image-bytes"

    test_db_session.expire_all()
    refreshed_share_record = test_db_session.scalar(select(ShareToken).where(ShareToken.token == share_token))
    assert refreshed_share_record is not None
    assert refreshed_share_record.view_count == 2
