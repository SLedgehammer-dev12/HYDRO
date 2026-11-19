# HYDRO — Proje Durumu

> Tek kaynak özet. Ayrıntı için "Ayrıntılı notlar" bölümündeki dosyalara bakın.
>
> **Son güncelleme:** 2026-11-19
> **Dal:** `main` (`v1.9.1` — Güvenlik Sertleştirme, Tip Temizliği & Güvenilirlik Güncellemeleri)
> **Son commit:** `hidrostatik-test-v1.9.1` hazırlık & üretim sertleştirme (`v1.9.0` → `v1.9.1`)

---

## 1. Tek Bakışta

| Alan | Durum | Kanıt |
| --- | --- | --- |
| Masaüstü uygulaması | Çalışıyor, kararlı | 709 unittest PASS (`skipped=1`) |
| Web backend (FastAPI) | Çalışıyor | 210 pytest PASS (Alembic `0003`), 81 OpenAPI path / 94 operation, 48 dosyada `mypy` temiz |
| Web frontend (React 19) | Çalışıyor | `npm run lint` (0 hata, `jsx-a11y`), `npm test` (21 Vitest), `npm run typecheck` + `npm run build` + `check:bundle` PASS (`143,2 kB` gzip ilk yükleme JS), `verify-tabs.mjs` 12/12 PASS |
| Program İkon & Marka Sistemi | Hazır | Boru kesiti + su dalgası + manometre ikonu (`tools/generate_icons.py`, `assets/icons/*`, `webapp/frontend/public/*`, `<HydroLogo />`, PyInstaller/Inno Setup/Tkinter) |
| Web Güncelleme Yöneticisi | Çalışıyor | `/api/update/*`, SHA-256 + fail-closed Ed25519 `.sig` doğrulama, `UpdateManagerModal`, macOS `.dmg` / Win `.exe`/`.zip` kurulum |
| BOTAŞ Test Bölümü Formları | Çalışıyor | Seçenek 1 sol menü (`015`..`023`, `KUR-001`, `KUR-002` + 5 ek), `SectionFormPage`, `rows`/`pig_runs`/`findings`, tekil OCR, `020`/`022` gömülü hesaplama ve `023` (`BOT-FRM-CDB-001-024`) Şartname 16–17 çift yönlü entegrasyonu |
| Bağımsız Web paketleme | Hazır (`v1.9.1`) | `HydroWeb.spec`, `build_web_dmg.sh` (`arm64`, taranmış PDF `--self-test` PASS), `build_web_exe.ps1` (WinRT `Windows.Media.Ocr` + `Windows.Data.Pdf`) + `installer/hydro_web.iss` |
| Kurumsal Windows OCR/PDF | Çalışıyor | Süreç-içi `Windows.Media.Ocr` + `Windows.Data.Pdf`, Proxy-bypass `127.0.0.1` + `instance_id` doğrulama, SQLite `WAL → DELETE` fallback |
| Domain parity | Masaüstü ile aynı kaynak | `hidrostatik_test.domain` doğrudan import edilir |
| Proje / Test Bölümü (Section) DB | Çalışıyor | `projects` + `sessions.project_id` + `inputs.section_meta` |
| KP sürekliliği + Segment denetimi | Tamamlandı | `lib/kp.ts`, Geometri & Saha sayfası |
| Plan-Profil PDF / CAD tarama | Çalışıyor (PDF + DWG/DXF) | `POST /api/projects/plan-profile/scan` |
| OCR rapor kontrolü | Çalışıyor (Vision + Excel) | `ocrmac`, `.xlsx`/`.xls`, `commit-dossier` proje/bölüm kaydı, tekil onay/uygulama |
| Docker / dağıtım | Hazır | `webapp/Dockerfile`, `docker-compose.yml`, `.github/workflows/release.yml` |

**Durum:** MVP, performans/güvenlik ön sertleştirmesi ve Alembic şema göçü (`0003`) tamam. Kalan işler kurumsal Auth/OIDC/RBAC kararı, `psycopg` Postgres runtime testi ve kurum onayı bekleyen veri işleridir.

---

## 2. Tamamlananlar

### 2.1 Masaüstü uygulaması

