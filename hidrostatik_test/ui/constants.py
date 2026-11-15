from __future__ import annotations

AUTO_A_MODE = "Otomatik"
TABLE_A_MODE = "Tablo"
REFERENCE_A_MODE = TABLE_A_MODE
MANUAL_A_MODE = "Manuel"

AUTO_B_MODE = "Otomatik"
TABLE_B_MODE = "Tablo"
REFERENCE_B_MODE = TABLE_B_MODE
MANUAL_B_MODE = "Manuel"


DEFAULT_DECISION_TITLE = "Henuz degerlendirme yapilmadi"
DEFAULT_DECISION_STATUS = "BEKLIYOR"
DEFAULT_DECISION_SUMMARY = (
    "Girdileri tamamlayip ilgili testi calistirdiginizda nihai karar burada gosterilecek."
)

# NGTL 5007 saha uygulama kontrol noktalarindan olusan kanonik liste.
# 14.3, 15.1, 16-17 ve 21 maddeleri burada birlikte temsil edilir.
FIELD_CHECK_DEFINITIONS = (
    ("ambient_temp", "Dolum sirasinda hava sicakligi +2 degC limitine gore kontrol edildi", "10.1"),
    ("temp_probes", "Boru ve toprak sicaklik problari uygun yerlere yerlestirildi", "10.4"),
    ("fill_air_entry", "Su dolumu sirasinda sisteme hava girmesi engellendi", "11.2"),
    ("fill_records", "Doldurulan su hacmi ve sicakligi saatlik olarak kaydedildi", "11.3-11.4"),
    ("thermal_balance", "Minimum 24 saat termal dengeleme ve 0.5 degC kosulu kontrol edildi", "12"),
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
    "AUTO_A_MODE",
    "AUTO_B_MODE",
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
