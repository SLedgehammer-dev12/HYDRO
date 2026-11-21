from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi
from typing import Final, TypeAlias

from .water_properties import (
    WaterPropertyError,
)
from .water_properties import (
    calculate_water_compressibility_a as calculate_water_compressibility_a_with_backend,
)
from .water_properties import (
    calculate_water_thermal_expansion_beta as calculate_water_thermal_expansion_beta_with_backend,
)
from .water_properties import (
    scale_expansion_coefficient_k_to_micro_per_c as scale_expansion_coefficient_k_to_micro_per_c,
)
from .water_properties import (
    scale_isothermal_compressibility_pa_to_micro_per_bar as scale_isothermal_compressibility_pa_to_micro_per_bar,
)

AIR_CONTENT_ACCEPTANCE_FACTOR: Final[float] = 1.06
PRESSURE_VARIATION_ACCEPTANCE_BAR: Final[float] = 0.3
SPEC_AIR_PRESSURE_RISE_BAR: Final[float] = 1.0
SPEC_AIR_PRESSURE_RISE_TOLERANCE: Final[float] = 1e-9
SEAMLESS_PIPE_K: Final[float] = 1.00
WELDED_PIPE_K: Final[float] = 1.02
FLOAT_TOLERANCE: Final[float] = 1e-9
NUMERIC_COMPARISON_RELATIVE_TOLERANCE: Final[float] = 1e-9

# Celik genlesme modeli secenekleri. B, suyun hacimsel genlesmesi ile celigin
# hacimsel genlesmesi arasindaki farktir; fiziksel olarak dogru yaklasim
# celigin lineer genlesme katsayisinin uc katini (hacimsel genlesme) almaktir.
STEEL_MODEL_LINEAR: Final[str] = "linear"
STEEL_MODEL_VOLUMETRIC: Final[str] = "volumetric"
STEEL_MODEL_VOLUMETRIC_TEMPERATURE: Final[str] = "volumetric_temperature"
DEFAULT_STEEL_MODEL: Final[str] = STEEL_MODEL_VOLUMETRIC
STEEL_MODELS: Final[tuple[str, ...]] = (
    STEEL_MODEL_LINEAR,
    STEEL_MODEL_VOLUMETRIC,
    STEEL_MODEL_VOLUMETRIC_TEMPERATURE,
)
# Arastirma raporundaki sicakliga bagli karbon celigi lineer genlesme modeli.
STEEL_ALPHA_TEMPERATURE_BASE_MICRO_PER_C: Final[float] = 10.8
STEEL_ALPHA_TEMPERATURE_SLOPE_MICRO_PER_C2: Final[float] = 0.012


class ValidationError(ValueError):
    """Raised when user data is incomplete or physically inconsistent."""


def _require_finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isfinite(value):
        raise ValidationError(f"{label} sonlu bir sayi olmalidir.")
    return value


