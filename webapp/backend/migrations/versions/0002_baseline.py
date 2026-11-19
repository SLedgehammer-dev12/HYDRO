"""Baseline HYDRO Web schema (v1.9.1 / legacy 0002 equivalent).

Revision ID: 0002
Revises:
Create Date: 2026-11-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | tuple[str, ...] | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "schema_migrations",
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("version", name="pk_schema_migrations"),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id_hash", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("client", sa.String(length=200), nullable=True),
        sa.Column("contractor", sa.String(length=200), nullable=True),
        sa.Column("supervisor", sa.String(length=200), nullable=True),
        sa.Column("pipeline_length_m", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("defaults", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_index("ix_projects_workspace_id_hash", "projects", ["workspace_id_hash"])
    op.create_index(
        "ix_projects_workspace_updated", "projects", ["workspace_id_hash", "updated_at"]
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("wizard_state", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("legacy_id", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_sessions_project_id_projects",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("legacy_id", name="uq_sessions_legacy_id"),
    )
    op.create_index("ix_sessions_workspace_id_hash", "sessions", ["workspace_id_hash"])
    op.create_index(
        "ix_sessions_workspace_updated", "sessions", ["workspace_id_hash", "updated_at"]
    )
    op.create_index("ix_sessions_project", "sessions", ["project_id"])
    op.create_index("ix_sessions_status", "sessions", ["status"])

    op.create_table(
        "test_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("test_type", sa.String(length=32), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("decision_status", sa.String(length=32), nullable=False),
        sa.Column("decision_title", sa.String(length=200), nullable=False),
        sa.Column("decision_summary", sa.Text(), nullable=False),
        sa.Column("decision_rule", sa.Text(), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_test_results_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_results"),
    )
    op.create_index("ix_test_results_session_id", "test_results", ["session_id"])
    op.create_index("ix_test_results_test_type", "test_results", ["test_type"])
    op.create_index("ix_test_results_decision_status", "test_results", ["decision_status"])
    op.create_index("ix_test_results_computed_at", "test_results", ["computed_at"])
    op.create_index("ix_results_session_computed", "test_results", ["session_id", "computed_at"])
    op.create_index("ix_results_type", "test_results", ["test_type"])
    op.create_index("ix_results_decision", "test_results", ["decision_status"])

    op.create_table(
        "time_series",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pressure_bar", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("volume_m3", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_time_series_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_time_series"),
    )
    op.create_index("ix_time_series_session_id", "time_series", ["session_id"])
    op.create_index("ix_time_series_timestamp", "time_series", ["timestamp"])
    op.create_index("ix_time_series_session_ts", "time_series", ["session_id", "timestamp"])

    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id_hash", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_attachments_session_id_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attachments"),
    )
    op.create_index("ix_attachments_workspace_id_hash", "attachments", ["workspace_id_hash"])
    op.create_index("ix_attachments_session_id", "attachments", ["session_id"])
    op.create_index("ix_attachments_sha256", "attachments", ["sha256"])
    op.create_index("ix_attachments_session", "attachments", ["session_id"])
    op.create_index("ix_attachments_sha", "attachments", ["sha256"])

    op.create_table(
        "ocr_mapping_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("format_key", sa.String(length=120), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ocr_mapping_profiles"),
        sa.UniqueConstraint(
            "workspace_id_hash", "format_key", name="uq_ocr_profile_workspace_format"
        ),
    )
    op.create_index(
        "ix_ocr_mapping_profiles_workspace_id_hash",
        "ocr_mapping_profiles",
        ["workspace_id_hash"],
    )

    op.create_table(
        "ocr_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id_hash", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("attachment_id", sa.String(length=36), nullable=False),
        sa.Column("mapping_profile_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("discrepancies", sa.JSON(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("dossier", sa.JSON(), nullable=True),
        sa.Column("needs_human_review", sa.Boolean(), nullable=False),
        sa.Column("approved_fields", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_ocr_analyses_attachment_id_attachments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_profile_id"],
            ["ocr_mapping_profiles.id"],
            name="fk_ocr_analyses_mapping_profile_id_ocr_mapping_profiles",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_ocr_analyses_session_id_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ocr_analyses"),
    )
    op.create_index("ix_ocr_analyses_workspace_id_hash", "ocr_analyses", ["workspace_id_hash"])
    op.create_index("ix_ocr_analyses_session_id", "ocr_analyses", ["session_id"])
    op.create_index("ix_ocr_analyses_attachment_id", "ocr_analyses", ["attachment_id"])
    op.create_index("ix_ocr_analyses_status", "ocr_analyses", ["status"])
    op.create_index("ix_ocr_status_created", "ocr_analyses", ["status", "created_at"])
    op.create_index("ix_ocr_attachment", "ocr_analyses", ["attachment_id"])

    op.create_table(
        "section_forms",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id_hash", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("form_code", sa.String(length=40), nullable=False),
        sa.Column("botas_code", sa.String(length=48), nullable=False),
        sa.Column("form_title", sa.String(length=160), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=True),
        sa.Column("attachment_id", sa.String(length=36), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("pages", sa.JSON(), nullable=False),
        sa.Column("form_date", sa.String(length=40), nullable=False),
        sa.Column("extracted_data", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["ocr_analyses.id"],
            name="fk_section_forms_analysis_id_ocr_analyses",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_section_forms_attachment_id_attachments",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_section_forms_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_section_forms_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_section_forms"),
        sa.UniqueConstraint("session_id", "form_code", name="uq_section_form_code"),
    )
    op.create_index("ix_section_forms_workspace_id_hash", "section_forms", ["workspace_id_hash"])
    op.create_index("ix_section_forms_project_id", "section_forms", ["project_id"])
    op.create_index("ix_section_forms_session_id", "section_forms", ["session_id"])
    op.create_index("ix_section_forms_status", "section_forms", ["status"])
    op.create_index("ix_section_forms_project", "section_forms", ["project_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id_hash", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_workspace_id_hash", "audit_events", ["workspace_id_hash"])
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_session_created", "audit_events", ["session_id", "created_at"])
    op.create_index("ix_audit_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("section_forms")
    op.drop_table("ocr_analyses")
    op.drop_table("ocr_mapping_profiles")
    op.drop_table("attachments")
    op.drop_table("time_series")
    op.drop_table("test_results")
    op.drop_table("sessions")
    op.drop_table("projects")
    op.drop_table("schema_migrations")
