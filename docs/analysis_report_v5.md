# HYDRO — v2.1.1 Durum ve Kapanış Raporu (v5)

> **Tarih:** 26 Kasım 2026
> **Baseline:** `main` @ `d99ff9d` (`hidrostatik-test-v2.1.1`)
> **Kapsam:** Web backend (FastAPI), web frontend (React/Vite), OCR/rapor hattı, masaüstü test/CI, dağıtım ve operasyon.
> **Yöntem:** Kalite kapılarının HEAD'de yeniden çalıştırılması, kaynak kod okuma, gerçek tarayıcı smoke + 4 viewport matrisi, release gate ve doküman metrik kontrolü.
> **Kanıt standardı:** Her sonuç komut çıktısı, `dosya:satır` veya commit ile desteklenir. Doğrulanamayanlar açıkça "doğrulanmadı" olarak işaretlenir.
> **Önceki rapor:** [`analysis_report_v4.md`](analysis_report_v4.md) v2.1.0 (`1a379ee`) anlık görüntüsüdür ve tarihsel kayıt olarak korunur. Aktif plan [`improvement_recommendations_v2.md`](improvement_recommendations_v2.md)'dir.

---

## 1. Yönetici Özeti

v2.1.1, v4 raporundaki **F18–F29 bulgularının tamamını kapatmış** ve v2 planındaki **R19–R26 başlıklarının büyük bölümünü** uygulamış durumda. HEAD `d99ff9d` üzerinde çalıştırılan kapılar yeşil:

- **289 backend pytest** (1 skipped: Postgres CI-only), **%83** kapsam.
- **83 Vitest / 25 dosya**, lint/typecheck/build/bundle PASS.
- **87 OCR unittest** (1 skipped), **744 masaüstü unittest OK** (1 skipped).
- **96 OpenAPI path / 111 operation**, sözleşme envanteri ve istemci sözleşmesi (78/96) PASS.
- **4 viewport × 12 rota** gerçek tarayıcı smoke PASS; derin E2E örnek proje → 020 formu doldur/kaydet → rapor önizleme → TXT dışa aktarma → proje silme akışını doğruluyor.
- `release_gate.py --quick` **10/10 PASS**, sürüm 7 dosyada `2.1.1`.

Kapanan başlıca üretim boşlukları: OCR worker'ın compose profili + healthcheck + kuyruk/DLQ uçları, OIDC rol eşlemesi + oturum iptali + onay sayfalama, 4 viewport CI matrisi, doküman metrik otomasyonu, `pip-audit`/`gitleaks`, yedek saklama ve Postgres doğrulama tatbikatı.

**Kalan riskler** yeni özellik değil, üretim işletimiyle ilgili: MFA/step-up yok, admin token'ı hâlâ `sessionStorage`'da, E2E axe taraması yok, iki worker'lı Postgres smoke ve 20 koşuluk flake ölçümü yapılmadı, CI required-check ayarı repodan doğrulanamıyor.

---

## 2. Ölçümler (26 Kasım 2026, `d99ff9d`)

| Kapı | Komut | Sonuç |
| --- | --- | --- |
| Ruff lint | `python3 -m ruff check .` | **PASS** |
| Ruff format | `python3 -m ruff format --check .` | **PASS** — 166 dosya biçimli |
| Mypy (domain) | `python3 -m mypy hidrostatik_test/domain/` | **PASS** — 14 dosya |
| Mypy (web) | `python3 -m mypy --ignore-missing-imports webapp/backend/app` | **PASS** — 56 dosya |
| Backend test | `python3 -m coverage run --source=webapp/backend/app -m pytest webapp/backend/tests -q` | **289 passed**, 1 skipped (Postgres CI-only), 42 sn |
| Web kapsam | `python3 -m coverage report --fail-under=80` | **%83** — 13.698 statement, 1.790 miss |
| OCR unittest | `python3 -m unittest tests.test_report_ocr` | **87 OK** (skipped=1) |
| Masaüstü paket | `python3 -m unittest discover -s tests -p "test_*.py"` | **744 OK** (skipped=1), 44,5 sn |
| OpenAPI | `dump_openapi --check` | **PASS** — 96 path / 111 operation |
| Sözleşme envanteri | `sync_api_inventory.py --check` | **PASS** |
| Frontend lint / typecheck / build | `npm run lint`, `npm run typecheck`, `npm run build` | **PASS** |
| Frontend test | `npm test` | **83 Vitest / 25 dosya** |
| Bundle bütçesi | `npm run check:bundle` | **149,8 kB** ilk JS + **15,4 kB** CSS gzip (≤ 200 kB) |
| İstemci sözleşmesi | `npm run check:api` | **PASS** — 78 şablon / 96 path |
| Üretilen tipler | `npm run check:api-types` | **PASS** |
| Sekme smoke | `verify-tabs.mjs` (1440×900) | **12/12 rota + E2E PASS** |
| Viewport matrisi | `verify-tabs.mjs --matrix` | **4 viewport × 12 rota PASS** (375×812, 768×1024, 1024×768, 1440×900) + E2E |
| Sürüm kapısı | `scripts/release_gate.py --quick` | **10/10 PASS** (doc-metrics dahil) |
| Sürüm eşitliği | `scripts/release_gate.py --version-only` | **PASS** — 7 dosyada `2.1.1` |
| Doküman metrikleri | `python3 scripts/sync_doc_metrics.py --check` | **PASS** — DURUM.md canlı kaynaklarla eşit |
| Postgres runtime | `test_postgres_runtime.py` | Yerelde **skip**; CI `postgres:16-alpine` işi mevcut |

