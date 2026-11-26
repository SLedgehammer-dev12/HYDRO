> **Arşiv Notu:** Bu rapor geçmiş bir sürüme ait anlık inceleme kaydıdır; güncel proje ve doğrulama durumu için `DURUM.md` dosyasına bakın.

# HYDRO — Derinlemesine Analiz ve İyileştirme Raporu

| Alan | Değer |
| --- | --- |
| Tarih | 2026-11-18 |
| Sürüm | 1.8.0 (`hidrostatik_test/app_metadata.py`) |
| İncelenen commit | `174c02a` (çalışma ağacı temiz) |
| Kapsam | `hidrostatik_test/`, `webapp/backend/app/`, `webapp/frontend/src/`, `tests/`, `webapp/backend/tests/`, `tools/`, CI |
| Yöntem | Kaynak kod okuma, AST analizi, lint/type çıktısı, test koşumu, build, CI yapılandırması |

> Bu rapor, bulguları **Düzeltme / Değiştirme / İyileştirme / Geliştirme** başlıkları altında
> önceliklendirir. Her bulgu; kanıt (dosya:satır), etki ve kabul kriteri içerir.

---

## 1. Yönetici Özeti

Proje işlevsel olarak olgun: domain katmanı tek doğruluk kaynağı, test sayısı yüksek,
ruff temiz, frontend tip güvenli ve build başarılı. Buna karşın **üç yapısal risk** öne çıkıyor:

1. **P0 — Plan-Profil hata yolları tamamen bozuk.** `plan_profile.py` içindeki **9 `AppError`
   çağrısının tamamı yanlış imza** kullanıyor. Çalışma zamanında `TypeError` oluşuyor ve
   kullanıcıya 415/422/503 yerine **500** dönüyor. Hata mesajları kayboluyor.
2. **P1 — CI, ürünün yarısını test etmiyor.** `webapp/backend/tests` (131 test) ve frontend
   (`typecheck`/`build`) PR'larda çalışmıyor; web testleri yalnızca release etiketinde koşuyor.
   P0-1'deki hata bu yüzden yakalanmadı.
3. **P1 — OCR "kuyruğu" gerçek değil.** `POST /ocr/analyze` tüm OCR + dossier analizini istek
   içinde senkron yapıyor; `queued/running` durumları tek istek içinde tükeniyor.
   `estimated_wait_s` alanı backend'de hiç üretilmiyor ama frontend'de tüketiliyor.

Ayrıca mypy borcu 214 hata/16 dosya, 500 MB'a kadar dosya belleğe okunuyor, migration altyapısı
yok ve masaüstü UI 8.414 satırlık tek dosya.

### Olgunluk Skoru (özet)

| Boyut | Durum | Not |
| --- | --- | --- |
| Domain doğruluğu | 🟢 İyi | Parity testleri, gerçek rapor kalibrasyonu |
| Test hacmi | 🟢 İyi | 131 web + 669 masaüstü + 63 OCR |
| Test kapsamı (CI) | 🔴 Zayıf | Web/frontend PR kapısı yok |
| Tip güvenliği | 🟡 Orta | Domain bloklayıcı; web/masaüstü borçlu |
| Hata yönetimi | 🔴 Zayıf | P0-1: 9 bozuk hata yolu |
| Güvenlik | 🟡 Koşullu | Auth yok; Docker 0.0.0.0 yayınlıyor |
| Performans | 🟡 Orta | Senkron OCR, 500 MB bellek, büyük bundle |
| Sürdürülebilirlik | 🟡 Orta | Monolit dosyalar, yüksek karmaşıklık |
| Dokümantasyon | 🟡 Orta | `implementation_status.md` eski |

---

## 2. Ölçümler (kanıt)

### 2.1 Kod hacmi

| Katman | Satır |
| --- | ---: |
| `hidrostatik_test/domain` | 3.592 |
| `hidrostatik_test/services` | 5.603 |
| `hidrostatik_test/ui` | 10.852 |
| `hidrostatik_test/data` | 2.630 |
| `webapp/backend/app` | 15.809 |
| `webapp/frontend/src` | 27.350 |
| `tests` (masaüstü) | 10.304 |
| `webapp/backend/tests` | 4.548 |
| `tools` | 837 |
| **Toplam (py/ts/tsx/css)** | **83.405** |

### 2.2 Kalite kapıları

| Komut | Sonuç |
| --- | --- |
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ 125 files already formatted |
| `mypy hidrostatik_test webapp/backend/app` | ❌ **214 hata / 16 dosya** |
| `pytest webapp/backend/tests -q` | ✅ 131 passed (~57–82 sn) |
| `pytest tests/test_report_ocr.py -q` | ✅ 63 passed, 1 skipped |
| `unittest discover -s tests` | ✅ 669 passed, 1 skipped (~137 sn) |
| `npm run typecheck` | ✅ PASS |
| `npm run build` | ✅ PASS |

