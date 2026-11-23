# Changelog

## 1.10.0 - 2026-11-23

### Added

- **Şartname 12, 14.1–14.3, 15, 16 ve 17 Saha Operasyon Modelleri (`hidrostatik_test/domain/`, `OperationsPanel`, `TimeSeriesPanel`, `TimeSeriesChart`)**:
  - Ardışık 4 saatlik pencereler ve 24 saatlik termal dengeleme modeli (`evaluate_time_series`), %95 SMYS sonrası %0,2 ilave su durdurma ve 2 saatlik basınç tutma kontrolü (`pressurization_monitor.py`), basınç düşürme/boşaltma kontrolleri (`post_test_operations.py`) ve `Form 018` / `021` / `023` çift yönlü senkronizasyonu eklendi.
- **Segment Bazlı SMYS, Gerçek 3D Kot Profili & Masaüstü Snapshot İçe Aktarma (`PipeSection.smys_mpa`, `SiteSurveyPanel`, `RevisionConflictModal`)**:
  - Segment başına malzeme kalitesi/SMYS tanımlama, gerçek `profile_points[]` ve `equipment[]` sahne verisi, masaüstü JSON snapshot içe aktarma ve `409 revision_conflict` satır bazlı fark çözümleme modalı eklendi.
- **Makine Doğrulanabilir API Sözleşmesi & Rapor Ham OCR Eki (`webapp/docs/openapi.json`, `dump_openapi.py`, `check:api`, `ReportsPage.tsx`)**:
  - `87` yol / `101` HTTP operasyonluk `openapi.json` sözleşmesi, CI denetimi ve TXT/PDF/XLSX raporlarına (`OCR_Ham_Metin` Excel formül enjeksiyon korumalı) `include_raw_ocr` eki eklendi.
- **Alembic Şema Göçü (`0002` → `0003`), DB Yönetimi & Docker Yönetici Token Arayüzü (`DatabaseAdminPanel.tsx`, `X-Hydro-Admin-Token`)**:
  - Rollback güvenli `restore_db_backup`, `db_stats`, çöp kutusu geri yükleme ve Docker (`0.0.0.0`) ortamında `sessionStorage` tabanlı `X-Hydro-Admin-Token` desteği eklendi.

### Fixed & Hardened

- **Form Eşzamanlılık Koruması & İstek Sınırları (`sessions.py`, `dossier.py`, `schemas.py`, `rate_limit.py`, `config.py`)**:
  - `PUT /sessions/{id}/forms/{form_code}` uç noktasına `ETag` / `If-Match` revizyon kontrolü ve `409 revision_conflict` kurtarma akışı, yazma modellerine `StrictWriteModel` (`extra="forbid"`), liste üst sınırları, workspace bazlı hız sınırları ve fail-closed `HYDRO_AUTH_MODE` doğrulaması eklendi.
- **Çevrimdışı Düşme, Kota & OCR Yoklama Yaşam Döngüsü (`queries.ts`, `useAppStore.ts`, `OcrPage.tsx`, `ocrApi.ts`)**:
  - Tekil ağ okuma hatalarının uygulamayı kalıcı `demo` moduna alması engellendi; çevrimdışı kayıtlarda açık uyarı + `pendingServerSync` + `QuotaExceededError` yakalama ve `OcrPage` ayrılışında sunucu işini koruyarak istemci yoklamasını durdurma eklendi.
- **Akışlı Yüklemeler, Diskten Proje Arşivi & Canlı DB Restore Bariyeri (`security.py`, `project_archive.py`, `db.py`, `main.py`, `reports.py`, `run_web.py`)**:
  - Yüklemeler `stream_upload_to_tempfile` ile diske akışlandı; JSON gövde boyutu `32 MB` ile sınırlandı; eski export dosyaları 24 saat TTL ile temizlenir hale getirildi; proje arşivleri geçici `.zip` dosyası üzerinden akışlandı; canlı DB değişimi sırasında `503 db_restoring` (`Retry-After: 2`) bariyeri ve SQLite'ta `HYDRO_WEB_WORKERS=1` koruması eklendi.
- **OCR / PDF / CAD Doğruluğu & CI Kapsam Kapısı (`report_ocr.py`, `dossier.py`, `plan_profile.py`, `webapp/Dockerfile`, `.github/workflows/test.yml`)**:
  - PDF satır gruplama, noktalı ondalık ayrıştırma, CAD dış çap okuma ve BOTAŞ form bulgu kontrolleri iyileştirildi; Docker imajına `tesseract-ocr-tur/eng` eklendi; CI web pytest işine `--fail-under=80` kapsam kapısı eklendi.

## 1.9.1 - 2026-11-18

### Added

- **Süreç-içi Windows 10/11 WinRT OCR & PDF Motoru (`hidrostatik_test/services/report_ocr.py`, `requirements-ocr.txt`)**:
  - Harici `tesseract.exe` alt süreci başlatmadan çalışan Windows 10/11 `Windows.Media.Ocr` motoru (`tr-TR` öncelikli dil seçimi, `4096 px` güvenli ölçekleme ve çok sütunlu BOTAŞ form tablo satır eşlemesi) ile yerleşik `Windows.Data.Pdf` sayfa görüntüleme yedeği eklendi (`winrt-*~=3.2.1.0; sys_platform == "win32"`).
