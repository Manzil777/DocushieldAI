from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    preview_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parent_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id"),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    extracted_fields: Mapped[dict] = mapped_column(JSON, nullable=False)
    bounding_boxes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    forgery_result: Mapped[dict] = mapped_column(JSON, nullable=False)
    qr_result: Mapped[dict] = mapped_column(JSON, nullable=False)
