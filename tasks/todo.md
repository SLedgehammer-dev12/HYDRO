# Aktif Plan (Tarihsel Masaüstü Kaydı)

> **Not:** Web backend/frontend ve güncel doğrulama durumu `DURUM.md` dosyasında takip edilir. Aşağıdaki açık maddeler yalnızca **masaüstü (Tkinter UI)** / kurum veri onayı backlog'una aittir.

## Tamamlananlar

- [x] Kaynak kod, testler, dokumantasyon ve build artefact'lari ayristirildi
- [x] Paket yapisi `hidrostatik_test/` altina kuruldu
- [x] Build ve test komutlari yeni yapiya gore guncellendi
- [x] PDF hidrostatik test bolumleri extract edilip analiz notuna donusturuldu
- [x] Agent rolleri ve proje ici skill klasorleri olusturuldu
- [x] UI'ye aktif teste ozel akis kontrol listesi eklendi
- [x] `Saha Kontrol` sekmesi ile operasyonel checklist ve pig hizi hesabi eklendi
- [x] Regresyon testleri yeni yapi ile yeniden yesil hale getirildi
- [x] Web uygulamasında 14.2 (`Form 018`), 12/15 24h zaman serisi (`Form 021`), 16–17 (`Form 023`), 21. bölüm BOTAŞ formları ve `+2 °C` / `0–4 °C` negatif `B` uyarıları tamamlandı (ayrıntı: `DURUM.md`)

## Masaüstü UI / Kurum Onayı Açık İşler

- [ ] (Masaüstü UI) 14.2 basinc-hacim iliskisi ve `%0.2` ilave su alarm mantigini Tkinter UI akisina bagla (web'de tamam)
- [ ] (Masaüstü UI) 12 ve 15 icin zaman serili termal dengeleme / 24 saatlik test kayit modelini Tkinter UI'de kur (web'de tamam)
- [ ] (Masaüstü UI) 16-17 icin basinc dusurme ve bosaltma is akislarini Tkinter UI'de tasarla (web'de tamam)
- [ ] (Masaüstü UI) 21. bolumdeki saha formlarina uygun rapor ciktisi uret (web'de tamam)
- [ ] Segmentli geometri indirgemesi icin kurum ici metod notu hazirla
- [ ] (Masaüstü UI) +2 degC dolum kisiti icin saha uyari mantigi ekle (web'de tamam)
- [ ] `table_v1` backend'i icin masaüstü Tkinter UI secici ekle (web'de tamam)
- [ ] Kurum ici dogrulanmis A/B veri seti geldikten sonra `table_v1` gridini resmi veri ile yeniden doldur
- [ ] (Masaüstü UI) 0-4 degC araliginda negatif `beta_water` ve gecersiz `B` davranisini Tkinter UI'de acik sekilde goster (web'de tamam)

## Dogrulama Kaydi

- `python tools\\generate_water_property_table.py` -> basarili
- `python -m unittest discover -s tests -p "test_*.py"` -> 61 test gecti
- `python -m py_compile Hidrostatik_Test_Chat.py hidrostatik_test\\app_metadata.py hidrostatik_test\\data\\coefficient_reference.py hidrostatik_test\\data\\pipe_catalog.py hidrostatik_test\\data\\water_property_table.py hidrostatik_test\\domain\\hydrotest_core.py hidrostatik_test\\domain\\operations.py hidrostatik_test\\domain\\water_properties.py hidrostatik_test\\services\\updater.py hidrostatik_test\\services\\water_property_table_builder.py hidrostatik_test\\ui\\app.py tools\\generate_water_property_table.py tests\\test_hydrotest_core.py tests\\test_operations.py tests\\test_pipe_catalog.py tests\\test_ui_workflow.py tests\\test_water_properties.py tests\\test_water_property_table.py tests\\test_updater.py` -> basarili
- `python -c "import sys; sys.path.insert(0, r'.'); import Hidrostatik_Test_Chat; import hidrostatik_test.app_metadata; import hidrostatik_test.domain.hydrotest_core; import hidrostatik_test.domain.water_properties; import hidrostatik_test.data.pipe_catalog; import hidrostatik_test.data.water_property_table; import hidrostatik_test.services.updater; import hidrostatik_test.services.water_property_table_builder; print('import-ok')"` -> basarili

## Kural

Her yeni hesap ozelligi icin:

1. Spec analizi guncellenecek
2. En az bir kabul ve bir red testi eklenecek
3. UI'de birim ve isaret konvansiyonu acikca gosterilecek
