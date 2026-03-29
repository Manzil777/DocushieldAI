from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.user import Base, UUID_SQL_TYPE


if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class VaultItem(Base):
    __tablename__ = "vault_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID_SQL_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    encrypted_key: Mapped[str] = mapped_column(String(512), nullable=False)
    minio_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="vault_items")
    document: Mapped["Document"] = relationship(back_populates="vault_items")
    share_tokens: Mapped[list["ShareToken"]] = relationship(
        back_populates="vault_item",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"VaultItem(id={self.id!s}, user_id={self.user_id!s}, document_id={self.document_id!s})"


class ShareToken(Base):
    __tablename__ = "share_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID_SQL_TYPE, primary_key=True, default=uuid.uuid4)
    vault_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vault_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_views: Mapped[int] = mapped_column(Integer, nullable=False)

    vault_item: Mapped["VaultItem"] = relationship(back_populates="share_tokens")

    def __repr__(self) -> str:
        return f"ShareToken(id={self.id!s}, vault_item_id={self.vault_item_id!s}, token={self.token!r})"
