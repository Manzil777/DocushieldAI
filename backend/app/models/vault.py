from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, LargeBinary, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.user import Base, UUID_SQL_TYPE


if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class VaultItem(Base):
    __tablename__ = "vault_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID_SQL_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID_SQL_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="vault_items")
    share_tokens: Mapped[list["ShareToken"]] = relationship(
        back_populates="vault_item",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"VaultItem(id={self.id!s}, user_id={self.user_id!s}, filename={self.filename!r})"


class ShareToken(Base):
    __tablename__ = "share_tokens"
    __table_args__ = (
        CheckConstraint(
            "(vault_item_id IS NOT NULL) OR (document_id IS NOT NULL)",
            name="ck_share_tokens_target_present",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_SQL_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID_SQL_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vault_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_SQL_TYPE,
        ForeignKey("vault_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_SQL_TYPE,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    masked_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="share_tokens")
    vault_item: Mapped["VaultItem | None"] = relationship(back_populates="share_tokens")
    document: Mapped["Document | None"] = relationship(back_populates="share_tokens")

    def __repr__(self) -> str:
        return (
            "ShareToken("
            f"id={self.id!s}, "
            f"user_id={self.user_id!s}, "
            f"vault_item_id={self.vault_item_id!s}, "
            f"document_id={self.document_id!s}, "
            f"token={self.token!r})"
        )
