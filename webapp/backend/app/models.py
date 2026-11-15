"""SQLAlchemy models for the HYDRO web database.

Portable across SQLite/PostgreSQL: UUIDs are stored as ``CHAR(36)`` strings,
timestamps as timezone-aware datetimes and structured payloads as ``JSON``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id_hash: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    client: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (Index("ix_projects_workspace_updated", "workspace_id_hash", "updated_at"),)


class HydroSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), default=None
    )
    workspace_id_hash: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    wizard_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    legacy_id: Mapped[str | None] = mapped_column(String(32), default=None, unique=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        Index("ix_sessions_workspace_updated", "workspace_id_hash", "updated_at"),
        Index("ix_sessions_project", "project_id"),
        Index("ix_sessions_status", "status"),
    )


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    test_type: Mapped[str] = mapped_column(String(32), index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decision_status: Mapped[str] = mapped_column(String(32), default="BEKLIYOR", index=True)
    decision_title: Mapped[str] = mapped_column(String(200), default="")
    decision_summary: Mapped[str] = mapped_column(Text, default="")
    decision_rule: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    engine_version: Mapped[str] = mapped_column(String(64), default="")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_results_session_computed", "session_id", "computed_at"),
        Index("ix_results_type", "test_type"),
        Index("ix_results_decision", "decision_status"),
    )


class TimeSeriesRecord(Base):
    __tablename__ = "time_series"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pressure_bar: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    volume_m3: Mapped[float | None] = mapped_column(Float, default=None)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_time_series_session_ts", "session_id", "timestamp"),)


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id_hash: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="SET NULL"), default=None, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="other")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_attachments_session", "session_id"),
        Index("ix_attachments_sha", "sha256"),
    )


class OcrAnalysis(Base):
    __tablename__ = "ocr_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id_hash: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="SET NULL"), default=None, index=True
    )
    attachment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("attachments.id", ondelete="CASCADE"), index=True
    )
    mapping_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ocr_mapping_profiles.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    source: Mapped[str | None] = mapped_column(String(32), default=None)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    discrepancies: Mapped[list[Any]] = mapped_column(JSON, default=list)
    issues: Mapped[list[Any]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        Index("ix_ocr_status_created", "status", "created_at"),
        Index("ix_ocr_attachment", "attachment_id"),
    )


class OcrMappingProfile(Base):
    __tablename__ = "ocr_mapping_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id_hash: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    format_key: Mapped[str] = mapped_column(String(120))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    mode: Mapped[str] = mapped_column(String(16), default="pre_extract")
    mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        UniqueConstraint("workspace_id_hash", "format_key", name="uq_ocr_profile_workspace_format"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    session_id: Mapped[str | None] = mapped_column(String(36), default=None, index=True)
    actor: Mapped[str] = mapped_column(String(80), default="anonymous")
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    request_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_audit_session_created", "session_id", "created_at"),
        Index("ix_audit_action", "action"),
    )


__all__ = [
    "Attachment",
    "AuditEvent",
    "Base",
    "HydroSession",
    "OcrAnalysis",
    "OcrMappingProfile",
    "Project",
    "TestResult",
    "TimeSeriesRecord",
    "new_uuid",
    "utcnow",
]