- **Yeni Program İkonu & Marka Sistemi (`tools/generate_icons.py`, `assets/icons/*`, `webapp/frontend/public/*`, `HydroLogo.tsx`)**:
  - Boru kesiti, hidrostatik su dalgası ve manometre temalı ikon seti (`.icns`, `.ico`, `favicon.svg`, `apple-touch-icon.png`, PWA `site.webmanifest`) masaüstü ve web sürümlerine entegre edildi.
- **BOTAŞ Form Ağacı Filtreleri, Yapışkan Tablolar & Excel TSV Yapıştırma (`Sidebar.tsx`, `DecisionStrip.tsx`, `RightPanel.tsx`, `FormBodyEditor.tsx`, `AcceptanceFormEditor.tsx`, `MonitoringFormEditor.tsx`, `pasteUtils.ts`)**:
  - Sol menüye `Tümü | Bulgulu | Eksik` filtre sekmeleri, üst karar şeridine `Formlar · Dolu/11` rozeti ve sağ panele `BOTAŞ Form Dosyası` ilerleme kartı eklendi.
  - Geniş form tablolarına sabit başlık/ilk sütun, `@container` düzeni, klavye kaydırma erişilebilirliği ve Excel/Sheets'ten (`TSV`) çoklu hücre/satır yapıştırma desteği eklendi.
- **Dashboard 3 Adımlı İş Akışı & Modüler Proje Modalları (`DashboardPage.tsx`, `ProjectsPage.tsx`, `PlanProfileScanModal.tsx`, `SectionFormsModal.tsx`)**:
  - `Dashboard` üzerinde adım çubuğu eklendi; `ProjectsPage.tsx` bileşenleri ayrıştırıldı.
- **Sürüm Yenilikleri Dokümanı (`WHATS_NEW.md`)**:
  - Hem GitHub Release sayfasında hem uygulama içi Güncelleme Yöneticisi (`UpdateManagerModal`) penceresinde doğrudan görüntülenecek Türkçe sürüm yenilikleri belgesi oluşturuldu.

### Changed

- **Kurumsal Windows Başlatıcı & Paketleme (`desktop_launcher.py`, `HydroWeb.spec`, `build_web_exe.ps1`, `build_exe.ps1`, `installer/hydro_web.iss`)**:
  - Varsayılan port aralığı `18790–18829` olarak güncellendi, başlatıcı penceresine **Küçült** düğmesi ve kapanış onay penceresi eklendi.
  - `build_web_exe.ps1` içinde harici taşınabilir `tesseract.exe` paketlemesi varsayılan olarak kapatıldı (isteğe bağlı `-BundleTesseract`), böylece harici `.exe` alt süreç tetiklemeleri azaltıldı ve Inno Setup'a `PrivilegesRequiredOverridesAllowed=dialog commandline` eklendi.
- **Erişilebilir Yerel `<dialog>` Pencereler & Form Koruması (`Dialog.tsx`, `Sidebar.tsx`, `SectionFormPage.tsx`, `styles.css`)**:
  - Modallar ve mobil çekmece `.showModal()` / `closedby="any"` ve Safari geri dönüşüyle yerel `<dialog>` üzerine taşındı; form sayfalarına kaydedilmemiş değişiklik onayı ve yükleme iskeleti eklendi.
- **Birleşik Release Notları (`.github/workflows/release.yml`)**:
  - `Create unified release notes` adımı `WHATS_NEW.md` içeriğini doğrudan `unified-notes.md` gövdesine yerleştirip sürüm eki olarak da ekleyecek şekilde güncellendi.

### Fixed

- **Kurumsal Ortamlarda `"Sunucuya ulaşılamadı"` & OCR Tanı Hatası (`OcrPage.tsx`, `StatusPanel.tsx`, `ocrApi.ts`, `ocr.py`, `db.py`)**:
  - `StatusPanel` bağlantı/zaman aşımı/HTTP hatalarını (`StatusErrorDetail`, `role="alert"`) açıkça ayıracak şekilde iyileştirildi ve sunucuya ulaşılamadığında sessizce sahte `DEMO_RESULT` gösterilmesi kaldırıldı.
  - Başlatıcı tarafında `HTTP_PROXY` atlatmalı `127.0.0.1` + `instance_id` doğrulaması, `SetErrorMode`, `stdin=os.devnull`, `SO_EXCLUSIVEADDRUSE` ve SQLite `WAL -> DELETE` yedeklemesi sağlandı.

### Security & Reliability

- **Zaman Aşımlı & Önbellekli OCR Yoklaması (`report_ocr.py`, `/api/ocr/status`)**:
  - `_probe_tesseract` alt süreç çağrıları `timeout=4.0`, `stdin=DEVNULL`, `CREATE_NO_WINDOW` ve TTL önbelleği ile korundu; `pypdfium2` yerel DLL hatalarında `OSError` yakalanarak süreç içi `Windows.Data.Pdf` / `Quartz` motoruna güvenli geçiş sağlandı.
  - `HydroWeb --self-test` hem `pypdfium2`/`Windows.Data.Pdf` rasterizer hem de WinRT modül yükleme ve kurulum sonrası duman testini doğrular hale getirildi.