> Not: Masaüstü paketi bu ölçümde 44,5 sn'de tamamlandı; v4'teki 155 sn'lik süre Tk teardown/izolasyon düzeltmeleri ve test düzeniyle açıklanır. Süre bütçesi R23 kapsamında ayrıca izlenmelidir.

---

## 3. v4 Bulgularının Kapanışı (F18–F29)

| ID | Bulgu | Durum | Kanıt |
| --- | --- | --- | --- |
| F18 | Rehberli tur <1024 px'te hedefsiz kalıyor | **Kapandı** | `GuidedTourOverlay.tsx:10-24` 1024 px altında anchor döndürmüyor; popover ekran içinde konumlanıyor |
| F19 | Örnek proje üreticisi limitsiz/tekrarlı | **Kapandı** | `api/projects.py:63` `generate-sample` için 5/60 sn rate limit |
| F20 | Onboarding kısmi hatası sahipsiz demo proje bırakıyor | **Kapandı** | Demo turu hata yolunda `deleteProject` temizliği |
| F21 | Yazma modelleri `extra="ignore"` | **Kapandı** | `schemas.py:39-40` `StrictWriteModel` + `extra="forbid"` |
| F22 | Sözleşme dokümanı/CI kapıları eksik | **Kapandı** | `lint.yml` OpenAPI, envanter, `check:api`, `check:api-types`; `api_contract.md` güncel |
| F23 | PostgreSQL doğrulanmamış | **Kapandı (CI)** | `test.yml` `postgres:16-alpine` + `psycopg[binary]`; yerelde URL yokken skip |
| F24 | Sekmeden ayrılınca OCR işi görünmez | **Kapandı** | `TopBar` arka plan göstergesi + iptal düğmesi |
| F25 | Masaüstü tam paket Tk çökmesi | **Kapandı** | Teardown + izolasyon; güncel **744 OK** (1 skipped) |
| F26 | Yardım menüsünden demo turu örnek proje üretmiyor | **Kapandı** | Yardım düğmesi `useStartDemoTour` akışına bağlı |
| F27 | README / implementation_status sayıları eski | **Kapandı** | Üç doküman güncel ölçümlerle senkron |
| F28 | HEAD `ruff format --check` kırmızı | **Kapandı** | `release_gate.py --quick` format adımı PASS |
| F29 | `verify-tabs` Dashboard beklentisi uyumsuz | **Kapandı** | 12/12 rota + E2E PASS |

**Özet:** F18–F29'un tamamı kapandı. F23'ün üretim davranışı yalnız CI'da doğrulanır; yerel ortamda `psycopg`/`HYDRO_TEST_POSTGRES_URL` yoksa test bilinçli olarak atlanır.

---

## 4. R19–R26 Durumu

| ID | Konu | Durum | Kalan iş |
| --- | --- | --- | --- |
| R19 | OCR worker üretim operasyonları | **Büyük ölçüde tamam** | Compose `ocr` profili, healthcheck, mem/pids limiti, `GET /api/ocr/queue` (kuyruk yaşı + DLQ), `POST .../retry` var. Kuyruk yaşı eşik alarmı ve sayfa başına maliyet ölçümü yok |
| R20 | OIDC/RBAC üretim operasyonları | **Kısmi** | `HYDRO_OIDC_ROLE_MAP`, oturum iptali, idle timeout, onay sayfalama/filtre ve giriş/çıkış audit'i var. MFA/step-up ve onay bildirimi/son kullanma yok |
| R21 | CI viewport matrisi + derin E2E + required check | **Büyük ölçüde tamam** | PR smoke 1440, CI matrisi 4 viewport, E2E 020 form kaydı + rapor export + proje silme. Required-check kurulumu `docs/release.md`'de belgelendi; GitHub ayarı ve 20 koşuluk flake ölçümü repodan doğrulanamıyor |
| R22 | Kontrast + E2E axe + odak tuzağı | **Kısmi** | Tema token'ları için WCAG AA kontrast testi, `prefers-reduced-motion`, tur `Esc` odak dönüşü var. `@axe-core/playwright` E2E taraması ve tam odak tuzağı yok |
| R23 | Test süresi/izolasyon/flake | **Kısmi** | Launcher rastgele port/tmp_path izolasyonu var; `slow` marker tanımlı. `ui/domain/web` ayrımı ve paralel/sharded koşu yok |
| R24 | Doküman tek kaynak + `analysis_report_v5` | **Tamam** | `sync_doc_metrics.py` sürüm/şema/OpenAPI bloğunu üretiyor; DURUM/README/implementation_status test-bundle sayıları senkron; bu rapor eklendi |
| R25 | Tedarik zinciri + admin token | **Kısmi** | `pip-audit`, `gitleaks`, `npm audit` CI'da. Admin token'ı hâlâ `sessionStorage` (`api.ts:175-191`); CSP `style-src 'unsafe-inline'` sürüyor |
| R26 | Postgres/ölçek + yedek otomasyonu | **Kısmi** | `backup_drill.py` saklama (gün/adet) ve Postgres doğrulama tatbikatı destekliyor. Zamanlanmış yedek, iki worker'lı Postgres smoke ve RPO/RTO tatbikat kaydı yok |

