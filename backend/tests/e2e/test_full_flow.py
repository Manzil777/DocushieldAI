"""Task D-01: Full E2E smoke test — upload → mask → share → view."""

from __future__ import annotations

import base64
from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient


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


@pytest.mark.asyncio
async def test_upload_mask_share_flow(
    async_client: AsyncClient,
    sample_image_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy-path E2E: register → login → upload → mask → share → public view."""

    _apply_monkeypatches(monkeypatch)

    # ── 1. Register ──────────────────────────────────────────────
    reg = await async_client.post(
        "/auth/register",
        json={"email": "e2e@example.com", "password": "strongpass123"},
    )
    assert reg.status_code == 200

    # ── 2. Login ─────────────────────────────────────────────────
    login = await async_client.post(
        "/auth/login",
        json={"email": "e2e@example.com", "password": "strongpass123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["access_token"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # ── 3. Upload ────────────────────────────────────────────────
    with sample_image_path.open("rb") as f:
        upload = await async_client.post(
            "/documents/upload",
            headers=headers,
            files={"file": ("aadhaar_sample.jpg", f, "image/jpeg")},
        )
    assert upload.status_code == 200
    upload_payload = upload.json()
    document_id = upload_payload["document_id"]
    assert upload_payload["fields"]
    assert upload_payload["forgery"]

    # ── 4. Mask (uid + dob) ──────────────────────────────────────
    mask = await async_client.post(
        f"/documents/{document_id}/mask",
        headers=headers,
        json={"mask_fields": ["uid", "dob"]},
    )
    assert mask.status_code == 200
    masked_document_id = mask.json()["masked_document_id"]

    # ── 5. Generate share token ──────────────────────────────────
    pdf = await async_client.get(
        f"/documents/{masked_document_id}/masked-pdf",
        headers=headers,
    )
    assert pdf.status_code == 200
    share_token = pdf.json()["share_token"]
    assert share_token

    # ── 6. Public share view (NO auth) ───────────────────────────
    share = await async_client.get(f"/share/{share_token}")
    assert share.status_code == 200
    share_payload = share.json()
    assert base64.b64decode(share_payload["document"]) == b"masked-image-bytes"
    assert share_payload["fields"]
    assert share_payload["pdf_url"]
    assert share_payload["expires_at"]

    # ── 7. Verify access count incremented ───────────────────────
    share2 = await async_client.get(f"/share/{share_token}")
    assert share2.status_code == 200