### 2.3 mypy dağılımı

| Dosya | Hata |
| --- | ---: |
| `hidrostatik_test/ui/app.py` | 96 |
| `webapp/backend/app/services/plan_profile.py` | 25 |
| `webapp/backend/app/services/dossier.py` | 22 |
| `hidrostatik_test/ui/wizard.py` | 16 |
| `webapp/backend/app/services/sessions.py` | 14 |
| `webapp/backend/app/services/scene.py` | 10 |
| `webapp/backend/app/services/calculations.py` | 6 |
| `hidrostatik_test/services/water_property_table_builder.py` | 6 |
| `hidrostatik_test/services/report_ocr.py` | 5 |
| `webapp/backend/app/services/catalog.py` | 4 |
| `hidrostatik_test/ui/download_dialog.py` | 4 |
| Diğer (6 dosya) | 6 |

Hata türleri: `arg-type` 64, `attr-defined` 53, `misc` 22, `union-attr` 21,
`assignment` 21, `call-arg` 11, `unused-ignore` 8.

### 2.4 Frontend build

| Varlık | Boyut | Gzip |
| --- | ---: | ---: |
| `index-*.js` | 1.338,22 kB | 379,68 kB |
| `PipelineScene-*.js` | 1.022,20 kB | 271,91 kB |
| `index-*.css` | 67,68 kB | 13,15 kB |

`vite.config.ts`: `sourcemap: true` (üretimde), `chunkSizeWarningLimit: 1600` (uyarıyı gizliyor).

---

## 3. Bulgu Özeti

| ID | Bulgu | Önem | Kategori |
| --- | --- | --- | --- |
| P0-1 | 9 adet bozuk `AppError` çağrısı → 500 | 🔴 Kritik | Düzeltme |
| P0-2 | Plan-Profil hata yolları testsiz | 🔴 Kritik | Düzeltme |
| P0-3 | Auth'suz Docker dağıtımı (0.0.0.0:8080) | 🔴 Kritik* | Düzeltme |
| P1-1 | CI web backend + frontend'i koşmuyor | 🟠 Yüksek | Düzeltme |
| P1-2 | mypy 214 hata, kademeli sıkılaştırma yok | 🟠 Yüksek | İyileştirme |
| P1-3 | OCR kuyruğu sahte; `estimated_wait_s` ölü | 🟠 Yüksek | Değiştirme |
| P1-4 | 500 MB dosya belleğe okunuyor | 🟠 Yüksek | Değiştirme |
| P1-5 | Migration altyapısı yok; Postgres test edilmiyor | 🟠 Yüksek | Değiştirme |
| P1-6 | Masaüstü UI monoliti (8.414 satır) | 🟠 Yüksek | Değiştirme |
| P1-7 | Frontend'de birim testi/lint yok | 🟠 Yüksek | Düzeltme |
| P1-8 | Aşırı karmaşık fonksiyonlar | 🟠 Yüksek | İyileştirme |
| P2-1 | Dokümantasyon test sayıları eski | 🟡 Orta | Düzeltme |
| P2-2 | Sürüm tutarsızlığı (1.8.0 / 0.1.0) | 🟡 Orta | Düzeltme |
| P2-3 | Bundle boyutu + üretim source map | 🟡 Orta | İyileştirme |
| P2-4 | Gözlemlenebilirlik (süre/metrik) eksik | 🟡 Orta | Geliştirme |
| P2-5 | Erişilebilirlik otomatik denetlenmiyor | 🟡 Orta | Geliştirme |
| P2-6 | Graphify `docs/legacy` gürültüsü | 🟢 Düşük | Düzeltme |
| P2-7 | Test süresi (137 sn) paralelleştirilebilir | 🟢 Düşük | İyileştirme |
| P2-8 | `plan_profile.py` 2.207 satır monolit | 🟢 Düşük | Değiştirme |

\* Yerel kullanımda P1; ağa açık dağıtımda P0.

---

## 4. P0 — Düzeltilmesi Gerekenler

### P0-1. Plan-Profil hata yolları `TypeError` üretiyor (500)

**Kanıt**

`AppError` imzası (`webapp/backend/app/core/errors.py:23-31`):

```python
def __init__(self, code: str, message: str, *, status_code: int = 400, details=None)
```

Buna karşın `webapp/backend/app/services/plan_profile.py` içindeki **9 çağrının tamamı**
`AppError("mesaj", code=..., status=...)` biçiminde:

| Satır | Kod | Amaçlanan HTTP |
| ---: | --- | ---: |
| 1550 | `cad_dependency_missing` | 503 |
| 1559 | `cad_parse_error` | 422 |
| 1856 | `unsupported_format` | 415 |
| 1865 | `empty_file` | 422 |
| 1867 | `file_too_large` | 413 |
| 1883 | `dwg_converter_missing` | 503 |
| 1901 | `dwg_convert_failed` | 422 |
| 1946 | `ReportOcrError` eşlemesi | 422 |
| 2026 | `validation_error` | 422 |

