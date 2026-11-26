# HYDRO — İyileştirme Önerileri (v2)

> **Tarih:** 26 Kasım 2026
> **Baseline:** `main` @ `d99ff9d` (`hidrostatik-test-v2.1.1`; `R1–R26` uygulama dalgası). Plan ilk olarak `b8fafe7` üzerinde hazırlandı; aşağıdaki b8fafe7 ölçümleri o anlık görüntüyü korur.
> **Kapsam:** Web backend (FastAPI), web frontend (React/Vite), OCR/rapor hattı, masaüstü test/CI, dağıtım ve operasyon.
> **Girdi:** [`improvement_recommendations_v1.md`](improvement_recommendations_v1.md), [`analysis_report_v4.md`](analysis_report_v4.md) (F1–F29), güncel kalite kapıları ve kod incelemesi.
> **Amaç:** v1'deki R1–R18'in gerçek durumunu kapatmak; kalan işleri ve v2.1.1 ile ortaya çıkan üretim boşluklarını yeniden önceliklendirmek.
> **Güncel durum:** [`analysis_report_v5.md`](analysis_report_v5.md) — F18–F29 kapandı; güncel ölçümler 289 pytest / %83 kapsam / 83 Vitest / 96 path / 744 masaüstü test. R19–R26 durumu §5'te işaretlendi.

---

## 1. Yönetici Özeti

> **Okuma notu:** Bu bölüm planın `b8fafe7` anındaki gerekçesini korur. `d99ff9d` sonrası güncel durum için §3 ve [`analysis_report_v5.md`](analysis_report_v5.md) esas alınmalıdır; R19–R26 uygulama durumu §5 tablosunda işaretlidir.

v2.1.1, v1 raporundaki 18 önerinin **4'ünü tamamen**, **14'ünü kısmen** uyguladı. Öne çıkanlar:

- **R1/R5:** CI'da gerçek tarayıcı smoke job'ı var (`test.yml:186`), `verify-tabs` artık 12 rota + temel E2E akışı ve yatay taşma kontrolü yapıyor.
- **R2:** `scripts/release_gate.py` eklendi; sürüm 7 dosyada eşitleniyor (`--version-only` PASS).
- **R3:** Kalıcı, DB tabanlı OCR worker (`0004`, lease/heartbeat/retry/cancel, Postgres `SKIP LOCKED`) eklendi.
- **R4:** OIDC PKCE + `HttpOnly` oturum + `operator/supervisor/admin` RBAC + iki kişi onayı (`0005`, `ApprovalsCard`) eklendi.
- **R6/R7/R8/R9:** Tur kalıcılığı + demo rozeti + demo silme, form otomatik taslağı, `axe-core` bileşen testleri, LTTB grafik örnekleme geldi.
- **R11/R16/R17:** OpenAPI → TypeScript tipleri ve sözleşme envanteri kapıya bağlandı; Tk testleri CI'da ayrı koşuyor; pre-commit + `Makefile` + Dependabot var.

Buna karşın **üretim güvenilirliğini doğrudan etkileyen boşluklar** sürüyor:

1. **Dokümanlar ürünün gerisindeydi; bu raporda senkron edildi.** `DURUM.md`, `README.md` ve `implementation_status.md` 255 pytest / 67 Vitest / 87 path / 148,8 kB ve "Auth/OIDC yok" diyordu; v2 hazırlanırken 269 / 77 / 94 / 149,8 kB ve OIDC ile güncellendi. `analysis_report_v4.md` tarihsel v2.1.0 anlık görüntüsü olarak banner ile işaretlendi; kalıcı çözüm otomatik üretim (R24).
2. **CI smoke tek viewport'ta ve E2E sığ.** Matris kodu var ama CI `--matrix` çalıştırmıyor; E2E yalnız örnek proje → form/rapor rotası açılışını kontrol ediyor, form doldurup kaydetmiyor.
3. **Büyük veri sanallaştırması yok.** LTTB geldi, ancak uzun tablolar için `@tanstack/react-virtual` benzeri sanallaştırma hâlâ yok.
4. **Yönetici token'ı `sessionStorage`'da.** XSS durumunda okunabilir; Python tarafında `pip-audit`, repoda secret taraması yok.
5. **OCR worker üretimde açık değil.** `docker-compose.yml` içindeki `ocr-worker` servisi yorum satırında; mimari dokümanı hâlâ "süreç-içi `ThreadPoolExecutor`" diyor.
6. **Yedek tatbikatı yalnız SQLite ve manuel.** Zamanlanmış yedek, saklama politikası, Postgres restore provası yok.
7. **Kapsam %83 → %82'ye düştü.** Yeni OCR/auth kodu test edildi, ancak genel kapıya göre marj 2 puan; kritik modüller için modül bazlı eşik yok.

