# HYDRO — İyileştirme Önerileri (v1)

> **Tarih:** 24 Kasım 2026
> **Baseline:** `main` @ `e413967` (`v2.1.0` + v4 denetim düzeltmeleri)
> **Kapsam:** Web backend (FastAPI), web frontend (React/Vite), OCR/rapor hattı, test/CI ve dağıtım.
> **Girdi:** [`analysis_report_v4.md`](analysis_report_v4.md) (F1–F29), güncel kalite kapıları ve kod incelemesi.

> **Not (26 Kasım 2026):** Bu dosya v2.1.0 (`e413967`) anlık görüntüsüdür ve tarihsel kayıt olarak korunur. Güncel durum, kapanan R1–R18 maddeleri ve yeni R19–R26 önerileri için [`improvement_recommendations_v2.md`](improvement_recommendations_v2.md) esas alınmalıdır.
> **Amaç:** Kapanan denetim bulgularından sonra sıradaki ürün, ölçek ve mühendislik yatırımlarını önceliklendirmek.

---

## 1. Yönetici Özeti

v4 denetimindeki F18–F29 bulguları `e413967` ile büyük ölçüde kapatıldı: tur mobil fallback'i, yazma şemalarında `extra="forbid"`, `generate-sample` hız sınırı + yeniden kullanım, OCR arka plan göstergesi, Postgres CI job'ı ve CI sözleşme kapıları eklendi. Mevcut kapılar yeşil:

| Kapı | Güncel sonuç |
| --- | --- |
| `ruff check` / `ruff format --check` | PASS (153 dosya) |
| `mypy` domain / web | PASS (14 / 50 dosya) |
| Backend pytest | **255 passed**, 1 skipped (Postgres CI-only), **%83** kapsam |
| OCR unittest | 76 OK (1 skipped) |
| OpenAPI | 87 path / 101 operation, dosya güncel |
| Frontend lint / typecheck / test | PASS — **67 Vitest / 21 dosya** |
| Build / bundle | PASS — **148,8 kB** JS + **15,3 kB** CSS gzip |
| `check:api` | PASS — 74 şablon / 87 path |
| `verify-tabs` | **12/12 PASS** (Dashboard stepper kontrolü güncel) |
| Masaüstü unittest | **733 OK** (1 skipped) — tam paket yeniden çalıştırıldı |

Bu nedenle öneriler artık "hata düzeltme" değil, şu üç başlıkta yoğunlaşıyor:

1. **Sürüm güvenilirliği:** Gerçek tarayıcı smoke/E2E'nin CI'da zorunlu olması ve sürüm öncesi tek komut kapı.
2. **Ölçeklenebilirlik:** OCR kuyruğunun süreç-içi yapıdan kalıcı işçiye taşınması; çok worker ve Postgres yolunun netleştirilmesi.
3. **Kurumsal ürünleşme:** Auth/OIDC + RBAC, mobil/erişilebilirlik kabulü, gözlemlenebilirlik ve yedekleme disiplini.

**En yüksek getirili 5 iş:** R1 (CI E2E), R2 (release gate), R3 (kalıcı OCR kuyruğu), R4 (Auth/OIDC), R5 (mobil + a11y kabul testleri).

---

## 2. Öncelik Matrisi

