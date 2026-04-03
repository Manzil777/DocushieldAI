"""archive legacy vault data and upgrade share schema

Revision ID: 7f6b7d1c2e4a
Revises: de26d69b69c6
Create Date: 2026-04-02 23:25:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f6b7d1c2e4a"
down_revision: Union[str, Sequence[str], None] = "de26d69b69c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID_SQL_TYPE = sa.UUID().with_variant(sa.String(length=36), "sqlite")
LEGACY_VAULT_NOTE = (
    "Archived during migration to AES-GCM vault schema; legacy rows lack a recoverable nonce "
    "and cannot be served safely by the current runtime."
)
LEGACY_SHARE_NOTE = "Archived during migration to Redis-backed share token schema."


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _create_legacy_archive_tables() -> None:
    tables = _table_names()

    if "vault_items_legacy_archive" not in tables:
        op.create_table(
            "vault_items_legacy_archive",
            sa.Column("id", UUID_SQL_TYPE, nullable=False),
            sa.Column("user_id", UUID_SQL_TYPE, nullable=False),
            sa.Column("document_id", UUID_SQL_TYPE, nullable=True),
            sa.Column("legacy_encrypted_key", sa.Text(), nullable=True),
            sa.Column("legacy_minio_path", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("document_file_path", sa.String(length=512), nullable=True),
            sa.Column(
                "archived_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("migration_note", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "share_tokens_legacy_archive" not in tables:
        op.create_table(
            "share_tokens_legacy_archive",
            sa.Column("id", UUID_SQL_TYPE, nullable=False),
            sa.Column("vault_item_id", UUID_SQL_TYPE, nullable=True),
            sa.Column("legacy_user_id", UUID_SQL_TYPE, nullable=True),
            sa.Column("token", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("view_count", sa.Integer(), nullable=True),
            sa.Column("max_views", sa.Integer(), nullable=True),
            sa.Column(
                "archived_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("migration_note", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def _archive_legacy_rows() -> None:
    bind = op.get_bind()
    tables = _table_names()

    if "vault_items" in tables:
        vault_columns = _column_names("vault_items")
        if {"document_id", "minio_path"} <= vault_columns:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO vault_items_legacy_archive (
                        id,
                        user_id,
                        document_id,
                        legacy_encrypted_key,
                        legacy_minio_path,
                        created_at,
                        document_file_path,
                        migration_note
                    )
                    SELECT
                        v.id,
                        v.user_id,
                        v.document_id,
                        v.encrypted_key,
                        v.minio_path,
                        v.created_at,
                        d.file_path,
                        :note
                    FROM vault_items AS v
                    LEFT JOIN documents AS d ON d.id = v.document_id
                    """
                ),
                {"note": LEGACY_VAULT_NOTE},
            )

    if "share_tokens" in tables:
        share_columns = _column_names("share_tokens")
        if {"view_count", "vault_item_id"} <= share_columns:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO share_tokens_legacy_archive (
                        id,
                        vault_item_id,
                        legacy_user_id,
                        token,
                        expires_at,
                        view_count,
                        max_views,
                        migration_note
                    )
                    SELECT
                        st.id,
                        st.vault_item_id,
                        v.user_id,
                        st.token,
                        st.expires_at,
                        st.view_count,
                        st.max_views,
                        :note
                    FROM share_tokens AS st
                    LEFT JOIN vault_items AS v ON v.id = st.vault_item_id
                    """
                ),
                {"note": LEGACY_SHARE_NOTE},
            )


def _drop_active_legacy_tables() -> None:
    tables = _table_names()
    if "share_tokens" in tables:
        op.drop_table("share_tokens")
    if "vault_items" in tables:
        op.drop_table("vault_items")


def _create_current_vault_items() -> None:
    tables = _table_names()
    if "vault_items" in tables:
        return

    op.create_table(
        "vault_items",
        sa.Column("id", UUID_SQL_TYPE, nullable=False),
        sa.Column("user_id", UUID_SQL_TYPE, nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(length=12), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index("ix_vault_items_user_id", "vault_items", ["user_id"], unique=False)


def _create_current_share_tokens() -> None:
    tables = _table_names()
    if "share_tokens" in tables:
        return

    op.create_table(
        "share_tokens",
        sa.Column("id", UUID_SQL_TYPE, nullable=False),
        sa.Column("user_id", UUID_SQL_TYPE, nullable=False),
        sa.Column("vault_item_id", UUID_SQL_TYPE, nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_views", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vault_item_id"], ["vault_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_share_tokens_token", "share_tokens", ["token"], unique=True)
    op.create_index("ix_share_tokens_user_id", "share_tokens", ["user_id"], unique=False)
    op.create_index("ix_share_tokens_vault_item_id", "share_tokens", ["vault_item_id"], unique=False)


def upgrade() -> None:
    """Upgrade schema."""
    _create_legacy_archive_tables()
    _archive_legacy_rows()
    _drop_active_legacy_tables()
    _create_current_vault_items()
    _create_current_share_tokens()


def downgrade() -> None:
    """Downgrade schema."""
    raise NotImplementedError(
        "This migration archives incompatible legacy vault/share rows and is intentionally irreversible."
    )
