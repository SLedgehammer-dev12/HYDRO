# HYDRO — Web Sürümü Canlı Denetim Raporu (v4)

> **Tarih:** 24 Kasım 2026 (v2.1.0 güncellemesi)
> **Baseline:** `main` @ `1a379ee` (`hidrostatik-test-v2.1.0`); önceki anlık görüntü `37843de` (`v2.0.0`)
> **Kapsam:** Web backend (FastAPI), web frontend (React/Vite), web'in kullandığı domain servisleri. Masaüstü Tkinter arayüzü kapsam dışıdır.
> **Yöntem:** Kaynak kod okuma, kalite kapılarının yeniden çalıştırılması, canlı sunucu + HTTP smoke, tarayıcı ile onboarding turu doğrulaması.
> **Kanıt standardı:** Her bulgu `dosya:satır` veya komut/ölçüm çıktısıyla desteklenir.

> **Güncelleme (26 Kasım 2026):** Bu rapor v2.1.0 (`1a379ee`) anlık görüntüsüdür. `v2.1.1` (`d99ff9d`) ile F18–F29 kapatıldı ve `R1–R26` iyileştirmeleri uygulandı. Güncel ölçümler ve kapanış için [`analysis_report_v5.md`](analysis_report_v5.md); kalan işler için [`improvement_recommendations_v2.md`](improvement_recommendations_v2.md) esas alınmalıdır.

> **Önceki rapor:** [`analysis_report_v3.md`](analysis_report_v3.md) 22 Kasım 2026 anlık görüntüsüdür. v3'teki "F1–F17 tamamen uygulandı" notu **kısmen** doğrudur: 10 bulgu kapanmış, 6 bulgu kısmi kalmış, 1 bulgu (Postgres) dış girdi beklemektedir. Bu v4 dosyası ilk olarak v2.0.0'da üretildi; 24 Kasım'da v2.1.0 (`1a379ee`) için ölçümler ve yeni bulgularla güncellendi.

---

## 1. Yönetici Özeti

v2.1.0 (24 Kasım 2026), v2.0.0'ın rehberli turunu ve gezinme sadeleştirmesini koruyup arayüzü üç fazda daha da inceltiyor; 020/022 kabul formlarında okunan/hesaplanan değer ayrımını ve birleşik su özelliği backend adlandırmasını (`IAPWS-95` / `IAPWS-IF97 Region 1`) ekliyor. Tur geniş ekranda amacına uygun çalışıyor; ancak **1024 px altındaki pencerelerde tur hedefi görünmez olduğu için popover sol üste düşüyor**; bu davranış v2.1.0'da yeniden doğrulandı (F18).

Kalite kapıları: **253 backend pytest / %83 kapsam**, **63 Vitest / 21 dosya**, **87 OpenAPI path / 101 operation**, **148,3 kB ilk JS + 15,2 kB CSS gzip**, `openapi.json` canlı şemayla birebir. Buna karşın **iki kapı kırmızı**: `ruff format --check` v2.1.0'da commit edilen iki dosyada başarısız (F28) ve `verify-tabs.mjs` Dashboard'dan kaldırılan bir başlığı beklediği için 11/12 (F29). Sözleşme dosyası (`api_contract.md`) hâlâ gerçek yüzeyin gerisinde ve CI'da OpenAPI/istemci sözleşme kapısı yok (F22).

Öne çıkan açıklar:

1. **HEAD biçim kapısını geçmiyor** (`ruff format --check`, F28).
2. **Sekme smoke testi v2.1.0 Dashboard'ıyla uyumsuz** (11/12, F29).
3. **Rehberli tur <1024 px'te kırılıyor** (F18).
4. **Örnek proje üreticisi sınırsız ve tekrarlı çalışıyor**; 40 ardışık istek 40 proje oluşturdu (F19).
5. **Onboarding'in ikinci adımı hata verirse oluşturulan demo proje sahipsiz kalıyor** (F20).
6. **Yazma modellerinin bir kısmı hâlâ `extra="ignore"`**; yanlış alan adları sessizce yutuluyor (F21).
7. **Postgres hâlâ doğrulanmamış**; `psycopg` bağımlılığı yorum satırında (F23).

Masaüstü tam test paketi bu makinede (macOS / Python 3.13) sıralamaya bağlı `Tcl_AsyncDelete` hatasıyla duruyor; Tk sınıfı hariç tutulduğunda **725 test OK** (skipped=1), sınıf tek başına **16 test OK**. Bu bir test izolasyonu sorunudur, ürün kodu hatası değildir (F25).

