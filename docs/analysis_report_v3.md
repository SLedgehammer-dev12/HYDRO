# HYDRO — Web Sürümü İnceleme Raporu (v3)

> **Uygulama Durumu (23 Kasım 2026):** Bu rapordaki tüm bulgular (`F1`–`F17`: 4 P1 + 13 P2) 4 dikey dilim halinde TDD ile uygulanmış ve doğrulanmıştır (`251` backend pytest / `%83` kapsam, `61` Vitest / `20` dosya, `openapi.json` + `check:api` sözleşme kapısı). Güncel özet için bkz. `DURUM.md`.

**Tarih:** 22 Kasım 2026
**Kapsam:** Web backend (FastAPI), web frontend (React/Vite) ve bu iki katmanın kullandığı domain servisleri. Masaüstü (Tkinter) arayüzü kapsam dışıdır.
**Baseline:** `main` @ `f9b7d09` (v1.9.1 + 6 commit) **+ commit edilmemiş çalışma ağacı**
**Yöntem:** Kaynak kod okuma, uç nokta/sözleşme karşılaştırması, kalite kapılarının yeniden çalıştırılması, web'e özel kapsam ölçümü. Alt ajan denemesi sağlayıcı kotası nedeniyle tamamlanamadı; denetim doğrudan yürütüldü.
**Kanıt standardı:** Her bulgu `dosya:satır` veya komut çıktısıyla desteklenir.

> **Arşiv notu:** `docs/analysis_report_v2.md` 19 Kasım 2026 anlık görüntüsüdür ve bu raporla çelişebilir. Güncel doğrulama için `DURUM.md` ve bu dosya esas alınmalıdır.

> **Önemli — baseline uyarısı**
> `HEAD` `f9b7d09` olsa da çalışma ağacında **13 dosyada commit edilmemiş değişiklik** vardır (`+1399 / −205`): OCR/PDF ayrıştırma iyileştirmeleri (`dossier.py`, `form_details.py`, `plan_profile.py`, `report_ocr.py`), ilgili testler (`test_dossier.py` +446 satır), Docker'a Tesseract eklenmesi ve `DURUM.md`/`README.md` güncellemeleri. Bu rapordaki satır numaraları ve ölçümler **çalışma ağacını** yansıtır. Rapor yazılırken ağaç hareketliydi.

---

## 1. Yönetici Özeti

Web sürümü, önceki rapora göre belirgin olgunlaşmış durumda: altı kalite kapısı da yeşil, 239 backend testi ve 56 frontend testi geçiyor, web'e özel kapsam **%83**, OpenAPI **87 path / 101 operation**. Son commit'lerle gelen 14.1–14.3 basınç izleme, 12/15 termal denge + Form 018/021 senkronizasyonu, segment bazlı SMYS ve 409 revizyon çakışma modalı uçtan uca bağlı; rapor üreticileri (`pdf/xlsx/txt`) bu yeni test türlerini içeriyor.

Buna karşın **hiçbir P0 bulunmadı**; ancak dört P1 ve on bir P2 açık var. En yüksek risk üç başlıkta toplanıyor:

1. **Form düzeyinde eşzamanlılık koruması yok.** Oturum güncellemesi ve snapshot uygulaması `If-Match`/`revision` ile korunurken, `PUT /sessions/{id}/forms/{code}` korunmuyor; iki sekme/iki kullanıcı aynı formu kaydedince sessiz "son yazan kazanır" oluşuyor (`sessions.py:127-146`). Saha verisi kaybı için en somut açık.
2. **Demo fallback yazmaları sessizce yutabiliyor.** Tek bir ağ hatası (`status=0`) global backend'i 45 saniyeliğine `demo` yapıyor; bu sırada kaydetmeler yalnız tarayıcıya gidiyor ve geri oynatma (replay) mekanizması yok (`queries.ts:86-103`, `974-1050`).
3. **Belgelenen Docker dağıtımında DB yönetimi ve güncelleme yöneticisi çalışmıyor.** `docker-compose.yml` `HYDRO_HOST=0.0.0.0` veriyor; yönetici kapısı `settings.is_loopback_host` ve soket eşi loopback istiyor, arayüzde `X-Hydro-Admin-Token` alanı da yok (`api/system.py:86-121`, `DatabaseAdminPanel.tsx`). Bu iki özellik Docker'da her istekte 403 alır.

Ayrıca API sözleşmesi (`api_contract.md`) gerçek yüzeyin gerisinde: 59 endpoint bölümüne karşı 101 operasyon; `include_raw_ocr` parametresi kabul edilip yok sayılıyor; sözleşmenin vaat ettiği `webapp/docs/openapi.json` ve CI üretimi yok.

---

