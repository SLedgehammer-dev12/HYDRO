"""Decision objects derived from domain results.

Decision text is produced server-side only (parity rule). The frontend renders
these fields verbatim.
"""

from __future__ import annotations

import math
from typing import Any

from hidrostatik_test.domain import (
    AIR_CONTENT_ACCEPTANCE_FACTOR,
    MAX_TEST_SECTION_LENGTH_M,
    MAX_TEST_SECTION_VOLUME_M3,
    PRESSURE_VARIATION_ACCEPTANCE_BAR,
    PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT,
)
from hidrostatik_test.domain.pressurization_monitor import (
    HOLD_DURATION_MIN,
    HOLD_READING_INTERVAL_MIN,
    MAX_RAMP_RATE_BAR_PER_MIN,
)
from hidrostatik_test.domain.time_series import (
    TEST_RECORDING_MAX_GAP_HOURS,
    TEST_RECORDING_MIN_HOURS,
    THERMAL_BALANCE_MIN_HOURS,
    THERMAL_BALANCE_THRESHOLD_C,
)

STATUS_PASS = "BASARILI"
STATUS_FAIL = "BASARISIZ"
STATUS_PENDING = "BEKLIYOR"
STATUS_UNKNOWN = "DOGRULANAMADI"
STATUS_STALE = "KATSAYI GUNCELLENMELI"

AIR_RULE = f"Vpa < {AIR_CONTENT_ACCEPTANCE_FACTOR:.2f} x Vp"
PRESSURE_RULE = f"(Pa - Pt) <= {PRESSURE_VARIATION_ACCEPTANCE_BAR} bar"
PROFILE_RULE = (
    f"min <= P <= max; L <= {MAX_TEST_SECTION_LENGTH_M:.0f} m; "
    f"Vt <= {MAX_TEST_SECTION_VOLUME_M3:.0f} m³"
)
PRESSURIZATION_RULE = (
    f"hacim sapmasi <= %{PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT} ve |dP| <= tolerans"
)
RAMP_RULE = (
    f"%80-%95 SMYS artis hizi <= {MAX_RAMP_RATE_BAR_PER_MIN:g} bar/dk; "
    f"%95 SMYS sonrasi basilan su <= %{PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT} toplam hacim"
)
HOLD_RULE = (
    f"bekleme >= {HOLD_DURATION_MIN:.0f} dk; okuma araligi <= {HOLD_READING_INTERVAL_MIN:.0f} dk"
)
DEPRESSURIZATION_RULE = (
    'basinc dusurme vanasi <= 2"; test basarili; boru/ekipman ve cevre onlemleri'
)
DISCHARGE_RULE = "bosaltma pigi; hidrolik yuk onlemi; onaylar; cevre onlemleri; 17.6 raporu"
THERMAL_RULE = (
    f"sure >= {THERMAL_BALANCE_MIN_HOURS:.0f} h ve |dT_4h| <= {THERMAL_BALANCE_THRESHOLD_C} °C"
)
TEST_RECORDING_RULE = (
    f"sure >= {TEST_RECORDING_MIN_HOURS:.0f} h ve "
    f"maks okuma araligi <= {TEST_RECORDING_MAX_GAP_HOURS:g} h (Sartname 15.1)"
)
PIG_RULE = "hiz <= limit"


def _decision(
    status: str, title: str, summary: str, rule: str, margin: float | None
) -> dict[str, Any]:
    return {
        "status": status,
        "title": title,
        "summary": summary,
        "rule": rule,
        "margin": margin,
    }


def air_decision(result: Any) -> dict[str, Any]:
    margin = result.acceptance_limit_m3 - result.actual_added_water_m3
    status = STATUS_PASS if result.passed else STATUS_FAIL
    summary = (
        f"Vp = {result.theoretical_added_water_m3:.6f} m³, "
        f"limit = {result.acceptance_limit_m3:.6f} m³, "
        f"Vpa = {result.actual_added_water_m3:.6f} m³, "
        f"oran = {result.ratio:.6f}. Kural: {AIR_RULE}; "
        f"marj = {margin:.6f} m³."
    )
    return _decision(status, "Hava Icerik Testi", summary, AIR_RULE, margin)


def pressure_decision(result: Any, *, negative_b: bool | None = None) -> dict[str, Any]:
    status = STATUS_PASS if result.passed else STATUS_FAIL
    is_negative_b = (
        negative_b if negative_b is not None else result.theoretical_pressure_change_bar < 0
    )
    summary = (
        f"Pt = {result.theoretical_pressure_change_bar:.6f} bar, "
        f"ust sinir = {result.allowable_upper_pressure_change_bar:.6f} bar, "
        f"Pa = {result.actual_pressure_change_bar:.6f} bar, "
        f"fark = {result.margin_bar:.6f} bar. Kural: {PRESSURE_RULE}; "
        f"marj = {result.margin_bar:.6f} bar."
    )
    if is_negative_b:
        summary = f"{summary} B negatif: dP isareti ters doner ve gecerlidir."
    return _decision(status, "Basinc Degisim Testi", summary, PRESSURE_RULE, result.margin_bar)


