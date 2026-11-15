# Audit Remediation Report

Tarih: 2026-11-15
Dal: `fix/audit-remediation`
Kapsam: `docs/analysis_report.md` bulgulari + `tasks/remediation.md`
Yontem: Graphify haritasi + paralel dosya-sahipligi iscileri + dogrulama dalgasi.

## 1. Sonuc Ozeti

| Alan | Durum | Kanit |
| --- | --- | --- |
| Domain fizigi | Tamam | 508 test, domain mypy temiz |
| Veri katmani | Tamam (veri duzeltmesi haric) | 12 + 10 test, anomali tespiti |
| Servisler / updater | Tamam | 113 hedefli test, guvenli cikarma + rollback |
| UI dogruluk | Tamam | 82 UI testi + 4 e2e |
| Paketleme / CI | Tamam | `.zip` sozlesmesi, tag↔surum kapisi |
| Dokumantasyon | Tamam | surum/test sayisi senkronu |
| Kod kalitesi | Tamam | ruff temiz, domain mypy temiz |
| E2E | Tamam | 4 senaryo |

**Dogrulama:**

- `python3 -m unittest discover -s tests -p "test_*.py"` → **508 test OK**
- `python3 -m coverage run -m unittest discover ...` → **%79** kaynak-only branch kapsami
- `python3 -m ruff check .` → **All checks passed**
- `python3 -m ruff format --check .` → **59+ dosya formatli**
- `python3 -m mypy hidrostatik_test/domain/` → **Success: no issues**
- `python3 -m unittest discover -s tests -p "test_e2e_workflow.py"` → **4 test OK**

## 2. Kapatilan Kritik Bulgular

### Domain

- Negatif B ve negatif su beta'si kabul ediliyor; 0–5.5 °C olu bolgesi kalkti.
- `math.isfinite` ile `nan/inf/1e999` tum sayisal girdilerde reddediliyor.
- Hava icerigi tam `1.06 * Vp` sinirinda FAIL (sartname: "%6 veya daha fazla").
- Termal denge: son 4 saat vs onceki 4 saat; referans `records[-1].timestamp`.
- %0.2 ilave su: tek tarafli fazla su kontrolu; basinc toleransi `max(0.05, 0.001*P)`.
- Bicubic backend aralik disinda `WaterPropertyError` veriyor; sessiz ekstrapolasyon yok.

### Veri

- BOTAŞ = kurum ici workbook (`ab_control_table_v1.csv`) semantigi netlesti.
- Kullanilmayan ve GAIL ile birebir ayni olan `botas_reference_table_v1.*` silindi.
- A/B tablosu icin monotonluk, sicrama, eksik/tekrarlı hucre denetimi eklendi.
- Bilinen 7 °C / 90–98 bar anomalisi testle yakalaniyor; **veri resmi onay olmadan degistirilmedi**.
- `compare_reference_b_sources` ile BOTAŞ/GAIL farki gorunur hale geldi.

### Servisler

- `DownloadManager.resume` yeni thread acmiyor; tek worker garantisi test edildi.
- Updater `.zip` ve `.exe` kabul ediyor; iki checksum adi adayi deneniyor.
- Yanlis surum fallback'i kaldirildi; asset adi surumle eslesmeli.
- Guvenli zip cikarma: path traversal, symlink, dosya sayisi/boyut/oran limitleri.
- Kurulum: `backup-<version>`, atomik takas, hata halinde rollback, `apply_update.log`.
- macOS: gecici readonly mount, `xattr -cr` kaldirildi, `codesign --verify` denemesi.
- Opsiyonel Ed25519 imza kancasi (`HYDRO_UPDATE_PUBKEY`, `HYDRO_REQUIRE_SIGNATURE`).
- SQLite: RLock + `check_same_thread=False`, `busy_timeout`, UTC, `0700/0600`, user_version migration.
- Otomatik kayit timer'i hata halinde yeniden kuruluyor; `updated_at` korunuyor.
- PDF: XML escaping, A4/Unicode font, atomik yazma; Excel: formül notrleme, tipli hucre.

### UI