**Sonuç:** v2.1.1 işlevsel olarak v1'in ana ajandasını kapattı. Sıradaki yatırım "yeni özellik" değil; **doküman doğruluğu, CI kapsamı, OCR/auth üretim operasyonları, büyük veri ve yedek/ölçek** başlıklarında. En yüksek getirili ilk beş iş: **R21 (CI matris + derin E2E), R24 (doküman tek kaynak), R19 (OCR worker ops), R20 (OIDC ops), R9 (sanallaştırma)**.

---

## 2. Plan Baseline Ölçümleri (26 Kasım 2026, `b8fafe7` — tarihsel)

| Kapı | Komut | Sonuç |
| --- | --- | --- |
| Ruff lint | `python3 -m ruff check .` | **PASS** |
| Ruff format | `python3 -m ruff format --check .` | **PASS** — 166 dosya biçimli |
| Mypy (domain) | `python3 -m mypy hidrostatik_test/domain/` | **PASS** — 14 dosya |
| Mypy (web) | `python3 -m mypy --ignore-missing-imports webapp/backend/app` | **PASS** — 56 dosya |
| Backend test | `python3 -m coverage run --source=webapp/backend/app -m pytest webapp/backend/tests -q` | **269 passed**, 1 skipped (Postgres CI-only), 36,9 sn |
| Web kapsam | `python3 -m coverage report --fail-under=80` | **%82** — 13.530 statement, 1.893 miss |
| OCR unittest | `python3 -m unittest tests.test_report_ocr` | **76 OK** (skipped=1) |
| Masaüstü paket | `python3 -m unittest discover -s tests -p "test_*.py"` | **741 OK** (skipped=1), 155 sn |
| OpenAPI | `dump_openapi --check` | **PASS** — 94 path / 109 operation |
| Sözleşme envanteri | `sync_api_inventory.py --check` | **PASS** |
| Frontend lint / typecheck / build | `npm run lint`, `npm run typecheck`, `npm run build` | **PASS** |
| Frontend test | `npm test` | **77 Vitest / 25 dosya** |
| Bundle bütçesi | `npm run check:bundle` | **149,8 kB** ilk JS + **15,4 kB** CSS gzip (≤ 200 kB) |
| İstemci sözleşmesi | `npm run check:api` | **PASS** — 78 şablon / 94 path |
| Üretilen tipler | `npm run check:api-types` | **PASS** |
| Sekme smoke | `verify-tabs.mjs` (1440×900) | **12/12 rota + E2E PASS** |
| Viewport matrisi | `verify-tabs.mjs --matrix --no-e2e` | **36/36 PASS** (375×812, 768×1024, 1440×900) |
| Sürüm kapısı | `scripts/release_gate.py --quick` | **9/9 PASS** (version-parity dahil) |
| Sürüm eşitliği | `scripts/release_gate.py --version-only` | **PASS** — 7 dosyada `2.1.1` |
| Postgres runtime | `test_postgres_runtime.py` | Yerelde **skip**; CI `postgres:16-alpine` işi mevcut |

> Not: Backend pytest ilk paralel koşuda `test_desktop_launcher_self_test_subprocess` ile bir kez düştü; tek başına ve ardışık tam koşuda **269 passed** verdi. Bu, testler arası port/süreç izolasyonu ihtiyacını gösteren bir flake'dir (bkz. R23), ürün regresyonu değildir.

> **Güncel ölçümler (`d99ff9d`):** 289 pytest (1 skipped) / **%83** kapsam; 83 Vitest / 25 dosya; 87 OCR unittest; 744 masaüstü unittest; **96 path / 111 operation**; 149,8 kB ilk JS + 15,4 kB CSS gzip; `release_gate --quick` **10/10**; 4 viewport × 12 rota PASS. Ayrıntı: [`analysis_report_v5.md`](analysis_report_v5.md).

---

## 3. v1 Önerilerinin Durumu (R1–R18)

