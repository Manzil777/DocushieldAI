from __future__ import annotations

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: str
    fields: dict
    forgery: dict
    qr: dict