def pig_decision(result: Any) -> dict[str, Any]:
    if result.passed is None:
        status = "BILGI"
        decision_status = STATUS_UNKNOWN
    elif result.passed:
        status = "UYGUN"
        decision_status = STATUS_PASS
    else:
        status = "LIMIT ASILDI"
        decision_status = STATUS_FAIL

    limit = result.limit
    limit_text = (
        f"{limit.max_speed_m_per_s:.6f} m/s"
        if limit.max_speed_m_per_s is not None
        else "limit tanimli degil"
    )
    outcome = "limit asildi" if result.passed is False else "limit asilmadi"
    if result.passed is None:
        outcome = "limit uygulanmaz (serbest kontrol)"
    summary = (
        f"Hesaplanan pig hizi = {result.speed_m_per_s:.6f} m/s "
        f"({result.speed_km_per_h:.6f} km/sa). {limit.spec_reference} icin "
        f"{outcome}; limit = {limit_text}."
    )
    margin = (
        limit.max_speed_m_per_s - result.speed_m_per_s
        if limit.max_speed_m_per_s is not None
        else None
    )
    return {
        "status": decision_status,
        "pig_status": status,
        "title": "Pig Hiz Hesabi",
        "summary": summary,
        "rule": PIG_RULE,
        "margin": margin,
    }


def profile_decision(result: Any) -> dict[str, Any]:
    checks: list[bool] = [bool(result.feasible)]
    if result.monitored_meets_minimum is not None:
        checks.append(bool(result.monitored_meets_minimum))
    if result.monitored_under_maximum is not None:
        checks.append(bool(result.monitored_under_maximum))
    status = STATUS_PASS if all(checks) else STATUS_FAIL

    window = result.selected_window
    if result.monitored_pressure_bar is None:
        summary = (
            f"Secili pompa noktasi icin basinc penceresi "
            f"{window.minimum_required_pressure_bar:.3f} - "
            f"{window.maximum_allowable_pressure_bar:.3f} bar."
        )
    else:
        summary = (
            f"Secili pompa noktasi icin izlenen basinc "
            f"{result.monitored_pressure_bar:.3f} bar; pencere "
            f"{window.minimum_required_pressure_bar:.3f} - "
            f"{window.maximum_allowable_pressure_bar:.3f} bar."
        )
    if not result.within_length_limit:
        summary += f" Hat uzunlugu {MAX_TEST_SECTION_LENGTH_M:.0f} m sinirini asiyor."
    if not result.within_volume_limit:
        summary += f" Hacim {MAX_TEST_SECTION_VOLUME_M3:.0f} m³ sinirini asiyor."
    if not result.within_100_smys_span_limit:
        summary += " Gerekli basinc 100% SMYS limitini asiyor."
    return _decision(status, "Test Bolumu Basinc Penceresi", summary, PROFILE_RULE, 0.0)


def pressurization_decision(result: Any) -> dict[str, Any]:
    status = STATUS_PASS if result.passed else STATUS_FAIL
    margin = PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT - abs(result.volume_deviation_percent)
    summary = (
        f"Hacim sapmasi = %{result.volume_deviation_percent:.3f}, "
        f"basinc sapmasi = {result.pressure_deviation_bar:.3f} bar. "
        f"Kural: {PRESSURIZATION_RULE}; marj = {margin:.3f}."
    )
    if result.underfilled:
        summary += f" Eksik dolum: teorik hacme gore %{result.volume_shortfall_percent:.3f} eksik."
    return _decision(status, "Basinclandirma Kontrolu", summary, PRESSURIZATION_RULE, margin)


def ramp_decision(result: Any) -> dict[str, Any]:
    if result.passed is False:
        status = STATUS_FAIL
    elif result.passed is None:
        status = STATUS_PENDING
    else:
        status = STATUS_PASS
    parts = [
        f"Azami artis hizi = {result.max_ramp_rate_bar_per_min:.3f} bar/dk "
        f"(limit {result.ramp_rate_limit_bar_per_min:g}).",
        f"%95 SMYS sonrasi basilan su = {result.pumped_since_95_smys_m3:.4f} m³ "
        f"(limit {result.excess_volume_limit_m3:.4f} m³).",
    ]
    if result.ramp_rate_violations:
        parts.append(f"{len(result.ramp_rate_violations)} aralikta artis hizi asildi (14.1).")
    if result.stop_required:
        parts.append("BASINCLANDIRMAYI DURDURUN ve Idarenin talimatini bekleyin (14.2).")
    elif result.volume_limit_exceeded:
        parts.append("Basilan su siniri asildi (14.2).")
    if result.monitoring_gaps:
        parts.append(f"{len(result.monitoring_gaps)} adimda 0,2 bar izleme araligi asildi.")
    if result.passed is None:
        parts.append("%100 SMYS'ye henuz ulasilmadi.")
    margin = result.excess_volume_limit_m3 - result.pumped_since_95_smys_m3
    return _decision(status, "Basinclandirma Izleme", " ".join(parts), RAMP_RULE, margin)