| ID | Öneri | Alan | Etki | Efor | Öncelik |
| --- | --- | --- | --- | --- | --- |
| R1 | CI'da gerçek tarayıcı smoke + E2E happy path | Test / CI | Yüksek | M | **P0** |
| R2 | Tek komut "release gate" + doküman/versiyon senkronu | CI / süreç | Yüksek | S | **P0** |
| R3 | OCR kuyruğunu kalıcı, çok-worker uyumlu işçiye taşı | Mimari | Yüksek | L | **P0** |
| R4 | Auth/OIDC + RBAC + iki kişi onayı | Güvenlik | Çok yüksek | L | **P0** |
| R5 | Mobil/tablet kabul testleri ve düzeltmeleri | UX | Yüksek | M | P1 |
| R6 | Tur yaşam döngüsü: kalıcılık, demo rozeti, temizlik | UX / veri | Orta | S | P1 |
| R7 | Form doldurma verimliliği (taslak, doğrulama özeti, kısayol) | UX | Yüksek | M | P1 |
| R8 | Erişilebilirlik: axe, odak yönetimi, kontrast, reduced-motion | UX / a11y | Orta | M | P1 |
| R9 | Büyük veri performansı: sanallaştırma + grafik örnekleme | Performans | Orta | M | P1 |
| R10 | Kritik hesap için golden/property/mutation testleri | Test | Yüksek | M | P2 |
| R11 | OpenAPI'den istemci tipi üretimi ve şema diff kapısı | Sözleşme | Orta | M | P2 |
| R12 | Hız sınırlayıcıyı dağıtık hale getir veya tek-worker zorunlu kıl | Mimari | Orta | M | P2 |
| R13 | Yönetici token'ı ve CSP/dependency sertleştirmesi | Güvenlik | Orta | M | P2 |
| R14 | Gözlemlenebilirlik: metrik, kuyruk/DB görünürlüğü, hata izleme | Operasyon | Orta | M | P2 |
| R15 | Yedekleme, saklama ve restore tatbikatı otomasyonu | Operasyon | Orta | M | P2 |
| R16 | Masaüstü Tk testlerini izole süreç/job'a al | Test | Düşük | S | P3 |
| R17 | DX: pre-commit, `make/just`, bağımlılık taraması | Mühendislik | Orta | S | P3 |
| R18 | Doküman tek kaynak: üretilen sayılar ve sözleşme bölümleri | Doküman | Düşük | S | P3 |

> Efor: S ≤ 1 gün, M ≈ 2–5 gün, L ≈ 1–3 hafta (tek geliştirici varsayımı).

---

## 3. P0 — Sürüm Güvenilirliği ve Kurumsal Ön Koşullar

### R1 — CI'da gerçek tarayıcı smoke + E2E happy path

**Neden**
- `verify-tabs.mjs` 12 sekmeyi gerçek tarayıcıda doğruluyor ancak `.github/workflows/*.yml` içinde **çalışmıyor**; yalnız elle koşuluyor.
- v2.1.0'da Dashboard başlığı kaldırıldığında smoke testi kırıldı (F29) ve ancak manuel denetimde fark edildi. Aynı sınıf hata, test çalışmadığı için sürüme girebilir.
- `npm test` bileşen düzeyinde güçlü; ancak gerçek yönlendirme, popover ve dialog davranışını kapsamıyor.

**Öneri**
- `verify-tabs.mjs`'i build + `uvicorn` başlatan bir CI job'ına bağla (izole SQLite, rastgele port, `--self-test` benzeri health bekleme).
- Playwright ile 1 kritik akış ekle: örnek proje oluştur → kesit aç → 020 formunu doldur → kaydet → rapor önizle.
- Başarısızlıkta ekran görüntüsü, trace ve sunucu logunu artifact olarak yükle.
- Smoke'u `pull_request` için **required check** yap; gece koşusunda 3 viewport (375 / 768 / 1440) çalıştır.

**Kabul kriteri**
- PR'larda smoke < 8 dk; 20 ardışık koşuda flake oranı < %2.
- Yönlendirme veya kritik akış kırıldığında PR kırmızı olur.

**Efor:** M

---

### R2 — Tek komut "release gate" + doküman/versiyon senkronu

**Neden**
- v2.1.0, `ruff format --check` kırmızıyken commit edildi (F28); sürüm commit'i kapıları çalıştırmadı.
- Test sayıları ve bundle değeri README/DURUM/`implementation_status` arasında geçmişte defalarca kaydı (F27).
- Kapılar birden fazla workflow'a dağılmış; yerelde "hepsini çalıştırdım" güvencesi yok.

**Öneri**
- `scripts/release_gate.py` (veya `make release-check`):
  - `ruff check`, `ruff format --check`, `mypy` (domain + web), backend pytest + kapsam, OCR testleri, `dump_openapi --check`, frontend lint/typecheck/test/build/bundle/check:api, `verify-tabs`.
  - Sürüm tutarlılığı: `app_metadata.APP_VERSION` = `package.json` = `CHANGELOG.md` başlığı = `WHATS_NEW.md` = `DURUM.md` dal satırı.
  - README/DURUM'daki test/bundle sayılarını komut çıktısından doğrula veya `--fix-docs` ile güncelle.