## 1.9.0 - 2026-11-18

- **HYDRO Web Güncelleme Yöneticisi (`WebUpdateManager` & `/api/update/*`)**:
  - GitHub Releases (`SLedgehammer-dev12/HYDRO`) üzerinden `HydroWeb-v*-macos-arm64.dmg` (macOS M1+),
    `HydroWeb-v*-windows-x64-setup.exe` ve `HydroWeb-v*-windows-x64-portable.zip` paketlerini
    denetleme, sürüm notlarını görüntüleme ve ilerleme takibiyle indirme.
  - Zorunlu SHA-256 ve **fail-closed** Ed25519 `.sig` imza doğrulaması; doğrulanmayan dosyaların
    anında reddedilip silinmesi.
  - Paketli `HydroWeb` çalıştırmalarında tek tıkla yerinde kurulum (macOS `.dmg` / Windows
    Inno Setup `.exe` & portable `.zip`) ve yeniden başlatma; `TopBar`, `Sidebar`, `SettingsPage`
    ve `UpdateManagerModal` arayüzü.
- **BOTAŞ Test Bölümü Formları Ağacı & Sıralı Form Denetim Sayfaları (`Seçenek 1`)**:
  - Sol menüde (`Sidebar`) aktif **Proje & Test Bölümü** seçici kartı, 11 zorunlu form
    (`015`..`023`, `KUR-001`, `KUR-002`) ve katlanabilir 5 ek form (`EK-014`, `EK-SPL`,
    `001-027`, `EK-KRT`, `EK-KLP`) için canlı durum göstergeli gezinme ağacı.
  - `#/forms/{form_code}` rotasında (`SectionFormPage` & `FormBodyEditor`) resmî `BOT-FRM`
    başlık, imza, notlar ve çok satırlı tablo düzeni (`rows`, `pig_runs`, `drying`, `findings`),
    satır içi düzenleme (`PUT /api/sessions/{session_id}/forms/{form_code}`) ve form içinden tekil
    doküman OCR tarama (`POST /api/sessions/{session_id}/forms/{form_code}/scan`).
  - `020` (**Hava İçerik Testi Kabul**) ve `022` (**Basınç Testi Kabul**) formlarında isteğe bağlı
    **"Detay Hesaplamaları Göster"** bandı ile mevcut `Hava İçerik Testi` ve `Basınç Değişim Testi`
    hesaplama modüllerinin form içi açılır/kapanır entegrasyonu (`#/air` ve `#/pressure` doğrudan
    rotaları korundu).
  - `Projeler & Kesitler` sayfasında her test bölümü için bulgu özet sayacı, anahtar metrikler ve
    ilk bulgulu forma tek tıkla geçiş desteği.

## 1.8.1 - 2026-11-17

- **Taranmis PDF OCR Rasterizer & Paketli Tesseract Cozumu**:
  - `requirements-ocr.txt` icine Apache-2.0/BSD-3-Clause lisansli `pypdfium2>=4,<6` eklendi;
    `PyMuPDF`/`pdf2image` kurulu olmayan paketli dagitimlarda taranmis (metin katmani olmayan)
    PDF dosyalari artik dogrudan sayfalar halinde goruntuye donusturulup OCR ile okunuyor.
  - macOS uzerinde yerel `Quartz` (`CGPDFDocument`) yedek PDF rasterizer eklendi ve hem `report_ocr`
    hem dondurulmus CAD pafta (`ocr_pdf_page_rotated` / `plan_profile`) akisina baglandi.
  - Windows `HydroWeb` paketine taşınabilir Tesseract + `tur.traineddata` / `eng.traineddata`
    otomatik gomuluyor ve `_resolve_tesseract_cmd` paket icindeki binary/tessdata'yi otomatik buluyor.
  - `HydroWeb --self-test` artik gercek taranmis (yalnizca goruntu) PDF OCR dogrulamasini da iceriyor;
    klasik masaustu dagitimlarina da `requirements-ocr.txt` ve `pypdfium2` eklendi.

## 1.8.0 - 2026-11-17

- **OCR Dosya & Proje Eşleme + Otomatik Form/Hesap Hattı (`DOSSIER_SCHEMA_VERSION = 3`)**:
  - Çoklu BOTAŞ test dosyalarının, Hizan mühendislik hesap sayfalarının, `.xlsx`/`.xls`
    raporlarının ve tekil test raporlarının doğrudan proje/bölüm bazlı kaydı (`commit-dossier`).
  - Mevcut projelerde bulanık ad eşlemesi (`>= %70`), KP aralığı (`±5 m`) bazlı kesit eşlemesi,
    eşleşme yoksa otomatik yeni proje + test bölümleri + 11 zorunlu `BOT-FRM` form slotu oluşturma.
  - Kümülatif hesaplama (`profile`, `air`, `pressure`, `pig`), 11 operasyonel kontrol ve katı
    şartname sınırları (`Vpa < 1.06 * Vp`, `PL = 0.30 bar`, `%0.2` basınçlandırma sapması, `24.0 saat`).
  - Demo/örnek verilerin çevrimiçi boş oturumlara sızmasını engelleyen izole başlangıç (`createEmptyInputs`).
