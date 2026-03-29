from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.user import Base, UUID_SQL_TYPE


if TYPE_CHECKING:
    from app.models.user import User
    from app.models.vault import VaultItem


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID_SQL_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    preview_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parent_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
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

    user: Mapped["User"] = relationship(back_populates="documents")
    vault_items: Mapped[list["VaultItem"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    parent_document: Mapped["Document | None"] = relationship(
        "Document",
        remote_side="Document.id",
        back_populates="child_documents",
    )
    child_documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="parent_document",
    )

    def __repr__(self) -> str:
        return f"Document(id={self.id!s}, user_id={self.user_id!s}, file_path={self.file_path!r})"