- CI, aynı betiği parçalara bölerek çalıştırsın; sürüm etiketi atmadan önce `release.yml` bu betiği zorunlu tutsun.
- `ruff format --check` ve `openapi --check` zaten `lint.yml`'de; betik bunları tekrar etmek yerine çağırsın.

**Kabul kriteri**
- Yeni sürüm yalnızca `release_gate` yeşilse etiketlenir.
- Doküman sayıları ile ölçümler arasında sürümde fark kalmaz.

**Efor:** S

---

### R3 — OCR kuyruğunu kalıcı, çok-worker uyumlu işçiye taşı

**Neden**
- OCR kuyruğu `ThreadPoolExecutor` ile **web süreci içinde** (`ocr_queue.py`); `HYDRO_WEB_WORKERS > 1` OCR açıkken önerilmiyor, SQLite'ta 1'e sabitleniyor.
- Süreç yeniden başlarsa `queued/running` kayıtlar `worker_interrupted` olarak işaretleniyor; iş kaybolmasa da ilerleme ve sahiplik tarayıcıya bağlı.
- v2.1.0'da TopBar göstergesi ve iptal eklendi; bu görünürlüğü kalıcı iş modeliyle tamamlamak gerekiyor.

**Öneri**
- `ocr_analyses` tablosunu iş kuyruğu olarak kullan: `status`, `lease_until`, `attempts`, `cancel_requested`, `progress`, `error_code`.
- Ayrı işçi süreci: `python -m app.worker.ocr`; Postgres'te `FOR UPDATE SKIP LOCKED`, SQLite'ta tek tüketici.
- Lease/heartbeat + sınırlı retry; iptal bayrağı DB'de (tarayıcı kapansa da geçerli).
- İlerleme için polling yeterli; ileride SSE/WebSocket'e geçiş kapısı bırak.
- Web ve worker aynı imajı kullansın; `docker-compose`'a `ocr-worker` servisi ekle.

**Kabul kriteri**
- Worker restart'ında iş kaybı yok; yarıda kalan iş yeniden denenir veya açık hata verir.
- 2 web worker + 1 OCR worker ile kuyruk tutarlı çalışır; kuyruk derinliği ve p95 bekleme ölçülür.

**Efor:** L

---

### R4 — Auth/OIDC + RBAC + iki kişi onayı

**Neden**
- `HYDRO_AUTH_MODE != none` başlatmayı reddediyor; uygulama anonim `X-Session-ID` ile çalışıyor ve loopback dışına çıkmak `HYDRO_ALLOW_REMOTE=1` istiyor.
- Kurumsal kullanımda "kim hangi projeyi değiştirdi", "raporu kim onayladı" sorusu audit kaydıyla sınırlı; kimlik doğrulama yok.
- Docker/uzak sunucu senaryosunda paylaşımlı yönetici token'ı tek başına yeterli değil.

**Öneri**
- OIDC Authorization Code + PKCE; web oturumu **HttpOnly, Secure, SameSite=Lax** çerez.
- Roller: `operator`, `supervisor`, `admin`; proje/workspace bazlı ACL.
- Nihai rapor ve `db-restore` için **iki kişi onayı** (istek + onay ayrı kullanıcı, audit kaydı).
- Yerel tek kullanıcı modu (`auth_mode=none`) korunur; kurumsal modda zorunlu.
- Oturum süresi/rotation, idle timeout, merkezi çıkış.

**Kabul kriteri**
- Yetkisiz kullanıcı proje verisi göremez; rol matrisi testlerle doğrulanır.
- Onay akışı olmadan rapor "final" işaretlenemez; audit kaydı iki aktörü de içerir.

**Efor:** L (mimari karar + güvenlik incelemesi)

---

## 4. P1 — Ürün ve Kullanıcı Deneyimi

### R5 — Mobil/tablet kabul testleri ve düzeltmeleri

