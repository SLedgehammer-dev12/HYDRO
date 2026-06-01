from __future__ import annotations

from typing import Final

FIELD_MESSAGE_PREFIXES: Final[dict[str, str]] = {
    "info": "",
    "success": "Hazir: ",
    "warning": "Uyari: ",
    "error": "Hata: ",
}

VISUAL_LEVEL_MAP: Final[dict[str, str]] = {
    "info": "neutral",
    "success": "success",
    "warning": "warning",
    "error": "error",
}

PALETTE: Final[dict[str, tuple[str, str]]] = {
    "neutral": ("#FFFFFF", "#6B7280"),
    "success": ("#EEF8EE", "#1E6F43"),
    "warning": ("#FFF6E5", "#8A5B00"),
    "error": ("#FDEAEA", "#A4262C"),
    "readonly": ("#F5F7FA", "#6B7280"),
}


def format_field_message(message: str, level: str) -> str:
    prefix = FIELD_MESSAGE_PREFIXES.get(level, "")
    return f"{prefix}{message}" if message else ""


def get_visual_level(level: str) -> str:
    return VISUAL_LEVEL_MAP.get(level, "neutral")


def get_palette_colors(level: str) -> tuple[str, str]:
    return PALETTE.get(level, PALETTE["neutral"])


def format_detail_value(value: str, unit: str = "") -> str:
    if value == "-" or not unit:
        return value
    return f"{value} {unit}"


__all__ = [
    "FIELD_MESSAGE_PREFIXES",
    "PALETTE",
    "VISUAL_LEVEL_MAP",
    "format_detail_value",
    "format_field_message",
    "get_palette_colors",
    "get_visual_level",
]
