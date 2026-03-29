from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pdf2image import convert_from_bytes
from PIL import Image
from sqlalchemy.orm import Session

from app.models.document import Document
from app.schemas.document import DocumentUploadResponse
from app.services.auth_service import get_current_user, get_db
from app.services.pipeline_service import run_pipeline
from app.services.storage_service import upload_file


router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}


def _bytes_to_image(file_bytes: bytes, content_type: str) -> np.ndarray:
    if content_type == "application/pdf":
        pages = convert_from_bytes(file_bytes, first_page=1, last_page=1)
        if not pages:
            raise HTTPException(status_code=400, detail="PDF contains no pages")
        rgb = np.array(pages[0].convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    array = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file")
    return image


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file")
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    document_id = str(uuid4())
    extension = ALLOWED_CONTENT_TYPES[file.content_type]
    storage_path = f"documents/{current_user}/{document_id}{extension}"

    try:
        file_path = upload_file(file_bytes, storage_path, content_type=file.content_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to store file") from exc

    try:
        image = _bytes_to_image(file_bytes, file.content_type)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to parse uploaded file") from exc

    try:
        pipeline_result = run_pipeline(image)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Pipeline execution failed") from exc

    document = Document(
        id=document_id,
        user_id=int(current_user),
        file_path=file_path,
        extracted_fields=pipeline_result["fields"],
        forgery_result=pipeline_result["forgery"],
        qr_result=pipeline_result["qr"],
    )
    db.add(document)
    db.commit()

    return DocumentUploadResponse(
        document_id=document_id,
        fields=pipeline_result["fields"],
        forgery=pipeline_result["forgery"],
        qr=pipeline_result["qr"],
    )
