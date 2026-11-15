"""Time and JSON helpers shared by the API layer."""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from .errors import AppError

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = ensure_utc(value)
    assert normalized is not None
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    """Recursively convert dataclasses/enums/datetimes into JSON values.

    ``inf``/``nan`` are not valid JSON; the contract asks for ``null`` in that
    case (thermal balance ``temp_diff_c``).
    """

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            return iso_z(value)
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in value]
    return str(value)


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    if not isinstance(value, str):
        raise AppError(
            "validation_error",
            "Gecersiz zaman degeri.",
            status_code=422,
            details={"value": str(value)},
        )
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AppError(
            "validation_error",
            f"Gecersiz ISO-8601 zaman degeri: {value}",
            status_code=422,
        ) from exc
    return ensure_utc(parsed)


def as_float(value: Any) -> float | None:
    """Best-effort numeric conversion; ``None``/empty stays ``None``."""

    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace(" ", "").replace("\u00a0", "")
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    else:
        normalized = normalized.replace(",", ".")
    try:
        number = float(normalized)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def fmt_number(value: float | None, digits: int = 6) -> str:
    if value is None:
        return ""
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``patch`` into a copy of ``base``.

    ``None`` clears the key (contract: "null göndermek alanı temizler").
    Lists and scalars replace the existing value.
    """

    merged: dict[str, Any] = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


__all__ = [
    "UTC",
    "as_float",
    "deep_merge",
    "ensure_utc",
    "fmt_number",
    "iso_z",
    "json_safe",
    "parse_datetime",
    "utcnow",
]