| ID | Konu | Durum (`d99ff9d`) | Kalan iş |
| --- | --- | --- | --- |
| R1 | CI'da gerçek tarayıcı smoke + E2E | **Tamam (kanıt hariç)** | 4 viewport matrisi + derin E2E var; required-check ve flake ölçümü repodan doğrulanamıyor |
| R2 | Tek komut release gate + sürüm senkronu | **Tamam** | `release.yml` tag öncesi `--quick` çalıştırıyor; 10/10 PASS |
| R3 | Kalıcı, çok-worker OCR worker | **Büyük ölçüde tamam** | Compose `ocr` profili, healthcheck, kuyruk/DLQ/retry var; kuyruk yaşı alarmı ve maliyet ölçümü yok |
| R4 | Auth/OIDC + RBAC + iki kişi onayı | **Tamam** | Üretim operasyonları R20'ye taşındı |
| R5 | Mobil/tablet kabul testleri | **Tamam** | CI matrisi 375/768/1024/1440; tüm rotalar PASS |
| R6 | Tur yaşam döngüsü | **Tamam** | Demo TTL/temizlik ve rozet eklendi |
| R7 | Form doldurma verimliliği | **Tamam** | `beforeunload`, `Ctrl/Cmd+S`, doğrulama özeti ve alana odaklanma eklendi |
| R8 | Erişilebilirlik disiplini | **Kısmi** | Token kontrast testi + azaltılmış hareket var; E2E axe ve `region` taraması yok |
| R9 | Büyük veri performansı | **Tamam** | LTTB + tablo sanallaştırması (`@tanstack/react-virtual`) |
| R10 | Golden/property/mutation testleri | **Kısmi** | Golden 020/022 + OCR F1 korpusu var; mutasyon testi yok |
| R11 | OpenAPI'den tip üretimi + şema diff | **Tamam** | — |
| R12 | Dağıtık hız sınırlayıcı | **Kısmi** | Limiter hâlâ süreç-içi; Redis/proxy kotası yok |
| R13 | Admin token / CSP / tedarik zinciri | **Kısmi** | `pip-audit` + `gitleaks` var; token `sessionStorage`'da, CSP `style-src 'unsafe-inline'` |
| R14 | Gözlemlenebilirlik | **Kısmi** | `/system/metrics` + disk telemetrisi var; scrape/alert/pano yok |
| R15 | Yedekleme ve restore tatbikatı | **Kısmi** | Saklama politikası + Postgres doğrulama tatbikatı var; zamanlanmış yedek/RPO-RTO kaydı yok |
| R16 | Tk testlerini izole et | **Tamam** | CI'da ayrı non-Tk/Tk adımları; paket 744 OK |
| R17 | DX: pre-commit, görev çalıştırıcı | **Tamam** | İsteğe bağlı: eslint/prettier/pip-audit hook'ları |
| R18 | Doküman tek kaynak | **Tamam (kısmi otomasyon)** | Sürüm/şema/OpenAPI bloğu otomatik; test/bundle sayıları senkron ama hâlâ elle |

**Özet:** 10 tamam (R1, R2, R4, R5, R6, R7, R9, R11, R16, R17), 2 büyük ölçüde tamam (R3, R18), 6 kısmi (R8, R10, R12, R13, R14, R15). Kalan işlerin çoğu üretim operasyonu ve kanıt üretimi; yeni özellik değil.

---

## 4. Kalan İşlerin Detayı

### 4.1 CI ve sürüm güvenilirliği (R1, R2, R5)

**Mevcut**
- `test.yml:186-241` gerçek Chrome ile `verify-tabs.mjs` çalıştırıyor; sunucu logu hata durumunda artifact olarak yükleniyor.
- `verify-tabs.mjs` 12 rotada `h1`, `data-page`, yatay taşma ve Dashboard stepper'ını kontrol ediyor; ardından örnek proje → `air_test` → `reports` E2E'sini koşuyor.
- `--matrix` ile 375×812 / 768×1024 / 1440×900 çalışıyor ve yerelde **36/36 PASS**.
- `release_gate.py --quick` 9 adımı (ruff, format, mypy, OpenAPI, envanter, istemci sözleşmesi, tipler) tek komutta koşuyor.

**Kalan**
- CI komutu `--matrix` içermiyor (`test.yml:234`); varsayılan yalnız 1440×900 (`verify-tabs.mjs:29`). 1024×768 hiç yok.
- E2E form doldurup kaydetmiyor, rapor üretmiyor; yalnız rota render'ını doğruluyor (`verify-tabs.mjs:271-330`).
- `release.yml:59` yalnız `--version-only` çağırıyor; tam/quick kapı tag öncesi zorunlu değil.
- Dal koruma kuralları repodan doğrulanamıyor; smoke'un required check olduğu ayrıca teyit edilmeli.

