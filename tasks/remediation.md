# Audit Remediation Plan

Kaynak: `docs/analysis_report.md` bulgulari + `docs/codebase_map.md`.
Dal: `fix/audit-remediation`. Hedef: P0 + uygulanabilir P1 bulgularini kapatmak,
davranis regresyonlarini testle sabitlemek ve e2e akisi eklemek.

## Dalga 1 - Domain, veri, servis, paketleme

### Domain fizigi
- [x] Negatif B kabulu (0-5.5 degC olu bolgesi)
- [x] `math.isfinite` ile sonlu deger dogrulamasi
- [x] Hava icerigi tam %6 sinirinda FAIL (sartname: "%6 veya daha fazla")
- [x] Termal denge: son 4 saat vs onceki 4 saat, `records[-1].timestamp` referansi
- [x] %0.2 ilave su: tek tarafli fazla su kontrolu, gercekci basinc toleransi
- [x] Bicubic aralik disi ekstrapolasyonun kapatilmasi
- [x] Regression testleri

### Veri katmani
- [x] BOTAS = kurum ici workbook semantigi; olu `botas_*_v1` CSV temizligi
- [x] A/B tablosu monotonluk/sureklilik dogrulamasi ve anomali raporu
- [x] Aralik metni/testlerinin gercek veriyle hizalanmasi
- [x] B kaynak karsilastirma yardimcisi + test

### Servisler
- [x] DownloadManager resume tek thread
- [x] Updater asset/checksum sozlesmesi (.zip + .exe, iki checksum adi)
- [x] Katı asset eslesmesi, yanlis surum fallback'inin kaldirilmasi
- [x] Guvenli zip cikarma (kota + beklenen yapi)
- [x] Yedek + atomik kurulum + rollback + log
- [x] SQLite thread guvenligi, busy_timeout, UTC, izinler
- [x] SessionManager timer hatasinda yeniden kurulum, `updated_at` korumasi
- [x] PDF/Excel escaping, formül notrleme, A4/Unicode, atomik yazma
- [x] Indirme yoneticisi ve rapor icerigi testleri

### Paketleme / CI / dokuman
- [x] Windows matrisinde bash sozdizimi duzeltmesi
- [x] Release testinde Xvfb
- [x] `.zip` uretimi ve checksum adi sozlesmesi
- [x] Runtime hook'un iki build yolunda da kullanilmasi
- [x] Spec surumunun `app_metadata`'dan okunmasi
- [x] Tag <-> surum ve artefakt sozlesmesi CI kapisi
- [x] Ruff/mypy yapilandirmasi, surum pinleri
- [x] README/CHANGELOG/docs surum ve test sayisi senkronu

## Dalga 2 - UI
- [x] `self.pressure_bar` rapor cokmesi
- [x] Bayat katsayi kapisi
- [x] Mod degisiminde provenance temizligi
- [x] Test bazli karar modeli
- [x] Canli sonucun kaydi (debounce + dedupe)
- [x] Banner'in karar durumuna baglanmasi
- [x] `nan/inf` ve alan bazli aralik dogrulamasi
- [x] Tek `FIELD_CHECK_DEFINITIONS` kaynagi
- [x] 10.1 icin ayri ortam sicakligi alani
- [x] Wizard adim -> sekme eslemesi
- [x] Canli yenileme firtinasi (debounce + reentrancy guard)
- [x] Minsize / kucuk ekran
- [x] DownloadDialog'a gercek `DownloadManager()` instance'i

## Dalga 3 - Dogrulama
- [x] Tam test paketi
- [x] Ruff check + format
- [x] Mypy (en az domain)
- [x] E2E: geometri -> A/B -> hava + basinc -> rapor (txt/pdf/xlsx) -> oturum kaydet/yukle
- [x] Graphify haritasinin yenilenmesi
- [x] Remediation raporu

## Karar gerektirenler (muhendislik onayi olmadan degistirilmez)
- B kaynagi: otomatik `beta-alpha` mi, kurum ici tablo mu, GAIL mi?
- Kurum ici A/B tablosundaki 7 degC / 90-98 bar anomalisinin resmi duzeltmesi
- Kod imzalama/notarization anahtarlari ve yayin sertifikalari
- A biriminin sartname icindeki 1/K vs 1/bar celiskisinin resmi yorumu
