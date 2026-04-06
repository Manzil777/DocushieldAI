"""add document share fields to share_tokens

Revision ID: 8c3d4b2a9f10
Revises: 7f6b7d1c2e4a
Create Date: 2026-04-06 18:20:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8c3d4b2a9f10"
down_revision: Union[str, Sequence[str], None] = "7f6b7d1c2e4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID_SQL_TYPE = sa.UUID().with_variant(sa.String(length=36), "sqlite")


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    columns = _column_names("share_tokens")

    with op.batch_alter_table("share_tokens") as batch_op:
        if "document_id" not in columns:
            batch_op.add_column(
                sa.Column(
                    "document_id",
                    UUID_SQL_TYPE,
                    sa.ForeignKey("documents.id", ondelete="CASCADE"),
                    nullable=True,
                )
            )
        if "view_count" not in columns:
            batch_op.add_column(
                sa.Column(
                    "view_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "masked_fields" not in columns:
            batch_op.add_column(sa.Column("masked_fields", sa.JSON(), nullable=True))
        if "vault_item_id" in columns:
            batch_op.alter_column(
                "vault_item_id",
                existing_type=UUID_SQL_TYPE,
                nullable=True,
            )

    indexes = _index_names("share_tokens")
    if "ix_share_tokens_document_id" not in indexes:
        op.create_index("ix_share_tokens_document_id", "share_tokens", ["document_id"], unique=False)


def downgrade() -> None:
    indexes = _index_names("share_tokens")
    if "ix_share_tokens_document_id" in indexes:
        op.drop_index("ix_share_tokens_document_id", table_name="share_tokens")

    columns = _column_names("share_tokens")
    with op.batch_alter_table("share_tokens") as batch_op:
        if "masked_fields" in columns:
            batch_op.drop_column("masked_fields")
        if "view_count" in columns:
            batch_op.drop_column("view_count")
        if "document_id" in columns:
            batch_op.drop_column("document_id")
        if "vault_item_id" in columns:
            batch_op.alter_column(
                "vault_item_id",
                existing_type=UUID_SQL_TYPE,
                nullable=False,
            )