**Neden**
- Tur için <1024 px fallback eklendi; ancak uygulama hâlâ masaüstü öncelikli. `verify-tabs` tek viewport'ta (1000×700) koşuyor.
- Form tabloları yoğun; 375 px'te yatay taşma, dokunma hedefi ve çekmece davranışı sistematik doğrulanmıyor.
- F18'in ilk hali, responsive davranışın yalnız kod incelemesiyle yakalanamayacağını gösterdi.

**Öneri**
- Playwright viewport matrisi: 375×812, 768×1024, 1024×768, 1440×900.
- Her viewport'ta: yatay taşma yok, ana eylemler görünür, tur adımları hedefi buluyor, tablolar kaydırılabiliyor, dialog'lar ekrana sığıyor.
- Görsel regresyon için kritik 5 ekranın snapshot'ı (dashboard, projeler, form, OCR, rapor).
- Dokunma hedefleri ≥ 44 px; sidebar çekmecesi ve TopBar eylemleri gözden geçirilir.

**Kabul kriteri**
- 375 px'te kritik ekranlarda yatay scroll yok; turun 5 adımı da hedefi vurguluyor.
- Viewport matrisi CI'da çalışır; yeni responsive regresyon PR'da yakalanır.

**Efor:** M

---

### R6 — Tur yaşam döngüsü: kalıcılık, demo rozeti ve temizlik

**Neden**
- `tourActive`, `tourStep`, `tourSampleProjectId` Zustand `partialize` listesinde yok; sayfa yenilenince tur ve demo proje ilişkisi kayboluyor.
- Terk edilen tur, `DEMO-TUR` projesini sahipsiz bırakabiliyor; yeniden kullanım (`reuse_existing`) eklendi ancak kullanıcıya görünür "demo" işareti ve temizleme akışı yok.
- Yardım menüsü artık aynı `useStartDemoTour` akışını kullanıyor; davranış tutarlı, yaşam döngüsü eksik.

**Öneri**
- Tur durumunu hafifçe kalıcılaştır: `tourActive`, `tourStep`, `tourSampleProjectId`, `tourStartedAt`.
- Demo projeye `is_demo`/rozet ve "Demo projeyi temizle" eylemi; tur bitince veya "Şimdi değil" sonrası sor.
- 7 günden eski sahipsiz `DEMO-*` projeler için bakım temizliği (soft-delete + çöp kutusu).
- Tur olayları için hafif telemetri (başladı/bitirdi/atladı) — yerel ve anonim.

**Kabul kriteri**
- Yenilemede tur kaldığı adımdan devam eder veya temiz kapanır; yetim demo proje kalmaz.
- Kullanıcı demo verisini tek tıkla temizleyebilir.

**Efor:** S

---

### R7 — Form doldurma verimliliği

**Neden**
- 11 BOTAŞ formu ve yoğun tablolar var; `pasteUtils` ile toplu yapıştırma mevcut, ancak otomatik taslak, alan bazlı doğrulama özeti ve kaydedilmemiş değişiklik koruması görünmüyor.
- `revision`/`If-Match` çakışma modalı güçlü; otomatik kaydetme olmadığı için kullanıcı sekme kapatınca iş kaybedebilir.

**Öneri**
- Form bazlı "eksik/hatalı alan" özeti ve tıklayınca alana gitme.
- 1–2 sn debounce'lu otomatik taslak (sunucuya değil, yerel taslak); "Kaydet" açık kalır.
- Sekme kapatma/uygulama içi geçişte kaydedilmemiş değişiklik uyarısı.
- Klavye: `Ctrl/Cmd+S`, alanlar arası `Tab` düzeni, satır ekle/sil kısayolları, `Esc` dialog kapatma.
- Toplu yapıştırmada önizleme + hücre tipi uyuşmazlığı uyarısı.

**Kabul kriteri**
- Örnek bir formun doldurulma süresi ölçülür ve %20+ iyileşir.
- Kaydedilmemiş değişiklikle sekme kapatma uyarısı test edilir.

**Efor:** M

---

### R8 — Erişilebilirlik disiplini