Doğrulama:

```text
$ python3 -c "raise AppError('Dosya boş.', code='empty_file', status=422)"
TYPEERROR (gerçek hata): AppError.__init__() got multiple values for argument 'code'
```

`mypy`, aynı sorunu 11 `call-arg` + `misc` hatasıyla işaretliyor; ancak CI webapp'i
denetlemediği için (P1-1) görünmüyor.

**Etki**

- Desteklenmeyen dosya, boş dosya, 500 MB aşımı, DXF parse hatası, DWG dönüştürücü yokluğu,
  geçersiz KP aralığı → **hepsi 500 Internal Server Error**.
- Kullanıcıya anlamlı mesaj yerine genel hata; `error_code` kaybolur; destek ekibi teşhis edemez.
- Hata zarfı sözleşmesi (`code`, `details`) bozulur; frontend `ApiError` dallanması çalışmaz.

**Düzeltme**

Her çağrıyı imzaya uydur:

```python
raise AppError("empty_file", "Yüklenen dosya boş.", status_code=422)
```

`1946` için:

```python
except ReportOcrError as exc:
    raise AppError(exc.code, str(exc), status_code=422) from exc
```

**Kabul kriteri**

- 9 çağrının tamamı `AppError(<code>, <message>, status_code=...)` biçiminde.
- `python3 -m mypy webapp/backend/app` çıktısında `AppError` kaynaklı `call-arg`/`misc` hatası yok.
- Aşağıdaki testler 415/422/413/503 döndürüyor.

### P0-2. Plan-Profil hata yolları test edilmiyor

**Kanıt**

`webapp/backend/tests/test_projects.py` yalnızca mutlu yolu kapsıyor:
`test_plan_profile_pdf_scan_and_batch_create` (satır 266) ve
`test_plan_profile_dxf_scan_and_pipe_meta` (satır 321). Hata dalları için test yok.

**Düzeltme**

```python
@pytest.mark.parametrize(
    ("filename", "content", "expected_status", "expected_code"),
    [
        ("plan_profile.txt", b"x", 415, "unsupported_format"),
        ("plan_profile.pdf", b"", 422, "empty_file"),
    ],
)
def test_plan_profile_error_contract(client, headers, filename, content, expected_status, expected_code):
    res = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": (filename, content, "application/octet-stream")},
        headers=headers,
    )
    assert res.status_code == expected_status
    assert res.json()["code"] == expected_code
```

Ek olarak boyut aşımı için `settings.max_upload_mb=1` fixture'ı ile 2 MB'lık sahte PDF,
geçersiz DXF için bozuk metin, geçersiz KP aralığı için `commit` testi eklenmeli.

**Kabul kriteri**

- En az 5 hata yolu testi; her biri doğru HTTP kodu + `code` alanı.
- Testler P0-1 düzeltmesi geri alındığında kırmızıya düşüyor (regresyon güvencesi).

### P0-3. Auth'suz Docker dağıtımı ağa açık

**Kanıt**

- `webapp/docker-compose.yml`: `HYDRO_HOST: "0.0.0.0"`, `ports: "8080:8080"`,
  yorum: *"Auth'suz MVP yalnız güvenilir ağda çalıştırılmalıdır."*
- `webapp/Dockerfile` CMD: `--host 0.0.0.0`.
- `core/config.py:132`: `auth_mode: str = "none"` — ayar var, **hiçbir yerde uygulanmıyor**
  (`grep` yalnızca `system.py` raporlamasında buluyor).
- Tek kiracı ayrımı istemcinin gönderdiği `X-Session-ID` başlığı; doğrulama yok.
- Hız sınırı / kota yok; tek istekte 500 MB'a kadar yükleme kabul ediliyor.

**Etki**

Docker ile yayınlanan bir kurulumda aynı ağdaki herkes:
başka workspace'lerin projelerini/OCR sonuçlarını okuyabilir, dosya yükleyip disk/CPU tüketebilir.
Varsayılan `127.0.0.1` yerel kullanımı korur; risk dağıtımda başlar.

**Düzeltme (kısa vade)**

1. `docker-compose.yml` varsayılanını `127.0.0.1:8080:8080` yap; ağa açmak için açık opt-in.
2. `HYDRO_AUTH_MODE=token` modunu uygula: `Authorization: Bearer <token>` doğrulaması,
   sabit zamanlı karşılaştırma, token yoksa 401.
3. `/api/health` dışındaki tüm route'lara bağımlılık olarak auth ekle.
4. Yükleme uçlarına workspace başına dakikalık kota (ör. 20 istek/dk, 2 GB/saat).

