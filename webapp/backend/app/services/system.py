"""System endpoints: health, meta and specification rules."""

from __future__ import annotations

import os
import time
from typing import Any

from hidrostatik_test import APP_NAME, APP_TITLE, APP_VERSION
from hidrostatik_test.app_metadata import (
    SPEC_DOCUMENT_CODE,
    SPEC_DOCUMENT_TITLE,
)
from hidrostatik_test.domain import (
    AMBIENT_TEMP_LIMIT_C,
    DEFAULT_B_SOURCE,
    DEFAULT_STEEL_MODEL,
    MAX_TEST_SECTION_LENGTH_M,
    MAX_TEST_SECTION_VOLUME_M3,
    PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT,
    STEEL_MODELS,
    get_available_water_property_backends,
    get_location_class_options,
    get_location_class_rule,
    get_pump_location_options,
)
from hidrostatik_test.domain.hydrotest_core import (
    AIR_CONTENT_ACCEPTANCE_FACTOR,
    PRESSURE_VARIATION_ACCEPTANCE_BAR,
    SPEC_AIR_PRESSURE_RISE_BAR,
)
from hidrostatik_test.domain.operations import PIG_SPEED_LIMITS
from hidrostatik_test.domain.time_series import (
    THERMAL_BALANCE_MIN_HOURS,
    THERMAL_BALANCE_THRESHOLD_C,
)
from hidrostatik_test.services.report_ocr import (
    MAX_FILE_SIZE_BYTES,
    MAX_OCR_PAGES,
    MAX_PDF_PAGES,
    SUPPORTED_EXTENSIONS,
    ocr_available,
    ocr_status,
)

from .. import db
from ..core.config import Settings
from ..core.security import WORKSPACE_HEADER
from ..desktop_labels import (
    AIR_ACCEPTANCE_RULE,
    FIELD_CHECKS,
    PRESSURE_ACCEPTANCE_RULE,
    SIGN_CONVENTION,
    SPEC_NOTES,
)

UPTIME_START = time.monotonic()
APP_VERSION_SHORT = APP_VERSION


def _backend_payloads() -> list[dict[str, Any]]:
    rows = []
    for info in get_available_water_property_backends(include_dev_backends=False):
        rows.append(
            {
                "key": info.key,
                "label": info.label,
                "distribution_ready": info.distribution_ready,
                "note": info.note,
            }
        )
    return rows


def _ocr_queue(db_session: Any) -> dict[str, int]:
    from sqlalchemy import func, select

    from ..models import OcrAnalysis

    counts = {"queued": 0, "running": 0}
    try:
        rows = db_session.execute(
            select(OcrAnalysis.status, func.count(OcrAnalysis.id)).group_by(OcrAnalysis.status)
        ).all()
        for status, count in rows:
            if status in counts:
                counts[status] = int(count)
    except Exception:
        pass
    return counts


def health_payload(settings: Settings) -> dict[str, Any]:
    db_health = db.database_health()
    data_dir_ok = settings.data_dir.exists() and settings.data_dir.is_dir()
    writable = data_dir_ok and os.access(settings.data_dir, os.W_OK)
    queue = {"queued": 0, "running": 0}
    if db_health.get("ok"):
        try:
            with db.session_scope() as session:
                queue = _ocr_queue(session)
        except Exception:
            queue = {"queued": 0, "running": 0}

    ocr_ok = ocr_available()
    if not db_health.get("ok"):
        status = "fail"
    elif not writable or not ocr_ok:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "version": APP_VERSION,
        "engine": "hidrostatik_test",
        "db": db_health,
        "data_dir": {"ok": data_dir_ok, "writable": writable},
        "ocr": {
            "available": ocr_ok,
            "status": ocr_status(),
            "queue": queue,
        },
        "uptime_s": int(time.monotonic() - UPTIME_START),
        "features": {
            "auth": settings.auth_mode,
            "ocr_enabled": settings.ocr_enabled,
            "workspace_header": WORKSPACE_HEADER,
        },
    }


