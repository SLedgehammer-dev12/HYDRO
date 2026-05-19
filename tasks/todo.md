# Aktif Plan

## Tamamlananlar

- [x] Kaynak kod, testler, dokumantasyon ve build artefact'lari ayristirildi
- [x] Paket yapisi `hidrostatik_test/` altina kuruldu
- [x] Build ve test komutlari yeni yapiya gore guncellendi
- [x] PDF hidrostatik test bolumleri extract edilip analiz notuna donusturuldu
- [x] Agent rolleri ve proje ici skill klasorleri olusturuldu
- [x] UI'ye aktif teste ozel akis kontrol listesi eklendi
- [x] `Saha Kontrol` sekmesi ile operasyonel checklist ve pig hizi hesabi eklendi
- [x] Regresyon testleri yeni yapi ile yeniden yesil hale getirildi

## Acik Isler

- [ ] 14.2 basinc-hacim iliskisi ve `%0.2` ilave su alarm mantigini modele ekle
- [x] 12 ve 15 icin zaman serili termal dengeleme / 24 saatlik test kayit veri modelini kur
- [x] 16-17 icin basinc dusurme ve bosaltma is akislarini rapor bazli tasarla
- [ ] 21. bolumdeki saha formlarina uygun rapor ciktisi uret
- [ ] Segmentli geometri indirgemesi icin kurum ici metod notu hazirla
- [x] +2 degC dolum kisiti icin saha uyari mantigi ekle
- [x] `table_v1` backend'i icin UI secici ve backend-karsilastirma raporu ekle
- [ ] Kurum ici dogrulanmis A/B veri seti geldikten sonra `table_v1` gridini resmi veri ile yeniden doldur
- [ ] 0-4 degC araliginda negatif `beta_water` ve gecersiz `B` davranisini UI'de acik sekilde goster

## Dogrulama Kaydi

- `python -m pytest tests/ -q` -> 165 passed, 1 skipped (v1.6.0)
- `python tools\\generate_water_property_table.py` -> basarili
- `build_exe.ps1 -SkipTests` -> basarili (PyInstaller 6.12.0, Windows manifest ve version resource eklendi)
- Release artefact'lari: `release/HidrostatikTest-v1.6.0-windows-x64.zip` (16.5 MB) + SHA256

## Kural

Her yeni hesap ozelligi icin:

1. Spec analizi guncellenecek
2. En az bir kabul ve bir red testi eklenecek
3. UI'de birim ve isaret konvansiyonu acikca gosterilecek
