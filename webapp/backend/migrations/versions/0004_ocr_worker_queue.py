"""Add persistent OCR queue / lease / cancellation columns to ocr_analyses.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision: str = "0004"
down_revision: str | tuple[str, ...] | None = "0003"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_QUEUE_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("job_payload", sa.Column("job_payload", sa.JSON(), nullable=True)),
    ("attempts", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")),
    ("max_attempts", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")),
    ("lease_until", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True)),
    ("worker_id", sa.Column("worker_id", sa.String(64), nullable=True)),
    (
        "cancel_requested",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    ),
)


def upgrade() -> None:
    if context.is_offline_mode():
        for _name, col in _QUEUE_COLUMNS:
            op.add_column("ocr_analyses", col)
        return

    inspector = sa.inspect(op.get_bind())
    existing = {col["name"] for col in inspector.get_columns("ocr_analyses")}
    for name, col in _QUEUE_COLUMNS:
        if name not in existing:
            op.add_column("ocr_analyses", col)


def downgrade() -> None:
    if context.is_offline_mode():
        for name, _col in reversed(_QUEUE_COLUMNS):
            op.drop_column("ocr_analyses", name)
        return

    inspector = sa.inspect(op.get_bind())
    existing = {col["name"] for col in inspector.get_columns("ocr_analyses")}
    with op.batch_alter_table("ocr_analyses") as batch_op:
        for name, _col in reversed(_QUEUE_COLUMNS):
            if name in existing:
                batch_op.drop_column(name)