@dataclass(frozen=True)
class PipeSection:
    outside_diameter_mm: float
    wall_thickness_mm: float
    length_m: float
    smys_mpa: float | None = None
    material_grade: str | None = None

    def __post_init__(self) -> None:
        _require_finite(self.outside_diameter_mm, "Dis cap")
        _require_finite(self.wall_thickness_mm, "Et kalinligi")
        _require_finite(self.length_m, "Hat uzunlugu")
        if self.outside_diameter_mm <= 0:
            raise ValidationError("Dis cap sifirdan buyuk olmalidir.")
        if self.wall_thickness_mm <= 0:
            raise ValidationError("Et kalinligi sifirdan buyuk olmalidir.")
        if self.length_m <= 0:
            raise ValidationError("Hat uzunlugu sifirdan buyuk olmalidir.")
        if self.wall_thickness_mm * 2 >= self.outside_diameter_mm:
            raise ValidationError(
                "Et kalinligi borunun ic capini sifira dusurecek kadar buyuk olamaz."
            )
        if self.smys_mpa is not None:
            _require_finite(self.smys_mpa, "Segment SMYS")
            if self.smys_mpa <= 0:
                raise ValidationError("Segment SMYS sifirdan buyuk olmalidir.")
        if self.material_grade is not None:
            if not isinstance(self.material_grade, str):
                raise ValidationError("Segment malzeme kalitesi metin olmalidir.")
            object.__setattr__(self, "material_grade", self.material_grade.strip() or None)

    @property
    def internal_radius_mm(self) -> float:
        return (self.outside_diameter_mm / 2) - self.wall_thickness_mm

    @property
    def internal_volume_m3(self) -> float:
        radius_m = self.internal_radius_mm / 1000
        return pi * (radius_m**2) * self.length_m

    @property
    def elasticity_term(self) -> float:
        return 0.884 * self.internal_radius_mm / self.wall_thickness_mm

    def pressure_at_100_smys_bar(self, fallback_smys_mpa: float | None = None) -> float:
        """Compute hoop-stress pressure at 100% SMYS in bar for this segment."""
        effective_smys = self.smys_mpa if self.smys_mpa is not None else fallback_smys_mpa
        if effective_smys is None:
            raise ValidationError("100% SMYS basinci icin SMYS degeri gereklidir.")
        _require_finite(effective_smys, "SMYS")
        if effective_smys <= 0:
            raise ValidationError("SMYS sifirdan buyuk olmalidir.")
        return 20.0 * effective_smys * self.wall_thickness_mm / self.outside_diameter_mm


@dataclass(frozen=True)
class PipeGeometry:
    sections: tuple[PipeSection, ...]

    def __post_init__(self) -> None:
        if not self.sections:
            raise ValidationError("En az bir boru segmenti tanimlanmalidir.")

    @property
    def total_length_m(self) -> float:
        return sum(section.length_m for section in self.sections)

    @property
    def internal_volume_m3(self) -> float:
        return sum(section.internal_volume_m3 for section in self.sections)

    @property
    def internal_radius_mm(self) -> float:
        total_volume = self.internal_volume_m3
        if total_volume <= FLOAT_TOLERANCE:
            raise ValidationError("Segmentlerden toplam hacim hesaplanamadi.")
        return (
            sum(
                section.internal_radius_mm * section.internal_volume_m3 for section in self.sections
            )
            / total_volume
        )

    @property
    def elasticity_term(self) -> float:
        total_volume = self.internal_volume_m3
        if total_volume <= FLOAT_TOLERANCE:
            raise ValidationError("Segmentlerden toplam hacim hesaplanamadi.")
        return (
            sum(section.elasticity_term * section.internal_volume_m3 for section in self.sections)
            / total_volume
        )


PipeModel: TypeAlias = PipeSection | PipeGeometry


def calculate_water_compressibility_a(
    temp_c: float, pressure_bar: float, backend: str | None = None
) -> float:
    try:
        return calculate_water_compressibility_a_with_backend(temp_c, pressure_bar, backend=backend)
    except WaterPropertyError as exc:
        raise ValidationError(str(exc)) from exc


def calculate_water_thermal_expansion_beta(
    temp_c: float, pressure_bar: float, backend: str | None = None
) -> float:
    try:
        return calculate_water_thermal_expansion_beta_with_backend(
            temp_c, pressure_bar, backend=backend
        )
    except WaterPropertyError as exc:
        raise ValidationError(str(exc)) from exc