**Kabul kriteri**

- Auth açıkken tokensiz istek 401; token ile 200.
- Varsayılan compose yalnızca loopback'e bağlanıyor.
- Kota aşımı 429 + `Retry-After`.

---

## 5. P1 — Yüksek Öncelikli Düzeltme ve Değiştirmeler

### P1-1. CI, web backend ve frontend'i kapsamıyor

**Kanıt**

| Workflow | Çalıştırdığı |
| --- | --- |
| `.github/workflows/test.yml` | `unittest discover -s tests` (yalnız masaüstü) |
| `.github/workflows/lint.yml` | `ruff` + `mypy` yalnız `hidrostatik_test/`, `tests/` |
| `.github/workflows/release.yml` | Web pytest **yalnız release etiketinde** (satır 119) |

Hiçbir workflow `npm run typecheck`, `npm run build` veya `verify:tabs` çalıştırmıyor.

**Etki**

- P0-1 sınıfı hatalar PR'da görünmüyor.
- Frontend tip hatası / build kırılması ancak release'te ortaya çıkıyor.
- 131 web testi geri bildirim döngüsünün dışında.

**Düzeltme**

`test.yml`'e ayrı job'lar ekle:

```yaml
  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: python -m pip install -r requirements.txt -r webapp/requirements-web.txt pytest
      - run: python -m pytest webapp/backend/tests -q
      - run: mypy --ignore-missing-imports webapp/backend/app

  frontend:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: webapp/frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: webapp/frontend/package-lock.json }
      - run: npm ci
      - run: npm run typecheck
      - run: npm run build
```

**Kabul kriteri**

- PR'da 4 job yeşil: masaüstü test, web test, frontend typecheck, frontend build.
- P0-1 düzeltmesi öncesi web job'ı kırmızı (kanıt).

### P1-2. mypy borcu: 214 hata / 16 dosya

**Kanıt**

Bkz. §2.3. En yoğun: `ui/app.py` (96), `plan_profile.py` (25), `dossier.py` (22).

**Etki**

Tip hataları gerçek çalışma zamanı hatalarını gizliyor (P0-1 buna örnek).
`unused-ignore` 8 adet, yani bastırma yorumları da bakımsız.

**Öneri — kademeli sıkılaştırma**

1. **Hafta 1:** `webapp/backend/app` mypy'yi CI'a ekle, `--ignore-missing-imports`, hata sayısını
   `214` → `0` hedefiyle dosya bazlı `# type: ignore` **eklemeden** düzelt.
2. `plan_profile.py`, `dossier.py`, `sessions.py`, `scene.py` için `disallow_untyped_defs`
   ve `warn_return_any` aç.
3. `ui/app.py` için ayrı `mypy.ini` bölümü: önce `attr-defined`/`union-attr` (74 hata),
   sonra `arg-type` (64).
4. `unused-ignore` hatalarını temizle; kalan ignore'lara gerekçe yorumu zorunlu kıl.

**Kabul kriteri**

- `mypy webapp/backend/app` sıfır hata ve CI'da bloklayıcı.
- `mypy hidrostatik_test` hata sayısı < 50 (domain zaten bloklayıcı).

### P1-3. OCR kuyruğu gerçek değil

**Kanıt**

- `services/ocr.py:403-460`: `analyze_upload` içinde sırasıyla
  `status="queued"` → commit → `status="running"` → **senkron** `analyze_report(...)` →
  `status="succeeded"`. Hepsi tek HTTP isteğinde.
- `api/ocr.py:19`: `POST /ocr/analyze` senkron `def`; `BackgroundTasks` yok, worker yok.
- `_queue_counts()` yalnızca DB'deki durumları sayıyor; tüketen bir kuyruk yok.
- `estimated_wait_s`: backend'de **hiç üretilmiyor**; frontend `types.ts:266` ve
  `OcrPage.tsx:487` tüketiyor → ölü sözleşme.
- `_OCR_LANG_LOCK` + `os.environ["HYDRO_OCR_LANG"]` mutasyonu süreç genelinde;
  çok iş parçacıklı/çok işçili sunucuda yarış koşulu.
- Frontend `analyzeOcr` timeout 600 sn; büyük PDF'te istek asılı kalabilir.

**Etki**

- 74 sayfalık gerçek rapor gibi işlerde HTTP isteği dakikalarca açık kalır; proxy/load balancer
  timeout'ları 502 üretir.
- "Tahmini bekleme" mesajı hiç görünmez; durum geçişleri yanıltıcı.
- Aynı anda iki OCR isteği dil ayarını birbirine karıştırabilir.

**Öneri**

1. `POST /ocr/analyze` → 202 + `{analysis_id, status: "queued", poll_url}` döndür.
2. Tek işçili (concurrency=1) bounded kuyruk: `queue.Queue` + daemon thread veya
   `concurrent.futures.ThreadPoolExecutor(max_workers=1)`; lifespan'de başlat/durdur.