## 2. Ölçümler (22 Kasım 2026, çalışma ağacı)

| Kapı | Komut | Sonuç |
| --- | --- | --- |
| Ruff lint | `python3 -m ruff check .` | **PASS** |
| Ruff format | `python3 -m ruff format --check .` | **PASS** (147 dosya) |
| Mypy (web) | `python3 -m mypy --ignore-missing-imports webapp/backend/app` | **PASS** (48 dosya, 0 hata) |
| Backend test | `python3 -m pytest webapp/backend/tests -q` | **239 passed**, ~39 sn |
| Frontend test | `cd webapp/frontend && npm test` | **56 passed / 16 dosya** |
| Frontend kapıları | `npm run lint && npm run typecheck && npm run build && npm run check:bundle` | **PASS**; ilk JS **147,5 kB** gzip, CSS 14,7 kB; `vendor-three` 726 kB lazy |
| OpenAPI | `create_app().openapi()` | **87 path / 101 operation** |
| Web'e özel kapsam | `coverage run --source=webapp/backend/app -m pytest …` | **%83** (12.302 statement) |
| Zayıf modüller | — | `web_updater` %61, `ocr` %73, `plan_profile` %78, `project_archive` %78, `snapshot` %80 |
| CI matrisi | `.github/workflows/test.yml`, `lint.yml` | Web pytest + frontend lint/test/build var; **web kapsam eşiği, Postgres ve e2e yok** |

> Not: `pyproject.toml` kapsam yapılandırması `source = ["hidrostatik_test"]` ve `fail_under = 65` olduğu için **web kodu varsayılan kapsam kapısına hiç girmiyor**. Yukarıdaki %83 yalnızca elle çalıştırılan özel komutla ölçüldü.

---

## 3. Bulgular

| ID | Önem | Başlık | Alan |
| --- | --- | --- | --- |
| F1 | **P1** | Form güncellemelerinde iyimser eşzamanlılık yok | Veri bütünlüğü |
| F2 | **P1** | API sözleşmesi gerçek yüzeyden kopuk | Sözleşme |
| F3 | **P1** | Demo fallback yazmaları sessizce yutuyor | Veri kaybı |
| F4 | **P1** | Docker'da DB yönetimi + güncelleme yöneticisi kilitli | Dağıtım |
| F5 | P2 | Büyük yüklemeler tamamen RAM'de; gövde/eşzamanlılık sınırı yok | Kaynak |
| F6 | P2 | Analiz uçlarında sınırsız liste girdileri | Kaynak |
| F7 | P2 | Üretilen export dosyaları birikiyor; arşiv bellekte kuruluyor | Kaynak/disk |
| F8 | P2 | Ağır uçlarda rate limit eksik | Kaynak/kötüye kullanım |
| F9 | P2 | OCR kuyruğu process-içi; worker sayısı sabit 1 | Ölçeklenme |
| F10 | P2 | OCR sayfasından ayrılınca analiz durmuyor | Kaynak/UX |
| F11 | P2 | OCR istemci timeout'u sabit 630 sn | Sözleşme |
| F12 | P2 | DB restore canlı isteklerin altında motoru değiştiriyor | Güvenilirlik |
| F13 | P2 | PostgreSQL desteği doğrulanmamış | Dağıtım |
| F14 | P2 | Web için kapsam eşiği ve sayfa testleri yok | Test |
| F15 | P2 | `extra="ignore"` sözleşme kaymasını gizliyor | Sözleşme |
| F16 | P2 | Şartname analiz dokümanı güncel değil | Doküman |
| F17 | P2 | `HYDRO_AUTH_MODE` kabul ediliyor ama uygulanmıyor | Güvenlik/operasyon |

---

### F1 — P1: Form güncellemelerinde iyimser eşzamanlılık yok

**Kanıt**
- `webapp/backend/app/api/sessions.py:127-146` — `PUT /sessions/{session_id}/forms/{form_code}` `If-Match` başlığı okumuyor.
- `webapp/backend/app/schemas.py:524-527` — `SectionFormUpdateRequest` içinde `revision` alanı yok.
- `webapp/backend/app/services/dossier.py:5431-5440` — `update_session_form(...)` `expected_revision` parametresi almıyor.
- `webapp/frontend/src/lib/api.ts:654-660` — istemci de `ifMatch` göndermiyor; oysa aynı istemci `If-Match` desteğine sahip (`api.ts:246`).
- Karşılaştırma: `webapp/backend/app/api/sessions.py:537-546` (snapshot) ve `sessions.py:201-218` (oturum güncellemesi) `If-Match` + `409 revision_conflict` kullanıyor.

