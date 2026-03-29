from __future__ import annotations

import mimetypes
from io import BytesIO
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.core.config import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
)


LOCAL_STORAGE_ROOT = Path(__file__).resolve().parents[2] / ".storage"


def init_minio_client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def _local_store(file_bytes: bytes, path: str) -> str:
    destination = LOCAL_STORAGE_ROOT / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(file_bytes)
    return path


def upload_file(file_bytes: bytes, path: str, content_type: str | None = None) -> str:
    if not file_bytes:
        raise ValueError("Cannot upload an empty file")

    content_type = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
    client = init_minio_client()

    try:
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)

        client.put_object(
            bucket_name=MINIO_BUCKET,
            object_name=path,
            data=BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type,
        )
        return path
    except Exception:
        return _local_store(file_bytes, path)
