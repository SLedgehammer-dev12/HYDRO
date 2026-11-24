"""Persistent DB-backed OCR worker (Postgres FOR UPDATE SKIP LOCKED + SQLite compatible)."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
import time
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from hidrostatik_test.services.report_ocr import (
    ERROR_CANCELLED,
    OcrAnalysisResult,
    ReportOcrError,
    analyze_report,
)

from .. import db as db_module
from ..core.config import Settings, ensure_repo_on_path
from ..core.timeutil import utcnow
from ..models import Attachment, OcrAnalysis, OcrMappingProfile
from ..services import ocr as ocr_service
from ..services.ocr_queue import OCR_QUEUE

ensure_repo_on_path()

logger = logging.getLogger("hydro.web.ocr_worker")


def default_worker_id() -> str:
    host = socket.gethostname()[:24] or "host"
    return f"{host}-{os.getpid()}-{uuid.uuid4().hex[:6]}"


def reclaim_expired_leases(db: OrmSession) -> dict[str, int]:
    """Requeue or fail running OCR jobs whose lease has expired."""
    now = utcnow()
    stale = (
        db.execute(
            select(OcrAnalysis).where(
                OcrAnalysis.status == "running",
                OcrAnalysis.lease_until.is_not(None),
                OcrAnalysis.lease_until < now,
            )
        )
        .scalars()
        .all()
    )
    requeued = 0
    failed = 0
    for row in stale:
        attempts = int(row.attempts or 0)
        max_attempts = max(1, int(row.max_attempts or 3))
        if row.cancel_requested:
            row.status = "cancelled"
            row.lease_until = None
            row.worker_id = None
            row.finished_at = now
        elif attempts < max_attempts:
            row.status = "queued"
            row.lease_until = None
            row.worker_id = None
            requeued += 1
        else:
            row.status = "failed"
            row.error_code = "worker_lease_expired"
            row.error_message = "OCR iscisi kira suresi doldugu icin is sonlandirildi."
            row.lease_until = None
            row.worker_id = None
            row.finished_at = now
            failed += 1
    if stale:
        db.commit()
    return {"requeued": requeued, "failed": failed}


def claim_next_job(
    db: OrmSession,
    *,
    worker_id: str,
    lease_seconds: int = 300,
) -> OcrAnalysis | None:
    """Reclaim stale leases and atomically claim the oldest queued OCR analysis."""
    reclaim_expired_leases(db)
    now = utcnow()
    stmt = (
        select(OcrAnalysis)
        .where(
            OcrAnalysis.status == "queued",
            OcrAnalysis.cancel_requested.is_(False),
        )
        .order_by(OcrAnalysis.created_at.asc())
        .limit(1)
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    row = db.execute(stmt).scalars().first()
    if row is None:
        return None

    row.status = "running"
    row.attempts = int(row.attempts or 0) + 1
    row.worker_id = worker_id[:64]
    row.started_at = row.started_at or now
    row.lease_until = now + timedelta(seconds=max(10, int(lease_seconds)))
    db.commit()
    db.refresh(row)
    return row


def process_claimed_job(
    session_factory: sessionmaker[OrmSession],
    settings: Settings,
    analysis_id: str,
    *,
    worker_id: str,
    lease_seconds: int = 300,
    heartbeat_interval_s: float = 5.0,
) -> str:
    """Execute one claimed OCR analysis with lease heartbeats and DB cancel polling."""
    cancel_event = threading.Event()
    stop_heartbeat = threading.Event()

    with session_factory() as db:
        row = db.get(OcrAnalysis, analysis_id)
        if row is None:
            return "missing"
        if row.cancel_requested or row.status == "cancelled":
            row.status = "cancelled"
            row.lease_until = None
            row.finished_at = row.finished_at or utcnow()
            db.commit()
            return "cancelled"
        att = db.get(Attachment, row.attachment_id)
        if att is None:
            row.status = "failed"
            row.error_code = "file_not_found"
            row.error_message = "Yuklenen dosya eki bulunamadi."
            row.lease_until = None
            row.finished_at = utcnow()
            db.commit()
            return "failed"

        stored_path = (settings.uploads_dir / att.stored_path).resolve()
        stored_filename = att.filename
        workspace_hash = row.workspace_id_hash
        job_payload: dict[str, Any] = dict(row.job_payload or {})
        calculated = job_payload.get("calculated")
        language = job_payload.get("language") or settings.ocr_lang
        profile = (
            db.get(OcrMappingProfile, row.mapping_profile_id) if row.mapping_profile_id else None
        )
        aliases = ocr_service._profile_aliases(profile)

    def _heartbeat_loop() -> None:
        interval = max(0.2, float(heartbeat_interval_s))
        while not stop_heartbeat.wait(interval):
            try:
                with session_factory() as hb_db:
                    hb_row = hb_db.get(OcrAnalysis, analysis_id)
                    if hb_row is None:
                        cancel_event.set()
                        return
                    if hb_row.cancel_requested or hb_row.status == "cancelled":
                        cancel_event.set()
                        return
                    if hb_row.worker_id == worker_id[:64] and hb_row.status == "running":
                        hb_row.lease_until = utcnow() + timedelta(
                            seconds=max(10, int(lease_seconds))
                        )
                        hb_db.commit()
            except Exception:
                logger.debug("Heartbeat failed for analysis %s", analysis_id, exc_info=True)

    hb_thread = threading.Thread(
        target=_heartbeat_loop,
        name=f"ocr-hb-{analysis_id[:8]}",
        daemon=True,
    )
    hb_thread.start()

    started = time.monotonic()
    result: OcrAnalysisResult | None = None
    caught_ocr_err: ReportOcrError | None = None
    caught_unexpected = False
    try:
        result = analyze_report(
            stored_path,
            calculated,
            extra_aliases=aliases,
            language=language,
            cancel_event=cancel_event,
            timeout_seconds=float(settings.ocr_timeout_s),
        )
    except ReportOcrError as exc:
        caught_ocr_err = exc
    except Exception:
        logger.exception("Unexpected OCR worker failure for analysis %s", analysis_id)
        caught_unexpected = True
    finally:
        stop_heartbeat.set()
        hb_thread.join(timeout=2.0)

    with session_factory() as db:
        row = db.get(OcrAnalysis, analysis_id)
        if row is None:
            stored_path.unlink(missing_ok=True)
            return "missing"

        if (
            cancel_event.is_set()
            or row.cancel_requested
            or row.status == "cancelled"
            or (caught_ocr_err is not None and caught_ocr_err.code == ERROR_CANCELLED)
        ):
            row.status = "cancelled"
            row.lease_until = None
            row.error_code = None
            row.error_message = None
            row.finished_at = row.finished_at or utcnow()
            db.commit()
            stored_path.unlink(missing_ok=True)
            return "cancelled"

        if caught_ocr_err is not None:
            row.status = "failed"
            row.error_code = caught_ocr_err.code
            row.error_message = caught_ocr_err.message
            row.lease_until = None
            row.finished_at = utcnow()
            db.commit()
            stored_path.unlink(missing_ok=True)
            return "failed"

        if caught_unexpected or result is None:
            row.status = "failed"
            row.error_code = "internal_error"
            row.error_message = "OCR analizi tamamlanamadi."
            row.lease_until = None
            row.finished_at = utcnow()
            db.commit()
            stored_path.unlink(missing_ok=True)
            return "failed"

        OCR_QUEUE.record_duration(time.monotonic() - started)
        row.lease_until = None
        ocr_service._apply_success_result(
            db,
            row,
            result=result,
            stored_filename=stored_filename,
            workspace_hash=workspace_hash,
        )
        return "succeeded"


def run_once(
    settings: Settings,
    *,
    worker_id: str | None = None,
    lease_seconds: int = 300,
) -> bool:
    """Configure DB if needed, claim one queued job, and process it."""
    db_module.configure_database(settings.database_url)
    if settings.auto_migrate:
        db_module.init_db()
    factory = db_module.get_sessionmaker()
    wid = worker_id or default_worker_id()
    with factory() as db:
        claimed = claim_next_job(db, worker_id=wid, lease_seconds=lease_seconds)
        if claimed is None:
            return False
        claimed_id = claimed.id

    process_claimed_job(
        factory,
        settings,
        claimed_id,
        worker_id=wid,
        lease_seconds=lease_seconds,
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HYDRO persistent OCR worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Idle poll seconds.")
    parser.add_argument("--lease-seconds", type=int, default=300, help="Job lease TTL seconds.")
    parser.add_argument("--worker-id", type=str, default=None, help="Explicit worker identifier.")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    settings.ensure_directories()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    wid = args.worker_id or default_worker_id()

    if args.once:
        run_once(settings, worker_id=wid, lease_seconds=args.lease_seconds)
        return 0

    stop = threading.Event()

    def _on_signal(_signum: int, _frame: object) -> None:
        logger.info("OCR worker stopping cleanly...")
        stop.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    logger.info("OCR worker started worker_id=%s", wid)
    poll_s = max(0.2, float(args.poll_interval))
    while not stop.is_set():
        try:
            processed = run_once(settings, worker_id=wid, lease_seconds=args.lease_seconds)
        except Exception:
            logger.exception("OCR worker poll cycle error")
            processed = False
        if not processed:
            stop.wait(poll_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
