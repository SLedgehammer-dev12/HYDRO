> **Arşiv Notu:** Bu rapor geçmiş bir sürüme ait anlık inceleme kaydıdır; güncel proje ve doğrulama durumu için `DURUM.md` dosyasına bakın.

# HYDRO — Kapsamlı Analiz Raporu v2

**Sürüm:** v1.9.1 (HEAD `26bb817`) + commit edilmemiş çalışma ağacı
**Tarih:** 19 Kasım 2026
**Kapsam:** Masaüstü uygulaması (Tkinter), web backend (FastAPI), web frontend (React/Vite), domain/şartname katmanı, CI, dağıtım ve dokümantasyon
**Yöntem:** Kod okuma + canlı uç nokta doğrulaması + kalite kapıları + 4 paralel alt ajan (3'ü "Free usage limit" nedeniyle tamamlanamadı; kalan alanlar doğrudan incelendi)
**Kanıt standardı:** Her bulgu `dosya:satır` veya komut çıktısıyla desteklenir. Doğrulanamayan ajan iddiaları "doğrulanmalı" olarak işaretlenmiştir.

> **Önemli — çalışma ağacı uyarısı**
> Depoda **56 değiştirilmiş dosya + 4 yeni backend dosyası** (`db_admin.py`, `project_data.py`, `project_archive.py`, `test_db_management.py`) commit edilmemiş durumda (`git status`). Bu rapor, aksi belirtilmedikçe **çalışma ağacını** esas alır. Kritik farklar "HEAD" ve "çalışma ağacı" olarak ayrıca işaretlenmiştir. Rapor yazılırken ağaç hareketliydi; ölçümler 19 Kasım 2026 anlık görüntüsüdür.

---

## 1. Yönetici Özeti

HYDRO, domain katmanı ve test disiplini açısından olgun bir üründür: 680 masaüstü testi, 147 web testi, ~%80 kapsam ve temiz bir domain tip kapısı bunu doğruluyor. Buna karşılık **dağıtım güvenliği, hata yolları ve karar bütünlüğü** hâlâ üretim için yeterli değil.

En kritik üç konu:

1. **Çalışma alanı ele geçirme (P0, çalışma ağacında yeni):** `GET /api/system/workspaces` tüm çalışma alanlarının özetlerini, `POST /api/system/workspaces/claim` ise **herhangi bir çalışma alanının tüm kayıtlarını** çağıranın alanına taşıyor. Varsayılan `auth_mode="none"` ve `0.0.0.0:8080` dağıtımıyla birleşince ağa açık her kurulumda **çapraz kiracı veri ele geçirme** mümkün.
2. **Plan-profile hata yolları HEAD'de 500 dönüyor (P0):** `AppError` çağrıları `code=`/`status=` ile yapıldığı için `TypeError` oluşuyor. Çalışma ağacında düzeltilmiş, ancak **commit edilmemiş**; HEAD'den kurulan sürüm hâlâ bozuk.
3. **Kimlik doğrulama yok + ağa açık Docker (P0/P1):** `auth_mode` yapılandırması yalnızca raporlanıyor; gerçek bir kimlik doğrulama katmanı yok. Çalışma alanı anahtarı (`X-Session-ID`) bir kimlik değil, istemcinin ürettiği bir UUID.

Bunlara ek olarak masaüstünde **rapor/karar bütünlüğü** (karar `BEKLIYOR` iken rapor kaydedilebiliyor, oturum değişiminde bayat karar kartı), **çift güncelleme indirmesi** ve **iki farklı sayı ayrıştırıcı** öne çıkan P1 bulgulardır.

### Olgunluk Skoru (özet)

| Alan | Durum | Not |
|---|---|---|
| Domain / şartname hesapları | 🟢 İyi | 12 dosya, mypy temiz, 14.2 ve %0.2 izleme dışında kapsam güçlü |
| Masaüstü test güvenilirliği | 🟢 İyi | 680 test, 1 skip, 58.8 sn |
| Web backend testleri | 🟡 Orta | 147 test; hata yolları ve yetki testleri zayıf |
| Web backend tip güvenliği | 🔴 Zayıf | 255 mypy hatası / 20 dosya |
| Frontend kalitesi | 🟡 Orta | Typecheck/build geçiyor; birim testi, lint ve E2E yok |
| Güvenlik / dağıtım | 🔴 Kritik | Auth yok, 0.0.0.0, workspace claim açığı |
| CI kapsamı | 🔴 Zayıf | PR'da yalnız masaüstü unittest |
| Dokümantasyon doğruluğu | 🟡 Orta | Sürüm/t_test/path sayıları eski |

---

## 2. Ölçümler (kanıt)

### 2.1 Kalite kapıları

| Kapı | Komut | Sonuç |
|---|---|---|
| Masaüstü testleri | `python3 -m unittest discover -s tests -p "test_*.py"` | **680 test OK** (`skipped=1`), 58.8 sn |
| Web testleri | `python3 -m pytest webapp/backend/tests -q` | **147 passed**, 25.2 sn |
| Kapsam | `coverage run --branch` + `coverage report` | **~%80** |
| Lint | `python3 -m ruff check .` | **5 hata** (çalışma ağacında kırmızı) |
| Domain tip | `python3 -m mypy hidrostatik_test/domain/` | **Temiz** (12 dosya) |
| Tüm tip | `python3 -m mypy --ignore-missing-imports hidrostatik_test webapp/backend/app` | **255 hata / 20 dosya** |
| Frontend tip | `npm run typecheck` | **PASS** |
| Frontend build | `npm run build` | **PASS** (1.70 sn) |
| OpenAPI | `create_app().openapi()` | **81 path / 94 operation** (HEAD: 61/74) |

**Ruff hataları (çalışma ağacı):**

- `webapp/backend/app/schemas.py:412-414,451` — `__all__` içinde tanımsız `DbBackupRequest`, `DbMaintenanceRequest`, `DbRestoreRequest`, `TrashRestoreRequest` (F822).
- `webapp/backend/app/services/project_archive.py:3` — kullanılmayan `Project` importu (F401).

> Bu, çalışma ağacındaki DB yönetim/arşiv özelliğinin **yarım bağlanmış** olduğunu gösterir: şemalar `__all__`'da listeleniyor ama sınıflar tanımlı değil; ilgili uç noktalar da `api/system.py` içinde yok.

### 2.2 mypy dağılımı (ilk 15)

| Dosya | Hata |
|---|---:|
| `hidrostatik_test/ui/app.py` | 101 |
| `webapp/backend/app/services/form_details.py` | 30 |
| `webapp/backend/app/services/dossier.py` | 25 |
| `webapp/backend/app/services/project_data.py` (yeni) | 21 |
| `hidrostatik_test/ui/wizard.py` | 17 |
| `webapp/backend/app/services/sessions.py` | 16 |
| `webapp/backend/app/services/scene.py` | 10 |
| `hidrostatik_test/ui/download_dialog.py` | 8 |
| `webapp/backend/app/services/plan_profile.py` | 7 |
| `webapp/backend/app/services/calculations.py` | 6 |
| `hidrostatik_test/ui/report_ocr_dialog.py` | 6 |
| `hidrostatik_test/services/water_property_table_builder.py` | 6 |
| `hidrostatik_test/services/report_ocr.py` | 5 |
| `webapp/backend/app/services/ocr.py` | 4 |
| `webapp/backend/app/services/db_admin.py` (yeni) | 4 |

### 2.3 Kod hacmi

| Dosya | Satır |
|---|---:|
| `hidrostatik_test/ui/app.py` | 8.438 |
| `webapp/backend/app/services/plan_profile.py` | 2.271 |
| `hidrostatik_test/ui/wizard.py` | 758 |
| `hidrostatik_test/ui/report_ocr_dialog.py` | 742 |

### 2.4 Frontend bundle

| Varlık | Boyut | gzip | map |
|---|---:|---:|---:|
| `dist/assets/index-*.js` | 1.455,52 kB | 405,16 kB | 6.266,74 kB |
| `dist/assets/PipelineScene-*.js` | 1.022,20 kB | 271,91 kB | 4.498,06 kB |
| `dist/assets/index-*.css` | 75,49 kB | 14,34 kB | — |

Üretimde `sourcemap: true` (`webapp/frontend/vite.config.ts:18`) ve `chunkSizeWarningLimit: 1600` (`:19`).

---

## 3. Önceki Raporun (v1.8.0) Bulgularının Durumu

> Eski kimlikler korunmuştur; bu raporun yeni numaralandırması Bölüm 4'te başlar. Örnek: eski P0-1 (plan-profile) = yeni P0-2.

| Eski bulgu | v1.9.1 durumu | Kanıt |
|---|---|---|
| Eski P0-1 Plan-profile `AppError` TypeError | **HEAD'de açık**, çalışma ağacında düzeltilmiş ama commit yok | `git show HEAD:webapp/backend/app/services/plan_profile.py` |
| Eski P0-2 Plan-profile hata yolları testsiz | **Kısmen kapandı** | `webapp/backend/tests/test_dossier.py:1595` yalnız `invalid_file_signature` |
| Eski P0-3 Auth'suz Docker | **Açık**, üstelik yeni claim uç noktasıyla ağırlaştı | `webapp/docker-compose.yml:8-14` |
| Eski P1-1 CI web/frontend kapsamıyor | **Açık** | `.github/workflows/test.yml` |
| Eski P1-2 mypy borcu | **Büyüdü** (214 → 255) | mypy çıktısı |
| Eski P1-3 OCR kuyruğu gerçek değil | **Açık** | `webapp/backend/app/services/ocr.py:319+` |
| Eski P1-4 Plan-profile belleğe okuyor | **Açık** | `plan_profile.py:1908` |
| Eski P1-5 Migration altyapısı yok | **Kısmen kapandı** | `webapp/backend/app/db.py:121-151` (0001/0002, `schema_migrations`) |
| Eski P1-6 Masaüstü UI monoliti | **Açık** (8.438 satır) | `hidrostatik_test/ui/app.py` |
| Eski P1-7 Frontend test/lint yok | **Açık** | `webapp/frontend/package.json:6-12` |
| Eski P1-8 Aşırı karmaşık fonksiyonlar | **Açık** | app.py / plan_profile.py |
| Eski P2 Doküman kayması | **Açık** | `README.md:137`, `DURUM.md:16`, `webapp/docs/implementation_status.md:12` |
| Eski P2 Sürüm tutarsızlığı | **Açık** | `webapp/backend/app/__init__.py:7`, `main.py:84` |
| Eski P2 Bundle/source map | **Açık** | `vite.config.ts:18-19` |
| Eski P2 Graphify gürültüsü | **Açık** | `docs/legacy`, `IF` tablosu |

---

## 4. P0 — Acil Düzeltme

### P0-1. Çalışma alanı listeleme ve ele geçirme uç noktaları (veri sızıntısı + tenant takeover)

**Kanıt**

- `webapp/backend/app/api/system.py:26-33` — `_require_local_admin` yalnız `settings.auth_mode != "none"` kontrolü yapıyor. Varsayılan `auth_mode="none"` (`core/config.py:132`), yani kontrol **normalde geçiyor**.
- `webapp/backend/app/api/system.py` — `GET /api/system/workspaces` ve `POST /api/system/workspaces/claim` uç noktaları.
- `webapp/backend/app/services/db_admin.py:23-70` — `list_workspaces` **tüm** workspace hash'lerini, proje/kesit sayılarını ve örnek proje adlarını döndürüyor.
- `webapp/backend/app/services/db_admin.py:118-180` — `claim_workspace`, verilen `source_workspace_hash` altındaki `Project`, `HydroSession`, `SectionForm`, `Attachment`, `OcrAnalysis`, `OcrMappingProfile` kayıtlarının tamamını çağıranın workspace'ine taşıyor.
- `webapp/backend/tests/test_db_management.py:130-160` — test, farklı bir workspace'in listelenip claim edilebildiğini **doğruluyor** (yani davranış kasıtlı, ancak yetkisiz).

**Etki**

- Ağa açık her kurulumda saldırgan önce tüm çalışma alanlarını listeleyebilir, sonra tek istekle başka bir müşterinin/şubenin tüm test verisini kendi alanına taşıyabilir.
- Workspace anahtarı istemci tarafından üretilen bir UUID olduğundan (`webapp/frontend/src/lib/api.ts:90-100`) ve sunucuda yalnız hash'lendiğinden, hash'i bilmek ham anahtarı bilmeye eşdeğerdir; claim uç noktası doğrudan hash kabul ediyor.
- `docker-compose.yml` `0.0.0.0:8080` ile yayınlandığından bu, "yerel MVP" varsayımıyla korunamaz.

**Öneri (acil)**

1. `auth_mode="none"` iken bu iki uç noktayı **tamamen kapat**; yalnızca gerçek bir yerel yönetici oturumu/jetonu ile aç.
2. Claim işlemini varsayılan olarak devre dışı bırak; etkinleştirilse bile **kaynak workspace'in sahipliğini doğrula** (ham anahtar veya imzalı bilet).
3. Claim'i tek işlemde (transaction) ve geri alınabilir (audit + soft-delete) hale getir.
4. Varsayılan `HYDRO_HOST` değerini `127.0.0.1` yap; `0.0.0.0` yalnızca `auth_mode != "none"` iken kabul edilsin.
5. Bu uç noktalar için "yetkisiz kullanıcı 403 alır" testi ekle.

### P0-2. Plan-profile hata yolları HEAD'de `TypeError` → HTTP 500

**Kanıt**

- HEAD sürümü: `git show HEAD:webapp/backend/app/services/plan_profile.py` → `raise AppError("...", code="unsupported_format", status=415)` biçiminde 9 çağrı.
- Doğru imza: `webapp/backend/app/core/errors.py` → `AppError(code, message, *, status_code=400, details=None)`.
- Çalışma ağacında düzeltilmiş: `plan_profile.py:1568-1585, 1883-1950` artık `AppError("kod", "mesaj", status_code=...)`.
- Ancak düzeltme **commit edilmemiş**; HEAD'den kurulan/dağıtılan sürüm hâlâ bozuk.
- Test kapsamı yalnız yeni imza doğrulaması için: `webapp/backend/tests/test_dossier.py:1595-1602` (`invalid_file_signature`). `unsupported_format`, `empty_file`, `file_too_large` plan-profile yolları hâlâ testsiz.

**Etki**

- Desteklenmeyen uzantı, boş dosya, aşırı boyut, eksik DWG dönüştürücü ve CAD parse hatası kullanıcıya 500 olarak döner; hata mesajı kaybolur.

**Öneri**

1. Çalışma ağacındaki düzeltmeyi ayrı bir commit olarak hemen gönder.
2. Yukarıdaki beş hata yolu için parametrik test ekle (her biri 4xx + doğru `code`).
3. `AppError` çağrılarını yakalayan bir ruff/mypy kuralı veya en azından bir AST testi ekle.

### P0-3. Kimlik doğrulama yok + `0.0.0.0` varsayılan dağıtım

**Kanıt**

- `webapp/docker-compose.yml:8-14` — `ports: "8080:8080"`, `HYDRO_HOST: "0.0.0.0"`, yorumda "Auth'suz MVP yalnız güvenilir ağda çalıştırılmalıdır".
- `webapp/backend/app/core/config.py:132` — `auth_mode: str = "none"`.
- `auth_mode` yalnızca `api/system.py:26` (DB admin kapısı) ve raporlama (`services/system.py:128,216`) için kullanılıyor; uygulama genelinde bir auth middleware'i yok.
- `webapp/backend/app/main.py:96-106` — `X-Session-ID` normalize edilip hash'leniyor; doğrulanmıyor.

**Etki**

- Ağa açık kurulumda tüm projeler, oturumlar, formlar ve OCR dosyaları kimlik doğrulaması olmadan erişilebilir.
- 500 MB'a kadar yükleme (`config.py:159`) ve senkron OCR ile kolayca hizmet dışı bırakılabilir.

**Öneri**

1. Varsayılanı `127.0.0.1` yap; compose'da `0.0.0.0` için açık `HYDRO_ALLOW_REMOTE=1` şartı getir.
2. En azından ters proxy (Caddy/nginx) + basic auth veya OIDC arkasında çalıştırma zorunluluğu belgele.
3. `auth_mode="none"` iken tehlikeyi `/api/health` ve başlangıç logunda yüksek sesle bildir.

---

## 5. P1 — Yüksek Öncelikli

### P1-1. CI, web backend ve frontend'i kapsamıyor

**Kanıt**

- `.github/workflows/test.yml` yalnız `unittest discover -s tests` çalıştırıyor; `pytest`, `ruff`, web mypy ve `npm run typecheck/build` yok.
- `release.yml` web pytest'i yalnız tag'de koşuyor.
- Sonuç: web backend'deki 255 mypy hatası ve 5 ruff hatası PR'da görünmüyor.

**Öneri**

- PR iş akışına üç ayrı job ekle: `lint` (ruff), `web` (pytest + mypy bilgilendirici), `frontend` (typecheck + build).
- Domain mypy'ı bloklayıcı, tam paket mypy'ı "ratchet" (hata sayısı artarsa kır) yap.

### P1-2. OCR sözleşmesi ile kod uyuşmuyor; "kuyruk" gerçek değil

**Kanıt**

- `webapp/backend/app/api/ocr.py:19` — `POST /api/ocr/analyze` **201** dönüyor; `webapp/docs/api_contract.md` 202 + `estimated_wait_s` yazıyor.
- `webapp/backend/app/services/ocr.py:319+` — `analyze_upload` senkron çalışıyor: `queued → running → succeeded` aynı istek içinde.
- `estimated_wait_s` yalnız frontend tipinde opsiyonel (`features/ocr/types.ts:266`) ve etikette (`OcrPage.tsx:492`); backend hiç üretmiyor.
- `cancel_analysis` yalnız DB durumunu değiştiriyor; çalışan işi durdurmuyor.
- `settings.ocr_timeout_s` (`config.py:131`) hiçbir yerde kullanılmıyor.
- `_OCR_LANG_LOCK` + `os.environ["HYDRO_OCR_LANG"]` mutasyonu eşzamanlı isteklerde dil sızıntısı riski taşıyor.

**Etki**

- Uzun OCR işleri HTTP isteğini dakikalarca açık tutar; istemci zaman aşımına uğrar, iş sunucuda devam eder.
- İptal düğmesi kullanıcıya yanlış güven verir.

**Öneri**

1. Sözleşmeyi koda uydur **veya** kodu sözleşmeye uydur: 202 + `job_id` + `estimated_wait_s` + `poll_url`.
2. Gerçek bir arka plan işçisi (FastAPI `BackgroundTasks` yeterli değil; ayrı worker/queue) ve iptal bayrağı ekle.
3. `ocr_timeout_s` ve toplam sayfa bütçesini uygula.
4. Dil seçimini global ortam değişkeni yerine çağrı parametresi olarak geçir.

### P1-3. Plan-profile yüklemesi belleğe okunuyor; iki ayrı boyut limiti

**Kanıt**

- `webapp/backend/app/services/plan_profile.py:1908` — `data = stream.read(max_bytes + 1)`; varsayılan 500 MB.
- `hidrostatik_test/services/report_ocr.py:85-95` — limit `HYDRO_MAX_UPLOAD_MB` ortam değişkeninden.
- `webapp/backend/app/core/config.py:159` — ayrı limit `settings.max_upload_bytes`; OCR bunu kullanıyor (`services/ocr.py:348`).
- Aynı anda birden fazla yükleme RAM'i kolayca tüketebilir.

**Öneri**

- Yükleme akışını parça parça diske yaz (streaming) ve hash'i akış sırasında hesapla.
- Tek bir limit kaynağı belirle (`settings.max_upload_bytes`) ve `effective_max_file_size_bytes`'ı ona delege et.
- Boyut kontrolünü `Content-Length` + akış sayacı ile erken yap.

### P1-4. Masaüstünde rapor/karar bütünlüğü zayıf

**P1-4a. Karar `BEKLIYOR` iken rapor kaydedilebiliyor**

- `hidrostatik_test/ui/app.py:1076` — `save_report_button` oluşturuluyor; `_refresh_action_gates` (`:5975+`) yalnız test düğmelerini ve `run_selected`'i yönetiyor, rapor düğmesini **hiç devre dışı bırakmıyor**.
- `:7614-7621` — `_build_report_text` karar durumundan bağımsız olarak `BEKLIYOR`, `KATSAYI GUNCELLENMELI` gibi durumları rapora yazıyor.
- `:8040` — `_save_report` öncesi `BASARILI` kapısı yok.

**Etki:** Sahte/eksik sonuçlar resmî rapor olarak dışa aktarılabilir.

**Öneri:** Rapor kaydını `air` ve `pressure` kararlarının ikisi de `BASARILI` (veya açıkça `DOGRULANAMADI` ve kullanıcı onayı) olana kadar kilitle; rapora "TASLAK" damgası ekle.

**P1-4b. Oturum değişiminde bayat karar kartı**

- `:8181-8188` — `_on_session_selected` yalnız `_apply_session_to_ui()` çağırıyor.
- `:7857-8000` — `_apply_input_snapshot` sonunda `_on_tab_changed()` var, `_reset_decision_card()` yok.
- `_reset_decision_card` yalnız yeni oturum (`:8194`) ve test yeniden çalıştırma (`:7465,7485`) yollarında çağrılıyor.

**Etki:** Önceki oturumun `BASARILI` kararı yeni oturumda görünür; kullanıcı yanlış rapor üretir.

**Öneri:** Oturum yükleme ve snapshot yükleme sonunda karar kartını sıfırla; snapshot'a karar durumunu da dahil et veya açıkça "karar yok" olarak yükle.

**P1-4c. Wizard "Test Uygulama" adımı global karara bakıyor**

- `hidrostatik_test/ui/wizard.py:540-547` — `_validate_execution` `app.decision_status_var` okuyor; aktif sekmenin/sonucun kararına bakmıyor.
- `wizard.py:32` — adım→sekme eşlemesi `("air", "pressure", "pressure", "pressure")`; 1-3. adımlar aynı basınç sekmesine gidiyor. (Tasarım kararı olabilir; belgelenmeli.)

**Etki:** Hava testi yapılmadan basınç adımı "tamam" sayılabilir veya tersi.

**Öneri:** Her adımın doğrulamasını ilgili test sonucuna bağla; sekme eşlemesini gerçek akışla hizala.

### P1-5. Güncelleme akışı paketi iki kez indiriyor; ilk indirme doğrulanmıyor

**Kanıt**

- `hidrostatik_test/ui/download_dialog.py:125-129` — `DownloadTask(url, destination, total_bytes)`; `expected_sha256` **verilmiyor**.
- `hidrostatik_test/ui/app.py:3064-3074` — indirme bittikten sonra `install_update(...)` çağrılıyor.
- `hidrostatik_test/services/updater.py:1290-1295` — `install_update` paketi **yeniden** `_download_asset` ile indiriyor; checksum doğrulaması burada yapılıyor (`:761-762`).

**Etki**

- Kullanıcı ilerleme çubuğunu izlerken indirilen dosya aslında kullanılmıyor; bant genişliği ve süre iki katına çıkıyor.
- Diyalog indirmesi bozulursa kullanıcı bunu ancak ikinci indirme aşamasında fark ediyor.

**Öneri**

- `DownloadDialog`'a `expected_sha256` geçir ve doğrulanmış dosyayı `install_update`'a ver (yeniden indirme yok).
- Checksum alınamazsa indirmeyi başlatma; kullanıcıya net hata göster.
- İndirme URL'si, boyutu ve `Content-Range` toplamını doğrula.

### P1-6. mypy borcu büyüdü: 255 hata / 20 dosya

**Kanıt:** Bölüm 2.2. En büyük katkı `ui/app.py` (101) ve yeni `project_data.py` (21).

**Etki:** Tip hataları gerçek hataları gizliyor; özellikle `dossier.py`'deki `AirContentResult` yanlış alan erişimleri (`margin_bar`, `actual_pressure_change_bar`) çalışma zamanı hatasına açık.

**Öneri:** Modül bazlı ratchet: her PR'da hata sayısı artamaz. Önce `webapp/backend/app/services` (dossier/form_details/project_data) temizlenmeli; `ui/app.py` bölünerek düşürülmeli.

### P1-7. Frontend sessizce demo verisine düşüyor

**Kanıt**

- `webapp/frontend/src/hooks/queries.ts:83-98` — `resolveWithMock`: backend "demo" ise veya gerçek çağrı "recoverable" hata verirse **mock** veri döner ve backend durumu `demo` yapılır.
- `webapp/frontend/src/lib/mock.ts` — `computeAir`, `computePressure`, `computeGeometry` vb. istemci tarafında yaklaşık hesaplar.

**Etki:** Ağ hatası sırasında kullanıcı gerçek backend sonucu sanarak demo hesap sonucu görebilir. TopBar'da "demo" göstergesi var (`TopBar.tsx:373-378`) ama sonuç panelleri bunu her yerde tekrar etmiyor.

**Öneri**

- Demo modunu yalnızca açık kullanıcı tercihiyle etkinleştir; otomatik düşüşte sonuç kartlarına kalıcı "DEMO — resmî sonuç değildir" bandı ekle.
- Rapor/dışa aktarma demo modunda kapatılsın.

### P1-8. Masaüstü OCR işi iptal edilemiyor; toplam bütçe yok

**Kanıt**

- `hidrostatik_test/ui/report_ocr_dialog.py:439-444` — analiz `daemon=True` thread'de çalışıyor.
- `:500-520` — diyalog kapatılırken yalnız `after_cancel` ve `destroy`; worker'a iptal sinyali gitmiyor (generation token yalnız sonucu yok sayıyor).
- `hidrostatik_test/services/report_ocr.py:99-101` — `MAX_OCR_PAGES = 200`; sayfa başına 45-60 sn timeout (`:1559, :1905, :2320`).
- Toplam süre bütçesi yok: en kötü durumda ~3 saat arka plan CPU/OCR.

**Öneri:** `threading.Event` tabanlı iptal, toplam süre bütçesi (`HYDRO_OCR_TOTAL_TIMEOUT_S`) ve diyalog kapanınca iptal.

### P1-9. İki farklı sayı ayrıştırıcı, farklı dilbilgisi

**Kanıt**

- `hidrostatik_test/ui/validators.py:96+` — `parse_finite_float`: `"1.234,56" → 1234.56`, `"1.000.000" → 1000000`, `"1.000" → 1.0`.
- `hidrostatik_test/ui/app.py:6445-6457` — `_read_float`: yalnız `replace(",", ".")` + `float()`; `"1.234,56"` → `"1.234.56"` → hata; `"1.000"` → `1.0`.
- Wizard `parse_finite_float` kullanırken ana form `_read_float` kullanıyor.

**Etki:** Aynı değer bir ekranda kabul, diğerinde ret; `"1.000"` bin olarak girildiğinde 1000× hata riski.

**Öneri:** Tek ayrıştırıcı (`parse_finite_float`) kullan; `"1.000"` belirsizliğini hata olarak reddet veya binlik ayırıcıyı zorunlu kıl.

### P1-10. Migration altyapısı hâlâ el yapımı; Postgres doğrulanmıyor

**Kanıt**

- `webapp/backend/app/db.py:121-151` — `create_all` + `_apply_migrations`, 0001/0002, `_ensure_column`.
- `db.py:198-205` — `/api/health` migration sürümünü DB'den okuyor (iyileşme).
- Alembic yok; ileri/geri alma, veri dönüşümü ve Postgres uyumu test edilmiyor.

**Öneri:** Alembic'e geç veya en azından Postgres üzerinde migration testi ekle; `create_all`'ı yalnız test için kullan.

---

## 6. P2 — İyileştirmeler

| # | Bulgu | Kanıt | Öneri |
|---|---|---|---|
| P2-1 | Doküman/test sayısı kayması | `README.md:137` (653), `DURUM.md:16` (137), `webapp/docs/implementation_status.md:12` (51 path / 97 pytest) | Gerçek: 680 / 147 / 81 path. Sayıları CI'dan üret. |
| P2-2 | Sürüm tutarsızlığı | `app_metadata.py:6` 1.9.1; `backend/app/__init__.py:7` 0.1.0; `main.py:84` 1.0.0 | Tek kaynak (`APP_VERSION`) ve otomatik senkron. |
| P2-3 | Üretimde source map açık | `vite.config.ts:18` | `sourcemap: false` veya `hidden`; CI artefaktı olarak sakla. |
| P2-4 | Büyük bundle | 1.46 MB + 1.02 MB three.js | Rota bazlı `lazy`, three.js sahnesini ayrı yükle. |
| P2-5 | Graphify gürültüsü | `docs/legacy` taranıyor; SQL'de `IF` tablosu | Skip listesine `docs/legacy` ve testleri ekle; SQL parser'ı düzelt. |
| P2-6 | Tessdata checksum'sız indirme | `build_web_exe.ps1:284-303` | SHA-256 pinle ve doğrula. |
| P2-7 | `estimated_wait_s` sözleşmede var, kodda yok | `api_contract.md`, `types.ts:266` | Backend üret veya sözleşmeden kaldır. |
| P2-8 | Erişilebilirlik | 261 `onClick`, 5 `onKeyDown`; `aria-live` 23 | Tıklanabilir `div`'leri `button` yap; odak/hata bildirimleri ekle. |
| P2-9 | Liste anahtarlarında index | `HistoryPanel.tsx:59`, `WarningsPanel.tsx:61` | Kararlı kimlik kullan. |
| P2-10 | Küçük ekran testi gerçek simülasyon değil | `tests/test_ui_workflow.py:1678-1685` yalnız `minsize()` okuyor | `winfo_screenwidth` mock'la ve yerleşimi doğrula. |
| P2-11 | `tsconfig` ölü kod denetimi kapalı | `webapp/frontend/tsconfig.json:15-16` | `noUnusedLocals/Parameters` aç; kademeli temizle. |
| P2-12 | Test süresi | 58.8 sn masaüstü | Yavaş testleri işaretle, paralelleştir. |

---

## 7. Kategori Eşlemesi

### Düzeltilmesi gerekenler (hatalı davranış)

- P0-1 workspace claim/list yetkisizliği
- P0-2 HEAD'deki `AppError` TypeError
- P0-3 auth'suz `0.0.0.0` dağıtım
- P1-4a/b rapor ve karar kartı bütünlüğü
- P1-5 çift indirme / doğrulanmamış ilk indirme
- P1-9 sayı ayrıştırıcı tutarsızlığı
- Ruff F822/F401 hataları

### Değiştirilmesi gerekenler (mimari)

- P1-2 OCR'ı gerçek kuyruğa taşı, sözleşmeyi hizala
- P1-3 yüklemeyi streaming yap, tek limit kaynağı
- P1-10 Alembic/Postgres migration
- P1-1 CI kapsamını genişlet
- P1-8 OCR iptal/bütçe
- P2-2 tek sürüm kaynağı

### İyileştirilmesi gerekenler (kalite)

- P1-6 mypy borcu (ratchet)
- P1-7 demo fallback görünürlüğü
- P2-1 doküman sayıları
- P2-3/4 bundle ve source map
- P2-8/9/11 erişilebilirlik ve tip disiplini
- P2-12 test süresi

### Geliştirilmesi gerekenler (yeni yetenek)

- Şartname 14.2: basınç–hacim ilişkisi izleme ve %0,2 ilave su alarmı (`docs/spec/ngtl_5007_hydrostatic_analysis.md:51,66,89`). Domain'de `pressurization.py` eşikleri var (`PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT = 0.2`) ancak uçtan uca akışa bağlı değil.
- Zaman serisi termal denge analizi (`domain/time_series.py`) UI/rapora bağlanmalı.
- Şartname 16-17 ve 21. bölüm izlenebilirliği (form → hesaplama → karar zinciri).
- Denetim izi (audit trail): kim, ne zaman, hangi kararı verdi.

---

## 8. Yol Haritası

### Sprint 0 — Acil (1-2 gün)

1. P0-1: workspace list/claim uç noktalarını `auth_mode="none"` iken kapat; varsayılan host `127.0.0.1`.
2. P0-2: çalışma ağacındaki `AppError` düzeltmesini commit et + 5 hata yolu testi.
3. Ruff'ı yeşile çek (F822/F401).
4. P1-4a: rapor kaydını karar kapısına bağla.

### Sprint 1 — Güvenlik ve doğruluk (1 hafta)

1. P0-3 auth katmanı (reverse proxy/OIDC veya yerel token).
2. P1-4b/c: oturum/snapshot karar sıfırlama, wizard doğrulaması.
3. P1-5: tek indirme + checksum.
4. P1-9: tek sayı ayrıştırıcı.
5. CI: ruff + web pytest + frontend typecheck/build.

### Sprint 2 — Dayanıklılık (2 hafta)

1. P1-2 OCR kuyruğu, iptal, timeout.
2. P1-3 streaming upload + tek limit.
3. P1-10 migration/Postgres testi.
4. P1-6 mypy ratchet (backend services önce).

### Sprint 3 — Sürdürülebilirlik (3 hafta)

1. `ui/app.py` bölme: `ui/state/*`, `ui/views/*`, `ui/reports.py`, `ui/update_controller.py`.
2. Frontend: Vitest + Testing Library + ESLint; kritik akışlar için Playwright.
3. P2 temizliği (doküman, sürüm, bundle, erişilebilirlik).
4. Şartname 14.2 ve zaman serisi entegrasyonu.

---

## 9. Hızlı Kazanımlar (bu hafta)

1. `AppError` düzeltmesini commit et (P0-2).
2. Workspace claim/list'i varsayılan kapalı yap (P0-1).
3. `save_report_button`'ı karar `BASARILI` olana kadar disable et (P1-4a).
4. `_on_session_selected` ve `_apply_input_snapshot` sonunda `_reset_decision_card()` çağır (P1-4b).
5. `vite.config.ts` → `sourcemap: false` (P2-3).
6. README/DURUM/implementation_status sayılarını 680/147/81 ile güncelle (P2-1).
7. CI'a `ruff check .` job'ı ekle (P1-1, kısmi).

---

## 10. Doğrulama Komutları

```bash
# Lint
python3 -m ruff check .

# Tip
python3 -m mypy hidrostatik_test/domain/
python3 -m mypy --ignore-missing-imports hidrostatik_test webapp/backend/app

# Test
python3 -m pytest webapp/backend/tests -q
python3 -m unittest discover -s tests -p "test_*.py"

# Kapsam
python3 -m coverage run --branch -m unittest discover -s tests -p "test_*.py"
python3 -m coverage report

# Frontend
cd webapp/frontend && npm run typecheck && npm run build

# OpenAPI
cd webapp/backend && python3 -c "from app.main import create_app; s=create_app().openapi(); print(len(s['paths']))"
```

**P0-2 regresyon testi (öneri):**

```python
def test_plan_profile_unsupported_format_returns_415(client, headers):
    r = client.post(
        "/api/projects/plan-profile/scan",
        files={"file": ("x.txt", b"hello", "text/plain")},
        headers=headers,
    )
    assert r.status_code == 415
    assert r.json()["code"] == "unsupported_format"
```

**P0-1 yetki testi (öneri):**

```python
def test_workspace_claim_requires_admin(client, headers):
    r = client.post(
        "/api/system/workspaces/claim",
        json={"source_workspace_hash": "a" * 64},
        headers=headers,
    )
    assert r.status_code == 403
```

---

## 11. Riskler ve Bağımlılıklar

| Risk | Olasılık | Etki | Azaltım |
|---|---|---|---|
| Workspace claim açığının fark edilmeden dağıtılması | Yüksek | Kritik | Sprint 0'da kapat, varsayılan host'u değiştir |
| HEAD'den kurulum yapılması | Orta | Yüksek | Düzeltmeyi hemen commit et, sürüm etiketiyle yayınla |
| OCR'ın senkron kalması | Yüksek | Orta | Kuyruk + timeout |
| 255 mypy hatasının daha da büyümesi | Yüksek | Orta | Ratchet + CI |
| Postgres'e geçişte migration kırılması | Orta | Yüksek | Alembic + staging testi |
| Frontend demo fallback'in yanlış sonuç göstermesi | Orta | Yüksek | Görünür DEMO bandı, rapor kilidi |
| Çalışma ağacının hareketli olması | Yüksek | Orta | Ölçümleri commit sonrası tekrarla |

---

## Ek A — Güçlü Yönler (korunmalı)

- **Domain saflığı:** `hidrostatik_test/domain/` mypy temiz; şartname sabitleri ve toleranslar açıkça tanımlı (`hydrotest_core.py`, `pressurization.py`).
- **Test disiplini:** 680 masaüstü + 147 web testi; hata senaryoları (negatif B, sınır değerler) kapsanıyor.
- **A/B kontrol tablosu:** Anomali tespiti ve onarım görünümü (`data/ab_control_table.py`) belgelenmiş, test edilmiş.
- **Hata zarfı:** `AppError` + `request_id` + Türkçe mesajlar tutarlı.
- **Frontend tip disiplini:** `tsc -b` temiz; API tipleri merkezi (`lib/types.ts`).
- **Güncelleme imzası:** Ed25519 imza doğrulaması ve checksum altyapısı mevcut (`updater.py`).

## Ek B — Bulgu → Kanıt İndeksi

| Bulgu | Kanıt |
|---|---|
| P0-1 | `api/system.py:26-33`, `services/db_admin.py:23-180`, `tests/test_db_management.py:130-160` |
| P0-2 | `git show HEAD:.../plan_profile.py`, `core/errors.py`, `plan_profile.py:1900-1950` |
| P0-3 | `docker-compose.yml:8-14`, `core/config.py:132`, `main.py:96-106` |
| P1-1 | `.github/workflows/test.yml` |
| P1-2 | `api/ocr.py:19`, `services/ocr.py:319+`, `api_contract.md`, `OcrPage.tsx:492` |
| P1-3 | `plan_profile.py:1908`, `report_ocr.py:85-95`, `config.py:159` |
| P1-4 | `app.py:1076,5975,7614,8040,8181,7857`; `wizard.py:540` |
| P1-5 | `download_dialog.py:125-129`, `app.py:3064-3074`, `updater.py:1290-1295` |
| P1-6 | mypy çıktısı (Bölüm 2.2) |
| P1-7 | `hooks/queries.ts:83-98`, `lib/mock.ts` |
| P1-8 | `report_ocr_dialog.py:439-444,500-520`, `report_ocr.py:99-101` |
| P1-9 | `validators.py:96+`, `app.py:6445-6457` |
| P1-10 | `db.py:121-151` |
| P2-1 | `README.md:137`, `DURUM.md:16`, `implementation_status.md:12` |
| P2-2 | `app_metadata.py:6`, `backend/app/__init__.py:7`, `main.py:84` |
| P2-3/4 | `vite.config.ts:18-19`, build çıktısı |
| P2-6 | `build_web_exe.ps1:284-303` |

---

## Ek C — İnceleme Notu

Bu raporda üç alt ajan (domain/şartname, web backend, frontend) "Free usage limit reached" nedeniyle tamamlanamadı. Bu alanlar doğrudan asistan tarafından incelendi; masaüstü ajanının iddiaları ayrıca kod üzerinden doğrulandı. Doğrulanamayan veya kodla çelişen iddialar (ör. `_restoring_snapshot` sırası) rapora alınmadı.

**Doğrulanan ancak etkisi düşük olduğu için P2'ye düşürülenler:**

- Snapshot geri yüklemede `_restoring_snapshot` doğru sırada set ediliyor (`app.py:7959-7965`); ajan iddiasının aksine burada hata yok.
- `download_manager` `Content-Range` ve 206 kontrolü yapıyor (`download_manager.py:390-405`); resume tamamen doğrulamasız değil.

**Sonraki adım:** Bu raporun P0 ve Sprint 0 maddeleri için düzeltme uygulanması. Kod değişikliği henüz yapılmadı.