def meta_payload(settings: Settings) -> dict[str, Any]:
    steel_models = list(STEEL_MODELS)
    location_classes = []
    for label in get_location_class_options():
        try:
            rule = get_location_class_rule(label)
        except Exception:  # pragma: no cover - options come from the same source
            continue
        location_classes.append(
            {
                "class_number": rule.class_number,
                "label": rule.label,
                "minimum_test_factor": rule.minimum_test_factor,
                "spec_reference": rule.spec_reference,
            }
        )

    pig_modes = [
        {
            "label": limit.label,
            "option_label": limit.option_label,
            "spec_reference": limit.spec_reference,
            "max_speed_m_per_s": limit.max_speed_m_per_s,
        }
        for limit in PIG_SPEED_LIMITS
    ]

    return {
        "app": {"name": APP_NAME, "title": APP_TITLE, "version": APP_VERSION},
        "spec": {"code": SPEC_DOCUMENT_CODE, "title": SPEC_DOCUMENT_TITLE},
        "engine": {
            "domain_schema": 1,
            "decision_statuses": [
                "BEKLIYOR",
                "KATSAYI GUNCELLENMELI",
                "DOGRULANAMADI",
                "BASARILI",
                "BASARISIZ",
            ],
        },
        "water_backends": _backend_payloads(),
        "b_sources": [
            {
                "key": "institutional",
                "label": "Kurum ici A/B kontrol tablosu",
                "default": DEFAULT_B_SOURCE.value == "institutional",
            },
            {
                "key": "gail",
                "label": "GAIL referans tablosu",
                "default": DEFAULT_B_SOURCE.value == "gail",
            },
            {
                "key": "auto",
                "label": "Otomatik beta - celik genlesmesi",
                "default": DEFAULT_B_SOURCE.value == "auto",
            },
        ],
        "steel_models": steel_models,
        "default_steel_model": DEFAULT_STEEL_MODEL,
        "location_classes": location_classes,
        "pump_locations": list(get_pump_location_options()),
        "pig_modes": pig_modes,
        "limits": {
            "max_file_size_bytes": MAX_FILE_SIZE_BYTES,
            "max_pdf_pages": MAX_PDF_PAGES,
            "max_ocr_pages": MAX_OCR_PAGES,
            "max_test_section_length_m": MAX_TEST_SECTION_LENGTH_M,
            "max_test_section_volume_m3": MAX_TEST_SECTION_VOLUME_M3,
            "air_acceptance_factor": AIR_CONTENT_ACCEPTANCE_FACTOR,
            "pressure_variation_acceptance_bar": PRESSURE_VARIATION_ACCEPTANCE_BAR,
            "pressurization_volume_limit_percent": (PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT),
            "thermal_balance_min_hours": THERMAL_BALANCE_MIN_HOURS,
            "thermal_balance_threshold_c": THERMAL_BALANCE_THRESHOLD_C,
            "ambient_temp_limit_c": AMBIENT_TEMP_LIMIT_C,
            "air_pressure_rise_bar": SPEC_AIR_PRESSURE_RISE_BAR,
        },
        "features": {
            "ocr": ocr_available(),
            "scene": True,
            "dev_backends": False,
            "auth": settings.auth_mode,
        },
        "units": {
            "pressure": "bar",
            "temperature": "°C",
            "length": "m",
            "diameter": "mm",
            "volume": "m³",
            "a": "10^-6/bar",
            "b": "10^-6/°C",
        },
        "supported_upload_extensions": sorted(SUPPORTED_EXTENSIONS),
    }


def spec_payload() -> dict[str, Any]:
    return {
        "code": SPEC_DOCUMENT_CODE,
        "title": SPEC_DOCUMENT_TITLE,
        "acceptance_rules": {
            "air": {
                "text": AIR_ACCEPTANCE_RULE,
                "factor": AIR_CONTENT_ACCEPTANCE_FACTOR,
            },
            "pressure": {
                "text": PRESSURE_ACCEPTANCE_RULE,
                "tolerance_bar": PRESSURE_VARIATION_ACCEPTANCE_BAR,
            },
        },
        "sign_convention": dict(SIGN_CONVENTION),
        "checks": [
            {"key": key, "label": label, "reference": reference}
            for key, label, reference in FIELD_CHECKS
        ],
        "notes": list(SPEC_NOTES),
    }


__all__ = [
    "APP_VERSION_SHORT",
    "health_payload",
    "meta_payload",
    "spec_payload",
]
