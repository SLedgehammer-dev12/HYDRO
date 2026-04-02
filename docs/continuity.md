# Sureklilik Notu

## Mevcut Durum

- Kod tabani paket yapisina tasindi: `hidrostatik_test/`
- Kokte sadece launcher, build dosyalari ve ust seviye dokumanlar kaldi
- Build artefact'i `dist/windows/` altina ayrildi
- Eski prototip ve onceki calisma notlari `docs/legacy/` altina arsivlendi
- Otomatik test paketi 75 test ile geciyor
- Updater birincil olarak `SLedgehammer-dev12/HYDRO`, gecis icin ikinci kaynak olarak `SLedgehammer-dev12/Programlar` release'lerini tarayacak sekilde calisiyor
- UI artik kok seviyede ve sekme seviyesinde kaydirilabilir
- `Boru Kesiti` alani sikistirildi; segment tablosu varsayilan olarak gizli ve ihtiyac halinde aciliyor
- Sabit `Uygulama / Guncelleme` paneli kaldirildi; guncelleme sadece menu ve durum mesajlari ile yonetiliyor
- `Canli Sema` paneli aktif sekmeye, segment geometriye, checklist ilerlemesine ve pig hizina gore dinamik guncelleniyor
- Guncelleme paketi icin kullanici secimli indirme klasoru akisi eklendi
- Manuel guncelleme kontrolunde yeni surum bulundugunda artik kurulum akisi tek adimda teklif ediliyor
- Sag yardimci alan, tek uzun kolon yerine `Rehber / Durum / Kayit` sekmeleriyle daha dar ve odakli calisiyor
- Hava, basinc ve saha sekmeleri genis ekranlarda yatay alan kullanacak sekilde iki kolonlu duzene yaklastirildi
- Kullanici isterse `Yan Paneli Gizle` ile sadece calisma alanina gecebilir
- Statik aciklama metinleri `Bilgi Notlarini Goster/Gizle` ile kontrol edilir; varsayilan ekran daha kompakt tutulur

## Teknik Gercekler

- Hesap cekirdegi `hidrostatik_test/domain/hydrotest_core.py`
- UI `hidrostatik_test/ui/app.py`
- Katalog ve referans veriler `hidrostatik_test/data/`
- Updater `hidrostatik_test/services/updater.py`
- Girdi akisini kolaylastirmak icin aktif teste ozel akis kontrol listesi eklendi
- Repo ayrisma gecisi icin updater kaynak secimi `hidrostatik_test/services/updater.py` icinde merkezilestirildi
- Table/interpolation backend secimi UI tarafinda kullaniciya acik
- Scroll ve canli sema davranislarinin regresyonu `tests/test_ui_workflow.py` ile korunuyor
- Guncelleme indirme klasoru akisi `tests/test_updater.py` ile korunuyor

## Acik Riskler

- 14.2 basinc-hacim `%0.2` limiti henuz modellenmedi
- 24 saatlik zaman serisi ve saha form akisi henuz yok
- Segmentli geometri yaklasimi icin kurum ici metod onayi alinmadi
- A birimi dokumanda tutarsiz gorunuyor; saha oncesi tablo ile teyit edilmeli
- EXE dagitimi icin kod imzalama halen yok; SmartScreen / kurumsal AV false positive riski suruyor
- Update paketi gecici klasor mantigiyla iniyor; audit / retention kurali gerekiyorsa ek saklama politikasi tanimlanmali

## Sonraki Oturumda Ilk Okunacaklar

1. `tasks/todo.md`
2. `tasks/lessons.md`
3. `docs/spec/ngtl_5007_hydrostatic_analysis.md`
4. `docs/ui_ergonomics.md`
5. `docs/repo_migration.md`

## Calisma Kuralı

Formul, katsayi veya kabul kriteri degisikligi yapilacaksa once spec analizi,
sonra test, sonra UI/rapor duzenlemesi yapilmalidir.