**Etki**
İki sekme, iki cihaz veya OCR onayı ile manuel düzenleme aynı anda yazdığında son yazan diğerinin değişikliğini sessizce siler. Form `revision` alanı artırılsa da istemciye çakışma sinyali gitmediği için 409 modalı (yeni eklenen `RevisionConflictModal`) bu akışta hiç devreye girmiyor. Bu, saha form verisi için en somut kayıp riskidir.

**Öneri**
`SectionFormUpdateRequest`'e `revision: int | None` ekle veya `If-Match` kullan; `update_session_form` içinde `row.revision` ile karşılaştır ve uyuşmazlıkta `revision_conflict` (409 + `details.expected_revision/current_revision`) döndür. İstemcide `api.updateSessionForm` çağrısına `ifMatch` geçir ve mevcut `extractRevisionConflict` akışına bağla. Form okuma yanıtına `ETag` ekle. **Efor: S–M.**

---

### F2 — P1: API sözleşmesi gerçek yüzeyden kopuk

**Kanıt**
- `webapp/docs/api_contract.md` içinde **59** endpoint bölümü var; uygulama **101** operasyon sunuyor (87 path).
- `webapp/docs/api_contract.md:1234-1235` — `include_raw_ocr` belgelenmiş; `webapp/backend/app/api/sessions.py:462,467` parametreyi alıp `_ = include_raw_ocr` ile **yok sayıyor**.
- `webapp/docs/api_contract.md:2204-2206` — "OpenAPI şeması CI'da üretilir ve `webapp/docs/openapi.json` olarak commit edilir" deniyor; dosya **yok**, CI'da üretim adımı **yok** (`.github/workflows/*.yml` içinde `openapi` geçmiyor).
- `webapp/frontend/src/lib/types.ts` elle yazılmış; `openapi-typescript` veya benzeri kod üretimi yok.

**Etki**
İstemci tipleri ile sunucu şeması sessizce ayrışabilir; `include_raw_ocr` gibi parametreler "çalışıyor" sanılır. Yeni müşteri/entegrasyon geliştiren ekip sözleşmeye güvenemez. Depoda tek doğruluk kaynağı yok.

**Öneri**
(a) `include_raw_ocr` ya uygulanmalı ya da sözleşmeden kaldırılmalı (tercihen uygulanması: OCR ham metnini rapora ekleme).
(b) CI'da `python -m app.tools.dump_openapi > webapp/docs/openapi.json` benzeri bir adım + `git diff --exit-code` kapısı ekle.
(c) Frontend tiplerini bu şemadan üret; en azından `npm run check:api` ile karşılaştır.
(d) `api_contract.md` bölüm sayısını gerçek yüzeyle eşleştir (eksik 42 operasyon). **Efor: M.**

---

### F3 — P1: Demo fallback yazmaları sessizce yutuyor

**Kanıt**
- `webapp/frontend/src/hooks/queries.ts:86-103` — `resolveWithMock`, `isRecoverableError` (yalnız `status === 0`) durumunda **global** `setBackend("demo")` yapıp mock döndürüyor.
- `webapp/frontend/src/lib/api.ts:338-340` — kurtarılabilir hata tanımı yalnız ağ/timeout (`status=0`).
- `webapp/frontend/src/hooks/queries.ts:145-173` — sağlık probu **45 sn**'de bir; bu süre boyunca backend `demo` kalıyor.
- `webapp/frontend/src/hooks/queries.ts:287-302` — oturum listesi bir kez ağ hatası alırsa `sessionApiReady=false`.
- `webapp/frontend/src/hooks/queries.ts:974-1050` — kaydetme, `backend !== "online" || sessionApiReady === false` iken sunucuya hiç gitmeden `{ demo: true }` dönüyor ve yalnız toast gösteriyor.
- Demo yazmalarını geri oynatan bir kuyruk yok (`grep` ile `replay|pendingSync|offlineQueue` sonuçsuz).
- `webapp/frontend/src/store/useAppStore.ts:430-459` — `inputs`/`results` doğrudan `localStorage`'a yazılıyor; kota hataları ele alınmıyor.

**Etki**
Güncelleme sırasında backend yeniden başlarsa veya kısa bir ağ kesintisi olursa, kullanıcının "Kaydet" işlemi tarayıcıya gider. 45 sn sonra backend `online` olsa bile bu değişiklikler sunucuya **asla** taşınmaz. `localStorage` kotası dolduğunda "kaydedildi" bildirimi yanlış olabilir. Sessiz veri kaybı riski.

