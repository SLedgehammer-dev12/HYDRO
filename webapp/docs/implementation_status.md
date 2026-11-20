# HYDRO Web - Uygulama Durumu

Tarih: 2026-11-20
Dal: `main` (`v1.9.1`)

> Tek sayfalık güncel özet ve yapılacaklar listesi: [`../../DURUM.md`](../../DURUM.md)

## Tamamlananlar

| Alan | Durum | Kanit |
| --- | --- | --- |
| Backend API | Calisiyor | 81 OpenAPI path (94 operation), 223 pytest (Alembic `0003`), 48 backend dosyada `mypy` temiz |
| Frontend kabuk | Calisiyor | 9 sekme (Projeler & Kesitler, birlesik Geometri & Saha, son sekmede birlesik Katsayilar & Detay), responsive, tema |
| Hesaplamalar | Parity | A/B, hava, basinc, profil, pig, pressurization, termal denge |
| Proje & Kesit DB | Calisiyor | `projects` + `sessions.project_id` + `inputs.section_meta`, kesit siralama/acma/kopyalama/silme |
| Oturum | Calisiyor | SQLite, revision/ETag, snapshot, audit |
| Raporlar | Calisiyor | TXT/PDF/XLSX indirme |
| 3D saha | Calisiyor | Segmentler, kot, ekipman, pig, akis, kesit, presetler, `SceneHtml` DOM etiket katmani |
| OCR | Calisiyor (macOS Vision + metin katmani) | Yukleme, bbox tabanli etiket/deger esleme, alan/uyusmazlik, onay, JSON; 9 resmi `.xls` + 74 sayfalik gercek raporla kalibre |
| OCR mapping profile | Calisiyor | `pre_extract` ek etiket adlari, `post_map` hedef yol gecersiz kilma |
| Docker | Hazir | `webapp/Dockerfile`, `docker-compose.yml` |

## Dogrulama

```bash
python3 -m pytest webapp/backend/tests -q          # 223 passed
python3 -m unittest discover -s tests -p "test_*.py"  # 715 tests OK (skipped=1)
cd webapp/frontend && npm run lint && npm test && npm run typecheck && npm run build && npm run check:bundle  # PASS (41 Vitest / 13 dosya, 147,7 kB gzip)
cd webapp/frontend && HYDRO_APP_URL=http://127.0.0.1:8099 node scripts/verify-tabs.mjs  # 12/12 PASS (önceki canlı kontrol)
```

Canli smoke:
- `GET /api/health` 200
- Dashboard, Geometri, Katsayilar, Hava, Basinc, Profil/Saha, Raporlar, OCR, Ayarlar render
- Hava testi UI'dan hesaplandi, sonuc `BASARILI`
- Oturum kaydedildi (rev 2) ve SQLite'ta gorundu
- PDF (46 KB, 2 sayfa), XLSX (6.7 KB), TXT export alindi
- OCR sentetik PDF: `pdf-text-layer`, 1 sayfa, %90 guven, 14 karsilastirma
- OCR gercek form (ERCIS, sayfa 8/11): `vision`, tum hava/basinc alanlari ve KP araligi dogru
- `GET /api/ocr/status`: `engine.name=vision`, diller `tr-TR,en-US`
- 3D sahne: 3 segment, 5 ekipman, pig/akis/kesit

## Calistirma

Yerel:

```bash
python3 -m pip install -r requirements.txt -r requirements-ocr.txt -r webapp/requirements-web.txt
python3 webapp/run_web.py --host 127.0.0.1 --port 8080
```

Frontend gelistirme:

```bash
cd webapp/frontend
npm install
npm run dev        # 5173, /api -> 8080 proxy
```

Docker:

```bash
docker compose -f webapp/docker-compose.yml up --build
```

## Notlar

- `THREE.Clock` deprecation uyarisi R3F v9 + Three r187 kaynaklidir; yalnizca
  dev modda ve yalnizca bu mesaj icin filtrelenir (`src/main.tsx`). R3F/Three
  surumu yukseltilince filtre kaldirilabilir.
- `@react-three/drei` `Html` bileseni React 19 uretim derlemesinde ic ice kok
  sokumu sirasinda `removeChild` hatasi urettigi icin kaldirildi; yerine ana
  React agacinda calisan `SceneHtml` + `SceneLabels` DOM katmani eklendi.
- Uretim build'inde console filtresi calismaz; hata/uyarilar aynen gorunur.

## Bilinen Eksikler / Sonraki Faz

1. **OCR kuyrugu (tamamlandi):** DB kuyrugu + sinirli calisan (`ocr_queue.py`) + iptal + asenkron `202` destegi aktif.
2. **OCR form kapsami:** hava icerik, basinc kabul ve `.xlsx`/`.xls` / ERCIS raporlari kalibre; diger ek formlar ve kurum onayli resmi A/B revizyonlari sirada.
3. **Alembic uretim gocu (tamamlandi):** `webapp/backend/migrations/` (`0002` → `0003`), `migrations_runner.py`, eski `0001`/`0002` koprusu, SQLite FK / Postgres advisory lock korumasi ve asamali geri alinabilir yedek geri yukleme tamamlandi.
4. **Auth/OIDC ve iki-kisi kurali:** MVP'de yok (kurumsal mimari karar bekleniyor).
5. **Postgres:** kod uyumlu, `psycopg` kurulu degil; canli Postgres runtime testi yapilmadi.
6. **Frontend kod bolme & birim testleri (tamamlandi):** rota/Recharts/three.js lazy-loading + `check:bundle` (`147,7 kB` gzip ilk yukleme JS) ve 41 Vitest bilesen/birim testi (13 dosya) aktif.
7. **3D gercek veri (tamamlandi):** `profile_points[]` ve `equipment[]` girdileri (`SiteSurveyPanel.tsx`, `buildSceneData()`, `build_scene()`, `build_project_scene()`), yoksa acik yaklasik sahne uyarilari gosterilir.
8. **Muhendislik guvenlik uyarilari, `water_backend` & rapor kimligi uyumu (tamamlandi):** `evaluate_fill_temperature` (`+2 °C` Madde 10.1 uyarisi), `negative_b = b < 0` duzeltmesi ve `0–4 °C` negatif `beta_water`/`B` UI uyarilari, ayri `inputs.water_backend` secicisi + TXT/CSV backend karsilastirma raporu, `t_initial`/`t_final` ve OCR `report_meta` -> `report` tam uyumu tamamlandi.
9. **Masaüstü JSON snapshot içe aktarma & eşzamanlı düzenleme 409 diff (tamamlandi):** `POST /api/import/desktop-snapshot` (`project_id`, audit & mapping özetleri) UI bağlantısı (`ProjectImportModal` + `ReportsPage`) ve `PUT /sessions/{id}`, `POST /snapshot`, `POST /results` için `If-Match` / `409 revision_conflict` (`details.current` + `details.diff`) ile satır bazlı Sunucu/Yerel birleştirme modalı (`RevisionConflictModal`) eklendi.
