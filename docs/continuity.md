# Sureklilik Notu

## Mevcut Durum

- Kod tabani paket yapisina tasindi: `hidrostatik_test/`
- Kokte sadece launcher, build dosyalari ve ust seviye dokumanlar kaldi
- Build artefact'lari `dist/` (PyInstaller ham cikti) ve `release/` (yayina hazir paketler) altinda ayrildi; ikisi de git disi
- Eski prototip ve onceki calisma notlari `docs/legacy/` altina arsivlendi
- Yerel calisma klasoru `hidrostatik-test-v1.5.9` yayin adayi ile hizalandi
- Otomatik test paketi 653 test ile geciyor
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
- `BOTAS referans tablosu` secenegi kurum ici `A ve B Katsayisi.xlsx` workbook'undan turetilen A/B kontrol tablosunu (`ab_control_table_v1.csv`) okur; ayri bir BOTAS CSV dosyasi yoktur
- `GAIL referans tablosu` secenegi GAIL dokumanindan uretilen `gail_reference_table_v1.csv` verisini kullanir
- Geometri alanina test bolumu profili eklendi; min/max kot, dizayn basinci, SMYS, Location Class ve pompa konumu ile basinc penceresi hesaplanabiliyor
- Referans tablo isimleri ayrildi; eski workbook kaynagi `BOTAS referans tablosu`, GAIL dokumanindan uretilen veri `GAIL referans tablosu` olarak kullaniciya sunuluyor
- Su backend secimi ust menuden yonetiliyor; varsayilan backend `CoolProp`
- UI uc bolmeli ve yeniden boyutlandirilabilir; girdiler solda, aktif test sekmeleri ortada, detay raporu sagda gosteriliyor
- Basinc kontrolu canli kart, kot semasi, `%100 SMYS` span kontrolu ve 5007 tek kesit uzunluk/hacim limitleriyle birlikte izleniyor
- Giris alanlari canli semantik dogrulama ve renkli geri bildirim ile kullaniciyi yonlendiriyor
- Guncelleme imzasi (Ed25519) artik **varsayilan olarak etkin**: gomulu public key (`app_metadata.UPDATE_SIGNING_PUBLIC_KEY`) sayesinde imzasi olmayan veya gecersiz paket kurulmuyor (fail-closed); imzasiz guncelleme yalnizca `HYDRO_ALLOW_UNSIGNED_UPDATE=1` / `HYDRO_REQUIRE_SIGNATURE=0` gelistirici kacis bayraklariyla mumkun ve dagitimda kullanilmiyor

## Teknik Gercekler

- Hesap cekirdegi `hidrostatik_test/domain/hydrotest_core.py`
- UI `hidrostatik_test/ui/app.py`
- Katalog ve referans veriler `hidrostatik_test/data/`
- Updater `hidrostatik_test/services/updater.py`, indirme `services/download_manager.py`
- Kalicilik `services/database.py` (SQLite, WAL) + `domain/session_manager.py` (JSON/SQLite oturum)
- Rapor ciktisi `services/report_export.py` (PDF/Excel)
- Zaman serisi `domain/time_series.py`; %0.2 ilave su hesabi `domain/pressurization.py`
- Girdi akisini kolaylastirmak icin aktif teste ozel akis kontrol listesi eklendi
- Repo ayrisma gecisi icin updater kaynak secimi `hidrostatik_test/services/updater.py` icinde merkezilestirildi
- Table/interpolation backend secimi UI tarafinda kullaniciya acik
- Scroll ve canli sema davranislarinin regresyonu `tests/test_ui_workflow.py` ile korunuyor
- Guncelleme indirme klasoru akisi `tests/test_updater.py` ile korunuyor
- `ab_control_table_v1.csv` ve `ab_control_table_v1.meta.json` hem kaynakta hem PyInstaller paketinde dogrulanmis durumda; `BOTAS referans tablosu` secenegi bu dosyalari paylasir
- `gail_reference_table_v1.csv` ve `gail_reference_table_v1.meta.json` dosyalari hem kaynakta hem PyInstaller paketinde dogrulanmis durumda
- Surum tek kaynaktan yonetiliyor: `hidrostatik_test/app_metadata.py` (`APP_VERSION`, `RELEASE_ASSET_TEMPLATE`)
- Guncelleme imzalama anahtari `tools/update_signing.py` ile yonetiliyor (`generate` / `sign` / `verify`); ozel anahtar `~/.config/hydro/update_signing_key.pem` (0600) konumunda ve repo disinda tutuluyor, CI'da `HYDRO_UPDATE_PRIVATE_KEY` secret'i olarak saglaniyor
- Updater imzayi `verify_asset_signature` icinde zorunlu tutuyor; `HYDRO_UPDATE_PUBKEY` ortam degiskeni gomulu anahtari gecersiz kilar (rotasyon kancasi)
- `.sig` dosyalari release sozlesmesinin parcasidir; build ve CI imzasiz artefakt yayinlamaz
- `pressure_profile.py` ile minimum yuksek nokta test basinci ve 100% SMYS kritik dusuk nokta limiti ayni ekranda izlenebiliyor

## Acik Riskler

- 14.2 basinc-hacim `%0.2` limiti domain katmaninda var (`pressurization.py`) ancak UI saha akisina tam bagli degil
- 24 saatlik zaman serisi modeli ve SQLite tablosu var; UI uzerinden tam saha formu akisi henuz yok
- Segmentli geometri yaklasimi icin kurum ici metod onayi alinmadi
- A birimi dokumanda tutarsiz gorunuyor; saha oncesi tablo ile teyit edilmeli
- EXE/DMG dagitimi icin kod imzalama ve notarization halen yok; SmartScreen / Gatekeeper / kurumsal AV false positive riski suruyor
- Guncelleme imzasi artik zorunlu ancak anahtar kaybi/sizmasi operasyonel risk: ozel anahtar yedegi sifreli medyada tutulmali, sizma suphesinde `generate --force` + public key rotasyonu + yeni surumun elle dagitimi gerekir
- `HYDRO_ALLOW_UNSIGNED_UPDATE=1` / `HYDRO_REQUIRE_SIGNATURE=0` gelistirici kacis bayraklari uretim makinelerinde veya kullanici ortaminda set edilmemeli; edilirse imzasiz paket kabul edilir (yalnizca imza yoklugunda, gecersiz imza yine reddedilir)
- Update paketi gecici klasor mantigiyla iniyor; audit / retention kurali gerekiyorsa ek saklama politikasi tanimlanmali

## Sonraki Oturumda Ilk Okunacaklar

1. `tasks/todo.md`
2. `tasks/lessons.md`
3. `docs/codebase_map.md`
4. `docs/release.md`
5. `docs/testing.md`
6. `docs/spec/ngtl_5007_hydrostatic_analysis.md`

## Calisma Kurali

Formul, katsayi veya kabul kriteri degisikligi yapilacaksa once spec analizi,
sonra test, sonra UI/rapor duzenlemesi yapilmalidir.