- Domain fizik modeli: negatif B kabulü, `nan/inf` doğrulaması, tam `%6` sınırında FAIL,
  ardışık 4 saatlik termal denge pencereleri, tek taraflı `%0.2` ilave su kontrolü,
  bicubic ekstrapolasyonun kapatılması.
- A/B modeli: `B = β − 3α` hacimsel model, seçilebilir B kaynağı (kurum içi tablo varsayılan,
  GAIL, otomatik), A biriminin `1/bar` olduğunun boyut analiziyle doğrulanması.
- Veri katmanı: BOTAŞ kurum içi workbook semantiği, A/B tablosu monotonluk/süreklilik denetimi,
  7 °C / 81–100 bar A anomalisinin çalışma zamanında lineer köprüyle onarımı (provenance ile).
- Servisler: `DownloadManager` resume, katı artefakt/checksum sözleşmesi, güvenli zip çıkarma,
  yedek + atomik kurulum + rollback, SQLite thread güvenliği, PDF/Excel escaping.
- Güncelleme: Ed25519 imza fail-closed, `HYDRO_UPDATE_PRIVATE_KEY` CI secret'ı.
- UI ergonomisi: her zaman görünür karar şeridi, zorunlu alan kapısı, klavye kısayolları,
  panel bazlı kaydırma, birim/terminoloji standardı, küçük ekran davranışı.
- OCR rapor kontrolü: PDF metin katmanı + Tesseract/macOS Vision, alan/uyuşmazlık, insan onayı,
  JSON çıktı, CLI (`tools/ocr_report.py`) ve UI.
- **OCR kalibrasyonu (gerçek formlar):** 9 resmî `.xls` şablonu ve 74 sayfalık ERCİŞ raporu
  Vision ile okundu. Bbox tabanlı satır/kolon eşleme, bulanık etiket eşleşmesi, formül satırı
  ayıklama, hava/basınç bölüm ayrımı. Ayrıntı: `docs/spec/report_forms.md`.
- Paketleme/CI: `.zip` + çift checksum, tag↔sürüm kapısı, ruff/mypy yapılandırması.

### 2.2 Web uygulaması

- Mimari doküman seti: `architecture.md`, `parity_matrix.md`, `api_contract.md`, `ux_plan.md`, `decisions.md`.
- FastAPI backend: oturum/snapshot/audit/hesap/rapor/OCR/proje uçları.
- React 19 + Vite + Tailwind 4 + TanStack Query + Zustand + Recharts + Three.js.
- 9 görünür sekme (legacy `field` → `geometry`, `coefficient_detail` → `coefficients` yönlendirmesi):

  `Dashboard · Projeler & Kesitler · Geometri & Saha · Hava İçerik · Basınç Değişim · Raporlar · OCR · Ayarlar · Katsayılar`

- Birleştirmeler:
  - **Geometri & Saha**: eski Profil/Saha sekmesi + tam 3D sahne tek sayfada.
  - **Katsayılar**: A/B hazırlama + üç kaynak + backend karşılaştırması + katsayı detayı, **son sekme**.
  - **Tek 3D saha görünümü**: önizleme/tam sahne ayrımı kaldırıldı.
- Proje & Test Bölümü (Section) katmanı: CRUD, sıralama, aç/kopyala/sil, `section_count`.
- KP kalıcılığı: `start_kp` / `end_kp` saklanır; `K+MMM` formatı, `0+000` / `12.5 km` / `12000 m` kabul,
  `location` alanından otomatik KP çıkarımı.
- KP süreklilik denetimi: ardışık test bölümlerinde önceki bitiş ↔ sonraki başlangıç,
  bindirme/boşluk uyarısı, `Σ Section = boru hattı KP aralığı` kontrolü.
- **Segment denetimi**: `Σ Segment = Section uzunluğu`, istasyon zinciri, OD/WT/uzunluk geçerliliği,
  satır bazlı KP aralığı ve OK/UYARI/HATA rozetleri, segment başına iç hacim.
