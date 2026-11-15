from __future__ import annotations

import math
import re

# Alan bazli makul araliklar. Wizard ve alan dogrulamasi ayni kaynagi kullanir.
A_MICRO_PER_BAR_MIN = 1.0
A_MICRO_PER_BAR_MAX = 200.0
B_MICRO_PER_C_MIN = -200.0
B_MICRO_PER_C_MAX = 500.0
K_FACTOR_MIN = 1.0
K_FACTOR_MAX = 1.1
DELTA_T_C_MIN = -20.0
DELTA_T_C_MAX = 20.0
ACTUAL_PRESSURE_CHANGE_BAR_MIN = -50.0
ACTUAL_PRESSURE_CHANGE_BAR_MAX = 50.0

NUMBER_FORMAT_MESSAGE = "Gecerli bir sayi girin."

# Yalnizca isaret + rakam (+ tek ondalik nokta) + opsiyonel us kabul edilir.
_PLAIN_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


class NumericInputError(ValueError):
    """Kullaniciya gosterilebilir sayisal giris hatasi."""


def _is_grouped_integer(text: str, separator: str) -> bool:
    """``1.000.000`` gibi gruplu tam sayi bicimini dogrular."""
    groups = text.split(separator)
    if len(groups) < 2:
        return False
    if not groups[0].isdigit() or not (1 <= len(groups[0]) <= 3):
        return False
    return all(group.isdigit() and len(group) == 3 for group in groups[1:])


def _normalize_numeric_text(text: str) -> str:
    """Metni ``float()`` icin tek ondalik noktali hale getirir.

    Sozlesme (Turkce arayuz varsayimi):

    * Ondalik ayirici olarak virgul her zaman ondaliktir: ``"3,14" -> 3.14``.
    * Nokta ondalik ayirici olarak da kullanilabilir: ``"3.14" -> 3.14``.
    * Binlik ayirici yalnizca acik bicimde grupluysa kabul edilir:
      ``"1.000.000" -> 1000000.0``.
    * Tek nokta her zaman ondalik ayiricidir; bu yuzden ``"1.000" -> 1.0``.
      Binlik olarak girilmek istenen deger ``"1.000.000"`` gibi yazilmalidir.
    * Iki ayirici birlikte varsa en sagdaki ondalik, digeri binliktir:
      ``"1.234,56" -> 1234.56`` ve ``"1,234.56" -> 1234.56``.
    * Bosluk, alt cizgi, ``nan``/``inf`` metinleri reddedilir.
    """
    candidate = text.strip()
    if not candidate:
        raise NumericInputError(NUMBER_FORMAT_MESSAGE)
    if any(character.isspace() for character in candidate):
        raise NumericInputError(NUMBER_FORMAT_MESSAGE)

    sign = ""
    if candidate[0] in "+-":
        sign, candidate = candidate[0], candidate[1:]
    if not candidate:
        raise NumericInputError(NUMBER_FORMAT_MESSAGE)

    has_dot = "." in candidate
    has_comma = "," in candidate

    if has_dot and has_comma:
        if candidate.rfind(",") > candidate.rfind("."):
            decimal_separator, grouping_separator = ",", "."
        else:
            decimal_separator, grouping_separator = ".", ","
        integer_part, _, fraction_part = candidate.rpartition(decimal_separator)
        if not _is_grouped_integer(integer_part, grouping_separator):
            raise NumericInputError(NUMBER_FORMAT_MESSAGE)
        if not fraction_part.isdigit():
            raise NumericInputError(NUMBER_FORMAT_MESSAGE)
        candidate = f"{integer_part.replace(grouping_separator, '')}.{fraction_part}"
    elif has_comma:
        if candidate.count(",") != 1:
            raise NumericInputError(NUMBER_FORMAT_MESSAGE)
        integer_part, fraction_part = candidate.split(",")
        if not integer_part.isdigit() or not fraction_part.isdigit():
            raise NumericInputError(NUMBER_FORMAT_MESSAGE)
        candidate = f"{integer_part}.{fraction_part}"
    elif has_dot and candidate.count(".") > 1:
        if not _is_grouped_integer(candidate, "."):
            raise NumericInputError(NUMBER_FORMAT_MESSAGE)
        candidate = candidate.replace(".", "")

    if not _PLAIN_NUMBER_RE.fullmatch(candidate):
        raise NumericInputError(NUMBER_FORMAT_MESSAGE)
    return sign + candidate


