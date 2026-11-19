"""Sartname 16 (basincin dusurulmesi) ve 17 (bosaltma) is akisi kontrolleri.

Kaynak: ``4-NGTL 0-GN-P-002-5007 R4``.

Bu bolumlerde sayisal kabul kriteri yalnizca 16'daki "2 inc veya daha kucuk capli
vana" kuralidir; geri kalani zorunlu onlem/onay/raporlama kontrol listesidir.
Girdiler uclu durumludur: ``True`` (saglandi), ``False`` (ihlal), ``None``
(henuz bilinmiyor/eksik). Sonuc: ``violations`` (ihlal), ``missing`` (eksik bilgi),
``passed`` (ihlal yok ve eksik yok).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Final

from .hydrotest_core import ValidationError

MAX_DEPRESSURIZATION_VALVE_INCH: Final[float] = 2.0

DESTINATION_OTHER_SECTION: Final[str] = "other_section"
DESTINATION_WATERCOURSE: Final[str] = "watercourse"
DESTINATION_PUBLIC_LAND: Final[str] = "public_land"
DESTINATION_PRIVATE_LAND: Final[str] = "private_land"
DISCHARGE_DESTINATIONS: Final[frozenset[str]] = frozenset(
    {
        DESTINATION_OTHER_SECTION,
        DESTINATION_WATERCOURSE,
        DESTINATION_PUBLIC_LAND,
        DESTINATION_PRIVATE_LAND,
    }
)


@dataclass(frozen=True)
class DepressurizationInputs:
    test_passed: bool | None
    release_valve_diameter_in: float | None
    pipe_equipment_checked: bool | None = None
    environmental_impact_checked: bool | None = None

    def __post_init__(self) -> None:
        diameter = self.release_valve_diameter_in
        if diameter is not None:
            if not isfinite(diameter):
                raise ValidationError("Vana capi sonlu bir sayi olmalidir.")
            if diameter <= 0:
                raise ValidationError("Vana capi sifirdan buyuk olmalidir.")


@dataclass(frozen=True)
class OperationCheckResult:
    violations: tuple[str, ...]
    missing: tuple[str, ...]
    passed: bool


def evaluate_depressurization(inputs: DepressurizationInputs) -> OperationCheckResult:
    """Bolum 16: basinc dusurme on kosullari ve vana cap siniri."""

    violations: list[str] = []
    missing: list[str] = []

    if inputs.test_passed is False:
        violations.append("Hidrostatik test basarili tamamlanmadan basinc dusurulemez (16).")
    elif inputs.test_passed is None:
        missing.append("Test sonucu (basarili/basarisiz) belirtilmeli.")

    diameter = inputs.release_valve_diameter_in
    if diameter is None:
        missing.append("Basinc dusurme vanasi capi girilmeli.")
    elif diameter > MAX_DEPRESSURIZATION_VALVE_INCH:
        violations.append(
            f'Basinc dusurme vanasi {MAX_DEPRESSURIZATION_VALVE_INCH:g}" veya daha kucuk '
            f'capli olmali (girilen: {diameter:g}").'
        )

    if inputs.pipe_equipment_checked is False:
        violations.append("Boru ve ekipman icin dikkat/kontrol onlemleri alinmamis (16).")
    elif inputs.pipe_equipment_checked is None:
        missing.append("Boru/ekipman kontrolu onaylanmali.")

    if inputs.environmental_impact_checked is False:
        violations.append("Cevresel etki icin onlemler alinmamis (16).")
    elif inputs.environmental_impact_checked is None:
        missing.append("Cevresel etki kontrolu onaylanmali.")

    return OperationCheckResult(
        violations=tuple(violations),
        missing=tuple(missing),
        passed=not violations and not missing,
    )


@dataclass(frozen=True)
class DischargeInputs:
    destination: str | None
    used_discharge_pig: bool | None = None
    hydraulic_load_measures_taken: bool | None = None
    approvals_obtained: bool | None = None
    treatment_requested: bool = False
    treatment_done: bool | None = None
    sample_analysis_requested: bool = False
    sample_analysis_done: bool | None = None
    erosion_prevented: bool | None = None
    report_date: str = ""
    report_time: str = ""
    pig_name: str = ""
    discharge_location: str = ""
    duration_min: float | None = None

    def __post_init__(self) -> None:
        if self.destination is not None and self.destination not in DISCHARGE_DESTINATIONS:
            raise ValidationError("Bosaltma yeri turu gecersiz.")
        if self.duration_min is not None:
            if not isfinite(self.duration_min):
                raise ValidationError("Islem suresi sonlu bir sayi olmalidir.")
            if self.duration_min <= 0:
                raise ValidationError("Islem suresi sifirdan buyuk olmalidir.")


def evaluate_discharge(inputs: DischargeInputs) -> OperationCheckResult:
    """Bolum 17: bosaltma pigi, onlemler, onaylar, cevre ve raporlama kontrolleri."""

    violations: list[str] = []
    missing: list[str] = []

    if inputs.used_discharge_pig is False:
        violations.append("Bosaltma mutlaka bosaltma pigi ile yapilmali (17).")
    elif inputs.used_discharge_pig is None:
        missing.append("Bosaltma pigi kullanimi belirtilmeli.")

    if inputs.hydraulic_load_measures_taken is False:
        violations.append(
            "Hidrolik yuklerin boruyu hareket ettirmesine karsi onlem alinmamis (17.1)."
        )
    elif inputs.hydraulic_load_measures_taken is None:
        missing.append("Hidrolik yuk onlemleri (17.1) onaylanmali.")

    destination = inputs.destination
    if destination is None:
        missing.append("Bosaltma yeri turu secilmeli.")
    elif destination != DESTINATION_OTHER_SECTION:
        if inputs.approvals_obtained is False:
            violations.append(
                "Su mecrasina veya araziye bosaltma icin gerekli onaylar alinmamis (17.3)."
            )
        elif inputs.approvals_obtained is None:
            missing.append("Bosaltma onaylari (17.3) belirtilmeli.")

    if destination == DESTINATION_WATERCOURSE:
        if inputs.erosion_prevented is False:
            violations.append("Kiyi erozyonu/silitasyon onlenmemis (17.5).")
        elif inputs.erosion_prevented is None:
            missing.append("Erozyon/silitasyon onlemi (17.5) onaylanmali.")

    if inputs.treatment_requested:
        if inputs.treatment_done is False:
            violations.append("Idarece istenen su aritma islemi yapilmamis (17.4).")
        elif inputs.treatment_done is None:
            missing.append("Su aritma islemi (17.4) tamamlandi mi belirtilmeli.")

    if inputs.sample_analysis_requested:
        if inputs.sample_analysis_done is False:
            violations.append("Idarece istenen su numune analizi yapilmamis (17.4).")
        elif inputs.sample_analysis_done is None:
            missing.append("Su numune analizi (17.4) tamamlandi mi belirtilmeli.")

    # 17.6: tarih, saat, kullanilan pig, bosaltma yeri ve islem suresi raporlanmali.
    report_gaps = [
        label
        for label, value in (
            ("tarih", inputs.report_date.strip()),
            ("saat", inputs.report_time.strip()),
            ("kullanilan pig", inputs.pig_name.strip()),
            ("bosaltma yeri", inputs.discharge_location.strip()),
        )
        if not value
    ]
    if inputs.duration_min is None:
        report_gaps.append("islem suresi")
    if report_gaps:
        missing.append("Bosaltma raporu (17.6) eksik alanlar: " + ", ".join(report_gaps) + ".")

    return OperationCheckResult(
        violations=tuple(violations),
        missing=tuple(missing),
        passed=not violations and not missing,
    )