- **HYDRO Web Bağımsız Masaüstü Paketleme ve Dağıtım (macOS M1+ & Windows)**:
  - `webapp/desktop_launcher.py` ve `HydroWeb.spec`: gömülü FastAPI + derlenmiş React arayüzünü yerel
    olarak başlatıp varsayılan tarayıcıda açan, durum/durdurma kontrollü bağımsız masaüstü paketi.
  - macOS Apple Silicon (`arm64`, M1/M2/M3/M4+) için `build_web_dmg.sh` (`HydroWeb-v1.8.0-macos-arm64.dmg`).
  - Windows x64 için Inno Setup kurulum sihirbazı (`installer/hydro_web.iss`,
    `HydroWeb-v1.8.0-windows-x64-setup.exe`) ve taşınabilir `.zip` (`build_web_exe.ps1`).
  - `--self-test` canlı ikili dosya doğrulama kapısı, Ed25519 imza ve GitHub Actions `release.yml` entegrasyonu.
- **Kapsamli denetim remedasyonu (audit remediation)**:
  - Domain: negatif B kabulu, `nan/inf` dogrulamasi, tam `%6` sinirinda FAIL,
    termal denge icin ardışık 4 saatlik pencereler, tek tarafli `%0.2` kontrolu,
    bicubic ekstrapolasyonun kapatilmasi.
  - Veri: BOTAŞ = kurum ici workbook semantigi netlestirildi; olu
    `botas_reference_table_v1.*` dosyalari kaldirildi; A/B tablosu icin
    monotonluk/sureklilik denetimi ve 7 °C anomalisini yakalayan test eklendi.
  - Servisler: `DownloadManager` resume tek thread, katı artefakt/checksum
    sozlesmesi, guvenli zip cikarma, yedek + atomik kurulum + rollback + log,
    SQLite thread guvenligi ve UTC zaman damgalari, PDF/Excel escaping ve
    atomik yazma.
  - UI: rapor cokmesi giderildi; bayat katsayi kapisi, mod provenance temizligi,
    test bazli karar modeli, canli sonuc kaydi, banner durumu, alan araligi
    dogrulamasi, tek checklist kaynagi, ayri 10.1 ortam sicakligi alani,
    yenileme firsatlarinin azaltilmasi, gercek `DownloadManager` instance'i.
  - Paketleme/CI: `.zip` + cift checksum sozlesmesi, runtime hook, surum tek
    kaynagi, tag↔surum kapisi, Windows matrisi duzeltmesi, Xvfb'li release
    testi, ruff/mypy yapilandirmasi.
- **Domain: A/B fizik modeli**
  - B artik hacimsel olarak hesaplaniyor: varsayilan `B = beta - 3*alpha`;
    lineer ve sicakliga bagli `3*alpha(T)` opsiyonel.
  - B kaynagi secilebilir: kurum ici tablo (varsayilan), GAIL, otomatik.
  - A'nin `1/bar` ve formülde `micro/bar` oldugu boyut analiziyle dogrulandi
    (`docs/spec/ab_methods_and_units.md`).
- **Veri: A anomalisi onarimi**
  - 7 °C / 81-100 bar A anomalisi ham CSV degistirilmeden calisma zamaninda
    onariliyor (7/90: 45.515 -> 47.115); `repaired` / `repair_note` provenance.
- **Guvenlik: guncelleme imzasi varsayilan acik**
  - Ed25519 detached imza (`<artifact>.sig`) fail-closed zorunlu; public key
    `app_metadata` icinde gomulu, ozel anahtar repo disinda.
  - `tools/update_signing.py` (generate/sign/verify/fingerprint); CI secret'i
    `HYDRO_UPDATE_PRIVATE_KEY`; imzasiz/bozuk paket kurulmuyor.
- **Dokumantasyon**: A/B yontem ve birim arastirmasi, imza runbook'u,
  remediation raporu ve guncel test sayilari.
- **UI ergonomisi (Faz 2)**: her zaman gorunur karar seridi (kural + limit +
  marj), zorunlu alan kapisi ve gerekcesi, dinamik `*`, `Enter`/`Shift+Enter`/
  `Ctrl+Enter`/`F5`, hatali alana odak + kaydirma, panel bazli mousewheel,
  birim/terminoloji standardi (`°C`, `m³`, `m/s`, `10^-6/bar`), varsayilan
  gorunur akis listesi, kucuk ekranda otomatik detay paneli gizleme.
- **OCR rapor kontrolu**: PDF metin katmani + opsiyonel Tesseract, rapor semasi,
  alan/guven cikarimi, hesaplanan degerlerle toleransli karsilastirma, CLI
  (`tools/ocr_report.py`) ve `Rapor > Test Raporu Kontrol (OCR)...` arayuzu
  (ozet/alan/uyusmazlik/uyari sekmeleri, JSON kaydetme, insan onayi).