def calculate_b_coefficient(
    water_beta_micro_per_c: float,
    steel_alpha_micro_per_c: float,
    steel_model: str = DEFAULT_STEEL_MODEL,
    temp_c: float | None = None,
) -> float:
    """Return B (10^-6 / degC) from water expansion minus steel expansion.

    ``steel_model`` selects how the steel contribution is derived:

    - ``"linear"``: historic behaviour, ``B = beta - alpha``.
    - ``"volumetric"`` (default): physically correct volume expansion,
      ``B = beta - 3 * alpha``.
    - ``"volumetric_temperature"``: ``B = beta - 3 * alpha(T)`` with
      ``alpha(T) = 10.8 + 0.012 * T`` (micro/K), the research-report model.
      ``temp_c`` is required for this model and the nominal
      ``steel_alpha_micro_per_c`` value is superseded by ``alpha(T)``.

    Negative water beta (below ~4 degC) and negative B are valid results.
    """

    _require_finite(water_beta_micro_per_c, "Su genlesme katsayisi")
    _require_finite(steel_alpha_micro_per_c, "Celik genlesme katsayisi")
    if steel_alpha_micro_per_c < 0:
        raise ValidationError("Celik genlesme katsayisi negatif olamaz.")

    model = normalize_steel_model(steel_model)
    if model == STEEL_MODEL_LINEAR:
        steel_contribution = steel_alpha_micro_per_c
    elif model == STEEL_MODEL_VOLUMETRIC:
        steel_contribution = 3.0 * steel_alpha_micro_per_c
    else:
        if temp_c is None:
            raise ValidationError(
                "volumetric_temperature modeli icin sicaklik (temp_c) gereklidir."
            )
        steel_contribution = 3.0 * steel_alpha_at_temperature_micro_per_c(temp_c)

    # 4 degC altinda suyun hacimsel genlesme katsayisi ve dolayisiyla B negatiftir.
    b_micro_per_c = water_beta_micro_per_c - steel_contribution
    if not isfinite(b_micro_per_c):
        raise ValidationError("Hesaplanan B katsayisi sonlu bir sayi olmalidir.")
    return b_micro_per_c


def normalize_steel_model(steel_model: str) -> str:
    """Return a canonical steel-model key or raise :class:`ValidationError`."""

    if not isinstance(steel_model, str):
        raise ValidationError("Celik genlesme modeli metin olmalidir.")
    normalized = steel_model.strip().lower()
    if normalized not in STEEL_MODELS:
        raise ValidationError(
            f"Bilinmeyen celik genlesme modeli: {steel_model!r}. "
            f"Gecerli modeller: {', '.join(STEEL_MODELS)}."
        )
    return normalized


def steel_alpha_at_temperature_micro_per_c(
    temp_c: float,
    *,
    base_micro_per_c: float = STEEL_ALPHA_TEMPERATURE_BASE_MICRO_PER_C,
    slope_micro_per_c2: float = STEEL_ALPHA_TEMPERATURE_SLOPE_MICRO_PER_C2,
) -> float:
    """Temperature-dependent linear steel expansion coefficient (micro/K)."""

    _require_finite(temp_c, "Sicaklik")
    _require_finite(base_micro_per_c, "Celik alpha taban degeri")
    _require_finite(slope_micro_per_c2, "Celik alpha egimi")
    alpha = base_micro_per_c + slope_micro_per_c2 * temp_c
    if not isfinite(alpha):
        raise ValidationError("Hesaplanan celik genlesme katsayisi sonlu bir sayi olmalidir.")
    if alpha < 0:
        raise ValidationError("Celik genlesme katsayisi negatif olamaz.")
    return alpha


@dataclass(frozen=True)
class AirContentInputs:
    pipe: PipeModel
    a_micro_per_bar: float
    pressure_rise_bar: float
    k_factor: float
    actual_added_water_m3: float

    def __post_init__(self) -> None:
        _require_finite(self.a_micro_per_bar, "A degeri")
        _require_finite(self.pressure_rise_bar, "Basinc artisi P")
        _require_finite(self.k_factor, "K faktoru")
        _require_finite(self.actual_added_water_m3, "Fiili ilave su hacmi")
        if self.a_micro_per_bar <= 0:
            raise ValidationError("A degeri sifirdan buyuk olmalidir.")
        if self.pressure_rise_bar <= 0:
            raise ValidationError("Basinc artisi P sifirdan buyuk olmalidir.")
        if (
            abs(self.pressure_rise_bar - SPEC_AIR_PRESSURE_RISE_BAR)
            > SPEC_AIR_PRESSURE_RISE_TOLERANCE
        ):
            raise ValidationError(
                "Hava icerik testi bu sartnameye gore tam 1.0 bar basinc artisi ile yapilmalidir."
            )
        if self.k_factor <= 0:
            raise ValidationError("K faktoru sifirdan buyuk olmalidir.")
        if self.actual_added_water_m3 < 0:
            raise ValidationError("Fiili ilave su hacmi negatif olamaz.")