**Öneri**
- CI'da iki smoke işi: hızlı (1440, PR) + gece matrisi (375 / 768 / 1024 / 1440).
- E2E'yi derinleştir: örnek proje → kesit aç → 020 formu doldur → kaydet → rapor önizle → sil.
- `release.yml` içinde tag öncesi `python3 scripts/release_gate.py --quick` zorunlu olsun.
- Başarısızlıkta ekran görüntüsü + trace + sunucu logu artifact'ı.

**Kabul:** PR smoke < 8 dk; matris gece < 25 dk; 20 ardışık koşuda flake < %2; form kaydetme kırılırsa PR kırmızı.

---

### 4.2 OCR ve veri yaşam döngüsü (R3, R6)

**Mevcut**
- `app/worker/ocr.py:44-116` lease, `SKIP LOCKED`, `attempts`, `max_attempts`, `cancel_requested` ve süre aşımı geri kazanımı içeriyor.
- `0004_ocr_worker_queue.py` kuyruk alanlarını ekliyor; `HYDRO_OCR_WORKER_MODE=external` ile web sürecinden ayrılabiliyor.
- Tur durumu artık `partialize` içinde (`useAppStore.ts:520-522`); demo proje rozeti (`TopBar.tsx:197`) ve "demo projeyi temizle" akışı (`GuidedTourOverlay.tsx:148-155`) var.

**Kalan**
- `docker-compose.yml:47-49` OCR worker servisi yorum satırında; standart kurulumda inline mod çalışıyor.
- Worker healthcheck, dead-letter/manuel yeniden kuyruk uçları ve kuyruk yaşı SLO'su yok.
- Terk edilen `DEMO-*` projeler için TTL/temizlik yok; kullanıcı turu yarıda bırakırsa proje kalıyor.
- `webapp/docs/architecture.md:872` hâlâ "OCR kuyruğu süreç-içi" diyor; operatörü yanıltıyor.

**Öneri**
- Compose'da `ocr-worker` profilini (`--profile ocr`) açık ve dokümante et; healthcheck + `restart: unless-stopped`.
- `GET /api/ocr/queue` veya metrikte kuyruk yaşı/deneme dağılımı; 3 denemeyi aşan işler için DLQ görünümü.
- 7 günden eski sahipsiz `DEMO-*` projeleri soft-delete + çöp kutusu bakım job'ı.
- Mimari dokümanındaki kuyruk bölümünü kalıcı worker ile güncelle.

**Kabul:** Worker yeniden başlatıldığında iş kaybı 0; kuyruk p95 bekleme < 30 sn; 7 gün sonra yetim demo proje 0.

---

### 4.3 Ürün deneyimi (R7, R8, R9)

**Mevcut**
- `formDraftStorage.ts` + `SectionFormPage.tsx:169,205` ile form taslağı yerelde saklanıyor ve geri yükleniyor.
- `a11y.test.tsx` tur, TopBar, onboarding ve Dashboard için `axe-core` çalıştırıyor; tur `Esc` ile odağı tetikleyiciye döndürüyor.
- `lib/downsample.ts` LTTB ile grafik noktalarını azaltıyor; `Charts.tsx` bunu kullanıyor.

**Kalan**
- Kaydedilmemiş değişiklikte `beforeunload` uyarısı ve `Ctrl/Cmd+S` yok; taslak yalnız otomatik.
- Alan bazlı "eksik/hatalı" özeti ve tıklayınca alana gitme yok.
- `a11y.test.tsx:14-15` `color-contrast` ve `region` kurallarını kapatıyor; kontrast hiç ölçülmüyor, E2E axe yok.
- Uzun time-series/audit tablolarında sanallaştırma yok (`react-virtual` bağımlılığı yok); LTTB yalnız grafikte.
- Mobil matris 1024×768'i kapsamıyor; 375 px'te tablo taşmaları yalnız smoke ile sınırlı.

**Öneri**
- `beforeunload` + uygulama içi geçiş uyarısı; `Ctrl/Cmd+S`; `Esc` dialog kapatma; taslak için 1–2 sn debounce.
- Form üstünde doğrulama özeti; hatalı alana odaklanan bağlantılar.
- Ayrı `a11y-contrast` testinde kontrastı aç; `@axe-core/playwright` ile 5 kritik ekranda E2E tarama.
- `@tanstack/react-virtual` ile time-series, audit ve büyük form tabloları; 2.000+ noktada LTTB eşiği belgele.
- Matrise 1024×768 ekle; 375 px'te yatay taşma testini tablo bazında genişlet.