- **Web uygulamasi (Faz 3)**: FastAPI + SQLAlchemy backend, React 19 + Vite +
  Tailwind + Three.js frontend; 9 sekmeli arayuz, tam saha 3D sahnesi, oturum,
  rapor exportu, OCR yukleme/analiz ve Docker dagitimi. 87 backend testi,
  653 masaustu testi, 9/9 sekme smoke.
- **Graphify**: `skills/graphify/` ve `docs/codebase_map.md`
  (2.200+ dugum, 18.000+ kenar, web backend dahil).
- **Test ve E2E**: 550+ otomatik test; kaynak-only branch kapsami ~%79;
  geometri -> A/B -> hava + basinc -> karar -> txt/pdf/xlsx rapor -> SQLite
  oturum kaliciligi -> updater asset/imza sozlesmesi e2e akisi.

## 1.7.3 - 2026-06-08

- **Surum Tek Kaynaktan Yonetiliyor (Version Automation)**:
  - `HidrostatikTest.spec` artik surumu `hidrostatik_test/app_metadata.py` icindeki `APP_VERSION` degerinden okur; spec dosyasindaki sabit `1.7.0` kaldirildi.
  - `build_dmg.sh` spec dosyasini `sed` ile yamalamayi birakti; macOS `BUNDLE` icindeki `CFBundleShortVersionString` / `CFBundleVersion` degerleri ayni kaynaktan uretiliyor.
  - macOS icin `target_arch='universal2'` denemesi eklendi; evrensel olmayan Python'da yerel mimariye guvenli dusus yapiliyor.
- **Test ve CI Genisletmesi**:
  - Otomatik test paketi 291 teste cikarildi (domain, servis, veritabani ve UI akislari).
  - CI'a kaynak-only kapsam olcumu ve bloklayici domain mypy adimi eklendi.
  - Updater'a SHA-256 artefakt dogrulamasi eklendi.

## 1.7.2 - 2026-06-08

- **Refactor (davranis korunarak)**:
  - UI sabitleri `hidrostatik_test/ui/constants.py` altinda tek kaynakta toplandi.
  - A/B katsayi secim ve dogrulama mantigi `hidrostatik_test/domain/coefficient_manager.py` modulune tasindi.
  - Enum/string karsilastirmalarindaki tutarsizliklar ve birkac UI hatasi giderildi.
- Otomatik test paketi genisletilerek kapsam artirildi.

## 1.7.1 - 2026-06-08