def hold_decision(result: Any) -> dict[str, Any]:
    status = STATUS_PASS if result.passed else STATUS_FAIL
    parts = [
        f"Sure = {result.duration_min:.0f} dk (en az {result.required_duration_min:.0f}).",
        f"En uzun okuma araligi = {result.max_reading_gap_min:.1f} dk "
        f"(en fazla {result.required_interval_min:.0f}).",
        f"Basinc dususu = {result.pressure_drop_bar:.3f} bar.",
    ]
    if result.repressurize_required:
        parts.append("Basinc yeniden izlenen basincin %100'une cikarilmali (14.3).")
    margin = result.duration_min - result.required_duration_min
    return _decision(status, "2 Saatlik Bekleme", " ".join(parts), HOLD_RULE, margin)


def _operation_decision(result: Any, title: str, rule: str, ok_text: str) -> dict[str, Any]:
    if result.violations:
        status = STATUS_FAIL
    elif result.missing:
        status = STATUS_PENDING
    else:
        status = STATUS_PASS
    parts: list[str] = list(result.violations) + list(result.missing)
    summary = " ".join(parts) if parts else ok_text
    return _decision(status, title, summary, rule, None)


def depressurization_decision(result: Any) -> dict[str, Any]:
    return _operation_decision(
        result,
        "Basincin Dusurulmesi",
        DEPRESSURIZATION_RULE,
        "Basinc dusurme kosullari saglandi (Sartname 16).",
    )


def discharge_decision(result: Any) -> dict[str, Any]:
    return _operation_decision(
        result,
        "Bosaltma",
        DISCHARGE_RULE,
        "Bosaltma kosullari ve raporlama saglandi (Sartname 17).",
    )


def thermal_decision(
    *,
    duration_hours: float,
    balanced: bool,
    temp_diff_c: float | None,
    reason: str = "",
) -> dict[str, Any]:
    if temp_diff_c is None:
        status = STATUS_UNKNOWN
        summary = reason or "Termal denge icin yeterli veri yok."
        margin = None
    else:
        status = STATUS_PASS if balanced else STATUS_FAIL
        margin = THERMAL_BALANCE_THRESHOLD_C - temp_diff_c
        summary = (
            f"Sure = {duration_hours:.1f} saat; son 4 saat ile onceki 4 saat "
            f"arasindaki sicaklik farki = {temp_diff_c:.3f} °C. "
            f"Kural: {THERMAL_RULE}."
        )
    return _decision(status, "Termal Denge", summary, THERMAL_RULE, margin)


def twenty_four_hour_recording_decision(
    *,
    record_count: int,
    duration_hours: float,
    max_gap_hours: float | None,
    duration_ok: bool,
    interval_ok: bool,
    passed: bool,
) -> dict[str, Any]:
    if record_count < 2:
        return _decision(
            STATUS_PENDING,
            "24 Saatlik Test Kaydi (15.1)",
            "24 saatlik test kaydi icin en az 2 zaman serisi okumasi gerekir.",
            TEST_RECORDING_RULE,
            None,
        )
    status = STATUS_PASS if passed else STATUS_FAIL
    margin = duration_hours - TEST_RECORDING_MIN_HOURS
    gap_text = (
        f"{max_gap_hours:.2f} sa ({max_gap_hours * 60.0:.0f} dk)"
        if max_gap_hours is not None
        else "-"
    )
    notes: list[str] = []
    if not duration_ok:
        notes.append(f"sure {TEST_RECORDING_MIN_HOURS:.0f} sa altinda")
    if not interval_ok:
        notes.append(f"okuma araligi {TEST_RECORDING_MAX_GAP_HOURS:g} sa sinirini asiyor")
    note_suffix = f" Eksik/ihlal: {', '.join(notes)}." if notes else ""
    summary = (
        f"{record_count} okuma, toplam sure = {duration_hours:.2f} saat, "
        f"en uzun okuma araligi = {gap_text}.{note_suffix} "
        f"Kural: {TEST_RECORDING_RULE}."
    )
    return _decision(status, "24 Saatlik Test Kaydi (15.1)", summary, TEST_RECORDING_RULE, margin)


def pending_decision(title: str, rule: str) -> dict[str, Any]:
    return _decision(
        STATUS_PENDING,
        title,
        "Hesaplama yapilmadi; girdiler bekleniyor.",
        rule,
        None,
    )


def finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


__all__ = [
    "AIR_RULE",
    "PIG_RULE",
    "PRESSURE_RULE",
    "PROFILE_RULE",
    "PRESSURIZATION_RULE",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_PENDING",
    "STATUS_STALE",
    "STATUS_UNKNOWN",
    "TEST_RECORDING_RULE",
    "THERMAL_RULE",
    "RAMP_RULE",
    "HOLD_RULE",
    "DEPRESSURIZATION_RULE",
    "DISCHARGE_RULE",
    "air_decision",
    "depressurization_decision",
    "discharge_decision",
    "hold_decision",
    "ramp_decision",
    "finite_or_none",
    "pending_decision",
    "pig_decision",
    "pressure_decision",
    "pressurization_decision",
    "profile_decision",
    "thermal_decision",
    "twenty_four_hour_recording_decision",
]