**Kabul:** 10.000 satırlık tablo < 200 ms açılır ve 60 fps kaydırır; axe serious/critical 0 (kontrast dahil); kaydedilmemiş değişiklikte sekme kapatma uyarısı test edilir.

---

### 4.4 Test ve sözleşme (R10, R18)

**Mevcut**
- `test_property_invariants.py` Hypothesis ile domain değişmezlerini kontrol ediyor.
- `gen:api-types` + `check:api-types` ve `sync_api_inventory.py --check` CI'da bloklayıcı.
- `api_contract.md` OpenAPI envanteri otomatik güncelleniyor.

**Kalan**
- Resmi `.xls` formlarından türetilmiş golden korpus ve mutasyon testi yok; 020/022 bağımsız kabul hesabı hâlâ örnek tabanlı.
- OCR için sabit regresyon korpusu ve alan çıkarımı F1 eşiği yok.
- Test/bundle/sürüm sayıları DURUM, README ve `implementation_status` içinde elle tutuluyor; v2 hazırlanırken senkron edildi ancak otomatik üretim yok.
- `analysis_report_v4.md` v2.1.0 bazlı tarihsel anlık görüntüdür; güncel durum `analysis_report_v5.md` ile belgelendi (F18–F29 kapanışı + R19–R26 durumu).

**Öneri**
- `webapp/backend/tests/golden/` altında resmi form revizyonlarından girdi → beklenen A/B/Vp/PT ve bulgu dosyaları; CI'da zorunlu.
- `dossier`/`form_details` için hedefli mutasyon testi (`mutmut` veya `cosmic-ray`), skor eşiği ≥ %70.
- OCR için 5–10 sayfalık sabit korpus; alan bazlı precision/recall raporu.
- `release_gate` çıktısından dokümanlara otomatik sayı bloğu yaz (`<!-- generated:metrics -->`); `analysis_report_v5.md` ile v2.1.1 durumunu kapat.

**Kabul:** Hedef modüllerde satır kapsamı ≥ %90, mutasyon ≥ %70; dokümanlarda elle tutulan test/bundle sayısı 0.

---

### 4.5 Güvenlik ve operasyon (R12, R13, R14, R15)

**Mevcut**
- `RateLimiter` süreç-içi; `run_web.py:87-110` çok worker'ı açıkça reddediyor/tek worker'a sabitliyor.
- `npm audit --omit=dev --audit-level=high` CI'da; CSP `object-src 'none'`, `frame-ancestors 'none'` içeriyor.
- `/system/metrics` JSON + Prometheus formatında; istek sayısı, gecikme, yavaş sorgu ve OCR kuyruğu veriyor; yerel admin korumalı.
- `scripts/backup_drill.py` SQLite yedeğini geçici dizinde açıp migration ve bütünlük kontrolü yapıyor.

**Kalan**
- Limiter çok worker/çok örnek durumunda limitleri çarpar; Redis veya ters proxy kotası yok.
- Yönetici token'ı `api.ts:179` `sessionStorage`'da; `pip-audit`, `gitleaks`/secret scan yok; CSP'de `style-src 'unsafe-inline'` sürüyor.
- Metrikler için scrape, eşik alarmı ve operasyon panosu yok.
- Yedek tatbikatı yalnız SQLite; zamanlanmış yedek, 7/30/90 saklama ve Postgres restore provası yok.
- Postgres CI'da doğrulanıyor, ancak yerel geliştirme varsayılanı SQLite; çok worker + pool ayarları üretimde denenmedi.

**Öneri**
- Çok worker açılacaksa limiterı Redis'e taşı veya ters proxy'de workspace bazlı kota uygula; `429` ve `Retry-After` sözleşmesini koru.
- Yönetici işlemleri için kısa ömürlü, `HttpOnly` oturum/tek kullanımlık token; `sessionStorage`'ı kaldır.
- CI'ya `pip-audit` ve `gitleaks`; kritik bulguda build'i durdur. CSP'yi nonce/hash'e taşımayı değerlendir.
- Prometheus scrape + temel alarmlar (5xx oranı, p95, OCR kuyruk yaşı, disk, yedek yaşı).
- Günlük otomatik yedek + saklama politikası + aylık Postgres restore tatbikatı; RPO ≤ 24 sa, RTO ≤ 1 sa.

**Kabul:** 2 worker'lı testte limit aşılamaz; yönetici token'ı JS'ten okunamaz; yedek/restore başarısızlığı alarm üretir; Postgres restore tatbikatı dokümante edilir.

