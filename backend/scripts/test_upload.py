from __future__ import annotations

import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_file = tempfile.NamedTemporaryFile(prefix="docushield_upload_", suffix=".db", delete=False)
db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["MINIO_ENDPOINT"] = "127.0.0.1:9001"

from fastapi.testclient import TestClient

from app.main import app


def _sample_image_path() -> Path:
    images = sorted((REPO_ROOT / "data" / "aadhaar" / "test" / "images").glob("*.jpg"))
    if not images:
        raise FileNotFoundError("No sample Aadhaar images found for upload test")
    return images[0]


def _make_pdf_bytes(image_path: Path) -> bytes:
    image = Image.open(image_path).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PDF")
    return buffer.getvalue()


def main() -> int:
    client = TestClient(app)
    email = "upload-test@example.com"
    password = "securepass123"

    client.post("/auth/register", json={"email": email, "password": password})
    login_response = client.post("/auth/login", json={"email": email, "password": password})
    tokens = login_response.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    image_path = _sample_image_path()
    image_bytes = image_path.read_bytes()
    pdf_bytes = _make_pdf_bytes(image_path)

    image_response = client.post(
        "/documents/upload",
        headers=headers,
        files={"file": (image_path.name, image_bytes, "image/jpeg")},
    )
    image_payload = image_response.json()
    print(
        "image_upload",
        image_response.status_code,
        {
            "document_id": image_payload.get("document_id"),
            "field_keys": sorted(image_payload.get("fields", {}).keys()),
            "forgery": {
                "is_forged": image_payload.get("forgery", {}).get("is_forged"),
                "confidence": image_payload.get("forgery", {}).get("confidence"),
            },
            "qr_valid": image_payload.get("qr", {}).get("qr_valid"),
        },
    )

    pdf_response = client.post(
        "/documents/upload",
        headers=headers,
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
    )
    pdf_payload = pdf_response.json()
    print(
        "pdf_upload",
        pdf_response.status_code,
        {
            "document_id": pdf_payload.get("document_id"),
            "field_keys": sorted(pdf_payload.get("fields", {}).keys()),
            "forgery": {
                "is_forged": pdf_payload.get("forgery", {}).get("is_forged"),
                "confidence": pdf_payload.get("forgery", {}).get("confidence"),
            },
            "qr_valid": pdf_payload.get("qr", {}).get("qr_valid"),
        },
    )

    invalid_response = client.post(
        "/documents/upload",
        headers=headers,
        files={"file": ("invalid.txt", b"not-a-document", "text/plain")},
    )
    print("invalid_upload", invalid_response.status_code, invalid_response.json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
