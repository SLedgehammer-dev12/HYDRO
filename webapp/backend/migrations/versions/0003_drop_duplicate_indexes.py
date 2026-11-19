"""Drop redundant duplicate indexes that already have single-column indexes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision: str = "0003"
down_revision: str | tuple[str, ...] | None = "0002"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_DUPLICATE_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("test_results", "ix_results_type", ("test_type",)),
    ("test_results", "ix_results_decision", ("decision_status",)),
    ("attachments", "ix_attachments_session", ("session_id",)),
    ("attachments", "ix_attachments_sha", ("sha256",)),
    ("ocr_analyses", "ix_ocr_attachment", ("attachment_id",)),
    ("section_forms", "ix_section_forms_project", ("project_id",)),
    ("audit_events", "ix_audit_action", ("action",)),
)


def upgrade() -> None:
    if context.is_offline_mode():
        for table_name, index_name, _cols in _DUPLICATE_INDEXES:
            op.drop_index(index_name, table_name=table_name)
        return

    inspector = sa.inspect(op.get_bind())
    for table_name, index_name, _cols in _DUPLICATE_INDEXES:
        existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table_name)


def downgrade() -> None:
    if context.is_offline_mode():
        for table_name, index_name, cols in _DUPLICATE_INDEXES:
            op.create_index(index_name, table_name, list(cols))
        return

    inspector = sa.inspect(op.get_bind())
    for table_name, index_name, cols in _DUPLICATE_INDEXES:
        existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
        if index_name not in existing:
            op.create_index(index_name, table_name, list(cols))