- Plan-Profil PDF tarama: metin katmanı/OCR ile taslak test bölümleri, düzenlenebilir tablo, toplu kaydet.
- 3D sahne: zemin, segmentler, ekipman, pig, akış, kesit, kamera presetleri, `SceneHtml` DOM etiket katmanı.
- Sekme başlıkları ve ana aksiyon butonları büyütüldü (25/30 px başlık, `btn-lg`).
- **Web Güncelleme Yöneticisi**: `webapp/backend/app/services/web_updater.py` (`WEB_UPDATE_MANAGER`) ve `/api/update/status|check|download|download/file|apply` uçları ile GitHub Releases (`SLedgehammer-dev12/HYDRO`) üzerinden sürüm denetimi, SHA-256 + fail-closed Ed25519 `.sig` doğrulaması, doğrulanmış paket indirme ve paketli `HydroWeb` (.dmg / Inno Setup `.exe` / portable `.zip`) üzerinde tek tıkla yerinde kurulum/yeniden başlatma; `TopBar`, `Sidebar`, `SettingsPage` ve `UpdateManagerModal` arayüzü.
- **Test Bölümü Formları Ağacı & Sıralı Form Denetim Sayfaları (`Seçenek 1`)**:
  - Sol menüde (`Sidebar.tsx`) aktif proje & test bölümü hızlı seçici kartı, **`Test Bölümü Formları (Dolu/11)`** (`015`..`023`, `KUR-001`, `KUR-002`) ve **`Ek Raporlar (Dolu/5)`** (`EK-014`, `EK-SPL`, `001-027`, `EK-KRT`, `EK-KLP`) durum rozetli ağaç listesi.
  - `#/forms/{form_code}` rotasında (`SectionFormPage.tsx` + `FormBodyEditor.tsx`) resmî `BOT-FRM` başlık/imza/tablo düzeni, satır içi düzenleme (`PUT /api/sessions/{id}/forms/{code}`), tekil form OCR tarama (`POST /api/sessions/{id}/forms/{code}/scan`), `form_details.py` ile yapılandırılmış `rows`/`pig_runs`/`drying`/`findings` kalıcılığı ve `4-NGTL 0-GN-P-002-5007 R4` şartname bulguları.
  - `020` (`air_acceptance`), `022` (`pressure_acceptance`) ve `023` (`dewatering` / `BOT-FRM-CDB-001-024`) formlarında isteğe bağlı açılıp kapanan **"Detay Hesaplamaları Göster"** bandı ile mevcut `<AirPage embedded />`, `<PressurePage embedded />` ve Şartname 16–17 `<OperationsPanel />` modülleri satır içi gösterilir; `023` formundaki Şartname 16–17 verileri ile oturum sonuçları çift yönlü senkronize edilir (`#/air` ve `#/pressure` doğrudan rotaları korunur).
  - `Projeler & Kesitler` sayfasında her kesit için genişletilmiş form bulgu özetleri (`findings_counts`, ilk bulgulu forma tek tıkla geçiş, `key_metrics`).
