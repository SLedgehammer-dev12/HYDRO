from __future__ import annotations

from typing import Final

FIELD_CHECK_DEFINITIONS: Final = (
    ("ambient_temp", "Dolum sirasinda hava sicakligi +2 degC limitine gore kontrol edildi", "10.1"),
    ("temp_probes", "Boru ve toprak sicaklik problari uygun yerlere yerlestirildi", "10.4"),
    ("fill_air_entry", "Su dolumu sirasinda sisteme hava girmesi engellendi", "11.2"),
    ("fill_records", "Doldurulan su hacmi ve sicakligi saatlik olarak kaydedildi", "11.3-11.4"),
    ("thermal_balance", "Minimum 24 saat termal dengeleme ve 0.5 degC kosulu kontrol edildi", "12"),
    ("air_content_limit", "Hava icerik testi %6 kabul sinirina gore teyit edildi", "13"),
    ("pressurization_volume", "14.2 icin basinc-hacim ve %0.2 ilave su limiti izlendi", "14.2"),
    ("two_hour_hold", "14.3 icin 2 saat bekleme ve 15 dakikalik okumalar alindi", "14.3"),
    ("pressure_records", "24 saatlik basinc ve sicaklik kayitlari duzenli tutuldu", "15.1"),
    ("depressurize_discharge", "Basinc dusurme ve bosaltma islemleri kontrollu ve raporlu yapildi", "16-17"),
)