**Sonuç:** v2.1.0 çekirdek hesaplarda ve API'de kararlıdır; yeni kabul-formu hesap ayrımı testlerle korunuyor. Ancak HEAD'de biçim ve smoke-test kapıları kırmızı olduğu için "yeşil sürüm" demek için önce F28/F29 kapatılmalı; tur deneyimi ve örnek veri üretimi için P2 düzeltmeleri, kurumsal dağıtım için Postgres doğrulaması gereklidir.

---

## 2. Önceki Bulguların Güncel Durumu (v3 → v4)

| ID | v3 Başlığı | Durum | Kanıt / Not |
| --- | --- | --- | --- |
| F1 | Form güncellemelerinde iyimser eşzamanlılık yok | **Kapandı** | `sessions.py:136-150` `If-Match` + gövde `revision`; `schemas.py:528-532`; `services/dossier.py:5440-5461` `expected_revision`; 409 testleri `test_security_and_errors.py:529-563` |
| F2 | API sözleşmesi gerçek yüzeyden kopuk | **Kısmi** | `openapi.json` var ve canlı şemayla eşit; `include_raw_ocr` uygulandı; ancak `api_contract.md` 65 bölüm / gerçek 101 operation; CI'da `openapi --check` ve `check:api` yok (F22) |
| F3 | Demo fallback yazmaları sessizce yutuyor | **Kısmi** | Tek okuma hatası artık global modu değiştirmiyor (`queries.ts:86-103`); offline yazma `pendingServerSync` + uyarı üretiyor (`queries.ts:1050-1075`); otomatik replay yok, kullanıcı yeniden Kaydet demeli |
| F4 | Docker'da DB yönetimi + güncelleme yöneticisi kilitli | **Kapandı** | `X-Hydro-Admin-Token` alanı `DatabaseAdminPanel.tsx:161-166`, `sessionStorage` (`api.ts:175-199`), backend token kapısı `system.py:86-121` |
| F5 | Büyük yüklemeler RAM'de; gövde/eşzamanlılık sınırı yok | **Kapandı** | `stream_upload_to_tempfile` + 2 eşzamanlılık semaforu (`core/security.py:177-218`), 32 MB JSON gövde sınırı (`main.py:207-222`); eski `read_upload_bounded` artık kullanılmıyor |
| F6 | Analiz uçlarında sınırsız liste girdileri | **Kapandı** | `schemas.py:69,190,202,257` üst sınırları |
| F7 | Export dosyaları birikiyor; arşiv bellekte | **Kapandı** | 24 saat TTL + periyodik budama (`services/reports.py:43-80`), arşiv disk tempfile + `BackgroundTask` (`project_archive.py:131-160`, `projects.py:327-338`) |
| F8 | Ağır uçlarda rate limit eksik | **Kısmi** | Export/arşiv/scene/system limitleri eklendi; `POST /api/projects/generate-sample` hâlâ limitsiz (F19) |
| F9 | OCR kuyruğu process-içi; worker sabit 1 | **Kısmi** | `HYDRO_WEB_WORKERS` uygulandı ve SQLite'ta 1'e sabitleniyor (`run_web.py:81-94,171-177`); OCR kuyruğu hâlâ `ThreadPoolExecutor` ve çok worker'da desteklenmiyor (`architecture.md:872`) |
| F10 | OCR sayfasından ayrılınca analiz durmuyor | **Kısmi / ürün kararı** | Unmount'ta yalnız client polling abort ediliyor (`OcrPage.tsx:310-314`); sunucu işi iptal edilmiyor, tur metni bunu "arka planda güvenli devam eder" diye açıklıyor (`tourSteps.ts:38`) |
| F11 | OCR istemci timeout'u sabit 630 sn | **Kapandı** | `(ocr_timeout_s + 30)` (`OcrPage.tsx:501-504`), meta `system.py:219` |
| F12 | DB restore canlı isteklerin altında motoru değiştiriyor | **Kapandı (2 sn drain residual)** | Restore sırasında yeni istekler `503 db_restoring` (`main.py:227-247`), `begin_restore_swap` in-flight sayacı (`db.py:53-63`); drain üst sınırı 2 sn |
| F13 | PostgreSQL desteği doğrulanmamış | **Açık / dış girdi** | `psycopg` yorum satırında (`requirements-web.txt:22`), compose Postgres bloğu yorumda (`docker-compose.yml:34-42`), CI'da Postgres job'ı yok |
| F14 | Web kapsam eşiği ve sayfa testleri yok | **Kapandı** | CI `--fail-under=80` (`test.yml:101-104`), 21 Vitest dosyası; OCR, Reports, SectionForm, Geometry, DatabaseAdmin ve onboarding sayfa/bileşen testleri var |
| F15 | `extra="ignore"` sözleşme kaymasını gizliyor | **Kısmi** | `StrictWriteModel` eklenmiş; ancak `SessionCreate`, `ProjectCreate`, `ResultCreate`, `SnapshotApply` gibi yazma modelleri hâlâ `StrictModel` (F21) |
| F16 | Şartname analiz dokümanı güncel değil | **Kapandı** | Tarihsel/güncel not `docs/spec/ngtl_5007_hydrostatic_analysis.md:3` |
| F17 | `HYDRO_AUTH_MODE` kabul ediliyor ama uygulanmıyor | **Kapandı** | `validate_bind_security` uygulanmayan modda başlatmayı reddediyor (`core/config.py:246-254`) |