**Neden**
- `eslint-plugin-jsx-a11y` ve native `<dialog>` kullanımı iyi bir temel; ancak otomatik axe taraması, odak tuzağı testi ve kontrast doğrulaması yok.
- Tur popover'ı manuel `popover="manual"`; klavye ile adım geçişi, `Esc` ile kapanma ve odak geri dönüşü açıkça test edilmiyor.
- Toast'lar `role="status"` kullanıyor; ancak yoğun ekranlarda `aria-live` gürültüsü ve odak yönetimi gözden geçirilmeli.

**Öneri**
- Vitest + Testing Library tarafında `jest-axe`; E2E'de Playwright `@axe-core/playwright`.
- Tur ve dialog için odak tuzağı, `Esc`, ilk/son öğe döngüsü, kapanınca odağın tetikleyiciye dönmesi.
- Renk kontrastı için tasarım token'ları üzerinden otomatik kontrol; `prefers-reduced-motion` desteği.
- Ekran okuyucu etiketleri: ikon-only düğmeler, grafik özetleri, tablo başlıkları.

**Kabul kriteri**
- Ana 5 ekranda axe "serious/critical" ihlal **0**.
- Tur klavye ile baştan sona tamamlanabilir; odak kaybolmaz.

**Efor:** M

---

### R9 — Büyük veri performansı

**Neden**
- Time-series ve audit listeleri büyüyebiliyor; grafiklerde belirgin bir downsample/decimation yok, tablolarda sanallaştırma yok.
- `three.js` chunk'ı ~743 kB (gzip ~188 kB) ve lazy; ilk yükleme 148,8 kB ile iyi, ancak sahne açılışında hissedilir.
- Form editörleri büyük `inputs` nesnesiyle çalışıyor; gereksiz render maliyeti riski var.

**Öneri**
- Uzun listelerde `@tanstack/react-virtual`; time-series tabloları ve audit/history için.
- Grafiklerde >2.000 nokta için LTTB downsample; zoom/pan sırasında pencereleme.
- Ağır form bölümlerini `React.memo` + seçici abonelik ile ayır; hesaplamaları `useMemo`/worker'a taşı.
- 3D sahneyi yalnız sekme görünürken mount et; `Suspense` iskeleti ve hata sınırı.
- Rota bazlı bundle bütçesi (rapor/OCR/3D ayrı).

**Kabul kriteri**
- 10.000 kayıtlı time-series tablosu < 200 ms açılır, kaydırma 60 fps.
- İlk yükleme JS bütçesi ≤ 160 kB gzip; 3D chunk ≥ 2 sn ertelenir.

**Efor:** M

---

## 5. P2 — Mimari, Test ve Operasyon

### R10 — Kritik hesap için golden/property/mutation testleri

**Neden**
- Genel kapsam %83; ancak `020`/`022` bağımsız kabul hesapları v2.1.0'da yeni ve yüksek riskli.
- OCR kalibrasyonu gerçek formlara dayanıyor; regresyon korpusu testlerde sınırlı.
- Birim testleri çoğunlukla örnek tabanlı; sınır/istisna durumları property-based testlerle daha iyi yakalanır.

**Öneri**
- Resmi `.xls` formlarından türetilmiş golden dosyalar: girdi → beklenen A/B/Vp/PT ve bulgular.
- Domain interpolasyonu ve kabul sınırları için `hypothesis` property testleri (monotonluk, süreklilik, negatif B, %6 sınırı).
- `dossier`/`form_details` için mutasyon testi (ör. `mutmut`) hedefli; skor eşiği.
- OCR için 5–10 sayfalık sabit regresyon korpusu; alan çıkarımı F1 skoru.

**Kabul kriteri**
- Hedef modüllerde satır kapsamı ≥ %90, mutasyon skoru ≥ %70.
- Golden testler CI'da zorunlu; resmi form revizyonunda kırılınca görünür.

**Efor:** M

---

### R11 — OpenAPI'den istemci tipi üretimi ve şema diff kapısı