- Bağımsız masaüstü Web dağıtımı (`v1.9.1`): `webapp/desktop_launcher.py` (yerel FastAPI + statik React + durum/durdurma penceresi + `--self-test`), `HydroWeb.spec`, macOS M1+ `arm64` `.dmg` (`build_web_dmg.sh`), Windows x64 Inno Setup kurulum `.exe` + taşınabilir `.zip` (`installer/hydro_web.iss`, `build_web_exe.ps1`).
- **Domain İkon Sistemi & Faz 1–5 Web Arayüzü İyileştirmeleri (`tasks/web_ui_plan.md`)**:
  - Konuya özgü Boru Kesiti + Hidrostatik Su + Manometre ikon seti (`tools/generate_icons.py`, `assets/icons/*`, `webapp/frontend/public/*`, `site.webmanifest`, `<HydroLogo />` + `Sidebar`/`TopBar`/`UpdateManagerModal`, `HydroWeb.spec`/`HidrostatikTest.spec`/`installer/hydro_web.iss`/`webapp/desktop_launcher.py`/`hidrostatik_test/ui/app.py`).
  - Modern Web & Erişilebilirlik: yerel `<dialog>` + `.showModal()` + `closedby="any"` + Safari pointer-coordinate light-dismiss fallback (`Dialog.tsx`, mobil `Sidebar.tsx` çekmecesi), `:root`/`[data-theme="dark"]` `color-scheme` + `accent-color` ve ilk boyama öncesi tema betiği (`index.html`, `styles.css`), `eslint-plugin-jsx-a11y` kapısı (tıklanabilir kart/tablo satırlarının native `<button>` dönüşümü, klavye `ArrowLeft/Right/Home/End` destekli WAI-ARIA `tablist`/`tabpanel`, kararlı liste anahtarları), **21 Vitest + Testing Library** birim/bileşen testi ve CI bağlantısı (`.github/workflows/lint.yml`).
  - Operatör Akışı & BOTAŞ Form Ergonomisi: `Sidebar.tsx` (`w-[280px]`, `Tümü | Bulgulu | Eksik` filtreleri), `DecisionStrip.tsx` (`Formlar · Dolu/11` + aktif form bağlamı) & `RightPanel.tsx` (`BOTAŞ Form Dosyası` ilerlemesi), `@container` yapışkan başlık/Saat sütunu (`role="region"`, `tabIndex={0}`), Excel/TSV çoklu satır yapıştırma (`pasteUtils.ts`, `FormTablePrimitives.tsx`, `MonitoringFormEditor.tsx`, `AcceptanceFormEditor.tsx`, `FormBodyEditor.tsx`), kaydedilmemiş değişiklik koruma diyaloğu + iskelet yükleyici (`SectionFormPage.tsx`), `DashboardPage.tsx` 3 adımlı iş akışı çubuğu ve `ProjectsPage.tsx` modülerleştirmesi (`SectionFormsModal.tsx`, `PlanProfileScanModal.tsx`).
- **Kurumsal Windows Uyumluluğu & Yerleşik WinRT OCR/PDF Motoru**:
  - `hidrostatik_test/services/report_ocr.py` ve `requirements-ocr.txt`: Windows 10/11 üzerinde harici imzasız `tesseract.exe` alt süreçleri yerine süreç-içi (in-process) Microsoft imzalı **WinRT `Windows.Media.Ocr`** ve **`Windows.Data.Pdf`** desteği (BCP-47 `tr-TR` öncelikli, `4096 px` ölçekleme, çok sütunlu BOTAŞ satır eşleyici ve `pypdfium2` `OSError` otomatik yedeği) + `4 sn` zaman aşımlı, `CREATE_NO_WINDOW`, `stdin=DEVNULL` ve TTL önbellekli (`clear_ocr_probe_cache`, `ocr_engine_details`) Tesseract yoklaması.
  - Backend & Başlatıcı sertleştirmesi (`webapp/backend/app/services/ocr.py`, `system.py`, `main.py`, `db.py`, `webapp/desktop_launcher.py`): `/api/ocr/status?refresh=true` tek yoklamada önbellekli yanıt, `/api/health` içinde `instance_id` doğrulaması, SQLite `WAL -> DELETE` otomatik geçişi, `SetErrorMode`, `ProxyHandler({})` loopback koruması, `8080` yerine çakışmasız `18790..18829` port aralığı + Windows `SO_EXCLUSIVEADDRUSE`, `"Küçült"` düğmesi ve `WM_DELETE_WINDOW` kapatma koruması.
  - Paketleme & Ön Uç tanılama (`HydroWeb.spec`, `build_web_exe.ps1`, `build_exe.ps1`, `installer/hydro_web.iss`, `StatusPanel.tsx`, `OcrPage.tsx`): varsayılan Windows paketinden harici `tesseract.exe` çıkarıldı (`-BundleTesseract` opsiyonel), `Program Files` kurulumu için `commandline` yetki yükseltme eklendi; `StatusPanel.tsx` / `OcrPage.tsx` zaman aşımı/HTTP hata/sunucu kapalı durumlarını ayırt eder ve sessiz sahte `DEMO_RESULT` düşüşü kaldırıldı.
- Dockerfile, docker-compose, README, kod haritası, GitHub Actions `release.yml`.

---

## 3. Devam Eden / Sıradaki İş

