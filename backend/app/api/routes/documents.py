from __future__ import annotations

import logging
from uuid import UUID
from uuid import uuid4

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pdf2image import convert_from_bytes
from sqlalchemy.orm import Session

from app.models.document import Document
from app.schemas.document import DocumentUploadResponse, MaskRequest, MaskResponse
from app.services.auth_service import get_current_user, get_db
from app.services.masking_service import collect_mask_boxes, create_masked_assets
from app.services.pipeline_service import run_pipeline
from app.services.storage_service import generate_presigned_url, upload_file


router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

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


def _parse_uuid(value: str, detail: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


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

    user_id = _parse_uuid(current_user, "Invalid authentication token")
    document_id = uuid4()
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
        user_id=user_id,
        file_path=file_path,
        preview_file_path=file_path if file.content_type != "application/pdf" else None,
        extracted_fields=pipeline_result["fields"],
        bounding_boxes=pipeline_result["bounding_boxes"],
        forgery_result=pipeline_result["forgery"],
        qr_result=pipeline_result["qr"],
    )
    db.add(document)
    db.commit()

    return DocumentUploadResponse(
        document_id=str(document_id),
        fields=pipeline_result["fields"],
        forgery=pipeline_result["forgery"],
        qr=pipeline_result["qr"],
    )


@router.post("/{id}/mask", response_model=MaskResponse)
def mask_document(
    id: str,
    payload: MaskRequest,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MaskResponse:
    user_id = _parse_uuid(current_user, "Invalid authentication token")
    document_id = _parse_uuid(id, "Invalid document ID")

    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this document")

    try:
        filtered_boxes, applied_boxes_by_field = collect_mask_boxes(
            document.bounding_boxes,
            payload.mask_fields,
        )
        masked_image_path, masked_pdf_path = create_masked_assets(
            document.preview_file_path or document.file_path,
            filtered_boxes,
        )
        preview_url = generate_presigned_url(masked_image_path, expires_in_seconds=600)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored document file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to mask document %s", id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to mask document") from exc

    masked_document = Document(
        user_id=document.user_id,
        file_path=masked_pdf_path,
        preview_file_path=masked_image_path,
        parent_document_id=document.id,
        extracted_fields=document.extracted_fields,
        bounding_boxes=applied_boxes_by_field,
        forgery_result=document.forgery_result,
        qr_result=document.qr_result,
    )
    db.add(masked_document)
    db.commit()

    return MaskResponse(
        masked_document_id=masked_document.id,
        preview_url=preview_url,
    )