**Neden**
- `check:api` yalnız istemcinin çağırdığı path'lerin OpenAPI'de var olduğunu doğruluyor; gövde/yanıt şeması karşılaştırmıyor.
- `api_contract.md` 70 bölüm; gerçek yüzey 101 operation. Bölümler elle ekleniyor.
- İstemci tipleri (`src/lib/types.ts`) elle bakımda; alan adı kayması riski.

**Öneri**
- `openapi-typescript` ile `src/lib/api-types.ts` üret; `api.ts` bu tipleri kullansın.
- CI'da üretilen dosyanın commit'li olduğunu doğrula (`git diff --exit-code`).
- Kritik yanıtlar için şema doğrulama testleri (pytest `jsonschema` veya Schemathesis smoke).
- `api_contract.md` bölümlerini OpenAPI'den üret; elle yazılan açıklamaları ayrı "notes" dosyasına taşı.

**Kabul kriteri**
- Şema değişikliği OpenAPI + tipler + sözleşme olmadan merge edilemez.
- Elle tutulan tip/endpoint listesi kalmaz.

**Efor:** M

---

### R12 — Hız sınırlayıcıyı dağıtık hale getir veya tek-worker zorunlu kıl

**Neden**
- `RateLimiter` bellek içi ve süreç başına; Postgres'te `HYDRO_WEB_WORKERS > 1` açılırsa limitler worker sayısıyla çarpılır.
- OCR kuyruğu da süreç-içi olduğundan çok worker yolu henüz tutarlı değil.
- `generate-sample`, export ve arşiv gibi maliyetli uçlar artık limitli; bu limitlerin dağıtık ortamda da geçerli olması gerekir.

**Öneri**
- Kısa vadede: çok worker açıkken OCR/limit uyarısı yerine **başlatmayı reddet** veya açıkça tek worker zorunlu kıl.
- Orta vadede: Redis tabanlı sliding-window/token-bucket; workspace bazlı kota; `429` ve kuyruk metrikleri.
- Rate limit yapılandırmasını ortam değişkeni/endpoint bazlı tabloya taşı.

**Kabul kriteri**
- 2 worker'lı testte toplam limit aşılamaz.
- Limitler audit/export/generate-sample için entegrasyon testiyle doğrulanır.

**Efor:** M

---

### R13 — Yönetici token'ı, CSP ve bağımlılık sertleştirmesi

**Neden**
- `X-Hydro-Admin-Token` tarayıcıda `sessionStorage`'da tutuluyor; XSS durumunda okunabilir.
- CSP başlığı var; nonce/hash tabanlı sıkılaştırma ve üçüncü taraf kaynak denetimi düzenli doğrulanmıyor.
- CI'da `pip-audit`/`npm audit`/secret scan adımı yok.

**Öneri**
- Yönetici işlemleri için kısa ömürlü, HttpOnly oturum çerezi veya yerel tek kullanımlık token endpoint'i; token'ı JS'ten okunamaz hale getir.
- CSP'yi nonce/hash ile sıkılaştır; `frame-ancestors`, `connect-src` daralt.
- CI'ya `pip-audit`, `npm audit --omit=dev`, `gitleaks` ekle; kritik açıkta build'i durdur.
- Yönetici eylemlerine ikinci faktör/onay (R4 ile birlikte).

**Kabul kriteri**
- Yönetici token'ı JS ile okunamaz; CSP ihlali raporlanır.
- Bağımlılık taraması PR'da çalışır; kritik bulgu merge'i engeller.

**Efor:** M

---

### R14 — Gözlemlenebilirlik

**Neden**
- `request_id` ve yapılandırılmış log altyapısı var; ancak `/metrics`, OCR kuyruk derinliği, DB yavaş sorgu ve hata izleme yok.
- Operasyon ekibi "sistem şu an ne yapıyor" sorusunu yalnız health ve loglardan yanıtlıyor.

**Öneri**
- Opsiyonel Prometheus `/metrics` (loopback/admin korumalı): istek sayısı/süre, 4xx/5xx, OCR kuyruğu, export TTL, DB bağlantı havuzu.
- Yavaş sorgu eşiği ve log; SQLAlchemy event ile süre ölçümü.
- Hata izleme (Sentry/GlitchTip) opsiyonel; PII maskeleme.
- Basit admin sağlık panosu: migration, disk, yedek yaşı, kuyruk.

