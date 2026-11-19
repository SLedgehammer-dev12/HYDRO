"""Selectable B coefficient sources.

B is the difference between the water volumetric expansion coefficient and the
steel volumetric expansion coefficient (10^-6 / degC). Three sources are
available:

- ``institutional`` (default): the corporate workbook-derived A/B control
  table. A anomalies are repaired at runtime; B is the raw table value.
- ``gail``: the independent GAIL public reference table.
- ``auto``: water ``beta`` from the configured water-property backend minus
  the steel contribution from :func:`calculate_b_coefficient`.

This module only resolves values and provenance; it never changes the stored
tables or the water-property formulas.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from ..data.ab_control_table import ABControlTableError, lookup_ab_control_point
from ..data.gail_reference_table import lookup_gail_reference_point
from .hydrotest_core import (
    DEFAULT_STEEL_MODEL,
    ValidationError,
    calculate_b_coefficient,
    calculate_water_thermal_expansion_beta,
    normalize_steel_model,
)
from .water_properties import ABSOLUTE_ZERO_C

INSTITUTIONAL_B_LABEL = "Kurum ici A/B kontrol tablosu"
GAIL_B_LABEL = "GAIL referans tablosu"
AUTO_B_LABEL = "Otomatik beta - celik genlesmesi"


class BSource(str, Enum):
    """Selectable B coefficient source."""

    INSTITUTIONAL = "institutional"
    GAIL = "gail"
    AUTO = "auto"


DEFAULT_B_SOURCE = BSource.INSTITUTIONAL


@dataclass(frozen=True)
class BSourceResult:
    b_micro_per_c: float
    source: BSource
    label: str
    note: str
    repaired_table: bool = False
    # Optional diagnostics; populated for the AUTO source only.
    water_beta_micro_per_c: float | None = None
    steel_alpha_micro_per_c: float | None = None
    steel_model: str = ""


@dataclass(frozen=True)
class BSourceComparison:
    """Three-source comparison at one ``(T, P)`` node."""

    temp_c: float
    pressure_bar: float
    institutional: BSourceResult
    gail: BSourceResult
    auto: BSourceResult

    @property
    def institutional_vs_gail(self) -> float:
        """Institutional B minus GAIL B (10^-6 / degC)."""
        return self.institutional.b_micro_per_c - self.gail.b_micro_per_c

    @property
    def auto_vs_institutional(self) -> float:
        """Automatic B minus institutional B (10^-6 / degC)."""
        return self.auto.b_micro_per_c - self.institutional.b_micro_per_c

    @property
    def auto_vs_gail(self) -> float:
        """Automatic B minus GAIL B (10^-6 / degC)."""
        return self.auto.b_micro_per_c - self.gail.b_micro_per_c


def normalize_b_source(source: BSource | str) -> BSource:
    """Return a :class:`BSource` for ``source`` or raise ``ValidationError``."""

    if isinstance(source, BSource):
        return source
    if not isinstance(source, str):
        raise ValidationError(
            f"Gecersiz B kaynagi: {source!r}. Gecerli kaynaklar: "
            f"{', '.join(item.value for item in BSource)}."
        )
    try:
        return BSource(source.strip().lower())
    except ValueError as exc:
        raise ValidationError(
            f"Gecersiz B kaynagi: {source!r}. Gecerli kaynaklar: "
            f"{', '.join(item.value for item in BSource)}."
        ) from exc


def _validate_state(temp_c: float, pressure_bar: float) -> None:
    if not isfinite(temp_c):
        raise ValidationError("Sicaklik sonlu bir sayi olmalidir.")
    if not isfinite(pressure_bar):
        raise ValidationError("Basinc sonlu bir sayi olmalidir.")
    if temp_c <= ABSOLUTE_ZERO_C:
        raise ValidationError("Sicaklik mutlak sifirin altinda olamaz.")
    if pressure_bar <= 0:
        raise ValidationError("Basinc sifirdan buyuk olmalidir.")


def _validate_steel_alpha(steel_alpha_micro_per_c: float) -> float:
    if not isfinite(steel_alpha_micro_per_c):
        raise ValidationError("Celik genlesme katsayisi sonlu bir sayi olmalidir.")
    if steel_alpha_micro_per_c < 0:
        raise ValidationError("Celik genlesme katsayisi negatif olamaz.")
    return steel_alpha_micro_per_c


def resolve_b_value(
    source: BSource | str,
    temp_c: float,
    pressure_bar: float,
    steel_alpha_micro_per_c: float = 12.0,
    steel_model: str = DEFAULT_STEEL_MODEL,
    backend: str | None = None,
) -> BSourceResult:
    """Resolve B (10^-6 / degC) from the requested source.

    ``source`` may be a :class:`BSource` or its string value. The application
    default is :data:`DEFAULT_B_SOURCE` (institutional table). Temperature and
    pressure must be finite, above absolute zero and above zero pressure.
    Range and backend errors are converted to :class:`ValidationError`.
    """

    resolved_source = normalize_b_source(source)
    _validate_state(temp_c, pressure_bar)
    steel_alpha = _validate_steel_alpha(steel_alpha_micro_per_c)
    model = normalize_steel_model(steel_model)

    if resolved_source is BSource.INSTITUTIONAL:
        try:
            point = lookup_ab_control_point(
                temp_c=temp_c,
                pressure_bar=pressure_bar,
                repair_anomalies=True,
            )
        except ABControlTableError as exc:
            raise ValidationError(str(exc)) from exc
        note = point.source_note
        if point.repair_note:
            note = f"{note}. {point.repair_note}"
        return BSourceResult(
            b_micro_per_c=point.b_micro_per_c,
            source=resolved_source,
            label=INSTITUTIONAL_B_LABEL,
            note=note,
            repaired_table=point.repaired,
        )

    if resolved_source is BSource.GAIL:
        try:
            point = lookup_gail_reference_point(
                temp_c=temp_c,
                pressure_bar=pressure_bar,
            )
        except ABControlTableError as exc:
            raise ValidationError(str(exc)) from exc
        return BSourceResult(
            b_micro_per_c=point.b_micro_per_c,
            source=resolved_source,
            label=GAIL_B_LABEL,
            note=point.source_note,
            repaired_table=point.repaired,
        )

    beta_micro_per_c = calculate_water_thermal_expansion_beta(
        temp_c=temp_c, pressure_bar=pressure_bar, backend=backend
    )
    b_value = calculate_b_coefficient(
        beta_micro_per_c,
        steel_alpha,
        steel_model=model,
        temp_c=temp_c,
    )
    if model == "linear":
        model_note = "B = beta - alpha (lineer model)"
    elif model == "volumetric":
        model_note = "B = beta - 3*alpha (hacimsel model)"
    else:
        model_note = "B = beta - 3*alpha(T) (sicakliga bagli hacimsel model)"
    backend_prefix = f"Otomatik hesap ({backend})" if backend else "Otomatik hesap"
    return BSourceResult(
        b_micro_per_c=b_value,
        source=resolved_source,
        label=AUTO_B_LABEL,
        note=(
            f"{backend_prefix}: beta = {beta_micro_per_c:.6f}, "
            f"celik alpha = {steel_alpha:.6f}; {model_note}."
        ),
        repaired_table=False,
        water_beta_micro_per_c=beta_micro_per_c,
        steel_alpha_micro_per_c=steel_alpha,
        steel_model=model,
    )


def compare_b_sources(
    temp_c: float,
    pressure_bar: float,
    steel_alpha_micro_per_c: float = 12.0,
    steel_model: str = DEFAULT_STEEL_MODEL,
    backend: str | None = None,
) -> BSourceComparison:
    """Return institutional, GAIL and automatic B values at one node.

    The institutional side uses the repaired A view (B itself is never
    repaired). ``steel_model`` must be one of :data:`STEEL_MODELS`; the
    default volumetric model matches the physical volume expansion.
    """

    model = normalize_steel_model(steel_model)

    return BSourceComparison(
        temp_c=temp_c,
        pressure_bar=pressure_bar,
        institutional=resolve_b_value(
            BSource.INSTITUTIONAL,
            temp_c=temp_c,
            pressure_bar=pressure_bar,
            steel_alpha_micro_per_c=steel_alpha_micro_per_c,
            steel_model=model,
        ),
        gail=resolve_b_value(
            BSource.GAIL,
            temp_c=temp_c,
            pressure_bar=pressure_bar,
            steel_alpha_micro_per_c=steel_alpha_micro_per_c,
            steel_model=model,
        ),
        auto=resolve_b_value(
            BSource.AUTO,
            temp_c=temp_c,
            pressure_bar=pressure_bar,
            steel_alpha_micro_per_c=steel_alpha_micro_per_c,
            steel_model=model,
            backend=backend,
        ),
    )


__all__ = [
    "AUTO_B_LABEL",
    "BSource",
    "BSourceComparison",
    "BSourceResult",
    "DEFAULT_B_SOURCE",
    "GAIL_B_LABEL",
    "INSTITUTIONAL_B_LABEL",
    "compare_b_sources",
    "normalize_b_source",
    "resolve_b_value",
]