3. Dil parametresini `os.environ` yerine `analyze_report(..., language=...)` üzerinden geçir;
   global lock'u kaldır.
4. `estimated_wait_s`'i kuyruk derinliği × ortalama süre ile hesapla **veya** alanı
   frontend'den kaldır.
5. İptal (`cancel`) endpoint'ini gerçekten işçiye bağla (iptal bayrağı).
6. Çok işçili dağıtım hedefleniyorsa RQ/arq + Redis'e geçiş planı.

**Kabul kriteri**

- `/ocr/analyze` < 1 sn'de 202 dönüyor.
- Durum `queued → running → succeeded` poll'da gözlenebiliyor.
- Eşzamanlı 2 istek farklı `language` ile doğru sonuç veriyor.
- `estimated_wait_s` ya doğru hesaplanıyor ya da sözleşmeden kaldırılmış.

### P1-4. Plan-Profil yüklemesi belleğe okunuyor

**Kanıt**

`plan_profile.py:1862-1867`:

```python
max_bytes = effective_max_file_size_bytes()
data = stream.read(max_bytes + 1)
```

`config.py:181`: varsayılan `max_upload_mb=500`. Aynı anda birkaç yükleme → GB'lı bellek.

**Etki**

- 500 MB PDF/DXF tek istekte RAM'e alınıyor; OCR ile birleşince OOM riski.
- `ezdxf.readfile` zaten yol istiyor; veri gereksiz yere bellekte tutuluyor.

**Düzeltme**

1. Yükleme akışını geçici dosyaya **parça parça** yaz, boyutu yazarken denetle
   (`storage.store_upload` zaten böyle yapıyor — aynı deseni kullan).
2. Plan-Profil için ayrı, daha düşük limit: ör. `HYDRO_PLAN_PROFILE_MAX_MB=100`.
3. Bellek içi `data` yerine `Path` üzerinden `pypdf`/`ezdxf`/görsel okuma.
4. `finally` bloğunda geçici dosyayı temizle.

**Kabul kriteri**

- 500 MB'lık sahte dosya yüklemesinde RSS artışı < 50 MB.
- Limit aşımı 413 + `details.max_bytes`.

### P1-5. Migration altyapısı yok; Postgres doğrulanmıyor

**Kanıt**

- `db.py:109-110`: `Base.metadata.create_all()` + `_apply_light_migrations()`.
- `_apply_light_migrations` yalnızca iki `ALTER TABLE` içeriyor (satır 85-105).
- Alembic yok; `psycopg` yorum satırında (`webapp/requirements-web.txt`).
- `db.py:158`: `/api/meta` `migration: "0001"` sabit değeri.

**Etki**

- Şema değişiklikleri mevcut kurulumlarda sessizce uygulanmaz (kolon eklenmezse 500).
- Postgres yolu hiç çalıştırılmadığı için üretim geçişi riskli.

**Öneri**

1. Alembic'i ekle; `create_all` yalnızca testlerde kalsın.
2. `0001_initial` + mevcut iki kolonu kapsayan `0002` üret.
3. CI'a Postgres service container'lı ikinci bir test matrisi ekle.
4. `/api/meta.migration` değerini Alembic head'den oku.

**Kabul kriteri**

- `alembic upgrade head` hem SQLite hem Postgres'te çalışıyor.
- CI'da Postgres'te 131 test yeşil.

### P1-6. Masaüstü UI monoliti

**Kanıt**

- `hidrostatik_test/ui/app.py`: **8.414 satır**, 292 metot, tek sınıf `HydrostaticTestApp`.
- `_build_ui` 462 satır; `_build_geometry_input_panel` 309 satır; `__init__` 294 satır.
- mypy: 96 hata (en yüksek).

**Etki**

- UI + iş akışı + dosya/DB/hesap orkestrasyonu aynı sınıfta; birim testi imkânsıza yakın.
- Değişikliklerin yan etkisi yüksek; code review zor.

**Öneri (kademeli, davranış değiştirmeden)**

1. **Presenter katmanı:** her sekme için `GeometryPresenter`, `AirPresenter`…;
   Tk widget'ları yalnızca görüntüler, hesaplama çağrıları presenter'da.
2. `_build_*` metotlarını `ui/panels/` altında modüllere taşı; `app.py` yalnızca kompozisyon.
3. Oturum/kaydetme orkestrasyonunu `services/` altına al (`session_manager` zaten var).
4. Her presenter için saf birim testi (Tk gerektirmeyen).

**Kabul kriteri**

- `app.py` < 2.000 satır.
- Presenter'lar için ≥ 40 yeni birim testi.
- Mevcut 669 test yeşil kalıyor.

### P1-7. Frontend'de birim testi ve lint yok