**Kabul kriteri**
- p95 istek süresi ve OCR bekleme süresi grafikten izlenir.
- 5xx artışında uyarı üretilir.

**Efor:** M

---

### R15 — Yedekleme, saklama ve restore tatbikatı

**Neden**
- `db-backup`/`db-restore` uçları ve restore bariyeri var; ancak zamanlanmış yedek, saklama politikası ve düzenli tatbikat otomasyonu yok.
- Export dosyaları 24 saat TTL ile temizleniyor; çöp kutusu ve ekler için saklama politikası elle.
- Disk dolması durumunda davranış (kota, uyarı) sınırlı.

**Öneri**
- Günlük otomatik yedek + 7/30/90 gün saklama; yedek yaşı metriği.
- Aylık restore tatbikatı (izole ortamda) ve rapor.
- Çöp kutusu/ek/audit saklama süreleri; otomatik GC job'ı.
- Disk kullanım eşiğinde uyarı ve yazma guard'ı.

**Kabul kriteri**
- RPO ≤ 24 saat, RTO ≤ 1 saat olarak dokümante ve tatbikatla doğrulanır.
- Yedek/restore başarısızlığı görünür alarm üretir.

**Efor:** M

---

## 6. P3 — Mühendislik Hijyeni

### R16 — Masaüstü Tk testlerini izole süreç/job'a al

**Neden**
- v2.0.0'da tam masaüstü paketi sıralamaya bağlı `Tcl_AsyncDelete` ile çöküyordu; `e413967`'de teardown sırası, `after_cancel` ve `gc.collect()` eklendi ve tam koşu **733 OK (1 skipped)** verdi.
- Yine de Tk testleri diğer testlerle aynı süreçte çalışıyor; CI matrisi Linux/macOS/Windows × Python 3.12/3.13 olduğundan ortam bağımlı kırılganlık sürüyor.

**Öneri**
- `DownloadDialogTkTests` ve diğer Tk sınıflarını ayrı `unittest` modülü/job'ında çalıştır.
- Tk testlerini `xvfb` altında ayrı işaretle; UI olmayan testlerle aynı süreçte koşma.
- Çökme tekrar ederse `faulthandler` + `-X dev` ile job artifact'ı topla.

**Kabul kriteri**
- Tam paket 20 ardışık koşuda kararlı; Tk job'u ayrı ve yeşil.

**Efor:** S

---

### R17 — DX: pre-commit, görev çalıştırıcı, bağımlılık bakımı

**Neden**
- Kapılar birden fazla komutta; yeni geliştirici hangi sırayla çalıştıracağını dokümandan çıkarıyor.
- Biçim/lint hataları commit'e girebiliyor (F28).
- Bağımlılık güncelleme ritmi ve güvenlik taraması otomatik değil.

**Öneri**
- `pre-commit`: ruff check/format, eslint/prettier, trailing whitespace, secret scan.
- `make` veya `just`: `setup`, `lint`, `test`, `test-web`, `release-check`.
- Aylık bağımlılık PR'ı (Dependabot/Renovate) + `pip-audit`/`npm audit`.
- Katkı rehberi: tek sayfa "ilk PR" akışı.

**Kabul kriteri**
- Yeni geliştirici tek komutla yeşil ortam kurar.
- Biçim ihlali commit'e giremez.

**Efor:** S

---

### R18 — Doküman tek kaynak

**Neden**
- Test sayıları, bundle değeri ve sürüm notları birden fazla dosyada elle tutuluyor; geçmişte kaydı.
- `api_contract.md` ile OpenAPI arasında 70/101 bölüm farkı var.
- `DURUM.md` "tek kaynak özet" diyor; ancak README/`implementation_status`/`WHATS_NEW` ile çakışabiliyor.