- Rapor cokmesi (`self.pressure_bar`) giderildi; tum uretim ve export `try` icinde.
- Bayat katsayi (`STALE`) canli kararda `BASARILI` uretmiyor.
- Mod degisiminde eski katsayi degeri temizleniyor; provenance karismiyor.
- Test bazli karar modeli: hava ve basinc kararlari birbirini silmiyor.
- Canli sonuc, girdi imzasiyla bir kez otomatik kaydediliyor (debounce + dedupe).
- Banner ve ust durum seridi karar durumundan turetiliyor.
- `nan/inf` ve alan bazli aralik dogrulamasi; tek `FIELD_CHECK_DEFINITIONS` kaynagi.
- 10.1 ortam hava sicakligi ayri alan; su sicakligi A/B icin korunuyor.
- Canli yenileme reentrancy guard + programmatic trace atlama; oturum kaydi 500 ms debounce.
- Gercek `DownloadManager()` instance'i; `SessionManager` public API'leri (`_db` erisimi kaldirildi).
- Wizard dogru sekmelere gidiyor; `DOGRULANAMADI`/`STALE` gecisi engelliyor.
- Download dialog thread-safe queue + `after`; instance kontrolu; kapatma/iptal ayrimi.

### Paketleme / CI

- Windows matrisindeki bash sozdizimi hatasi giderildi; Linux Xvfb, Windows/macOS ayri adim.
- `.zip` artefakti + cift checksum (`<stem>.sha256.txt`, `<<artifact>.sha256.txt`).
- `New-ReleaseArchive` gercekten cagriliyor; runtime hook iki build yolunda da kullaniliyor.
- Spec surumu `app_metadata.py`'den; `build_dmg.sh` sed yamalama kaldirildi.
- Tag ↔ `APP_VERSION` kapisi, job bazli izinler, concurrency, timeout.
- ruff/mypy yapilandirmasi; domain mypy bloklayici; surum pinleri.
- README/CHANGELOG/docs test sayisi ve surum senkronu.

## 3. Mühendislik Onayi Gerektirenler

Bu maddeler bilincli olarak veri/karar degistirmeden birakildi:

1. **B kaynagi:** Otomatik `beta - alpha`, kurum ici tablo ve GAIL tablosu arasinda
   %26–45 fark var. Hangisinin resmi oldugu belirlenmeli; UI'de karsilastirma ve
   uyari altyapisi hazir.
2. **7 °C / 90–98 bar A anomalisi:** Dokuz hucrede ~%4 sapma. Test ve denetim
   hazir; resmi duzeltme veri sahibinden gelmeli.
3. **Kod imzalama/notarization:** Anahtarlar ve sertifikalar yok. Imza dogrulama
   kancasi hazir; `HYDRO_REQUIRE_SIGNATURE=1` icin Ed25519 public key ve
   `<asset>.sig` yayini gerekli.
4. **A birimi:** Sartnamede `1/K` ve `1/bar` celiskisi. Kod `1e-6 / bar` olarak
   normalize ediyor; yazili kurum onayi bekliyor.

## 4. Kalan Riskler

- Windows build ve PowerShell updater bu makinede calistirilamadi; statik olarak
  dogrulandi. Gercek Windows runner'da smoke test gerekli.
- macOS DMG olusturma/imzalama bu ortamda anahtar olmadigi icin ad-hoc kalabilir.
- Tam paket mypy hala bilgilendirici (116 hata, agirlikli `ui/app.py` snapshot
  tipleri); domain bloklayici ve temiz.
- Updater imza kancasi varsayilan kapali; guvenlik tam olarak anahtar yayinlandiginda saglanir.
- Graphify haritasi `_pyinstaller_hook.py` disinda tum kaynaklari testlerle eslestiriyor.

## 5. Yeniden Uretim

```bash
cd HYDRO
python3 -m unittest discover -s tests -p "test_*.py"
python3 -m unittest discover -s tests -p "test_e2e_workflow.py" -v
python3 -m coverage run -m unittest discover -s tests -p "test_*.py"
python3 -m coverage report
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy hidrostatik_test/domain/
python3 skills/graphify/scripts/graphify.py build
python3 tools/generate_codebase_map.py
```