**Kanıt**

- `package.json` script'leri: `dev, build, typecheck, preview, verify:tabs`.
- `vitest`/`jest`/`@testing-library` yok; `src` altında `.test.*` dosyası yok.
- ESLint yapılandırması yok.
- `tsconfig.json`: `strict: true` (iyi) ama `noUnusedLocals/Parameters: false`.
- `verify-tabs.mjs` çalışan sunucu + Chrome ister; CI'da yok.

**Etki**

- 27.350 satır frontend yalnızca tip denetimiyle korunuyor; davranış regresyonları görünmez.
- Kullanılmayan değişken/parametreler birikiyor.

**Öneri**

1. Vitest + React Testing Library + jsdom; `happy-dom` alternatif.
2. İlk hedef: `lib/kp.ts`, `lib/scene.ts`, `store/useAppStore.ts` saf fonksiyon testleri.
3. MSW ile `fetch` mock'layarak `OcrPage` akış testi (queued→running→succeeded).
4. ESLint + `typescript-eslint` + `eslint-plugin-react-hooks` + `jsx-a11y`.
5. `verify:tabs`'ı Playwright'a taşı veya CI'da `vite preview` + Chrome ile çalıştır.

**Kabul kriteri**

- `npm test` ≥ 30 test, CI'da bloklayıcı.
- `npm run lint` sıfır hata.
- `noUnusedLocals: true` derlemeden geçiyor.

### P1-8. Aşırı karmaşık fonksiyonlar

**Kanıt (AST ile ölçüldü)**

| Fonksiyon | Satır | Dal |
| --- | ---: | ---: |
| `dossier.evaluate_operational_checks` | 572 | 112 |
| `scene.build_project_scene` | 524 | 148 |
| `dossier._extract_form_specific_data` | 434 | 92 |
| `ab_control_table.find_ab_control_table_issues` | 326 | 36 |
| `dossier.evaluate_section_calculations` | 319 | 69 |
| `plan_profile._extract_cad_plan_profile_page` | 307 | 89 |
| `plan_profile._extract_dxf_plan_profile` | 303 | 85 |
| `dossier._cumulative_recompute_section` | 297 | 102 |
| `scene.build_scene` | 295 | 65 |

**Etki**

- Tek fonksiyonda onlarca kabul kuralı; regresyon izolasyonu zor.
- Yeni kural eklemek mevcut dallanmayı büyütüyor.

**Öneri**

1. `evaluate_operational_checks` → kural kayıt defteri:
   `CHECKS: list[Callable[[Context], list[Finding]]]`; her kural ayrı fonksiyon + test.
2. `build_project_scene` → `build_sections`, `build_equipment`, `build_pig`, `build_flow`
   alt fonksiyonları; ortak `SceneContext` dataclass.
3. `_cumulative_recompute_section` → saf `recompute_cumulative(rows, start)` fonksiyonu.
4. Her ayrıştırma sonrası parity testlerinin yeşil kalması şart.

**Kabul kriteri**

- Hiçbir fonksiyon > 150 satır veya > 40 dal değil.
- Kabul kriteri kuralları tek tek test edilebiliyor.

---

## 6. P2 — İyileştirmeler

### P2-1. Dokümantasyon kayması

`webapp/docs/implementation_status.md`:

| Alan | Dokümanda | Gerçek |
| --- | ---: | ---: |
| Web pytest | 97 | **131** |
| OCR testi | 53 (+1 skip) | **63** (+1 skip) |
| Masaüstü unittest | 653 | **669** |
| Tarih / dal | 2026-11-16 / `feat/ergonomics-ocr` | 2026-11-18 / güncel |

`DURUM.md` doğru (131/669). Öneri: test sayılarını `tools/` altında bir betikle üret,
dokümana "elle güncelleme" yerine "üretilen dosya" notu koy.

### P2-2. Sürüm tutarsızlığı

- `hidrostatik_test/app_metadata.py`: `1.8.0` (tek kaynak, release gate bunu okuyor)
- `webapp/frontend/package.json`: `1.8.0` (elle senkron)
- `webapp/backend/app/__init__.py`: **`0.1.0`**

Öneri: backend sürümünü `app_metadata.APP_VERSION`'dan türet (veya `/api/meta`'da tek kaynak
göster); frontend sürümünü build sırasında `package.json`'dan `VITE_APP_VERSION` olarak ver.

### P2-3. Bundle ve source map

- `index` 1,34 MB + `PipelineScene` 1,02 MB (gzip 380 + 272 kB).
- `sourcemap: true` üretimde: `dist` içinde ~10 MB `.map`; kaynak kodu ifşa riski.
- `chunkSizeWarningLimit: 1600` uyarıyı susturuyor.

Öneri: `manualChunks` ile `three`, `recharts`, `framer-motion` ayrı; üretimde
`sourcemap: false` (veya hata izleme servisine yükle); limiti 800'e çek.