---

## 5. Yeni Öneriler (R19–R26)

| ID | Öneri | Alan | Etki | Efor | Öncelik | Durum (`d99ff9d`) |
| --- | --- | --- | --- | --- | --- | --- |
| R19 | OCR worker üretim operasyonları (compose, health, DLQ, SLO) | Operasyon | Yüksek | M | **P0** | **Büyük ölçüde tamam** — alarm/maliyet ölçümü kaldı |
| R20 | OIDC/RBAC üretim operasyonları (claim eşleme, revocation, login audit, MFA) | Güvenlik | Çok yüksek | L | **P0** | **Kısmi** — MFA/step-up ve onay bildirimi kaldı |
| R21 | CI viewport matrisi + derin E2E + required check | CI / test | Yüksek | M | **P0** | **Büyük ölçüde tamam** — required-check/flake kanıtı kaldı |
| R22 | Erişilebilirlik: kontrast + E2E axe + odak tuzağı | UX / a11y | Orta | M | P1 | **Kısmi** — E2E axe kaldı |
| R23 | Test süresi/flake: paralel koşu, port izolasyonu, sharding | Test | Orta | M | P1 | **Kısmi** — marker ayrımı/sharding kaldı |
| R24 | Doküman tek kaynak + `analysis_report_v5` | Doküman | Yüksek | S | **P0** | **Tamam** |
| R25 | Tedarik zinciri + admin token sertleştirmesi | Güvenlik | Yüksek | M | P1 | **Kısmi** — admin token/CSP kaldı |
| R26 | Postgres/ölçek ve yedek otomasyonu | Operasyon | Yüksek | L | P1 | **Kısmi** — zamanlanmış yedek/restore tatbikatı kaldı |

### R19 — OCR worker üretim operasyonları

**Neden:** Kalıcı worker kodu var, ancak standart Docker kurulumunda kapalı; operatör "iş nerede" sorusunu yalnız OCR ekranından yanıtlıyor. 300 DPI + deskew + çok sayfalı PDF maliyeti arttı.

**Yapılacak**
- Compose'da `ocr-worker` servisini profil ile aç; healthcheck, kaynak limiti ve log rotasyonu ekle.
- `queued/running/failed` sayıları, en eski iş yaşı ve deneme dağılımı için metrik; eşik alarmı.
- 3 denemeyi aşan işler için DLQ listesi + "yeniden kuyruğa al" uçları.
- 300 DPI/deskew açık/kapalı maliyet ölçümü; sayfa başına süre ve bellek tavanı.

**Kabul:** Worker restart'ında iş kaybı 0; kuyruk p95 < 30 sn; başarısız iş operatör tarafından görünür ve yeniden denenebilir.

### R20 — OIDC/RBAC üretim operasyonları

**Neden:** OIDC PKCE, `HttpOnly` çerez, rol hiyerarşisi ve iki kişi onayı kodda var; kurumsal işletim için kimlik yaşam döngüsü eksik.

**Yapılacak**
- `groups`/`roles` claim → uygulama rolü eşlemesini yapılandırılabilir yap ve dokümante et.
- Oturum iptali/merkezi çıkış (revocation list veya kısa TTL + refresh), idle timeout testleri.
- Giriş/çıkış, rol değişimi ve onay kararlarını audit kaydına ekle; onay listesine sayfalama/filtre.
- Yönetici ve `db_restore` için MFA/step-up; onay isteği bildirimi ve son kullanma süresi.

**Kabul:** Yetkisiz kullanıcı proje verisi göremez; kendi isteğini onaylayamaz (mevcut); iptal edilen oturum sonraki istekte `401` alır; tüm onay kararları audit'te aktörleriyle görünür.

### R21 — CI viewport matrisi + derin E2E + required check

**Neden:** Matris kodu yerelde 36/36 geçiyor, ancak CI yalnız 1440×900 ve sığ E2E koşuyor; bu yüzden v2.1.0'daki Dashboard kırılması ancak elle yakalandı.

**Yapılacak**
- PR'da hızlı smoke (1440), gece 375/768/1024/1440 matrisi.
- E2E: örnek proje → kesit → 020 formu doldur → kaydet → rapor önizle → sil.
- Trace, ekran görüntüsü ve sunucu logunu artifact yap; smoke'u required check işaretle.
- 20 ardışık koşuda flake ölçümü.

