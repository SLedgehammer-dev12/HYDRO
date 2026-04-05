# Sureklilik Notu

## Mevcut Durum

- Kod tabani paket yapisina tasindi: `hidrostatik_test/`
- Kokte sadece launcher, build dosyalari ve ust seviye dokumanlar kaldi
- Build artefact'i `dist/windows/` altina ayrildi
- Eski prototip ve onceki calisma notlari `docs/legacy/` altina arsivlendi
- Yerel calisma klasoru `hidrostatik-test-v1.5.9` yayin adayi ile hizalandi
- Otomatik test paketi 120 test ile geciyor
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
- Updater yeniden baslatma akisi `cmd` yerine `PowerShell` ile calisir; Turkce karakterli klasor yollarinda daha guvenli hale getirildi
- Build zinciri artik kurum ici `A/B` kontrol tablosu veri dosyalarini da bundle eder ve build sonunda bu dosyalari dogrular
- GAIL dokumanindan turetilen secilebilir `BOTAŞ referans tablosu` runtime veri kaynagi olarak eklendi
- Geometri alanina test bolumu profili eklendi; min/max kot, dizayn basinci, SMYS, Location Class ve pompa konumu ile basinc penceresi hesaplanabiliyor
- Referans tablo isimleri ayrildi; eski workbook kaynagi `BOTAS referans tablosu`, GAIL dokumanindan uretilen veri `GAIL referans tablosu` olarak kullaniciya sunuluyor
- Su backend secimi ust menuden yonetiliyor; varsayilan backend `CoolProp`
- UI uc bolmeli ve yeniden boyutlandirilabilir; girdiler solda, aktif test sekmeleri ortada, detay raporu sagda gosteriliyor
- Basinc kontrolu canli kart, kot semasi, `%100 SMYS` span kontrolu ve 5007 tek kesit uzunluk/hacim limitleriyle birlikte izleniyor
- Giris alanlari canli semantik dogrulama ve renkli geri bildirim ile kullaniciyi yonlendiriyor

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
- `ab_control_table_v1.csv` ve `ab_control_table_v1.meta.json` dosyalari hem kaynakta hem PyInstaller paketinde dogrulanmis durumda
- `botas_reference_table_v1.csv` ve `botas_reference_table_v1.meta.json` dosyalari hem kaynakta hem PyInstaller paketinde dogrulanmis durumda
- `pressure_profile.py` ile minimum yuksek nokta test basinci ve 100% SMYS kritik dusuk nokta limiti ayni ekranda izlenebiliyor

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

## Calisma Kurali

Formul, katsayi veya kabul kriteri degisikligi yapilacaksa once spec analizi,
sonra test, sonra UI/rapor duzenlemesi yapilmalidir.