Aktif çalışma yok. 74 sayfalık ERCİŞ toplu OCR kalibrasyon raporu (`docs/spec/ocr_calibration_report.md`),
`SectionIdentityCard` segment özeti, terminoloji standardizasyonu, Projeler sayfası `Σ Section` boru hattı KPI'ı,
`three.js` kod bölme, OCR Test Raporu Kontrolü'nden çoklu/hesap/tekil raporların proje & bölüm eşleyerek (veya
yeni proje/test bölümü açarak) kaydedilmesi, kümülatif hesaplama (`profile`/`air`/`pressure`/`pig`), 11 kontrol
noktası değerlendirmesi ve canlı oturum hidrasyonu tamamlandı.

Sıradaki adımlar §4'teki üretim sertleştirmesi ve kurum onayı bekleyen işlerdir:
1. Kurumsal Auth / OIDC + iki kişi onay politikası (kullanıcı mimari kararı bekliyor).
2. Postgres runtime testi (`psycopg` kurulumu + test ortamı).
3. Kurum onayı bekleyen resmi A/B ve form revizyonları.

---

## 4. Yapılacaklar

### 4.1 Web / üretim sertleştirmesi (P1)

- [x] OCR mapping profile `pre_extract` / `post_map` uygulanması (`pre_extract`: ek etiket adları; `post_map`: hedef yol geçersiz kılma).
- [x] Frontend kod bölme (`three.js` / `PipelineScene` lazy load; ana bundle ~2.26 MB → ~1.25 MB + 1.02 MB ayrı chunk).
- [x] `SectionIdentityCard` segment özeti, terminoloji ayrımı ("Test Bölümü (Section)" / "Segment") ve Projeler sayfası `Σ Section` KPI'ı.
- [x] 74 sayfalık ERCİŞ toplu OCR doğrulaması ve `.Başlık Yeri` / alfanümerik `BÖLÜM` iyileştirmesi (`docs/spec/ocr_calibration_report.md`).
- [x] `.xlsx` / `.xls` test raporlarının doğrudan hücre tabanlı (`source="spreadsheet"`) okunması (`openpyxl` + `xlrd`, magic-byte/ZIP doğrulama).
- [x] OCR Test Raporu Kontrolü kayıt & hesap hattı (`commit-dossier` liste sözleşmesi, mühendislik hesap paketi & boş `.xls` ayrımı, proje/KP kesit eşleme veya otomatik yeni proje + 11 zorunlu form slotu açma, `profile`/`air`/`pressure`/`pig` `TestResult` kaydı + canlı hidrasyon, tekil rapor onay/uygulama).
- [x] OCR DB kuyruğu + worker + iptal (`ocr_queue.py` bounded executor, `async_mode`/`Prefer: respond-async` `202` + `estimated_wait_s`, `cancel_event`, `ocr_timeout_s`, parametrik `language`, başlangıç `worker_interrupted` toparlaması).
- [x] Web güvenlik & dağıtım sertleştirmesi (geriye dönük uyumlu): fail-closed `HYDRO_AUTH_MODE` bağlanma kapısı + `desktop_launcher.py` `validate_bind_security`, harici `/theme-init.js` + CSP + `X-Content-Type-Options`/`X-Frame-Options`/`COOP`/`CORP`/`Cache-Control: no-store`, `Host` DNS-rebinding kapısı, `/api/update/*` yerel yönetici + same-origin/proxy başlık kapısı, akışlı dosya boyutu sınırı (`read_upload_bounded`), bellek-içi `RateLimiter` (`429 Retry-After`), maskelenmiş DB logları ve `Dockerfile`/`docker-compose.yml`/CI düzeltmeleri.
- [x] Alembic üretim migrasyonu (`migrations/versions/0002_baseline.py` → `0003_drop_duplicate_indexes.py`, `migrations_runner.py`, legacy `0001`/`0002` köprüsü, SQLite FK/Postgres advisory lock koruması, geri alınabilir `restore_db_backup`, `HYDRO_AUTO_MIGRATE`, `HydroWeb.spec` paketlemesi).
- [ ] Auth / OIDC + iki kişi onay kuralı (MVP'de anonim `X-Session-ID`).
- [ ] Postgres runtime testi (kod uyumlu, `psycopg` kurulu değil).
- [x] Frontend birim testleri, kod bölme & paket bütçesi (`21` Vitest testi, rota/Recharts/3D lazy-loading, Vite 8 Rolldown chunk bölmesi, `check:bundle` ≤ `200 kB` gzip kapısı, `GZipMiddleware` + HTML `no-cache` bfcache uyumu + `verify-tabs.mjs`).
- [ ] 3D gerçek veri: `profile_points[]` / `equipment[]` girdileri (yoksa yaklaşık sahne + uyarı).

### 4.2 Domain / masaüstü (P1–P2, `tasks/todo.md`)

- [x] 14.1–14.3 basınç–hacim izleme, `%0.2` ilave su durdurma mantığı ve 2 saatlik bekleme domain + API (`pressurization_monitor.py`); [x] Web UI paneli (Basınç Değişim sayfası, `OperationsPanel`); [x] oturum kaydı, özet ve TXT/PDF/XLSX rapor bağlantısı.
- [ ] 12 ve 15 için zaman serili termal dengeleme / 24 saatlik test kayıt veri modeli.
- [x] 16–17 basınç düşürme ve boşaltma kontrol listesi domain + API (`post_test_operations.py`); [x] Web UI paneli (`OperationsPanel`); [x] oturum kaydı ve rapor bağlantısı; [x] BOT-FRM-CDB-001-024 formu bağlantısı.
- [ ] 21. bölümdeki saha formlarına uygun rapor çıktısı.
- [ ] Segmentli geometri indirgemesi için kurum içi metod notu.
- [ ] +2 °C dolum kısıtı için saha uyarı mantığı.
- [ ] `table_v1` backend'i için UI seçici + backend karşılaştırma raporu.
- [ ] `table_v1` gridinin resmi veriyle yeniden doldurulması (kurum verisi bekleniyor).
- [ ] 0–4 °C aralığında negatif `beta_water` ve geçersiz `B` davranışının UI'de açık gösterimi.

### 4.3 Parity borcu (P2, `webapp/docs/parity_matrix.md` §10)

- [ ] Gerçek kot profili (`profile_points[]`) ve ekipman konumları (`equipment[]`).
- [ ] `t_initial` / `t_final` alanları (basınç sekmesi; `dT` türetimi).
- [ ] Rapor kimliği alanları (`report_no`, `operator`, `date`).
- [ ] Masaüstü JSON içe aktarma: `POST /api/import/desktop-snapshot`.
- [ ] Eşzamanlı düzenleme: `revision` + `If-Match`, çakışmada 409 + diff.
- [x] Taranmış (metin katmanı olmayan) PDF için rasterizer (`pypdfium2` Apache-2.0/BSD-3-Clause + macOS `Quartz` + Windows taşınabilir Tesseract).
- [ ] Segment bazlı SMYS/kalite (şu an tek kalite tüm hat için).

---

## 5. Engellenenler (dış girdi bekliyor)

| Konu | Beklenen |
| --- | --- |
| Resmî form revizyonu | Kurum onaylı güncel `.xls` revizyonları (OCR envanteri `docs/spec/report_forms.md`) |
| B tablosu resmi kaynağı | Kurum içi ölçüm zinciri / resmi revizyon |
| A/B tablosu kalıcı düzeltmesi | Kurum onaylı veri (şu an çalışma zamanı onarımı) |
| Notarization | Kod imzalama sertifikası ve kurumsal anahtar yedeği/rotasyonu |
| Release CI | `HYDRO_UPDATE_PRIVATE_KEY` secret'ı ayarlandığında tam otomatik; yerel doğrulama için Ed25519 anahtarı `~/.config/hydro/` |
| Postgres | `psycopg` kurulumu + test ortamı |

---

## 6. Doğrulama (son çalıştırma: 2026-11-19)

```bash
# Lint & tip denetimi
python3 -m ruff check . && python3 -m ruff format --check .     # PASS (146 dosya)
python3 -m mypy hidrostatik_test/domain/                       # Success: no issues found (14 files)
python3 -m mypy --ignore-missing-imports webapp/backend/app    # Success: no issues found (48 files)

# Web backend (Alembic + API + domain parity)
python3 -m pytest webapp/backend/tests -q                      # 210 passed

# Masaüstü
python3 -m unittest discover -s tests -p "test_*.py"           # 709 tests OK (skipped=1)

# Masaüstü paketli Web self-test
python3 webapp/desktop_launcher.py --self-test                 # SELF_TEST_OK

# Frontend derleme, lint & test
cd webapp/frontend && npm run lint && npm test && npm run typecheck && npm run build && npm run check:bundle

# Sekme + BOTAŞ Form Ağacı & 020/022/023 Gömülü Hesaplama & Güncelleme Yöneticisi smoke (port 8099, izole DB)
cd webapp/frontend && HYDRO_APP_URL=http://127.0.0.1:8099 \
  node scripts/verify-tabs.mjs                                 # 12/12 PASS
```

Çalıştırma:

```bash
python3 webapp/run_web.py --host 127.0.0.1 --port 8095
# veya
docker compose -f webapp/docker-compose.yml up --build
```

---

## 7. Bilinen Tuzaklar / Notlar

- `@react-three/drei` `Html` React 19 üretim derlemesinde `removeChild` hatası veriyor;
  yerine `SceneHtml` + `SceneLabels` DOM katmanı kullanılıyor. Geri dönülmemeli.
- Demo proje ID'leri (`demo-*`) backend'e gönderilmez; `App.tsx` ve mutation hook'ları filtreler.
- İlk yükleme frontend JS paketi rota/Recharts/three.js kod bölme ve lazy-loading ile 143,2 kB gzip altındadır (`npm run check:bundle` ≤ 200 kB bütçe kapısı).
- `implementation_status.md` içindeki test sayıları bu dosyayla hizalandı.
- Plan-Profil tarama motoru PDF metin katmanı veya Tesseract/macOS Vision varsa çalışır;
  hiçbiri yoksa yanıt `ocr.available=false` döner.
- OCR'da etiket/değer eşlemesi bbox tabanlıdır; dikey tolerans (`0.005`) satır
  aralığına göre kalibre edildi. Değiştirilirse `tests/test_report_ocr.py`
  içindeki gerçek form fixture'ları ve `VisionBlockPairingTests` kırılır.

---

## 8. Ayrıntılı Notlar (nerede ne var)

| Dosya | İçerik |
| --- | --- |
| `tasks/todo.md` | Masaüstü açık işler (bölüm bazlı) — tarihsel, eski test sayıları |
| `tasks/web_ui_plan.md` | Domain ikonu ve Web arayüzü Faz 1–5 uygulama planı (tamamlandı) |
| `tasks/remediation.md` | Denetim remediasyonu + faz planı, işaretli maddeler |
| `docs/remediation_report.md` | Remediasyon sonuç özeti ve kanıt tablosu |
| `docs/continuity.md` | Masaüstü süreklilik/karar geçmişi |
| `docs/spec/report_forms.md` | Resmî form envanteri, gerçek saha değerleri, OCR kalibrasyonu |
| `docs/ui_ergonomics.md` | Masaüstü ergonomi kararları |
| `docs/codebase_map.md` | Üretilen kod haritası |
| `webapp/docs/implementation_status.md` | Web uygulaması durumu ve doğrulama |
| `webapp/docs/parity_matrix.md` | Masaüstü↔web parity matrisi, 28 maddelik eksik listesi |
| `webapp/docs/api_contract.md` | API sözleşmesi |
| `webapp/docs/architecture.md` | Web mimarisi |
| `webapp/docs/ux_plan.md` | UX planı + açık UX kararları |
| `webapp/docs/decisions.md` | Web karar kaydı |
| `WHATS_NEW.md` | Sürüm bazlı yenilik özeti (`v1.9.1`) |
| `CHANGELOG.md` | Sürüm bazlı yapılanlar |

---

## 9. Güncelleme Kuralı

1. Her özellik commit'inde bu dosyanın **"Son güncelleme"**, ilgili bölüm ve doğrulama sayıları yenilenir.
2. Bir iş bitince `[ ]` → `[x]` yapılır; iptal edilirse satır silinmez, "iptal: gerekçe" eklenir.
3. Yeni engel çıkarsa §5'e, yeni teknik borç §4'e yazılır.
4. Ayrıntı bu dosyaya taşınmaz; ilgili nota link verilir (tekrar bilgi çoğaltılmaz).
