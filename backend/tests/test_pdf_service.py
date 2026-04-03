from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image


pytest.importorskip("reportlab")

from app.services.pdf_service import generate_masked_pdf


@pytest.mark.asyncio
async def test_generate_masked_pdf_returns_pdf_bytes() -> None:
    image = Image.new("RGB", (240, 140), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    pdf_bytes = await generate_masked_pdf(
        image_bytes=buffer.getvalue(),
        document_id="doc-123",
        share_token="share-token-123",
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert b"Masked Document doc-123" in pdf_bytes
    assert b"document_id=doc-123; share_token=share-token-123" in pdf_bytes