**Tamam:** R24. **Büyük ölçüde tamam:** R19, R21. **Kısmi:** R20, R22, R23, R25, R26.

---

## 5. Kalan Üretim Riskleri (öncelik sırası)

1. **MFA/step-up yok (R20).** Yönetici ve `db_restore` gibi yüksek etkili işlemler yalnız rol + iki kişi onayına dayanıyor. Kurumsal OIDC'de `acr`/`amr` claim kontrolü eklenmeli.
2. **Admin token'ı JS'ten okunabilir (R25).** `sessionStorage` XSS durumunda token sızdırır. Kısa ömürlü `HttpOnly` oturum veya tek kullanımlık token'a geçilmeli.
3. **E2E axe taraması yok (R22).** Bileşen düzeyi axe + token kontrast testi var; beş kritik ekranın tam sayfa taraması yok.
4. **Postgres çok-worker ve restore tatbikatı (R26).** CI tek süreçli runtime testi koşuyor; 2 web worker + 1 OCR worker ve restore süresi ölçülmedi.
5. **Flake ve required-check kanıtı (R21/R23).** 20 ardışık koşu ölçümü ve dal koruma kuralı repodan doğrulanamıyor.
6. **Kuyruk SLO alarmı (R19).** Kuyruk yaşı ve DLQ görünür, ancak eşik aşımında alarm/uyarı yok.

---

## 6. Doğrulanan Olumlu Noktalar

- **Sözleşme disiplini:** OpenAPI, envanter, istemci şablonları ve üretilen tipler tek kapıda doğrulanıyor; `release_gate.py --quick` bunları tek komutta koşuyor.
- **OCR dayanıklılığı:** Kalıcı DB kuyruğu lease/heartbeat/retry/cancel, `SKIP LOCKED`, DLQ görünümü ve operatör retry ucu birlikte çalışıyor.
- **Kimlik ve yetki:** OIDC PKCE, `HttpOnly` oturum, rol hiyerarşisi, iki kişi onayı, kendi isteğini onaylama engeli, oturum iptali ve onay sayfalaması testli.
- **Tarayıcı kapsamı:** 375/768/1024/1440 px'te 12 rota yatay taşma olmadan açılıyor; E2E gerçek form kaydı ve rapor export'u doğruluyor.
- **Doküman doğruluğu:** DURUM.md metrik bloğu canlı kaynaklardan üretiliyor; test/bundle sayıları dört dokümanda aynı.
- **Tedarik zinciri:** `pip-audit`, `gitleaks`, `npm audit --audit-level=high` CI'da bloklayıcı.

---

## 7. Doğrulama Komutları (bu raporda çalıştırıldı)

```bash
# Python kalite kapıları
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy hidrostatik_test/domain/
python3 -m mypy --ignore-missing-imports webapp/backend/app

# Web backend + kapsam
python3 -m coverage run --source=webapp/backend/app -m pytest webapp/backend/tests -q
python3 -m coverage report --fail-under=80

# OCR ve masaüstü
python3 -m unittest tests.test_report_ocr
python3 -m unittest discover -s tests -p "test_*.py"

# Sözleşme ve sürüm
python3 scripts/release_gate.py --quick
python3 scripts/sync_doc_metrics.py --check

# Frontend
cd webapp/frontend
npm run lint && npm run typecheck && npm test && npm run build && npm run check:bundle
npm run check:api && npm run check:api-types

# Gerçek tarayıcı smoke + matris (ayrı terminalde sunucu 8099'da)
HYDRO_DATA_DIR="$(mktemp -d)" python3 webapp/run_web.py --host 127.0.0.1 --port 8099
HYDRO_APP_URL=http://127.0.0.1:8099 node webapp/frontend/scripts/verify-tabs.mjs --matrix
```

---

## 8. Sonuç

v2.1.1, v4 denetiminin tüm bulgularını kapatmış ve v2 planının P0 başlıklarını (OCR operasyonları, OIDC operasyonları, CI matrisi/derin E2E, doküman tek kaynağı) büyük ölçüde uygulamış durumda. Ürün ve sözleşme kapıları yeşil; kalan işler üretim güvenliği (MFA, admin token), erişilebilirlik derinliği (E2E axe), ölçek/restore kanıtı ve flake ölçümü etrafında toplanıyor. Bu başlıklar [`improvement_recommendations_v2.md`](improvement_recommendations_v2.md) içindeki R20, R22, R23, R25 ve R26 ile izlenmeye devam etmelidir.