### P2-4. Gözlemlenebilirlik

Mevcut: `request_id`, audit tablosu, `/api/health`, `/api/meta`.
Eksik: istek süresi, OCR iş süresi, kuyruk derinliği, hata oranı metrikleri.

Öneri: yapılandırılmış JSON log + süre alanları; `/api/health/ready` DB ping;
opsiyonel Prometheus `/metrics`. OCR için `duration_ms`, `page_count`, `engine` alanları.

### P2-5. Erişilebilirlik

265 `aria-*` kullanımı ve `PageErrorBoundary` iyi başlangıç. Otomatik denetim yok.
Öneri: Vitest + `vitest-axe` veya Playwright + `@axe-core/playwright`; kritik sayfalarda
klavye ile tam akış testi.

### P2-6. Graphify gürültüsü

`docs/legacy` altında 1 Python dosyası taranıyor; `should_skip` listesinde `docs/legacy` yok.
Öneri: `docs/legacy`, `agents/`, `scratch/` skip listesine; `tests` için ayrı `--include-tests`
bayrağı.

### P2-7. Test süresi

669 masaüstü testi ~137 sn, 131 web testi ~57–82 sn. Öneri: `pytest-xdist -n auto`,
OCR/ağır testler için `@pytest.mark.slow`, PR'da hızlı alt küme + nightly tam koşu.

### P2-8. `plan_profile.py` monoliti

2.207 satır; PDF, CAD/DXF/DWG, görsel, metin ayrıştırma ve taslak kesit üretimi tek dosyada.
Öneri: `plan_profile/` paketi → `pdf.py`, `dxf.py`, `image.py`, `text_parser.py`,
`drafts.py`, `service.py`. P0-1 düzeltmesi bu ayrıştırmadan **önce** yapılmalı.

---

## 7. Geliştirme Fırsatları

| Fırsat | Değer | Efor |
| --- | --- | --- |
| OCR iş kuyruğu + iptal + ilerleme yüzdesi | Uzun raporlarda güvenilirlik | M |
| Şablon tabanlı rapor doğrulama kuralları (kural kayıt defteri) | Yeni kural eklemek kolaylaşır | M |
| Proje bazlı dashboard metrikleri (test durumu, eksik kesit) | Saha kullanımı | S |
| PDF raporlarında alan bazlı güven göstergesi + toplu onay | OCR verimliliği | M |
| Çoklu kullanıcı/rol (auth mode token → kullanıcı) | Kurumsal dağıtım | L |
| Postgres + Alembic ile üretim dağıtımı | Ölçeklenebilirlik | M |
| Otomatik erişilebilirlik ve görsel regresyon testleri | Kalite | S |
| Feature flag altyapısı (`HYDRO_FEATURES`) | Kademeli yayın | S |
| Telemetri (opt-in) ile saha hata analizi | Ürün kararları | M |
| Masaüstü → web geçişinde ortak presenter katmanı | Bakım maliyeti | L |

---

## 8. Kategori Eşlemesi

### Düzeltilmesi gerekenler
P0-1 (AppError), P0-2 (hata testleri), P0-3 (dağıtım güvenliği),
P1-1 (CI), P1-7 (frontend test/lint), P2-1 (doküman), P2-2 (sürüm), P2-6 (graphify).

### Değiştirilmesi gerekenler
P1-3 (OCR kuyruğu), P1-4 (bellek), P1-5 (migration), P1-6 (UI monoliti),
P2-8 (plan_profile paketi).

### İyileştirilmesi gerekenler
P1-2 (mypy), P1-8 (karmaşıklık), P2-3 (bundle/sourcemap), P2-7 (test süresi).

### Geliştirilmesi gerekenler
P2-4 (gözlemlenebilirlik), P2-5 (erişilebilirlik) ve §7 tablosu.

---

## 9. Yol Haritası

### Sprint 1 — Güvenlik ve doğruluk (1 hafta)
- [ ] P0-1: 9 `AppError` çağrısını düzelt
- [ ] P0-2: 5 hata yolu testi ekle
- [ ] P1-1: CI'a web + frontend job'ları ekle
- [ ] P2-1/P2-2: doküman ve sürüm düzeltmeleri

**Çıkış:** PR'da 4 yeşil job; plan-profile hata sözleşmesi testli.

### Sprint 2 — Dayanıklılık (2 hafta)
- [ ] P1-3: OCR kuyruğu + 202/poll + dil parametresi
- [ ] P1-4: akışkan yükleme + endpoint limiti
- [ ] P0-3: token auth + loopback varsayılanı + kota
- [ ] P1-2: webapp mypy sıfır + CI bloklayıcı

**Çıkış:** Büyük PDF'lerde 202 + poll; RSS sabit; auth'lu dağıtım.