- **PyInstaller Derleme Düzeltmeleri (Build & Packaging Fixes)**:
  - Windows `.exe`'de "Importing the numpy C-extensions failed" hatası giderildi.
  - macOS `.app`'in açılışta sessizce çökmesi engellendi.
  - `build_exe.ps1`'e `--collect-all numpy` ve `--collect-all scipy` parametreleri eklenerek C-extension modüllerinin paketlenmesi sağlandı.
  - `HidrostatikTest.spec`'e numpy/scipy hidden import'ları eklendi (`numpy.core._multiarray_umath`, `scipy.interpolate` vb.).
  - PyInstaller runtime hook (`_pyinstaller_hook.py`) oluşturuldu: Windows'ta `os.add_dll_directory()` ile DLL yolları, macOS'te `DYLD_LIBRARY_PATH` ile `.dylib` yolları ayarlanır.
  - Spec dosyasındaki versiyon `1.6.0` → `1.7.0` olarak güncellendi (önceden outdated'ti).
- **Import Esneklik İyileştirmeleri (Import Resilience)**:
  - `numpy`, `scipy`, `CoolProp` import'ları `try/except` bloklarına alındı. Eksik kütüphane durumunda uygulama çökmek yerine `table_v1` (bilinear) backend'i ile çalışmaya devam eder.
  - `bicubic` interpolasyon numpy/scipy yoksa otomatik olarak `bilinear` (saf Python) fallback'e düşer.
- **macOS İmzalama ve Hardened Runtime**:
  - `build_dmg.sh`'e ad-hoc code signing adımı eklendi (`codesign --deep --force --sign -`).
  - `runtime_entitlements.plist` oluşturuldu: `com.apple.security.cs.disable-library-validation`, `allow-unsigned-executable-memory`, `allow-dyld-environment-variables` exception'ları ile imzasız `.dylib` yüklenmesine izin verilir.
  - `Info.plist`'e `NSHighResolutionCapable`, `NSAppTransportSecurity` eklendi.

## 1.7.0 - 2026-06-08

- **Güncelleme Mekanizması Yeniden Tasarlandı (Update Manager Redesign)**:
  - `DownloadManager` servisi eklendi: chunked HTTP download, pause/resume, SHA-256 doğrulama, exponential backoff retry.
  - `DownloadDialog` UI widget eklendi: Toplevel progress bar, anlık hız/ETA gösterimi, duraklat/devam et/iptal kontrolleri.
  - Güncelleme akışı tarayıcı yönlendirme yerine uygulama içi indirme yöneticisi ile çalışacak şekilde yeniden tasarlandı.
  - macOS self-update desteği eklendi: DMG mount → kopyalama → xattr temizlik → yeni app açma.
- **Test ve Derleme Altyapısı**:
  - Windows ve macOS build doğrulama scriptleri eklendi (`tests/test_build_windows.ps1`, `tests/test_build_macos.sh`).
  - Release workflow'una build artifact boyut doğrulama adımı eklendi.
  - Otomatik test paketi 157 test ile korunmaya devam ediyor.

## 1.6.2 - 2026-06-06

- **Çalışma Zamanı Düzeltmeleri (Runtime Hotfixes)**:
  - macOS ve Linux sistemlerinde otomatik veya manuel güncelleme denetimi yapılırken powershell komut satırı aracının bulunmaması durumunda oluşan `FileNotFoundError` hatası giderildi (PowerShell yoksa düzgün bir şekilde hata yakalanıp atlanmaktadır).
  - Güncelleme denetimi hata geri bildirimi sırasında `Tkinter` callback'lerinde oluşan lambda değişken kapsamı hatası (`NameError: cannot access free variable 'exc'`) giderilerek arayüz kararlılığı artırıldı.
  - Bağımlılık paketleme spec'inde (`HidrostatikTest.spec`) ve betiklerinde (`build_exe.ps1`) `iapws` kütüphanesi hariç bırakılarak GPLv3 lisans uyumluluğu ve paketleme bütünlüğü sağlandı.

## 1.6.1 - 2026-06-02

- **Derleme Hata Düzeltmeleri (Hotfix)**:
  - PyInstaller excludes listesinden `scipy` kaldırıldı; böylece `WaterPropertyTableBackend` interpolasyon hesaplamasında kullanılan `scipy.interpolate` modülünün bulunamaması nedeniyle uygulamanın açılışta çökmesi kökünden engellendi.
  - PyInstaller excludes listesinden `openpyxl` kaldırıldı; böylece rapor dışa aktarma (Excel Export) adımında karşılaşılan Excel motoru yükleme hatası çözüme kavuşturuldu.
  - Windows (`.exe`) ve macOS (`.dmg`) paketleme spec ve betik dosyaları güncellenerek kararlı çalışma her iki platformda da garantiye alındı.

## 1.6.0 - 2026-06-01

- **Faz 4.1: İkinci Backend Doğrulama (IAPWS-95)**:
  - CoolProp dışı bağımsız IAPWS-95 su özellik hesaplama motoru geliştirici/development moduna özel olarak entegre edildi.
  - "Hesap" menüsü altına "Geliştirici Modu" menü seçeneği eklenerek bu modun aktif/deaktif edilebilmesi sağlandı.
  - IAPWS-95 seçildiğinde GPLv3 lisans uyumluluk uyarıları içeren görsel uyarı bandı dinamik hale getirildi.
  - Bağımlılıklar `requirements-dev.txt` içerisine izole edilerek standart dağıtımların lisans kapsamı dışında kalması sağlandı.
- **Faz 4.2: Çoklu Oturum Yönetimi**:
  - `TestSession` veri modeli oluşturularak tüm form elemanları, aktif checklist adımları, wizard ilerlemesi ve zaman serisi verileri oturum snapshot'ı olarak kaydedilebilir hale getirildi.
  - Arayüze "Yeni" oturum başlatma, "Kaydet" ve oturumlar arası hızlı geçiş sağlayan dinamik combobox araç çubuğu eklendi.
  - Kullanıcı girdilerinde ve form değişikliklerinde otomatik oturum kaydetme (auto-save) tetikleyicileri entegre edildi.
- **Faz 4.3: SQLite Veritabanı Entegrasyonu**:
  - `DatabaseManager` ile WAL modu ve yabancı anahtar (foreign key) kısıtlamalarını içeren SQLite tabanlı kalıcı veri katmanı eklendi.
  - JSON ve SQLite oturum kayıtları arasında birebir veri modeli eşitliği sağlandı.
  - Menüye "Dosya -> Oturum Geçmişi..." eklenerek kayıtlı oturumların Treeview üzerinden izlenmesi, silinmesi ve yüklenebilmesi sağlandı.
  - Oturum istatistikleri penceresi ile veritabanındaki test durumları, tipleri ve kayıt sayıları görsel özet rapor olarak sunuldu.
- **Faz 4.4: CI/CD Pipeline ve Çoklu Platform Derleme**:
  - Ruff (kod formatlama) ve MyPy (statik tip kontrolü) test otomasyonu Github Actions entegrasyonu tamamlandı.
  - Windows (`.exe`) ve macOS (`.dmg`) için otomatik çoklu platform derleme süreçleri kuruldu.
  - Otomatik test paketi 157 teste çıkarılarak kararlı çalışma garanti altına alındı.

## 1.5.9 - 2026-04-06

- Arayuz uc bolmeli ve yeniden boyutlandirilabilir hale getirildi; girdi paneli sola, aktif test sekmeleri ortaya, detay raporu saga tasindi.
- A/B secim akisi `Otomatik / Tablo / Manuel` olarak sadelelestirildi; tablo modunda `BOTAS referans tablosu` ile `GAIL referans tablosu` ayri secenekler olarak sunuluyor, su backend secimi ust menuden yonetiliyor.
- Test bolumu profilinde API 5L PSL2 malzeme secimi, otomatik SMYS atamasi, canli basinc penceresi, kot semasi ve `%100 SMYS` span kontrolu eklendi.
- NGTL 5007 tek kesit limitleri (`20 km` ve `12.500 m3`) geometri ve basinc kontrolu icine alindi; asim durumlari canli uyari olarak gosteriliyor.
- Girdiler icin genel canli dogrulama sistemi eklendi; hatali veya eksik alanlar renkli olarak vurgulaniyor ve kullaniciya aciklayici etiketler gosteriliyor.
- Dinamik hesap akisi guclendirildi; ilgili girdiler degistiginde katsayilar, basinc kontrolu ve nihai karar karti otomatik yenileniyor.
- Otomatik test paketi 120 teste cikarildi.

## 1.5.8 - 2026-04-03

- Aktif sekme icin canli `Detay Raporu` paneli eklendi; katsayi kaynagi, kullanici girdileri ve karar hesabinda kullanilan ara terimler arayuzde gorunur hale getirildi.
- Manuel A/B modlarinda katsayinin kullanici tarafindan girildigi ve degerlendirmede hangi degerin kullanildigi artik acikca ayirt ediliyor.
- `Katsayi Durumu` paneline kisa kaynak rozetleri eklendi; `HESAP / REFERANS / MANUEL / YENILE` durumu tek bakista gorulebiliyor.
- A ve B alanlarinin yanina da ayni kaynak rozetleri tasindi; kullanici formdan ayrilmadan aktif katsayi kaynagini gorebiliyor.
- Hesap ve degerlendirme butonlari renkli ilerleme geri bildirimi aldi; hesap sirasinda sari, tamamlandiginda yesil, uyari/hata durumunda turuncu-kirmizi durum kisa sureyle gosteriliyor.
- Guncelleme paketi hedef klasoru secim ekranindaki `farkli klasor sec / mevcut klasorle devam et / iptal` akisi testle koruma altina alindi.

## 1.5.7 - 2026-04-03

- `A ve B Katsayisi.xlsx` kaynagindan uretilen kurum ici `A/B` kontrol tablosu uygulamaya eklendi.
- Hava ve basinc testlerinde mevcut hesaplanan katsayilar ile kontrol tablosu degerleri ayni ekranda karsilastirilabilir hale getirildi.
- Kontrol tablosu ozeti rapor ve oturum kaydina da eklendi; resmi tablo kapsami `T=1-25 degC`, `P=30-120 bar` olarak korunuyor.

## 1.5.6 - 2026-04-03

- Updater uygulama adimi `cmd + .cmd` yerine Unicode yol adlarina daha dayanikli `PowerShell + .ps1` akisina tasindi.
- Guncelleme script'i `utf-8-sig` ile yazilarak Turkce karakter iceren klasor adlarinda gorulen bozulma riski azaltildi.
- Dosya kopyalama `Copy-Item -LiteralPath` ile yapilacak sekilde degistirildi; `robocopy/cmd` tabanli karakter sorunu ortadan kaldirildi.
- Updater testleri Turkce karakterli yol senaryosu ile genisletildi; otomatik test paketi 76 teste cikarildi.

## 1.5.5 - 2026-04-03

- `Yan Paneli Gizle/Goster` kontrolu eklendi; operator isterse sag yardimci alan kapatilarak calisma alani genisletilebiliyor.
- `Bilgi Notlarini Goster/Gizle` kontrolu eklendi; varsayilan ekranda statik aciklama bloklari gizlenerek daha kompakt bir akisa gecildi.
- Sag panel yerlesimi ve sash konumu daha tutarli hale getirildi; kapanista gorulen gereksiz Tk callback gurultusu temizlendi.
- UI regresyon testleri yan panel ve bilgi notu gorunurluk kontrolleriyle genisletildi; otomatik test paketi 75 teste cikarildi.

## 1.5.4 - 2026-04-03

- Manuel guncelleme kontrolunde yeni surum bulundugunda kurulum akisi artik dogrudan teklif ediliyor; sadece acilista degil, kullanici talebinde de `indir/uygula` akisi basliyor.
- Guncelleme paketi hedef klasoru icin `farkli klasor sec / mevcut klasorle devam / iptal` secenekleri netlestirildi; onceki sessiz varsayilan davranis kaldirildi.
- Sag yardimci alan `Rehber / Durum / Kayit` sekmelerine ayrildi; uzun tek kolon nedeniyle olusan dikey yigilma azaltildi.
- Hava, basinc ve saha sekmeleri genis ekranlarda yatay alani daha iyi kullanacak sekilde iki kolonlu duzene yaklastirildi.
- UI ve updater testleri genisletildi; otomatik test paketi 73 teste cikarildi.

## 1.5.3 - 2026-04-02

- Arayuz kok seviyede ve sekme seviyesinde kaydirilabilir hale getirildi; buyuk ama dikey olarak uzun ekranlarda tasma davranisi azaltildi.
- `Boru Kesiti` bolumu sikistirildi; `Hat uzunlugu` ust satira alindi ve segment tablosu varsayilan olarak gizlendi.
- Ayrik `Uygulama / Guncelleme` paneli kaldirildi; guncelleme akisi menu uzerinden korunarak ana ekran sadeletirildi.
- `Canli Sema` paneli aktif sekme, segment geometri, checklist ilerlemesi, katsayi durumu ve pig hizina gore dinamik guncellenir hale getirildi.
- Guncelleme paketi icin kullanici secimli indirme klasoru ve kurulum onayi eklendi; updater bu klasoru dogrudan kullanir hale getirildi.
- UI ve updater regresyon testleri genisletildi; otomatik test paketi 71 teste cikarildi.

## 1.5.1 - 2026-03-31

- `pipe_catalog.py` icindeki ASME B36.10 katalogu, Wermac uzerindeki `part-a`...`part-k` tablolarina gore NPS `1/8`-`80` araliginda yeniden uretildi.
- Daha once eksik kalan buyuk cap aileleri (`48`, `52`, `56`, `60`, `64`, `68`, `72`, `76`, `80`) ve ara et kalinliklari dropdown seceneklerine eklendi.
- Schedule adi olmayan ama B36.10 tablosunda bulunan ara et kalinliklari UI'de `WT ... mm (B36.10)` biciminde secilebilir hale getirildi.
- Katalog testleri buyutulerek buyuk cap kapsamasi ve unlabeled wall-thickness satirlari otomatik olarak dogrulanir hale getirildi.
- Otomatik test paketi 42 teste cikarildi.

## 1.5.0 - 2026-03-31

- `A` ve `B` katsayilari icin `referans - hazir dogrulanmis nokta` secenegi eklendi.
- Hava testi ve basinc testi ekranlarina referans nokta acilir listeleri baglandi.
- Referans modunda secilen noktanin `A` degeri dogrudan, `B` degeri ise secili su beta referansi ve celik alpha ile olusturulur.
- Alan ipuclari, durum mesajlari ve rapor icerigi secilen referans noktasini gosterecek sekilde genisletildi.
- Basinc testi icin `A referans` akisi da otomatik test kapsamına alindi.
- Otomatik test paketi 41 teste cikarildi.

## 1.4.0 - 2026-03-31

- A katsayisi icin hava testi ve basinc testi ekranlarina `otomatik` ve `manuel` secenekleri eklendi.
- B katsayisi icin secim modeli checkbox yerine daha acik `otomatik` ve `manuel` secenegine donusturuldu.
- A ve B alanlarinin kilitli/duzenlenebilir davranisi secilen moda gore dinamik hale getirildi.
- Alan mesajlari ve aciklayici bilgi satirlari, secilen katsayi kaynagina gore guncellenecek sekilde zenginlestirildi.
- Rapor metnine A/B secenekleri de eklendi.
- UI regresyon testleri manuel A ve manuel B akislari ile genisletildi.
- Otomatik test paketi 38 teste cikarildi.

## 1.3.1 - 2026-03-30

- `4-NGTL 0-GN-P-002-5007 R4` sartnamesindeki hava icerik ve basinc testi veri giris tanimlari arayuze acikca yansitildi.
- Hava icerik testi icin `P = 1.0 bar` kosulu cekirdek seviyede dogrulanir hale getirildi.
- Basinc testinde `dT = Tilk - Tson` ve `Pa = Pilk - Pson` isaret tanimi UI ve rapora eklendi.
- `A` ve `B` katsayilari icin IAPWS-95 capraz kontrol noktalarini koruyan yeni cekirdek testleri eklendi.
- GitHub updater modulu, Python TLS zinciri hata verdiginde Windows PowerShell fallback'i kullanacak sekilde guclendirildi.
- `NGTL_5007_Validation.md` ile sartname, katsayi ve updater ariza notlari proje icine kaydedildi.
- Otomatik test paketi 36 teste cikarildi.

## 1.3.0 - 2026-03-30

- UI form temizleme ve karar karti sifirlama davranisi duzeltildi.
- `K` ve celik preset geri yukleme davranislari tutarli hale getirildi.
- Canli validasyon aktif sekmeye gore daraltildi.
- Rapor metni surum ve giris ozetleriyle genisletildi.
- `0 bar` su ozellik hesaplari cekirdek seviyede reddedildi.
- ASME B36.10 tabanli cap ve schedule secim listesi eklendi.
- Farkli et kalinliklarina sahip segmentli geometri modeli eklendi.
- Ust menu yapisi `Dosya`, `Rapor`, `Guncelleme`, `Hakkinda` olarak duzenlendi.
- GitHub Releases tabanli updater modulu eklendi.
- Acilista otomatik guncelleme kontrolu ve manuel guncelleme kontrolu eklendi.
- Windows `.exe` icin indir ve uygula akisi eklendi.
- Repo-ozel `hidrostatik-test-v*` release tag duzeni eklendi.
- Otomatik test paketi 33 teste cikarildi.
- Windows manifest, uygulama metadata'si ve release build scripti iyilestirildi.
- GitHub release'e uygun zip, checksum ve release note uretimi eklendi.
- Monorepo ve bagimsiz repo icin GitHub Actions workflow dosyalari eklendi.
