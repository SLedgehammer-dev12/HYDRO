"""Desktop-compatible presentation labels.

These are UI labels only (mode/source names and the canonical field-check
list). Physics, limits and decisions still come from ``hidrostatik_test``.
They exist here so the web layer can read/write the desktop snapshot format
without importing ``hidrostatik_test.ui`` (which imports Tkinter).
"""

from __future__ import annotations

from hidrostatik_test.domain import DEFAULT_STEEL_MODEL

AUTO_MODE = "Otomatik"
TABLE_MODE = "Tablo"
MANUAL_MODE = "Manuel"

MODE_TO_KEY = {AUTO_MODE: "auto", TABLE_MODE: "table", MANUAL_MODE: "manual"}
KEY_TO_MODE = {value: key for key, value in MODE_TO_KEY.items()}

B_SOURCE_INSTITUTIONAL_LABEL = "Kurum ici tablo (varsayilan)"
B_SOURCE_GAIL_LABEL = "GAIL referans tablosu"
B_SOURCE_AUTO_LABEL = "Otomatik (beta - 3*alpha)"

B_SOURCE_TO_KEY = {
    B_SOURCE_INSTITUTIONAL_LABEL: "institutional",
    B_SOURCE_GAIL_LABEL: "gail",
    B_SOURCE_AUTO_LABEL: "auto",
}
KEY_TO_B_SOURCE_LABEL = {value: key for key, value in B_SOURCE_TO_KEY.items()}

STEEL_MODEL_VOLUMETRIC_LABEL = "Hacimsel 3*alpha (varsayilan)"
STEEL_MODEL_LINEAR_LABEL = "Lineer alpha"
STEEL_MODEL_TEMPERATURE_LABEL = "Sicakliga bagli 3*alpha(T)"

STEEL_MODEL_TO_KEY = {
    STEEL_MODEL_VOLUMETRIC_LABEL: "volumetric",
    STEEL_MODEL_LINEAR_LABEL: "linear",
    STEEL_MODEL_TEMPERATURE_LABEL: "volumetric_temperature",
}
KEY_TO_STEEL_MODEL_LABEL = {value: key for key, value in STEEL_MODEL_TO_KEY.items()}
DEFAULT_STEEL_MODEL_LABEL = KEY_TO_STEEL_MODEL_LABEL[DEFAULT_STEEL_MODEL]

AIR_ACCEPTANCE_RULE = "Vpa < 1.06 x Vp"
PRESSURE_ACCEPTANCE_RULE = "(Pa - Pt) <= 0.3 bar"

#: Canonical field-check list (desktop NGTL 5007 checklist).
FIELD_CHECKS: tuple[tuple[str, str, str], ...] = (
    (
        "ambient_temp",
        "Dolum sirasinda hava sicakligi +2 °C limitine gore kontrol edildi",
        "10.1",
    ),
    (
        "temp_probes",
        "Boru ve toprak sicaklik problari uygun yerlere yerlestirildi",
        "10.4",
    ),
    (
        "fill_air_entry",
        "Su dolumu sirasinda sisteme hava girmesi engellendi",
        "11.2",
    ),
    (
        "fill_records",
        "Doldurulan su hacmi ve sicakligi saatlik olarak kaydedildi",
        "11.3-11.4",
    ),
    (
        "thermal_balance",
        "Minimum 24 saat termal dengeleme ve 0.5 °C kosulu kontrol edildi",
        "12",
    ),
    (
        "air_content_limit",
        "Hava icerik testi %6 kabul sinirina gore teyit edildi",
        "13",
    ),
    (
        "pressurization_volume",
        "14.2 icin basinc-hacim ve %0.2 ilave su limiti izlendi",
        "14.2",
    ),
    (
        "two_hour_hold",
        "14.3 icin 2 saat bekleme ve 15 dakikalik okumalar alindi",
        "14.3",
    ),
    (
        "pressure_records",
        "24 saatlik basinc ve sicaklik kayitlari duzenli tutuldu",
        "15.1",
    ),
    (
        "depressurize_discharge",
        "Basinc dusurme ve bosaltma islemleri kontrollu ve raporlu yapildi",
        "16-17",
    ),
    ("forms", "21.1-21.5 saha formlari dolduruldu", "21"),
)

FIELD_CHECK_KEYS: tuple[str, ...] = tuple(item[0] for item in FIELD_CHECKS)

SIGN_CONVENTION = {
    "delta_t": "dT = Tilk - Tson",
    "pa": "Pa = Pilk - Pson",
}

SPEC_NOTES = (
    "Nihai karar ASME B31.8 ve proje proseduru ile birlikte degerlendirilmelidir.",
    "OCR cikti resmi kabul raporu degildir; insan onayi zorunludur.",
)


__all__ = [
    "AIR_ACCEPTANCE_RULE",
    "AUTO_MODE",
    "B_SOURCE_AUTO_LABEL",
    "B_SOURCE_GAIL_LABEL",
    "B_SOURCE_INSTITUTIONAL_LABEL",
    "B_SOURCE_TO_KEY",
    "DEFAULT_STEEL_MODEL_LABEL",
    "FIELD_CHECKS",
    "FIELD_CHECK_KEYS",
    "KEY_TO_B_SOURCE_LABEL",
    "KEY_TO_MODE",
    "KEY_TO_STEEL_MODEL_LABEL",
    "MANUAL_MODE",
    "MODE_TO_KEY",
    "PRESSURE_ACCEPTANCE_RULE",
    "SIGN_CONVENTION",
    "SPEC_NOTES",
    "STEEL_MODEL_LINEAR_LABEL",
    "STEEL_MODEL_TEMPERATURE_LABEL",
    "STEEL_MODEL_TO_KEY",
    "STEEL_MODEL_VOLUMETRIC_LABEL",
    "TABLE_MODE",
]