### Sprint 3 — Sürdürülebilirlik (3 hafta)
- [ ] P1-5: Alembic + Postgres CI
- [ ] P1-8: kural kayıt defteri + sahne alt kurucuları
- [ ] P1-6: UI presenter ayrıştırması (kademeli)
- [ ] P1-7: Vitest + ESLint
- [ ] P2-3: bundle bölme + sourcemap politikası

**Çıkış:** Karmaşıklık hedefleri tutuyor; frontend testli; Postgres doğrulanmış.

---

## 10. Hızlı Kazanımlar (bu hafta)

1. **P0-1 tek dosyalık düzeltme** — 9 çağrı, ~15 dakika, tüm hata sözleşmesini düzeltir.
2. **CI'a `pytest webapp/backend/tests` + `npm run typecheck`** — ~20 satır YAML.
3. **`implementation_status.md` sayı güncellemesi** — 3 satır.
4. **`docker-compose.yml` loopback** — 1 satır (`"127.0.0.1:8080:8080"`).
5. **`estimated_wait_s` temizliği** — backend'de üretilmiyorsa frontend'den kaldır.

---

## 11. Doğrulama Komutları

```bash
# Lint / format
python3 -m ruff check .
python3 -m ruff format --check .

# Tip
python3 -m mypy hidrostatik_test webapp/backend/app

# Testler
python3 -m pytest webapp/backend/tests -q
python3 -m pytest tests/test_report_ocr.py -q
python3 -m unittest discover -s tests -p "test_*.py"

# Frontend
cd webapp/frontend && npm run typecheck && npm run build

# Uygulama
python3 webapp/run_web.py --host 127.0.0.1 --port 8095
HYDRO_APP_URL=http://127.0.0.1:8095 node webapp/frontend/scripts/verify-tabs.mjs

# Harita
python3 skills/graphify/scripts/graphify.py build
python3 tools/generate_codebase_map.py
```

---

## 12. Riskler ve Bağımlılıklar

| Risk | Durum | Etki |
| --- | --- | --- |
| Gerçek saha raporlarının resmi revizyonu | Kurum onayı bekliyor | Kalibrasyon doğrulaması sınırlı |
| B tablosu kaynağı | Kurum onaylı veri yok | Katsayı B doğrulaması eksik |
| Notarization sertifikası | Yok | macOS dağıtımı imzasız |
| `HYDRO_UPDATE_PRIVATE_KEY` | CI secret yoksa fail-fast | Release durabilir |
| Postgres runtime testi | `psycopg` yok | Üretim geçişi doğrulanmadı |
| OCR motoru platform bağımlılığı | Vision macOS / Tesseract | Linux'ta 1 test skip |

---

## Ek A — Güçlü Yönler (korunmalı)

- Domain katmanı tek doğruluk kaynağı; web doğrudan import ediyor (31 import).
- Gerçek raporlarla OCR kalibrasyonu (9 resmi `.xls`, 74 sayfa).
- Yükleme güvenliği: sihirli bayt doğrulama, `0600` geçici dosya, `ensure_within` path traversal koruması.
- Hata zarfı standardı (`code`, `message`, `details`, `request_id`).
- Frontend `strict: true`, `any` kullanımı 0, 265 `aria-*`, sayfa bazlı error boundary.
- Kapsamlı parity testleri ve release version gate.
- ruff temiz; commit disiplini ve CHANGELOG/DURUM güncel.

## Ek B — Bulgu → Kanıt İndeksi

| Bulgu | Kanıt |
| --- | --- |
| P0-1 | `plan_profile.py:1550,1559,1856,1865,1867,1883,1901,1946,2026`; `errors.py:23-31` |
| P0-2 | `webapp/backend/tests/test_projects.py:266,321` |
| P0-3 | `docker-compose.yml`, `Dockerfile`, `config.py:132`, `security.py` |
| P1-1 | `.github/workflows/test.yml`, `lint.yml`, `release.yml:119` |
| P1-2 | mypy çıktısı §2.3 |
| P1-3 | `services/ocr.py:198-233,403-460`; `OcrPage.tsx:487`; `types.ts:266` |
| P1-4 | `plan_profile.py:1862-1867`; `config.py:181` |
| P1-5 | `db.py:85-110,158` |
| P1-6 | `hidrostatik_test/ui/app.py` (8.414 satır) |
| P1-7 | `webapp/frontend/package.json`, `tsconfig.json`, `vite.config.ts` |
| P1-8 | AST ölçümü §5/P1-8 |
| P2-1 | `webapp/docs/implementation_status.md:26-28` |
| P2-2 | `app_metadata.py:5`, `package.json:4`, `app/__init__.py:7` |
| P2-3 | `vite.config.ts`, build çıktısı §2.4 |
| P2-6 | `skills/graphify/scripts/graphify.py:38-40` |