**Kabul:** Matris CI'da yeşil; form kaydetme veya rapor üretimi kırılırsa PR kırmızı; flake < %2.

### R22 — Erişilebilirlik: kontrast + E2E axe + odak tuzağı

**Neden:** Bileşen testi `color-contrast` ve `region` kurallarını kapatıyor; gerçek kontrast ve tam sayfa yapısı ölçülmüyor.

**Yapılacak**
- Kontrastı ayrı testte aç; tasarım token'ları için eşik belirle.
- Playwright + `@axe-core/playwright` ile Dashboard, Projeler, Form, OCR, Raporlar.
- Dialog/tur için odak tuzağı, ilk/son öğe döngüsü ve kapanışta odağın tetikleyiciye dönüşü.
- `prefers-reduced-motion` ve ikon-only düğme etiketleri.

**Kabul:** 5 kritik ekranda serious/critical ihlal 0 (kontrast dahil); tur klavye ile baştan sona tamamlanır.

### R23 — Test süresi, izolasyon ve flake

**Neden:** Masaüstü paketi 741 test / 155 sn; backend pytest paralel çalışan masaüstü paketiyle bir kez `desktop_launcher` testinde düştü. CI matrisi 6 kombinasyon × tam paket.

**Yapılacak**
- Testleri `ui`, `domain`, `web`, `slow` marker'larına ayır; PR'da hızlı alt küme, gece tam koşu.
- `desktop_launcher`/port kullanan testlerde rastgele port + `tmp_path`; paralel koşuda çakışma yok.
- Masaüstü paketini ikiye böl (Tk / non-Tk zaten ayrı) ve süre bütçesi koy.
- CI'da `pytest -n auto` veya `unittest` sharding değerlendir.

**Kabul:** PR geri bildirimi < 10 dk; 20 ardışık tam koşuda flake 0; testler sıra bağımsız.

### R24 — Doküman tek kaynak + `analysis_report_v5`

**Neden:** Ölçümler ve özellik durumu dört dosyada kaymıştı: DURUM 255/67/87/148,8 ve "Auth yok"; README 253/63/725; `implementation_status` 255/67/148,8 ve "Auth yok"; `analysis_report_v4` v2.1.0/F28-F29 açık. Bu v2 hazırlanırken ilk üç dosya 269/77/94/149,8 + OIDC ile senkron edildi; kalan risk, sayıların yine elle kayması ve tarihsel denetim raporunun güncel sanılması.

**Yapılacak**
- `release_gate` çıktısından üretilen `metrics` bloğunu DURUM/README/`implementation_status` içine yaz.
- `analysis_report_v5.md` ile v2.1.1 durumunu, kapanan F18–F29'u ve yeni R19–R26'yı belgele.
- `architecture.md` OCR worker/kuyruk bölümünü güncelle.
- Sürüm notu kontrol listesine "doküman sayıları" maddesi ekle.

**Kabul:** Dört dosyada test/bundle/path sayıları aynı; "Auth yok" ifadesi kalmaz; sürümde doküman farkı 0.

### R25 — Tedarik zinciri + admin token

**Neden:** `npm audit` var, Python tarafı ve secret taraması yok; admin token'ı `sessionStorage`'da.

**Yapılacak**
- CI'ya `pip-audit` ve `gitleaks`; kritik bulguda durdur.
- Admin token'ı kısa ömürlü `HttpOnly` oturuma taşı; JS'ten okunamaz yap.
- CSP'de `style-src 'unsafe-inline'` bağımlılığını gözden geçir; nonce/hash yolunu değerlendir.
- Pre-commit'e secret scan ve frontend lint/format ekle.

**Kabul:** Kritik bağımlılık/secret bulgusu merge'i engeller; admin token'ı devtools'tan okunamaz.

### R26 — Postgres/ölçek ve yedek otomasyonu

**Neden:** Postgres CI'da doğrulanıyor, ancak çok worker, bağlantı havuzu ve restore provası üretimde denenmedi; yedek tatbikatı SQLite ve manuel.

**Yapılacak**
- Postgres'te 2 web worker + 1 OCR worker smoke; pool boyutu ve `SKIP LOCKED` davranışı.
- Günlük otomatik yedek + 7/30/90 saklama; yedek yaşı metriği ve alarmı.
- Aylık Postgres restore tatbikatı; RPO/RTO ölçümü.
- Disk dolma eşiğinde yazma guard'ı ve uyarı.

**Kabul:** 2 worker'da kuyruk/limit tutarlı; RPO ≤ 24 sa, RTO ≤ 1 sa tatbikatla doğrulanır.

