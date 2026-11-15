# HYDRO Web

Mevcut Tkinter masaüstü uygulamasının (`hidrostatik_test/`) tüm işlevlerini kapsayan
web uygulaması. Hesaplama motoru **yeniden yazılmaz**; web katmanı aynı domain paketini
import eder.

> **Durum:** Uygulama calisiyor. Backend, frontend, 3D saha sahnesi, oturum,
> rapor exportu ve OCR arayuzu tamamlandi. Ayrintili durum:
> [docs/implementation_status.md](docs/implementation_status.md).

---

## Hizli Baslangic

```bash
# Bagimliliklar
python3 -m pip install -r requirements.txt -r requirements-ocr.txt -r webapp/requirements-web.txt

# Backend + statik frontend (frontend/dist varsa)
python3 webapp/run_web.py --host 127.0.0.1 --port 8080

# Frontend gelistirme (ayri terminal)
cd webapp/frontend && npm install && npm run dev
```

Docker:

```bash
docker compose -f webapp/docker-compose.yml up --build
```

---

## Dokümanlar

| Doküman | İçerik |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Teknoloji seçimi, repo yapısı, katmanlar, DB şeması, dosya depolama, hata modeli, 3D veri modeli, dağıtım, test, güvenlik, teslim planı |
| [docs/parity_matrix.md](docs/parity_matrix.md) | Masaüstündeki her girdi/hesap/sonuç alanının web karşılığı ve durumu |
| [docs/api_contract.md](docs/api_contract.md) | Tüm endpoint'ler, JSON örnekleri, Pydantic ve TypeScript tipleri, hata kataloğu |
| [docs/ux_plan.md](docs/ux_plan.md) | Sekmeler, 3D etkileşimleri, tasarım dili, erişilebilirlik, OCR akışı |

Masaüstü tarafı için: `docs/codebase_map.md`, `docs/spec/ab_methods_and_units.md`,
`docs/ocr_report_pipeline.md`.

---

## Hedeflenen çalıştırma

Yerel (tek makine):

```bash
python3 -m pip install -r requirements.txt -r requirements-ocr.txt
python3 webapp/run_web.py --host 127.0.0.1 --port 8080
# http://127.0.0.1:8080
```

LAN (auth'suz MVP — yalnız güvenilir ağda):

```bash
python3 webapp/run_web.py --host 0.0.0.0 --port 8080
```

Docker:

```bash
docker compose -f webapp/docker-compose.yml up --build
```

`run_web.py` planlanan sorumlulukları: repo kökünü `sys.path`'e eklemek, ayarları
okumak, Alembic migration çalıştırmak, `frontend/dist` varsa statik olarak servis etmek
ve uvicorn'u başlatmak. Hiçbir iş mantığı içermez.

---

## Klasör yapısı

```text
webapp/
├── docs/              # mimari, parity, API, UX
├── backend/           # FastAPI + SQLAlchemy + servisler (S0'da oluşturulacak)
│   ├── app/
│   ├── tests/parity/  # domain'den üretilen altın fixture'lar
│   └── alembic/
├── frontend/          # React 19 + TypeScript + Vite (S0'da oluşturulacak)
│   ├── src/
│   └── e2e/
├── data/              # git dışı: DB, uploads, exports
├── run_web.py         # tek giriş noktası (S0)
├── Dockerfile         # (S6)
└── docker-compose.yml # (S6)
```

---

## Temel kararlar (özet)

- **Tek doğruluk kaynağı:** `hidrostatik_test.domain`. Katsayı, limit ve karar mantığı
  web'de kopyalanmaz; parity fixture'ları bunu kanıtlar.
- **Auth yok (MVP):** `X-Session-ID` tabanlı anonim çalışma alanı; ileride OIDC için
  `users`/`memberships` yeri ayrıldı. LAN'da proxy allowlist önerilir.
- **Veri:** SQLite (WAL) → Postgres; aynı SQLAlchemy şeması, Alembic migration.
- **Dosyalar:** `data/uploads/<session>/<uuid>.<ext>`; 25 MB, uzantı allowlist, MIME sniff,
  path traversal koruması.
- **3D:** tam saha sahnesi (zemin, segmentler, vanalar, pompa, test başlığı, pig, kot
  profili, basınç/utilization renkleri, kesit). Gerçek kot/ekipman konumu masaüstünde
  olmadığı için MVP'de yaklaşık türetim + uyarı; `profile_points[]`/`equipment[]` opsiyonel
  genişleme olarak planlandı.
- **OCR:** mevcut `report_ocr` servisi; DB kuyruğu + tek worker; alan eşleme profilleri
  (rapor formatı yarın geleceği için veri odaklı).

---

## İlk uygulama adımı (S0)

1. `webapp/backend/pyproject.toml` + `app/main.py` + `core/config.py` + hata zarfı.
2. `run_web.py` (path bootstrap, migration, statik).
3. Migration 0001: `projects`, `sessions`, `test_results`, `time_series`, `attachments`,
   `ocr_analyses`, `ocr_mapping_profiles`, `audit_events`.
4. `GET /api/health`, `GET /api/meta`.
5. Frontend shell: layout, tema token'ları, API client, boş Dashboard.
6. İlk parity fixture üreticisi ve CI iskeleti.

Kabul: `pytest` yeşil, `npm run build` başarılı, `GET /api/health` 200.