**Öneri**
- Ölçümleri `release_gate` çıktısından üret; dokümanlara `<!-- generated:... -->` bloğu olarak yaz.
- `api_contract.md` başlıklarını OpenAPI'den üret (R11).
- `DURUM.md`'yi tek durum özeti, diğerlerini ona bağlantı verecek şekilde sadeleştir.
- ADR şablonu: auth, OCR kuyruğu, Postgres/SQLite kararları.

**Kabul kriteri**
- Dokümanlarda elle tutulan test/bundle sayısı kalmaz.
- Sözleşme bölüm sayısı OpenAPI operation sayısıyla otomatik eşleşir.

**Efor:** S

---

## 7. 90 Günlük Yol Haritası

### 0–2 hafta
- **R2** release gate + doküman senkronu.
- **R1** CI smoke (önce `verify-tabs`, sonra tek Playwright akışı).
- **R16** Tk testlerini ayrı job'a al.
- **R6** tur kalıcılığı ve demo temizliği.

### 2–6 hafta
- **R5** viewport matrisi + mobil düzeltmeleri.
- **R7** form taslağı/doğrulama özeti.
- **R8** axe + odak yönetimi.
- **R10** golden/property testleri.
- **R11** üretilen istemci tipleri.

### 6–12 hafta
- **R3** kalıcı OCR worker.
- **R4** OIDC/RBAC (mimari karar + pilot).
- **R9** sanallaştırma/grafik örnekleme.
- **R12** dağıtık limit veya tek-worker sözleşmesi.
- **R13/R14/R15** güvenlik, metrik, yedek tatbikatı.

### Sürekli
- **R17** pre-commit/Dependabot.
- **R18** doküman otomasyonu.
- Üç aylık restore tatbikatı ve erişilebilirlik taraması.

---

## 8. Başarı Ölçütleri (KPI)

| Alan | KPI | Hedef |
| --- | --- | --- |
| CI | Required check yeşil oranı | ≥ %98 |
| CI | Smoke/E2E flake oranı | < %2 |
| CI | PR geri bildirim süresi | < 10 dk |
| OCR | Restart sonrası iş kaybı | 0 |
| OCR | Kuyruk bekleme p95 | < 30 sn |
| UX | 375 px yatay taşma | 0 kritik ekran |
| a11y | axe serious/critical | 0 |
| Perf | 10k satır time-series açılış | < 200 ms |
| Perf | İlk yükleme JS | ≤ 160 kB gzip |
| Test | Domain/dossier kapsam | ≥ %90 |
| Test | Hedefli mutasyon skoru | ≥ %70 |
| Operasyon | RPO / RTO | ≤ 24 sa / ≤ 1 sa |
| Sözleşme | Elle tutulan endpoint/type | 0 |

---

## 9. Bilinçli Olarak Önerilmeyenler

- **Mikroservislere bölme / Kubernetes:** Mevcut ölçek ve ekip için operasyonel maliyet, kazançtan yüksek. Önce tek uygulama + ayrı OCR worker yeterli.
- **Tam offline-first senkronizasyon:** Çevrimdışı taslak ve uyarı mevcut; çift yönlü otomatik çakışma çözümü domain karmaşıklığını artırır. Talep gelene kadar ertelenmeli.
- **Masaüstü Tkinter'ı yeniden yazma:** Web sürümü ana ürün; masaüstü yalnız kritik regresyon ve paketleme için korunmalı.
- **Erken i18n:** Tek dil (Türkçe) ve kurumsal kullanım; çok dillilik ancak talep doğrulanınca.
- **Native mobil uygulama:** Responsive web + PWA yeterli; mağaza dağıtımı ayrı ürün kararı.

---

## 10. Sonuç

v2.1.0 ve `e413967`, denetimden çıkan somut hataları kapatmış durumda; yazılım artık "çalışıyor" aşamasından "kurumsal olarak işletilebilir" aşamasına geçmek için gerekli yatırımları seçebilecek olgunlukta. İlk iki haftada **R1 + R2** tamamlanırsa sürüm güvenilirliği ölçülebilir hale gelir; ardından **R3 + R4** kurumsal ölçek ve güvenlik omurgasını kurar. Ürün tarafında **R5–R9**, sahadaki operatörün günlük verimliliğini ve erişilebilirliğini doğrudan artırır.
