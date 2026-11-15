from __future__ import annotations

AUTO_A_MODE = "Otomatik"
TABLE_A_MODE = "Tablo"
REFERENCE_A_MODE = TABLE_A_MODE
MANUAL_A_MODE = "Manuel"

AUTO_B_MODE = "Otomatik"
TABLE_B_MODE = "Tablo"
REFERENCE_B_MODE = TABLE_B_MODE
MANUAL_B_MODE = "Manuel"

# B katsayisi kaynak secenekleri. Varsayilan kaynak kurum ici A/B kontrol
# tablosudur; degerler domain.coefficient_sources.BSource ile ayni anahtarlari
# kullanir.
B_SOURCE_INSTITUTIONAL_LABEL = "Kurum ici tablo (varsayilan)"
B_SOURCE_GAIL_LABEL = "GAIL referans tablosu"
B_SOURCE_AUTO_LABEL = "Otomatik (beta - 3*alpha)"
B_SOURCE_MANUAL_LABEL = "Manuel B"
B_SOURCE_LABELS = (
    B_SOURCE_INSTITUTIONAL_LABEL,
    B_SOURCE_GAIL_LABEL,
    B_SOURCE_AUTO_LABEL,
)
B_SOURCE_BY_LABEL = {
    B_SOURCE_INSTITUTIONAL_LABEL: "institutional",
    B_SOURCE_GAIL_LABEL: "gail",
    B_SOURCE_AUTO_LABEL: "auto",
}

# Otomatik B hesabinda celik genlesme modeli. Varsayilan fiziksel olarak dogru
# hacimsel modeldir (B = beta - 3*alpha).
STEEL_MODEL_VOLUMETRIC_LABEL = "Hacimsel 3*alpha (varsayilan)"
STEEL_MODEL_LINEAR_LABEL = "Lineer alpha"
STEEL_MODEL_TEMPERATURE_LABEL = "Sicakliga bagli 3*alpha(T)"
STEEL_MODEL_LABELS = (
    STEEL_MODEL_VOLUMETRIC_LABEL,
    STEEL_MODEL_LINEAR_LABEL,
    STEEL_MODEL_TEMPERATURE_LABEL,
)
STEEL_MODEL_BY_LABEL = {
    STEEL_MODEL_VOLUMETRIC_LABEL: "volumetric",
    STEEL_MODEL_LINEAR_LABEL: "linear",
    STEEL_MODEL_TEMPERATURE_LABEL: "volumetric_temperature",
}
DEFAULT_STEEL_MODEL_LABEL = STEEL_MODEL_VOLUMETRIC_LABEL


DEFAULT_DECISION_TITLE = "Henuz degerlendirme yapilmadi"
DEFAULT_DECISION_STATUS = "BEKLIYOR"
DEFAULT_DECISION_SUMMARY = (
    "Girdileri tamamlayip ilgili testi calistirdiginizda nihai karar burada gosterilecek."
)

# Kabul kurallari tek kaynaktan yonetilir; karar seridi, karar karti ve rapor
# ayni metni gosterir.
AIR_ACCEPTANCE_RULE = "Vpa < 1.06 x Vp"
PRESSURE_ACCEPTANCE_RULE = "(Pa - Pt) <= 0.3 bar"

# Zorunlu alan kapisi: degerlendirme/hesaplama butonlari bu alanlar gecerli
# olmadan pasif kalir. Geometri segmentli modda ayrica kontrol edilir.
GEOMETRY_REQUIRED_FIELDS = (
    "geometry.outside_diameter_mm",
    "geometry.wall_thickness_mm",
    "geometry.length_m",
)
AIR_REQUIRED_FIELDS = (
    *GEOMETRY_REQUIRED_FIELDS,
    "air.pressure_rise_bar",
    "air.k_factor",
    "air.actual_added_water_m3",
)
PRESSURE_REQUIRED_FIELDS = (
    *GEOMETRY_REQUIRED_FIELDS,
    "pressure.delta_t_c",
    "pressure.actual_pressure_change_bar",
)
PIG_REQUIRED_FIELDS = (
    "field.pig_distance_m",
    "field.pig_travel_time_min",
)