**Öneri**
- `setBackend("demo")` yalnız kullanıcı açıkça demo moduna geçtiğinde veya prob üst üste N kez başarısız olduğunda tetiklensin; tek bir okuma hatası global modu değiştirmesin.
- Demo modunda yazma denendiğinde engelleyici bir uyarı göster ("Sunucuya ulaşılamıyor; bu kayıt yalnız tarayıcıda") ve/veya bekleyen değişiklik kuyruğu + bağlantı gelince otomatik gönderim ekle.
- `persist` için `QuotaExceededError` yakala, kullanıcıya bildir ve `markSaved` çağrısını yalnız gerçekten kalıcı olduğunda yap. **Efor: M.**

---

### F4 — P1: Docker dağıtımında DB yönetimi ve güncelleme yöneticisi kilitli

**Kanıt**
- `webapp/docker-compose.yml:12-14` — `HYDRO_HOST: "0.0.0.0"`, `HYDRO_ALLOW_REMOTE: "1"`.
- `webapp/backend/app/core/config.py:186-187` — `is_loopback_host` yalnız `127.0.0.1/localhost/::1` için `True`.
- `webapp/backend/app/api/system.py:86-121` — yönetici kapısı sırasıyla: token varsa zorunlu; `auth_mode != none` ise 403; **bind loopback değilse 403**; proxy başlığı varsa 403; soket eşi loopback değilse 403.
- `webapp/frontend/src/features/settings/DatabaseAdminPanel.tsx` — `X-Hydro-Admin-Token` alanı yok; `webapp/frontend/src/lib/api.ts` bu başlığı hiç göndermiyor.
- Aynı kapı `/api/update/*` uçlarında da kullanılıyor (`api/system.py:168-230`).

