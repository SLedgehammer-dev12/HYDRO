# Audit Remediation Report

Tarih: 2026-11-15
Dal: `fix/audit-remediation`
Kapsam: `docs/analysis_report.md` bulgulari + `tasks/remediation.md`
Yontem: Graphify haritasi + paralel dosya-sahipligi iscileri + dogrulama dalgasi.

## 1. Sonuc Ozeti

| Alan | Durum | Kanit |
| --- | --- | --- |
| Domain fizigi | Tamam | 653 test, domain mypy temiz |
| Veri katmani | Tamam (veri duzeltmesi haric) | 12 + 10 test, anomali tespiti |
| Servisler / updater | Tamam | 113 hedefli test, guvenli cikarma + rollback |
| UI dogruluk | Tamam | 82 UI testi + 4 e2e |
| UI ergonomisi (Faz 2) | Tamam | 114 UI testi |
| OCR rapor kontrolu | Tamam (servis + UI) | 61 OCR testi |
| Paketleme / CI | Tamam | `.zip` sozlesmesi, tag↔surum kapisi |
| Dokumantasyon | Tamam | surum/test sayisi senkronu |
| Kod kalitesi | Tamam | ruff temiz, domain mypy temiz |
| E2E | Tamam | 5 senaryo |

**Dogrulama:**

- `python3 -m unittest discover -s tests -p "test_*.py"` → **653 test OK**
- `python3 -m coverage run -m unittest discover ...` → **%81** kaynak-only branch kapsami
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
- Ed25519 detached imza varsayilan olarak zorunlu (fail-closed); public key
  gomulu, ozel anahtar repo disinda, CI secret'i `HYDRO_UPDATE_PRIVATE_KEY`.
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

## 3. Cozulen Kararlar ve Kalan Onaylar

### Cozulenler

1. **B kaynagi:** Secilebilir hale getirildi; varsayilan **kurum ici A/B tablosu**.
   GAIL ve otomatik (`beta - 3*alpha`) ikincil kaynaklar. Her kaynak raporda
   provenance satiriyla gorunur; fark esikleri warn/confirm olarak isaretlenir.
2. **7 °C / 81–100 bar A anomalisi:** Ham CSV degistirilmeden calisma zamaninda
   ayni T satirinda lineer kopru ile onariliyor (7/90: 45.515 -> 47.115).
   `repaired` / `repair_note` alanlariyla izlenebilir; B etkilenmiyor.
3. **Kod imzalama:** Ed25519 detached imza (`<artifact>.sig`) varsayilan olarak
   **zorunlu (fail-closed)**. Public key `app_metadata` icinde gomulu; ozel
   anahtar repo disinda (`~/.config/hydro/update_signing_key.pem`, 0600).
   `tools/update_signing.py` ile uretim/imzalama/dogrulama; CI secret'i
   `HYDRO_UPDATE_PRIVATE_KEY`. Imzasiz/bozuk paket kurulmuyor.
4. **A birimi:** `docs/spec/ab_methods_and_units.md` boyut analiziyle A'nin
   `1/bar` ve formülde `micro/bar` oldugunu dogruladi; §13'teki `1/K` basim
   hatasi. Vp ve ΔP sayisal ornekleri kodla birebir.

### Kalan kurum onaylari

- B tablosunun resmi kaynagi ve olcum zinciri (0.5 °C belirsizlik ~0.5 bar;
  0.3 bar esiginden buyuk).
- Kurum ici tablonun kalici resmi revizyonu (runtime onarim yerine veri duzeltmesi).
- Notarization sertifikasi ve imza anahtarinin kurumsal yedegi/rotasyonu.

## 4. Kalan Riskler

- Windows build ve PowerShell updater bu makinede calistirilamadi; statik olarak
  dogrulandi. Gercek Windows runner'da smoke test gerekli.
- macOS DMG notarization kurumsal sertifika gerektiriyor; ad-hoc imza kalabilir.
- Ozel imza anahtari yalnizca bu makinede; `HYDRO_UPDATE_PRIVATE_KEY` secret'i
  eklenmezse release kasitli olarak durur. Sifreli yedek alinmali.
- Tam paket mypy hala bilgilendirici (agirlikli `ui/app.py` snapshot tipleri);
  domain bloklayici ve temiz.
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
