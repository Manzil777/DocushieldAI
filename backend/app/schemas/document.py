from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from pydantic import Field


class DocumentUploadResponse(BaseModel):
    document_id: str
    fields: dict
    forgery: dict
    qr: dict


class MaskRequest(BaseModel):
    mask_fields: list[str] = Field(default_factory=list)


class MaskResponse(BaseModel):
    masked_document_id: UUID
    preview_url: str