---

## 6. 90 Günlük Yol Haritası

> **Güncelleme (`d99ff9d`):** 0–2 hafta kalemleri (R24, R21, R2) tamamlandı. 2–6 hafta kalemlerinden R9, R7 ve R19 büyük ölçüde tamam; R22, R10 ve R23 kısmi. 6–12 hafta kalemlerinden R20, R25 ve R26 kısmi; R14 planlı.

### 0–2 hafta
- **R24** doküman senkronu + `analysis_report_v5`.
- **R21** CI matrisi ve smoke'un required check olması.
- **R2** `release_gate --quick` adımının tag öncesi zorunlu hale getirilmesi.

### 2–6 hafta
- **R19** OCR worker compose/health/DLQ.
- **R9** tablo sanallaştırması; **R7** kaydedilmemiş değişiklik uyarısı.
- **R22** kontrast + E2E axe.
- **R10** golden korpus + hedefli mutasyon testleri.
- **R23** test marker/paralel koşu.

### 6–12 hafta
- **R20** OIDC claim eşleme, revocation, login audit, MFA/step-up.
- **R25** admin token + `pip-audit`/secret scan.
- **R26** Postgres çok worker + yedek otomasyonu + restore tatbikatı.
- **R14** Prometheus scrape + alarmlar.

### Sürekli
- Aylık bağımlılık PR'ları ve güvenlik taraması.
- Üç aylık restore tatbikatı ve erişilebilirlik taraması.
- Sürüm öncesi `release_gate` + doküman sayı kontrolü.

---

## 7. Başarı Ölçütleri (KPI)

| Alan | KPI | Hedef |
| --- | --- | --- |
| CI | Required check yeşil oranı | ≥ %98 |
| CI | Smoke matrisi (375/768/1024/1440) | 4/4 yeşil |
| CI | PR geri bildirim süresi | < 10 dk |
| CI | Flake oranı (20 koşu) | < %2 |
| Test | Genel web kapsamı | ≥ %85 |
| Test | OCR/auth/dossier modül kapsamı | ≥ %90 |
| Test | Hedefli mutasyon skoru | ≥ %70 |
| OCR | Restart sonrası iş kaybı | 0 |
| OCR | Kuyruk bekleme p95 | < 30 sn |
| UX | 375 px kritik ekranlarda yatay taşma | 0 |
| a11y | axe serious/critical (kontrast dahil) | 0 |
| Perf | 10k satır time-series açılış | < 200 ms |
| Perf | İlk yükleme JS | ≤ 160 kB gzip |
| Güvenlik | Kritik bağımlılık/secret bulgusu | 0 açık |
| Operasyon | RPO / RTO | ≤ 24 sa / ≤ 1 sa |
| Doküman | Sayı/özellik uyuşmazlığı | 0 |

---

## 8. Bilinçli Olarak Önerilmeyenler

- **Mikroservislere bölme / Kubernetes:** Tek uygulama + ayrı OCR worker bu ölçek için yeterli; operasyonel maliyet kazancı aşar.
- **Tam offline-first çift yönlü senkron:** Mevcut taslak/çevrimdışı uyarı yeterli; çakışma çözümü domain karmaşıklığını artırır.
- **Masaüstü Tkinter'ı yeniden yazma:** Web ana ürün; masaüstü kritik regresyon ve paketleme için korunmalı.
- **Erken i18n / native mobil uygulama:** Tek dil ve responsive web + PWA yeterli; talep doğrulanmadan yatırım yapılmamalı.
- **Tam otomatik demo veri üretimini kaldırma:** Tur için değerli; yalnız TTL/temizlik ve görünür rozet eklenmeli.

---

## 9. Sonuç

v2.1.1, v1'in ana mühendislik ajandasını (CI smoke, release gate, kalıcı OCR worker, OIDC/RBAC, tur yaşam döngüsü, tipler, Tk izolasyonu) büyük ölçüde kapattı. Ancak üretim olgunluğu için kritik olan **doküman doğruluğu, CI matrisi/derin E2E, OCR/auth operasyonları, büyük veri ve yedek/ölçek** hâlâ açık.

İlk iki haftada **R24 + R21** tamamlanırsa sürüm güvenilirliği ölçülebilir hale gelir; ardından **R19 + R20** kurumsal işletim omurgasını kurar. Ürün tarafında **R7 + R9 + R22**, sahadaki operatörün günlük verimliliğini ve erişilebilirliğini doğrudan artırır.