@dataclass(frozen=True)
class AirContentResult:
    theoretical_added_water_m3: float
    acceptance_limit_m3: float
    actual_added_water_m3: float
    ratio: float
    passed: bool


def evaluate_air_content_test(inputs: AirContentInputs) -> AirContentResult:
    deformation_term = inputs.pipe.elasticity_term + inputs.a_micro_per_bar
    if deformation_term <= 0:
        raise ValidationError("Hava icerik hesabi icin payda/carpan pozitif olmalidir.")

    theoretical_added_water_m3 = (
        deformation_term
        * 1e-6
        * inputs.pipe.internal_volume_m3
        * inputs.pressure_rise_bar
        * inputs.k_factor
    )
    if not isfinite(theoretical_added_water_m3):
        raise ValidationError("Teorik su ilavesi sonlu bir sayi olarak hesaplanamadi.")
    if theoretical_added_water_m3 <= FLOAT_TOLERANCE:
        raise ValidationError("Teorik su ilavesi hesaplanamadi.")

    acceptance_limit_m3 = theoretical_added_water_m3 * AIR_CONTENT_ACCEPTANCE_FACTOR
    ratio = inputs.actual_added_water_m3 / theoretical_added_water_m3
    # Sartname "%6 veya daha fazla" ilaveyi reddeder; tam sinir PASS olamaz.
    strict_acceptance_limit_m3 = acceptance_limit_m3 * (1.0 - NUMERIC_COMPARISON_RELATIVE_TOLERANCE)
    passed = inputs.actual_added_water_m3 < strict_acceptance_limit_m3

    return AirContentResult(
        theoretical_added_water_m3=theoretical_added_water_m3,
        acceptance_limit_m3=acceptance_limit_m3,
        actual_added_water_m3=inputs.actual_added_water_m3,
        ratio=ratio,
        passed=passed,
    )


@dataclass(frozen=True)
class PressureVariationInputs:
    pipe: PipeModel
    a_micro_per_bar: float
    b_micro_per_c: float
    delta_t_c: float
    actual_pressure_change_bar: float

    def __post_init__(self) -> None:
        _require_finite(self.a_micro_per_bar, "A degeri")
        _require_finite(self.b_micro_per_c, "B degeri")
        _require_finite(self.delta_t_c, "Sicaklik farki dT")
        _require_finite(self.actual_pressure_change_bar, "Basinc farki Pa")
        if self.a_micro_per_bar <= 0:
            raise ValidationError("A degeri sifirdan buyuk olmalidir.")


@dataclass(frozen=True)
class PressureVariationResult:
    theoretical_pressure_change_bar: float
    allowable_upper_pressure_change_bar: float
    actual_pressure_change_bar: float
    margin_bar: float
    passed: bool


def evaluate_pressure_variation_test(inputs: PressureVariationInputs) -> PressureVariationResult:
    deformation_term = inputs.pipe.elasticity_term + inputs.a_micro_per_bar
    if deformation_term <= 0:
        raise ValidationError("Basinc degisim hesabi icin payda pozitif olmalidir.")

    theoretical_pressure_change_bar = (inputs.b_micro_per_c * inputs.delta_t_c) / deformation_term
    if not isfinite(theoretical_pressure_change_bar):
        raise ValidationError("Teorik basinc degisimi sonlu bir sayi olarak hesaplanamadi.")
    allowable_upper_pressure_change_bar = (
        theoretical_pressure_change_bar + PRESSURE_VARIATION_ACCEPTANCE_BAR
    )
    margin_bar = inputs.actual_pressure_change_bar - theoretical_pressure_change_bar
    # Karar, sonuc icinde dondurulen ayni margin degeri uzerinden verilir.
    passed = margin_bar <= PRESSURE_VARIATION_ACCEPTANCE_BAR + FLOAT_TOLERANCE

    return PressureVariationResult(
        theoretical_pressure_change_bar=theoretical_pressure_change_bar,
        allowable_upper_pressure_change_bar=allowable_upper_pressure_change_bar,
        actual_pressure_change_bar=inputs.actual_pressure_change_bar,
        margin_bar=margin_bar,
        passed=passed,
    )