# Kapi mesajlarinda kullanilan kisa alan adlari. Operator "Eksik: geometri, A,
# Vpa" satirinda hangi alanin eksik oldugunu tek bakista gorur.
REQUIRED_FIELD_LABELS = {
    "geometry": "geometri",
    "geometry.outside_diameter_mm": "dis cap",
    "geometry.wall_thickness_mm": "et kalinligi",
    "geometry.length_m": "hat uzunlugu",
    "air.temperature_c": "su sicakligi",
    "air.pressure_bar": "su basinci",
    "air.a_micro_per_bar": "A",
    "air.pressure_rise_bar": "P",
    "air.k_factor": "K",
    "air.actual_added_water_m3": "Vpa",
    "pressure.temperature_c": "su sicakligi",
    "pressure.pressure_bar": "su basinci",
    "pressure.a_micro_per_bar": "A",
    "pressure.b_micro_per_c": "B",
    "pressure.delta_t_c": "dT",
    "pressure.actual_pressure_change_bar": "Pa",
    "field.pig_distance_m": "mesafe",
    "field.pig_travel_time_min": "sure",
}

REQUIRED_FIELD_HINT = "* = zorunlu"

# NGTL 5007 saha uygulama kontrol noktalarindan olusan kanonik liste.
# 14.3, 15.1, 16-17 ve 21 maddeleri burada birlikte temsil edilir.
FIELD_CHECK_DEFINITIONS = (
    ("ambient_temp", "Dolum sirasinda hava sicakligi +2 °C limitine gore kontrol edildi", "10.1"),
    ("temp_probes", "Boru ve toprak sicaklik problari uygun yerlere yerlestirildi", "10.4"),
    ("fill_air_entry", "Su dolumu sirasinda sisteme hava girmesi engellendi", "11.2"),
    ("fill_records", "Doldurulan su hacmi ve sicakligi saatlik olarak kaydedildi", "11.3-11.4"),
    ("thermal_balance", "Minimum 24 saat termal dengeleme ve 0.5 °C kosulu kontrol edildi", "12"),
    ("air_content_limit", "Hava icerik testi %6 kabul sinirina gore teyit edildi", "13"),
    ("pressurization_volume", "14.2 icin basinc-hacim ve %0.2 ilave su limiti izlendi", "14.2"),
    ("two_hour_hold", "14.3 icin 2 saat bekleme ve 15 dakikalik okumalar alindi", "14.3"),
    ("pressure_records", "24 saatlik basinc ve sicaklik kayitlari duzenli tutuldu", "15.1"),
    (
        "depressurize_discharge",
        "Basinc dusurme ve bosaltma islemleri kontrollu ve raporlu yapildi",
        "16-17",
    ),
    ("forms", "21.1-21.5 saha formlari dolduruldu", "21"),
)

# Alan bazli makul sinirlar. Harita disindaki alanlar yalnizca sonluluk ve
# isaret/sifir kontrollerinden gecer.
FIELD_VALUE_RANGES = {
    "air.a_micro_per_bar": (1.0, 200.0),
    "pressure.a_micro_per_bar": (1.0, 200.0),
    "pressure.b_micro_per_c": (-200.0, 500.0),
    "air.k_factor": (1.0, 1.1),
    "pressure.delta_t_c": (-20.0, 20.0),
    "pressure.actual_pressure_change_bar": (-50.0, 50.0),
    "geometry.outside_diameter_mm": (1.0, 5000.0),
    "geometry.wall_thickness_mm": (0.1, 200.0),
    "geometry.length_m": (0.1, 1_000_000.0),
}

__all__ = [
    "AIR_ACCEPTANCE_RULE",
    "AIR_REQUIRED_FIELDS",
    "AUTO_A_MODE",
    "AUTO_B_MODE",
    "B_SOURCE_AUTO_LABEL",
    "B_SOURCE_BY_LABEL",
    "B_SOURCE_GAIL_LABEL",
    "B_SOURCE_INSTITUTIONAL_LABEL",
    "B_SOURCE_LABELS",
    "B_SOURCE_MANUAL_LABEL",
    "DEFAULT_STEEL_MODEL_LABEL",
    "PRESSURE_ACCEPTANCE_RULE",
    "PRESSURE_REQUIRED_FIELDS",
    "PIG_REQUIRED_FIELDS",
    "GEOMETRY_REQUIRED_FIELDS",
    "REQUIRED_FIELD_HINT",
    "REQUIRED_FIELD_LABELS",
    "STEEL_MODEL_BY_LABEL",
    "STEEL_MODEL_LABELS",
    "STEEL_MODEL_LINEAR_LABEL",
    "STEEL_MODEL_TEMPERATURE_LABEL",
    "STEEL_MODEL_VOLUMETRIC_LABEL",
    "TABLE_A_MODE",
    "TABLE_B_MODE",
    "REFERENCE_A_MODE",
    "REFERENCE_B_MODE",
    "MANUAL_A_MODE",
    "MANUAL_B_MODE",
    "DEFAULT_DECISION_TITLE",
    "DEFAULT_DECISION_STATUS",
    "DEFAULT_DECISION_SUMMARY",
    "FIELD_CHECK_DEFINITIONS",
    "FIELD_VALUE_RANGES",
]