**Etki**
Belgelenen Docker kurulumunda (konak loopback'e publish edilse bile) sunucu `0.0.0.0` dinlediği için yedekleme, geri yükleme, çöp kutusu, workspace devralma ve güncelleme yöneticisi **tamamen 403** döner. Arayüzde token girme yolu olmadığından `HYDRO_LOCAL_ADMIN_TOKEN` ayarlamak da sorunu çözmez; aksine paneli kilitlemeye devam eder.

**Öneri**
- Kapıyı bind adresine değil **istek kaynağına** göre değerlendir (Docker'da `172.17.0.1` / konak ağ geçidi güvenilir kabul edilebilir) veya Docker için ayrı bir `HYDRO_TRUSTED_ADMIN_CIDRS` ayarı ekle.
- `DatabaseAdminPanel`'e token alanı ekle ve `api.ts` üzerinden `X-Hydro-Admin-Token` gönder; token'ı yalnız `sessionStorage`'da tut.
- Docker README'sinde bu iki özelliğin token olmadan çalışmadığını açıkça yaz. **Efor: S–M.**

---

### F5 — P2: Büyük yüklemeler tamamen RAM'de; gövde/eşzamanlılık sınırı yok

**Kanıt**
- `webapp/backend/app/core/security.py:137-158` — `read_upload_bounded` parçaları `list[bytes]` içinde toplayıp sonda `b"".join(...)` yapıyor; 500 MB'a kadar iki kat bellek.
- `webapp/backend/app/core/config.py:178-179` — üst sınır 500 MB.
- `webapp/backend/app/api/projects.py:83-95` (arşiv, 200 MB), `webapp/backend/app/api/system.py:341-348` (DB restore, 500 MB), `webapp/backend/app/api/imports.py:94-100` (masaüstü DB) aynı yolu kullanıyor.
- JSON gövdeleri için `Content-Length`/gövde boyutu denetimi yok (`grep` sonuçsuz); eşzamanlı yükleme sayısını sınırlayan global bir semafor yok.

**Etki**
Docker'da `mem_limit: 2g`; 500 MB'lık bir yükleme + join + SQLAlchemy nesneleri OOM'a yol açabilir. Aynı anda iki büyük yükleme kabul edilirse süreç düşer (tek worker).

**Öneri**
- Yüklemeyi geçici dosyaya akıt (`SpooledTemporaryFile`), yalnız gerekli kısmı belleğe al; arşiv/zip için `zipfile` üzerinden akışlı doğrulama yap.
- Global yükleme semaforu (ör. 1–2 eşzamanlı) ve JSON gövdeleri için `max_body_bytes` middleware'i ekle. **Efor: M.**

---

### F6 — P2: Analiz uçlarında sınırsız liste girdileri

**Kanıt**
- `webapp/backend/app/schemas.py:185-188` — `PressurizationRampRequest.readings` üst sınırsız.
- `webapp/backend/app/schemas.py:197-199` — `PressureHoldRequest.readings` üst sınırsız.
- `webapp/backend/app/schemas.py:252-253` — `ThermalBalanceRequest.records` üst sınırsız.
- `webapp/backend/app/schemas.py:64-66` — `GeometryIn.sections` üst sınırsız.
- Karşılaştırma: `webapp/backend/app/schemas.py:461` — time-series batch `max_length=1000` ile sınırlı.

**Etki**
Tek istekte milyonlarca kayıt gönderilerek CPU/bellek tüketilebilir (özellikle `thermal_balance` ve geometri indirgemesi O(n log n)). `extra="ignore"` ile birleşince istemci hatası da sessizce kabul edilir.

**Öneri**
Her alana gerçekçi üst sınır koy (ramp/hold için ör. 5.000, termal için 10.000, geometri için 2.000) ve aşımda 422 döndür. **Efor: S.**

---

### F7 — P2: Export dosyaları birikiyor; proje arşivi bellekte kuruluyor

**Kanıt**
- `webapp/backend/app/services/reports.py:544-548` — her oturum export'u `exports_dir/{session_id}/{zaman}-{uuid}-report.*` olarak **yeni** dosya üretiyor.
- `webapp/backend/app/services/reports.py:636-642` — ad-hoc export'lar `exports_dir/_adhoc` altında birikiyor.
- Otomatik yaşlandırma/TTL yok; temizlik yalnız yönetici "Bakım" işleminde `clean_exports=True` ile yapılıyor (`services/db_admin.py:849-861`).
- `webapp/backend/app/api/projects.py:306-323` — proje arşivi `zip_bytes` olarak bellekte üretilip döndürülüyor; `project_archive.py` ekleri de `attachment_blobs` sözlüğünde topluyor.

**Etki**
Uzun süre çalışan kurulumda disk şişer; her export yeni dosya olduğu için aynı rapor tekrar tekrar üretilir. Proje arşivi 200 MB'a kadar eklerle bellekte iki kopya oluşturabilir.

**Öneri**
- Export'ları içerik hash'i ile anahtarla ve aynı parametrelerle tekrar üretme; `created_at` + TTL (ör. 24 saat) ile otomatik sil.
- Proje arşivini `StreamingResponse` + geçici dosya ile üret. **Efor: M.**

---

### F8 — P2: Ağır uçlarda rate limit eksik

**Kanıt**
- `webapp/backend/app/api/sessions.py:457-467` — `GET /sessions/{id}/export` rate limit yok.
- `webapp/backend/app/api/projects.py:306-323` — `GET /projects/{id}/archive` rate limit yok.
- `webapp/backend/app/api/sessions.py:417-425` — `GET /sessions/{id}/scene` rate limit yok.
- `webapp/backend/app/api/system.py:313-322` — yedek indirme rate limit yok.
- Karşılaştırma: `webapp/backend/app/api/reports.py:24` ad-hoc export'ta `limit=30` uyguluyor.
- `webapp/backend/app/core/rate_limit.py` süreç-içi ve yalnız istemci IP'sine göre; proxy arkasında tüm istemciler tek kovayı paylaşır, çok worker'da limit çarpanlanır.

**Etki**
PDF/zip üretimi CPU ve disk yoğun; tek istemci art arda çağırarak sunucuyu meşgul edebilir. Proxy arkasında ise tek kullanıcı diğerlerinin kotasını tüketebilir.

**Öneri**
Export/arşiv/scene uçlarına `bucket` bazlı limit ekle; anahtarı `workspace.hash` ile birleştir; çok worker hedefi varsa Redis tabanlı limitleyiciye geçiş planla. **Efor: S.**

---

### F9 — P2: OCR kuyruğu process-içi; worker sayısı sabit 1

**Kanıt**
- `webapp/backend/app/services/ocr_queue.py:1-60` — `ThreadPoolExecutor` tabanlı, süreç-içi kuyruk; iptal/ETA durumu bellekte.
- `webapp/run_web.py:150-157` — `uvicorn.run(..., workers=1)` sabit.
- `webapp/docs/architecture.md:801,872` — `HYDRO_WEB_WORKERS` ile Postgres'te worker artırılabileceği yazıyor; kodda bu değişken **hiç okunmuyor**.
- `webapp/backend/app/core/config.py:140` — varsayılan OCR eşzamanlılığı 1.

**Etki**
Birden fazla worker/konteyner çalıştırılırsa `status`, `cancel`, `eta` yanıtları yanlış sonuç verir (iş başka worker'da). Tek worker'da ise uzun bir OCR işi tüm kuyruğu bloklar.

**Öneri**
`HYDRO_WEB_WORKERS`'ı gerçekten uygula (SQLite'ta 1'e zorla) veya kuyruğu Redis/RQ / Postgres `FOR UPDATE SKIP LOCKED` tabanlı hale getir; `run_web.py` sabitini kaldır. **Efor: L.**

---

### F10 — P2: OCR sayfasından ayrılınca analiz durmuyor

**Kanıt**
- `webapp/frontend/src/features/ocr/OcrPage.tsx:470-471` — analiz `AbortController` oluşturup `abortRef`'e atıyor.
- `OcrPage.tsx:534-541` — iptal yalnız `handleCancel` ile.
- `OcrPage.tsx:591-595` — `resetAll` de abort ediyor.
- Sayfa unmount olduğunda `abortRef.current?.abort()` çağıran bir `useEffect` cleanup'ı **yok** (yalnız profil efekti `OcrPage.tsx:341-362` cleanup'lı).
- `webapp/frontend/src/features/ocr/ocrApi.ts:307` — `waitForAnalysis` 750 ms'de bir, 630 sn'ye kadar poll ediyor.

**Etki**
Kullanıcı sekme değiştirse bile istemci polling'e devam eder; sunucudaki iş `cancelOcrAnalysis` çağrılmadığı için çalışmaya devam eder ve tek OCR slotunu işgal eder. Bir sonraki analiz kuyrukta bekler.

**Öneri**
`useEffect(() => () => { abortRef.current?.abort(); if (jobIdRef.current) void cancelOcrAnalysis(jobIdRef.current); }, [])` ekle; `jobId`'yi ref'te tut. **Efor: S.**

---

### F11 — P2: OCR istemci timeout'u sabit 630 sn

**Kanıt**
- `webapp/frontend/src/features/ocr/ocrApi.ts:307` — `timeoutMs = 630_000` sabit.
- `webapp/backend/app/core/config.py:139,214` — sunucu `HYDRO_OCR_TIMEOUT_S` (varsayılan 600) ile değiştirilebilir.

**Etki**
Sunucu timeout'u 1.800 sn'ye çıkarılırsa istemci 630 sn'de vazgeçer, sunucu işi sürer; kullanıcı "zaman aşımı" görürken arka planda iş Devam eder. Tersi durumda da gereksiz bekleme olur.

**Öneri**
`/api/system/meta` yanıtına `ocr_timeout_s` ekle ve istemciyi bundan türet; en az `timeout = server + 30 sn` kullan. **Efor: S.**

---

### F12 — P2: DB restore canlı isteklerin altında motoru değiştiriyor

**Kanıt**
- `webapp/backend/app/services/db_admin.py:548` — `_RESTORE_LOCK` yalnız restore'ları serileştiriyor.
- `db_admin.py:595-611` — `dispose_database()` + dosya değiştirme + `configure_database()` + `init_db()`.
- `webapp/backend/app/api/system.py:330-348` — restore ucu bilinçli olarak `get_db()` bağımlılığı almıyor; ancak diğer eşzamanlı istekler açık oturum tutabilir.

**Etki**
Tek süreç/tek worker varsayımı altında bile threadpool'daki bir istek eski SQLite dosyasına yazarken dosya değiştirilirse "database is locked" veya kayıp yazma oluşabilir. Çok worker'da diğer süreçler eski dosyayı kullanmaya devam eder.

**Öneri**
Restore sırasında uygulamayı bakım moduna al (yeni istekleri 503 ile reddet), aktif isteklerin bitmesini bekle; çok worker'da yönetici işlemini ayrı süreç/CLI'ya taşı. **Efor: M.**

---

### F13 — P2: PostgreSQL desteği doğrulanmamış

**Kanıt**
- `webapp/requirements-web.txt:21-22` — `psycopg` yalnız **yor** olarak duruyor.
- `webapp/docs/architecture.md:44-45,265,625,850,872` — Postgres'e geçiş ve `HYDRO_DATABASE_URL` örnekleri anlatılıyor.
- `.github/workflows/test.yml` — Postgres servisi veya Postgres'e karşı test adımı yok.
- `webapp/docker-compose.yml:39-49` — Postgres servisi yorum satırında.

**Etki**
Kullanıcı dokümana güvenip Postgres'e geçtiğinde `psycopg` kurulu olmadığı için uygulama açılmaz; kurulsa bile Alembic `0002/0003` ve JSON/UUID tipleri yalnız SQLite'ta test edilmiştir.

**Öneri**
Ya "deneysel" olarak işaretle ve README'de SQLite'ı tek desteklenen yol ilan et, ya da `psycopg[binary]` bağımlılığını ekleyip CI'ya Postgres servisli bir pytest job'ı koy. **Efor: M.**

---

### F14 — P2: Web için kapsam eşiği ve sayfa testleri yok

**Kanıt**
- `pyproject.toml:42,56` — `[tool.coverage.run] source = ["hidrostatik_test"]`, `fail_under = 65`; webapp kapsam dışı.
- `.github/workflows/test.yml:100-120` — web pytest job'ı kapsam ölçmüyor.
- `webapp/frontend/src` altında 16 test dosyası var; `OcrPage`, `ReportsPage`, `SectionFormPage`, `ProjectsPage`, `SettingsPage`, `DashboardPage` için sayfa testi yok.

**Etki**
Web kapsamı regresyona açık; yeni eklenen OCR/segment/SMYS akışları yalnız backend testleriyle korunuyor. Sayfa düzeyi hatalar (F10 gibi) birim testlerle yakalanmıyor.

**Öneri**
Web için ayrı bir kapsam hedefi tanımla (ör. `--source=webapp/backend/app --fail-under=80`), CI'ya ekle. En az OCR akışı, form kaydetme/409, rapor export ve DB admin paneli için Testing Library testleri ekle. **Efor: M.**

---

### F15 — P2: `extra="ignore"` sözleşme kaymasını gizliyor

**Kanıt**
- `webapp/backend/app/schemas.py:34-35` — `StrictModel` `extra="ignore"`.

**Etki**
İstemci yanlış alan adı gönderdiğinde (ör. `smysMpa` yerine `smys_mpa` yazım hatası) sunucu 422 vermez, alanı sessizce atar; sonuç "değer kaydedilmedi" şeklinde fark edilmesi zor bir hataya dönüşür. Sözleşme testleri de bu tür kaymayı yakalayamaz.

**Öneri**
Yazma modellerinde `extra="forbid"` kullan; en azından form/analiz gövdelerinde. Kırıcı olabilecek alanlar için geçiş dönemi tanı. **Efor: S.**

---

### F16 — P2: Şartname analiz dokümanı güncel değil

**Kanıt**
- `docs/spec/ngtl_5007_hydrostatic_analysis.md:11-15` — "24 saatlik kayıt toplama, basınç-hacim izleme, basınç düşürme ve boşaltma iş akışları henüz modellenmedi" deniyor.
- `docs/spec/ngtl_5007_hydrostatic_analysis.md:50-52` — 12. bölüm ve 14.3 için "yok" deniyor; oysa `hidrostatik_test/domain/time_series.py` ve `pressurization_monitor.py` ile web'e bağlı.
- Dosyada arşiv/tarih notu yok.

**Etki**
Yeni geliştirici veya denetçi, tamamlanmış özellikleri eksik sanıp tekrar iş planlar; şartname uyum kanıtı olarak kullanıldığında yanıltıcı olur.

**Öneri**
Dosyanın başına "tarihsel analiz" notu ekle veya güncel durumu yansıtacak şekilde revize et; `DURUM.md` ile çapraz bağlantı ver. **Efor: S.**

---

### F17 — P2: `HYDRO_AUTH_MODE` kabul ediliyor ama uygulanmıyor

**Kanıt**
- `webapp/backend/app/core/config.py:189-192` — `has_enforced_auth` her zaman `False`.
- `webapp/backend/app/main.py:125-129` — `HYDRO_AUTH_MODE != "none"` ise yalnız uyarı loglanıyor.
- `webapp/backend/app/core/config.py:246-259` — uzak bind yalnız `HYDRO_ALLOW_REMOTE=1` ile açılabiliyor (fail-closed, doğru davranış).
- `webapp/docs/architecture.md:237` — `none|oidc` "planlanan" bölümünde.

**Etki**
Operatör `HYDRO_AUTH_MODE=oidc` ayarlayıp `HYDRO_ALLOW_REMOTE=1` verirse hiçbir kimlik doğrulama olmadan dış arayüze açılır. Başlangıç uyarısı log'da kalır; README'de bu değişkenin etkisiz olduğu açıkça yazmıyor.

**Öneri**
`HYDRO_AUTH_MODE != "none"` iken uygulamayı **başlatmayı reddet** ("bu sürümde uygulanmıyor") veya reverse-proxy auth zorunluluğunu `HYDRO_ALLOW_REMOTE` ile birlikte açık onay metniyle iste. README'ye net not ekle. **Efor: S.**

---

## 4. Kategori Eşlemesi

| Kategori | Bulgular |
| --- | --- |
| Veri bütünlüğü | F1, F3, F12 |
| Güvenlik / kötüye kullanım | F4, F5, F6, F8, F17 |
| API sözleşmesi | F2, F11, F15 |
| Performans / kaynak | F5, F6, F7, F9, F10 |
| Güvenilirlik / dağıtım | F4, F9, F12, F13 |
| Test / kalite kapısı | F14 |
| Dokümantasyon | F2, F13, F16, F17 |

---

## 5. Yol Haritası

### Aşama 0 — Hızlı kazanımlar (1–2 gün)
1. **F1**: Form `PUT` için `If-Match`/`revision` + 409 (S–M).
2. **F4**: Docker yönetici kapısını istek kaynağına göre düzelt; panele token alanı ekle (S–M).
3. **F10**: OCR sayfası unmount cleanup + `cancelOcrAnalysis` (S).
4. **F15**: Yazma modellerinde `extra="forbid"` (S).
5. **F6**: Analiz listelerine üst sınır (S).
6. **F8**: Export/arşiv/scene için rate limit (S).
7. **F17**: `HYDRO_AUTH_MODE != none` iken başlatmayı reddet (S).
8. **F16**: Şartname analiz dokümanına arşiv notu (S).

### Aşama 1 — Sözleşme ve dayanıklılık (1–2 hafta)
9. **F2**: `include_raw_ocr` uygula; OpenAPI dump + CI `git diff` kapısı; frontend tiplerini üret (M).
10. **F3**: Demo fallback'i tek hata ile tetiklenmeyecek şekilde sıkılaştır; bekleyen yazma kuyruğu veya engelleyici uyarı (M).
11. **F7**: Export TTL + içerik hash'i; proje arşivini akıt (M).
12. **F11**: OCR timeout'unu meta'dan türet (S).
13. **F5**: Yüklemeleri geçici dosyaya akıt; global yükleme semaforu + gövde sınırı (M).
14. **F14**: Web kapsam eşiği + eksik sayfa testleri (M).

### Aşama 2 — Ölçeklenme ve dağıtım (2–6 hafta)
15. **F9**: OCR kuyruğunu süreçler arası hale getir; `HYDRO_WEB_WORKERS`'ı uygula (L).
16. **F12**: Restore için bakım modu / ayrı CLI (M).
17. **F13**: Postgres CI job'ı ve bağımlılığı; gerçekten desteklenmiyorsa "deneysel" olarak işaretle (M).

---

## 6. Doğrulama Komutları

```bash
# Backend kalite kapıları
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy --ignore-missing-imports webapp/backend/app
python3 -m pytest webapp/backend/tests -q

# Web'e özel kapsam (varsayılan kapı web'i ölçmüyor)
python3 -m coverage run --source=webapp/backend/app -m pytest webapp/backend/tests -q
python3 -m coverage report --skip-covered

# OpenAPI yüzeyi
python3 - <<'PY'
from webapp.backend.app.main import create_app
from webapp.backend.app.core.config import Settings
spec = create_app(Settings.from_env()).openapi()
ops = sum(len([m for m in v if m in {"get","post","put","patch","delete"}]) for v in spec["paths"].values())
print("paths", len(spec["paths"]), "operations", ops)
PY

# Frontend
cd webapp/frontend
npm run lint && npm test && npm run typecheck && npm run build && npm run check:bundle
```

---

## 7. Doğrulanan Olumlu Noktalar

- **Güvenlik varsayılanı doğru**: loopback dışı bind, `HYDRO_ALLOW_REMOTE=1` olmadan reddediliyor (`config.py:246-259`); Host/DNS-rebinding, CSP, same-origin ve proxy başlığı kapıları mevcut.
- **Updater fail-closed**: SHA-256 + Ed25519 imza zorunlu; `HYDRO_ALLOW_UNSIGNED_UPDATE` gibi kaçış bayrakları yalnız açıkça verilirse devre dışı (`updater.py:547-558`).
- **Arşiv/DB import sağlamlaştırılmış**: zip yol geçişi, boyut ve entry sayısı sınırları, SQLite sihirli bayt denetimi, atomik staging + rollback (`db_admin.py:528-635`, `project_archive.py:340-420`).
- **Formül enjeksiyonu önlenmiş**: XLSX/CSV hücrelerinde `=`, `+`, `-`, `@` kaçışı uygulanıyor.
- **Yeni domain modelleri web'e bağlı**: 14.1–14.3, 12/15, 16–17, +2 °C ve segment SMYS; `reports.py:227-231,427-431` bu bölümleri PDF/XLSX/TXT çıktısına ekliyor.
- **409 revizyon akışı oturum düzeyinde çalışıyor**: `RevisionConflictModal` + `extractRevisionConflict` + `If-Match` (`api.ts:98-140,246`, `sessions.py:537-546`).

---

## 8. Kapsam Dışı ve Doğrulanmayanlar

- Masaüstü Tkinter arayüzü ve `hidrostatik_test/ui/*` incelenmedi (yalnız web'e bağlanan domain servisleri).
- Docker imajı ve Postgres bağlantısı **çalıştırılmadı**; ilgili bulgular kod/doküman karşılaştırmasına dayanır.
- Tarayıcıda gerçek uçtan uca senaryo (Playwright/Cypress) çalıştırılmadı; `verify-tabs.mjs` CI'da yok ve bu raporda koşturulmadı.
- Çalışma ağacındaki commit edilmemiş OCR/ayrıştırma değişiklikleri kullanıcı işi kabul edildi; değiştirilmedi.
