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

FIELD_CHECK_DEFINITIONS = (
    ("ambient_temp", "Dolum sirasinda hava sicakligi +2 degC limitine gore kontrol edildi", "10.1"),
    ("temp_probes", "Boru ve toprak sicaklik problari uygun yerlere yerlestirildi", "10.4"),
    ("fill_air_entry", "Su dolumu sirasinda sisteme hava girmesi engellendi", "11.2"),
    ("fill_records", "Doldurulan su hacmi ve sicakligi saatlik olarak kaydedildi", "11.3-11.4"),
    ("thermal_balance", "Minimum 24 saat termal dengeleme ve 0.5 degC kosulu kontrol edildi", "12"),
    ("air_content_limit", "Hava icerik testi %6 kabul sinirina gore teyit edildi", "13"),
    ("pressurization_volume", "14.2 icin basinc-hacim ve %0.2 ilave su limiti izlendi", "14.2"),
    ("pressure_test_period", "Basinc testi minimum 24 saat uygulandi", "15"),
    ("vent_drain", "Test sonrasi vana tahliye ve bosaltma islemi gerceklestirildi", "16"),
    ("decommission", "Test ekipmani ve basinclandirma araci devre disi birakildi", "17-20"),
    ("forms", "21.1-21.5 saha formlari dolduruldu", "21"),
)

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
]