**Özet:** 10 kapandı · 6 kısmi · 1 açık (dış girdi bekliyor).

---

## 3. Ölçümler (24 Kasım 2026, `1a379ee` / `v2.1.0`)

| Kapı | Komut | Sonuç |
| --- | --- | --- |
| Ruff lint | `python3 -m ruff check .` | **PASS** |
| Ruff format | `python3 -m ruff format --check .` | **FAIL** — `dossier.py`, `form_details.py` yeniden biçimlendirilmeli (F28) |
| Mypy domain | `python3 -m mypy hidrostatik_test/domain/` | **PASS** (14 dosya) |
| Mypy web | `python3 -m mypy --ignore-missing-imports webapp/backend/app` | **PASS** (50 dosya) |
| Backend test | `python3 -m coverage run --source=webapp/backend/app -m pytest webapp/backend/tests -q -W default::sqlalchemy.exc.SAWarning` | **253 passed**, 60,9 sn, SAWarning yok |
| Web kapsam | `python3 -m coverage report --fail-under=80` | **%83** (12.728 statement, 1.670 miss) |
| OCR birim testleri | `python3 -m unittest tests.test_report_ocr` | **76 OK** (skipped=1) |
| Masaüstü test keşfi | `unittest.defaultTestLoader.discover(...)` | **733 test** |
| Masaüstü tam koşu | `python3 -m unittest discover -s tests -p "test_*.py"` | **Tcl_AsyncDelete** ile 122 test sonrası durdu (F25) |
| Masaüstü (Tk sınıfı hariç) | özel loader, `DownloadDialogTkTests` dışlandı | **725 OK** (skipped=1) |
| Tk diyalog sınıfı tek başına | `python3 -m unittest tests.test_download_dialog` | **16 OK** |
| Web self-test | `python3 webapp/desktop_launcher.py --self-test` | **SELF_TEST_OK version=2.0.0** |
| Frontend lint / typecheck | `npm run lint` / `npm run typecheck` | **PASS** |
| Frontend test | `npm test` | **63 passed / 21 dosya** |
| Frontend build | `npm run build` | **PASS** |
| Bundle bütçesi | `npm run check:bundle` | **148,3 kB** ilk JS gzip, **15,2 kB** CSS (≤ 200 kB) |
| API sözleşmesi (istemci) | `npm run check:api` | **74 şablon / 87 path** |
| OpenAPI | `create_app(...).openapi()` | **87 path / 101 operation** |
| OpenAPI dosyası | `python3 -m app.tools.dump_openapi --check` | **PASS** (canlı şema = commit'li dosya) |
| Sekme smoke | `HYDRO_APP_URL=http://127.0.0.1:8099 node scripts/verify-tabs.mjs` | **11/12 PASS** — `dashboard` FAIL (F29) |
| Canlı health | `GET /api/health` | `ok`, `version=2.1.0`, SQLite, Alembic `0003`, OCR `vision` |
| Örnek proje limiti | 40 ardışık `POST /generate-sample` | **40 × 201** (rate limit yok; v2.1.0'da da doğrulandı) |

> Not: Masaüstü tam koşu hatası `tests/test_download_dialog.py:160-180` içindeki Tk sınıfının teardown'ından sonra, sonraki `test_download_manager` testinde tetikleniyor. Sınıf tek başına geçtiği için kök neden test izolasyonudur.

---

## 4. Yeni ve Kalan Bulgular

| ID | Önem | Başlık | Alan |
| --- | --- | --- | --- |
| F18 | **P2** | Rehberli tur <1024 px'te hedefsiz kalıyor | Arayüz |
| F19 | **P2** | Örnek proje üreticisi limitsiz ve tekrarlı | Kaynak / veri |
| F20 | **P2** | Onboarding kısmi hatası sahipsiz demo proje bırakıyor | Veri / UX |
| F21 | **P2** | Yazma modellerinin bir kısmı hâlâ `extra="ignore"` | Sözleşme |
| F22 | **P2** | Sözleşme dokümanı ve CI kapıları eksik | Doküman / CI |
| F23 | **P2** | PostgreSQL doğrulanmamış | Dağıtım |
| F24 | P3 | Sayfadan ayrılınca OCR sunucu işi devam ediyor | Kaynak / UX |
| F25 | P3 | Masaüstü tam test paketi sıralamaya bağlı Tk çökmesi | Test |
| F26 | P3 | Yardım'dan başlatılan "demo turu" örnek proje üretmiyor | UX tutarlılığı |
| F27 | P3 | README / implementation_status test sayıları eski — **kapatıldı** (v2.1.0) | Doküman |
| F28 | **P2** | v2.1.0 HEAD `ruff format --check` kapısını geçmiyor | CI / biçim |
| F29 | P3 | `verify-tabs` Dashboard beklentisi v2.1.0 ile uyumsuz | Test |

---

### F18 — P2: Rehberli tur <1024 px'te hedefsiz kalıyor

**Kanıt**
- `GuidedTourOverlay.tsx:51-67` hedefi `document.querySelector('[data-tour="nav-*"]')` ile bulup `anchor-name` veriyor.
- `Sidebar.tsx:542-560` masaüstü `<aside>` `hidden lg:block`; 1024 px altında `display:none`. Mobil çekmece yalnız `sidebarOpen` true iken render ediliyor.
- `styles.css:1417-1425` `position-area: right center` + `position-anchor: --hydro-tour-anchor` kullanıyor; anchor çözümlenemediğinde `@supports not` dalına geçilmiyor.
- Canlı ölçüm (1000×700): `aside.display="none"`, hedef `getBoundingClientRect()` sıfır, popover `rect={x:12,y:0,w:390,h:268}`; yani popover sol üstte açılıyor.

**Etki**
Tablet veya dar pencere kullanıcısı turu başlattığında hedef sekme vurgulanmıyor, popover başlık alanının üzerine biniyor. Turun "hedefi işaret etme" amacı kayboluyor.

**Öneri**
- Hedef görünmüyorsa (`offsetParent === null` veya rect alanı 0) mobil çekmeceyi aç veya TopBar'daki menü düğmesini hedefle.
- Anchor çözümlenemediğinde `@supports not` benzeri sabit konum fallback'ine geç (ör. alt-orta panel).
- `GuidedTour.test.tsx`'e `matchMedia`/dar görünüm senaryosu ekle. **Efor: S.**

---

### F19 — P2: Örnek proje üreticisi limitsiz ve tekrarlı

**Kanıt**
- `projects.py:55-70` `POST /api/projects/generate-sample`; çevresinde `enforce_rate_limit` yok (karşılaştırma: `projects.py:86,327`).
- `project_data.py:1199,1206` `code` verilirse aynen kullanılıyor; `DEMO-TUR` için tekillik denetimi yok.
- Canlı test: aynı gövdeyle 2 istek → 2 ayrı `DEMO-TUR` projesi; 40 ardışık istek → **40 × 201**.
- `schemas.py:356-362` `section_count` 1–6, `include_time_series` / `include_forms` true; her istek çok sayıda bölüm, form ve zaman serisi üretiyor.

**Etki**
Tek bir sekme/istemci saniyeler içinde onlarca demo projesi ve yüzlerce form üretebilir. Proje listesi kirlenir, SQLite dosyası büyür; onboarding tekrarlandığında aynı kodlu projeler ayırt edilemez.

**Öneri**
- `bucket="project_generate_sample"` ile limit (ör. 5/dk) ekle.
- `code` + `workspace` için mevcut demo projesini yeniden kullan veya otomatik son ek üret (`DEMO-TUR-2`).
- Onboarding'de "mevcut demo varsa aç" kontrolü yap. **Efor: S.**

---

### F20 — P2: Onboarding kısmi hatası sahipsiz demo proje bırakıyor

**Kanıt**
- `OnboardingWelcomeCard.tsx:36-43` proje oluşturuluyor.
- `:50-61` ilk bölüm ayrı bir `GET /sessions/{id}` ile yükleniyor.
- `:65-71` herhangi bir hata `catch`'e düşünce yalnız uyarı gösterip `startTour(null)` çağırıyor; oluşturulmuş `generated.project.id` temizlenmiyor ve `tourSampleProjectId` olarak da saklanmıyor.

**Etki**
`POST /generate-sample` başarılı olup ardından session okuması/timeout başarısız olursa kullanıcıya "örnek proje oluşturulamadı" denir; oysa proje veritabanında durur. Tur sonunda "Örnek projeyi temizle" seçeneği de görünmez, çünkü ID kaydedilmemiştir.

**Öneri**
- `generated` başarılı olduğu anda `startTour(generated.project.id)` için ID'yi sakla; hata durumunda `api.deleteProject` ile temizle.
- Alternatif olarak ilk bölümü `generate-sample` yanıtına gömüp ikinci isteği kaldır. **Efor: S.**

---

### F21 — P2: Yazma modellerinin bir kısmı hâlâ `extra="ignore"`

**Kanıt**
- `schemas.py:39-40` `StrictWriteModel(extra="forbid")` var.
- Ancak yazma gövdeleri olarak kullanılan `SessionCreate` (`:270`), `ProjectCreate` (`:289`), `ResultCreate` (`:455`), `TimeSeriesBatchCreate` (`:464`), `SnapshotApply` (`:477`), `OcrApplyRequest` (`:513`) hâlâ `StrictModel` (`extra="ignore"`).
- Canlı test: `POST /api/sessions` gövdesinde `"smysMpa": 999` → **201**, alan sessizce yutuldu. `POST /generate-sample` gövdesinde `"unexpected_field": true` → **201**.

**Etki**
İstemci alan adını yanlış yazdığında (ör. `smysMpa` ↔ `smys_mpa`) 422 yerine sessizce kabul edilir; değer kaydedilmemiş olur ve hata çok sonra fark edilir. v3'te "F15 kapandı" denmesi bu nedenle erken olmuştur.

**Öneri**
- Tüm yazma gövdelerini `StrictWriteModel`'e taşı; okuma/hesap modelleri `StrictModel` kalabilir.
- Geçiş dönemi için bilinen eski alanlara açık `Field(alias=...)` ver, sonra kaldır. **Efor: S–M.**

---

### F22 — P2: Sözleşme dokümanı ve CI kapıları eksik

**Kanıt**
- `webapp/docs/api_contract.md` 65 `###` endpoint bölümü içeriyor; gerçek yüzey 87 path / 101 operation. Dosya `11.5 POST /api/projects/{id}/sections/batch` sonrasında yalnızca kısa bir "Ek uç grupları" listesiyle bitiyor; `/generate-sample`, `/forms/*`, `/time-series/batch`, `/system/*` ve `/update/*` için ayrıntılı sözleşme bölümü yok.
- `webapp/docs/openapi.json` güncel ve canlı şemayla eşit (`dump_openapi --check` PASS), ancak `.github/workflows/*.yml` içinde `openapi` / `check:api` / `verify-tabs` adımı yok.
- `check-api-contract.mjs` yalnız istemcinin çağırdığı path'lerin OpenAPI'de var olduğunu doğruluyor; şema/yanıt tipi karşılaştırması yapmıyor.

**Etki**
Bugünkü uyum elle korunuyor. Yeni endpoint veya alan eklendiğinde `openapi.json`, `api_contract.md` ve istemci tipleri sessizce ayrışabilir.

**Öneri**
- CI'ya `python -m app.tools.dump_openapi --check` ve `npm run check:api` ekle.
- `api_contract.md`'yi OpenAPI'den üret veya en azından eksik bölümleri tamamla.
- `verify-tabs.mjs`'i gece/CI smoke job'ına bağla. **Efor: M.**

---

### F23 — P2: PostgreSQL doğrulanmamış

**Kanıt**
- `webapp/requirements-web.txt:22` `# psycopg[binary]>=3.2,<4` yorum satırında.
- `webapp/docker-compose.yml:34-42` Postgres servisi ve `HYDRO_DATABASE_URL` örneği yorumda.
- `.github/workflows/test.yml` yalnız SQLite ile backend testi çalıştırıyor.
- README doğru şekilde "resmi varsayılan SQLite; Postgres deneysel/opsiyonel" diyor.

**Etki**
Dokümana güvenip Postgres'e geçen kurum `psycopg` kurulu olmadığı için uygulamayı açamaz; kurulsa bile Alembic `0003`, JSON/UUID ve eşzamanlılık davranışı yalnız SQLite'ta test edilmiştir.

**Öneri**
- Ya resmî olarak "SQLite only" ilan et ve Postgres örneklerini kaldır; ya da `psycopg[binary]` + Postgres servisli CI job'ı ekle. **Efor: M (dış ortam).**

---

### F24 — P3: Sayfadan ayrılınca OCR sunucu işi devam ediyor

**Kanıt**
- `OcrPage.tsx:310-314` unmount cleanup yalnız `abortRef.current?.abort()` çağırıyor; `cancelOcrAnalysis` yok.
- `run_web.py`/`ocr_queue.py` tek süreç içi kuyruk; `architecture.md:872` çok worker önermiyor.
- `tourSteps.ts:38` bunu bilinçli olarak "arka planda güvenli şekilde devam eder" diye anlatıyor.

**Etki**
Kullanıcı OCR sekmesinden ayrılsa da tek OCR slotu işgal edilir; yeni analiz kuyrukta bekler. İş kaybolmaz, ancak kaynak yönetimi kullanıcıya görünmez.

**Öneri**
Ürün kararını netleştir: ya unmount'ta `cancelOcrAnalysis` çağır, ya da "arka planda devam" durumunu global bir iş göstergesinde (TopBar/StatusPanel) göster. **Efor: S.**

---

### F25 — P3: Masaüstü tam test paketi sıralamaya bağlı Tk çökmesi

**Kanıt**
- `tests/test_download_dialog.py:160-180` her testte `tk.Tk()` + `root.destroy()`.
- Tam koşu: 122 test OK sonrası `test_download_manager...` sırasında `Tcl_AsyncDelete: async handler deleted by the wrong thread` (exit 134).
- `DownloadDialogTkTests` dışlandığında **725 test OK** (skipped=1); `tests.test_download_dialog` tek başına **16 test OK**.

**Etki**
Yerel macOS/Python 3.13 tam koşusu güvenilir değil; CI macOS'ta Tk bulunmadığı için testler skip olabilir, bu da gerçek regresyonu gizler.

**Öneri**
Tk testlerini ayrı süreç/job'a taşı (`unittest` ile tek modül), `root.update_idletasks()` + `root.quit()` + `root.destroy()` sırasını düzelt, `after` callback'lerini teardown'da iptal et. **Efor: S.**

---

### F26 — P3: Yardım'dan başlatılan "demo turu" örnek proje üretmiyor

**Kanıt**
- `HelpDialog.tsx:45-52` `startTour(null)` çağırıyor; örnek proje üretimi yok.
- Onboarding akışı ise `OnboardingWelcomeCard.tsx:36-64` ile örnek proje üretiyor.
- Aynı düğme metni "Rehberli Demo Turunu Başlat".

**Etki**
Kullanıcı Yardım'dan turu açtığında "demo" adı altında yalnız 5 navigasyon adımı görür; örnek veri yoktur. Beklenti ile davranış çelişir.

**Öneri**
Yardım akışını onboarding ile aynı örnek proje üretimine bağla veya düğmeyi "İş akışı turunu başlat" olarak yeniden adlandır. **Efor: S.**

---

### F27 — P3: README / implementation_status test sayıları eski — **kapatıldı (v2.1.0)**

**Kanıt (önce)**
- v2.0.0'da `README.md:139` "61 frontend Vitest testi (20 dosya)" ve "723 unittest"; `webapp/docs/implementation_status.md:27` "723 tests OK".
- v2.1.0 `1a379ee` itibarıyla `README.md:139` **253 pytest / %83**, **63 Vitest / 21 dosya**, **725 OK**; `implementation_status.md:12,26-28` **253 pytest**, **148,3 kB**, **733 keşif / 725 OK** yazıyor.
- `DURUM.md` §1 ve §6 aynı sayılara çekildi.

**Kalan**
`DURUM.md:129` bu güncellemeden önce hâlâ `150,1 kB` diyordu; v4 denetiminde **148,3 kB** olarak düzeltildi. Test sayısını CI artifact'ından tek kaynaktan üretme önerisi geçerlidir. **Efor: S.**

---

### F28 — P2: v2.1.0 HEAD `ruff format --check` kapısını geçmiyor

**Kanıt**
- `python3 -m ruff check .` → **PASS**.
- `python3 -m ruff format --check .` → **FAIL**: `Would reformat: webapp/backend/app/services/dossier.py`, `Would reformat: webapp/backend/app/services/form_details.py` (150 dosya biçimli).
- `.github/workflows/lint.yml` bu adımı **bloklayıcı** çalıştırıyor (`ruff format --check .`, `continue-on-error` yok).
- Sorun `37843de..1a379ee` aralığında, 020/022 kabul-formu değişikliğiyle (`a7cdcb5`) girmiş; sürüm commit'i biçim kapısı çalıştırılmadan atılmış.

**Etki**
`main` üzerindeki `Lint` iş akışı kırmızı; sonraki PR'lar aynı kapıya takılır ve gerçek regresyonlar gürültü içinde kaybolur. Biçim farkı işlevsel değil, ancak sürümün "tüm kapılar yeşil" iddiasını geçersiz kılar.

**Öneri**
- `ruff format webapp/backend/app/services/dossier.py webapp/backend/app/services/form_details.py` çalıştır, farkı gözden geçir ve commit'le.
- Sürüm öncesi yerel kapı betiğine (`make lint` benzeri) `ruff format --check` ekle veya pre-commit hook kullan. **Efor: S.**

---

### F29 — P3: `verify-tabs` Dashboard beklentisi v2.1.0 ile uyumsuz

**Kanıt**
- `scripts/verify-tabs.mjs:209` Dashboard için `<main>` içinde `"Denetimli Hidrostatik Test İş Akışı"` metnini arıyor.
- v2.1.0 sadeleştirmesinde bu başlık `webapp/frontend/src` içinden kaldırıldı (`grep` sonuç yok); Dashboard artık `"Yeni Kesit 1"` H1'i ve 4 katmanlı özet gösteriyor.
- Canlı koşu: **11/12 PASS**, yalnız `dashboard` FAIL (`h1="Yeni Kesit 1"`, `greeting=false`).
- Test CI'da çalışmadığı için bu sapma sürümde görünmedi.

**Etki**
Smoke testi, ürün regresyonu ile testin kendi eskimesini ayırt edemiyor; "12/12 PASS" iddiası v2.1.0 için yanlış.

**Öneri**
- Dashboard kontrolünü yeni yapıya göre güncelle (ör. 4 adımlı ilerleme çubuğu `aria-label="Test değerlendirme adımları"` veya H1)`.
- `verify-tabs` için CI'da ayrı, sunucu ayağa kaldıran bir smoke job'ı ekle. **Efor: S.**

---

## 5. Doğrulanan Olumlu Noktalar

- **Güvenlik varsayılanı doğru:** loopback dışı bind `HYDRO_ALLOW_REMOTE=1` olmadan reddediliyor; uygulanmayan `HYDRO_AUTH_MODE` başlatmayı durduruyor (`core/config.py:246-254`).
- **Form eşzamanlılığı uçtan uca:** `If-Match`/gövde `revision` + 409 `revision_conflict` + istemci diff modalı; testlerle korunuyor.
- **Büyük dosya yolu sağlamlaştırılmış:** geçici dosyaya akış, 2 eşzamanlılık, 500 MB üst sınır, 32 MB JSON gövde kapısı.
- **Export/arşiv disiplini:** 24 saat TTL, periyodik budama, disk tempfile + background unlink.
- **Admin token:** Docker için `X-Hydro-Admin-Token` UI + `sessionStorage`; backend `hmac.compare_digest`.
- **OpenAPI dosyası canlı şemayla birebir:** `dump_openapi --check` PASS.
- **Yeni testler:** onboarding/tur için 2 kullanıcı akışı testi, OCR timeout/unmount testi, DB admin token testi; v2.1.0'da 020/022 bağımsız kabul hesabı için `test_dossier.py`/`test_coefficients.py` genişletildi (253 pytest).
- **Canlı smoke:** 11/12 sekme (Dashboard beklentisi eski, F29), health `ok` / `version=2.1.0`, OCR `vision`, Alembic `0003`, `SELF_TEST_OK`.

---

## 6. Kapsam Dışı ve Doğrulanmayanlar

- Masaüstü Tkinter arayüzü ve `hidrostatik_test/ui/*` derinlemesine incelenmedi; yalnız test çalıştırma davranışı gözlendi.
- Docker imajı ve Postgres bağlantısı çalıştırılmadı; F4/F23 kod ve doküman karşılaştırmasına dayanır.
- Tarayıcı testi 1000×700 görünümde yapıldı; 375 px mobil ve Safari/Firefox anchor davranışı ayrıca doğrulanmadı.
- OCR kalibrasyonu (gerçek 74 sayfa) bu turda yeniden koşturulmadı; yalnız birim testleri çalıştırıldı.
- v2.1.0'ın 020/022 bağımsız kabul hesapları (`dossier.py`, `form_details.py`) testlerle koşuldu ancak formül/kabul kriterleri bu raporda satır satır denetlenmedi; ayrı bir şartname denetimi gerekir.

---

## 7. Yol Haritası

### Hemen (1–2 gün)
1. **F28:** `ruff format` uygula ve `main` Lint iş akışını yeşile çevir.
2. **F29:** `verify-tabs` Dashboard beklentisini v2.1.0'a güncelle.
3. **F18:** Tur anchor fallback + mobil çekmece entegrasyonu.
4. **F19:** `generate-sample` rate limit + demo proje tekrar kullanımı.
5. **F20:** Onboarding hata yolunda proje temizliği.
6. **F21:** Yazma modellerini `StrictWriteModel`'e taşı.
7. ~~**F27:** Doküman test sayılarını eşitle.~~ *(v2.1.0'da yapıldı; DURUM 148,3 kB notu bu raporla düzeltildi)*

### Kısa vade (1 hafta)
8. **F22:** CI'ya `dump_openapi --check` + `check:api` + `verify-tabs`.
9. **F25:** Tk testlerini ayrı süreç/job'a al.
10. **F24:** OCR arka plan işi için görünür durum veya iptal kararı.
11. **F26:** Yardım turu ile onboarding'i birleştir.

### Kurumsal dağıtım
10. **F23:** Postgres CI job'ı + `psycopg[binary]`; aksi halde "SQLite only" ilanı.
11. Auth/OIDC + iki kişi onay politikası (mimari karar bekliyor).

---

## 8. Doğrulama Komutları (bu raporda çalıştırıldı)

```bash
# Python kalite kapıları
python3 -m ruff check . && python3 -m ruff format --check .
python3 -m mypy hidrostatik_test/domain/
python3 -m mypy --ignore-missing-imports webapp/backend/app

# Web backend + kapsam
python3 -m coverage run --source=webapp/backend/app -m pytest webapp/backend/tests -q \
  -W default::sqlalchemy.exc.SAWarning
python3 -m coverage report --fail-under=80

# OCR birim testleri
python3 -m unittest tests.test_report_ocr

# Masaüstü (Tk sınıfı hariç güvenilir koşu)
python3 -m unittest tests.test_ui_workflow
python3 -m unittest tests.test_download_dialog

# OpenAPI sözleşmesi
python3 -m webapp.backend.app.tools.dump_openapi --check

# Frontend
cd webapp/frontend
npm run lint && npm run typecheck && npm test
npm run build && npm run check:bundle && npm run check:api

# Canlı smoke (ayrı terminalde sunucu 8099'da)
HYDRO_APP_URL=http://127.0.0.1:8099 node scripts/verify-tabs.mjs
python3 webapp/desktop_launcher.py --self-test
```

---

## 9. Sonuç

HYDRO v2.1.0, hesap çekirdeği ve API katmanında önceki sürümlere göre belirgin şekilde daha sağlam. v3'teki 17 bulgunun 10'u kapanmış; kalanların çoğu artık "eksik özellik" değil, **sözleşme disiplini, kaynak sınırları ve test izolasyonu** başlıklarına kaymış durumda. v2.1.0 ayrıca kabul formlarında okunan/hesaplanan ayrımını getiriyor ve bunu 253 testle koruyor.

Sürümün vitrin özelliği olan rehberli tur geniş ekranda amacına uygun; ancak dar ekran anchor davranışı (F18) ve örnek proje üretiminin sınırsız/tekrarlı olması (F19) ilk kullanıcı deneyimindeki iki somut P2 olmayı sürdürüyor. Buna ek olarak HEAD'de `ruff format --check` (F28) ve `verify-tabs` (F29) kapıları kırmızı; ikisi de küçük eforla kapatılabilir. Bunlar giderildiğinde v2.1.x için "kararlı" demek için ek engel kalmaz; kurumsal dağıtım için Postgres doğrulaması ve Auth/OIDC kararı beklenmeye devam eder.
