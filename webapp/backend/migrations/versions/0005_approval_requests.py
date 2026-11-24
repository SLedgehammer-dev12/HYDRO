"""Add two-person approval_requests table for RBAC and sign-off workflows.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision: str = "0005"
down_revision: str | tuple[str, ...] | None = "0004"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    if not context.is_offline_mode():
        inspector = sa.inspect(op.get_bind())
        if "approval_requests" in set(inspector.get_table_names()):
            return

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id_hash", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column(
            "requested_role", sa.String(length=32), nullable=False, server_default="operator"
        ),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_role", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_requests")),
    )
    op.create_index(
        op.f("ix_approval_requests_workspace_id_hash"),
        "approval_requests",
        ["workspace_id_hash"],
        unique=False,
    )
    op.create_index(
        "ix_approvals_workspace_status",
        "approval_requests",
        ["workspace_id_hash", "status"],
        unique=False,
    )
    op.create_index(
        "ix_approvals_target",
        "approval_requests",
        ["action", "target_id"],
        unique=False,
    )


def downgrade() -> None:
    if not context.is_offline_mode():
        inspector = sa.inspect(op.get_bind())
        if "approval_requests" not in set(inspector.get_table_names()):
            return

    op.drop_index("ix_approvals_target", table_name="approval_requests")
    op.drop_index("ix_approvals_workspace_status", table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_workspace_id_hash"), table_name="approval_requests")
    op.drop_table("approval_requests")