def parse_finite_float(
    value: str | None,
    label: str,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    """Metni sonlu bir ``float`` degerine cevirir; hatalari Turkce firlatir.

    ``nan``, ``inf`` ve ``1e999`` gibi tasan degerler reddedilir. ``None`` ve
    bos metin "bos birakilamaz" hatasi verir. Aralik kontrolu kapali araliktir.
    """
    text = "" if value is None else str(value).strip()
    if not text:
        raise NumericInputError(f"{label} bos birakilamaz.")
    if text.lower().lstrip("+-") in {"nan", "inf", "infinity"}:
        raise NumericInputError(f"{label} sonlu bir sayi olmalidir.")
    try:
        normalized = _normalize_numeric_text(text)
        parsed = float(normalized)
    except NumericInputError as exc:
        if str(exc) == NUMBER_FORMAT_MESSAGE:
            raise NumericInputError(f"{label} icin {NUMBER_FORMAT_MESSAGE.lower()}") from None
        raise
    except (TypeError, ValueError):
        raise NumericInputError(f"{label} icin {NUMBER_FORMAT_MESSAGE.lower()}") from None

    if not math.isfinite(parsed):
        raise NumericInputError(f"{label} sonlu bir sayi olmalidir.")
    if min_value is not None and max_value is not None:
        if not (min_value <= parsed <= max_value):
            raise NumericInputError(f"{label} {min_value:g} - {max_value:g} araliginda olmalidir.")
    elif min_value is not None and parsed < min_value:
        raise NumericInputError(f"{label} en az {min_value:g} olmalidir.")
    elif max_value is not None and parsed > max_value:
        raise NumericInputError(f"{label} en fazla {max_value:g} olmalidir.")
    return parsed


def safe_float(value: str) -> float | None:
    try:
        return parse_finite_float(value, "Deger")
    except NumericInputError:
        return None


def _finite_check(label: str, value: float | None) -> str | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return f"{label} sonlu bir sayi olmalidir."
    return None


def validate_geometry_inputs(
    outside_diameter_mm: float | None,
    wall_thickness_mm: float | None,
    length_m: float | None,
) -> tuple[str | None, str]:
    if outside_diameter_mm is None or wall_thickness_mm is None or length_m is None:
        return None, "incomplete"

    for label, value in (
        ("Dis cap", outside_diameter_mm),
        ("Et kalinligi", wall_thickness_mm),
        ("Hat uzunlugu", length_m),
    ):
        message = _finite_check(label, value)
        if message is not None:
            return message, "error"

    if outside_diameter_mm <= 0:
        return "Dis cap sifirdan buyuk olmalidir.", "error"

    if wall_thickness_mm <= 0:
        return "Et kalinligi sifirdan buyuk olmalidir.", "error"

    if length_m <= 0:
        return "Hat uzunlugu sifirdan buyuk olmalidir.", "error"

    if wall_thickness_mm * 2 >= outside_diameter_mm:
        return "Et kalinligi borunun ic capini sifira dusurecek kadar buyuk olamaz.", "error"

    return None, "valid"


def validate_geometry_text_inputs(
    outside_diameter_mm: str | None,
    wall_thickness_mm: str | None,
    length_m: str | None,
) -> tuple[str | None, str]:
    """Wizard icin metin tabanli geometri dogrulamasi.

    Alanlardan biri bile bossa ``incomplete`` doner; boylece cagiran taraf
    "henuz doldurulmadi" ile "hatali deger" durumunu ayirt edebilir.
    """
    raw_values = (
        ("Dis cap", outside_diameter_mm),
        ("Et kalinligi", wall_thickness_mm),
        ("Hat uzunlugu", length_m),
    )
    for _label, raw in raw_values:
        if raw is None or not str(raw).strip():
            return None, "incomplete"

    parsed: list[float] = []
    for label, raw in raw_values:
        try:
            parsed.append(parse_finite_float(raw, label, min_value=0.0))
        except NumericInputError as exc:
            return str(exc), "error"

    return validate_geometry_inputs(parsed[0], parsed[1], parsed[2])


def validate_elevation_inputs(
    highest_elevation_m: float | None,
    lowest_elevation_m: float | None,
    start_elevation_m: float | None,
    end_elevation_m: float | None,
) -> tuple[str | None, str]:
    if (
        highest_elevation_m is None
        or lowest_elevation_m is None
        or start_elevation_m is None
        or end_elevation_m is None
    ):
        return None, "incomplete"

    for label, value in (
        ("En yuksek kot", highest_elevation_m),
        ("En dusuk kot", lowest_elevation_m),
        ("Baslangic koti", start_elevation_m),
        ("Bitis koti", end_elevation_m),
    ):
        message = _finite_check(label, value)
        if message is not None:
            return message, "error"

    if highest_elevation_m < lowest_elevation_m:
        return "En yuksek nokta kotu, en dusuk noktadan kucuk olamaz.", "error"

    assert start_elevation_m is not None
    assert end_elevation_m is not None
    for label, elevation in [("Baslangic", start_elevation_m), ("Bitis", end_elevation_m)]:
        if elevation < lowest_elevation_m or elevation > highest_elevation_m:
            return f"{label} noktasi kotu, min/max kot araligi icinde olmalidir.", "error"

    return None, "valid"


__all__ = [
    "A_MICRO_PER_BAR_MAX",
    "A_MICRO_PER_BAR_MIN",
    "ACTUAL_PRESSURE_CHANGE_BAR_MAX",
    "ACTUAL_PRESSURE_CHANGE_BAR_MIN",
    "B_MICRO_PER_C_MAX",
    "B_MICRO_PER_C_MIN",
    "DELTA_T_C_MAX",
    "DELTA_T_C_MIN",
    "K_FACTOR_MAX",
    "K_FACTOR_MIN",
    "NumericInputError",
    "parse_finite_float",
    "safe_float",
    "validate_elevation_inputs",
    "validate_geometry_inputs",
    "validate_geometry_text_inputs",
]
