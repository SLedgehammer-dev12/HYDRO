# HYDRO Web - Uygulama Durumu

Tarih: 2026-11-16
Dal: `feat/ergonomics-ocr`

> Tek sayfalık güncel özet ve yapılacaklar listesi: [`../../DURUM.md`](../../DURUM.md)

## Tamamlananlar

| Alan | Durum | Kanit |
| --- | --- | --- |
| Backend API | Calisiyor | 51 path (`/api/projects` dahil), 97 pytest |
| Frontend kabuk | Calisiyor | 9 sekme (Projeler & Kesitler, birlesik Geometri & Saha, son sekmede birlesik Katsayilar & Detay), responsive, tema |
| Hesaplamalar | Parity | A/B, hava, basinc, profil, pig, pressurization, termal denge |
| Proje & Kesit DB | Calisiyor | `projects` + `sessions.project_id` + `inputs.section_meta`, kesit siralama/acma/kopyalama/silme |
| Oturum | Calisiyor | SQLite, revision/ETag, snapshot, audit |
| Raporlar | Calisiyor | TXT/PDF/XLSX indirme |
| 3D saha | Calisiyor | Segmentler, kot, ekipman, pig, akis, kesit, presetler, `SceneHtml` DOM etiket katmani |
| OCR | Calisiyor (metin katmani) | Yukleme, alan/uyusmazlik, onay iskeleti, JSON |
| Docker | Hazir | `webapp/Dockerfile`, `docker-compose.yml` |

## Dogrulama

```bash
python3 -m pytest webapp/backend/tests -q          # 97 passed
python3 -m unittest discover -s tests -p "test_*.py"  # 653 passed
cd webapp/frontend && npm run build                # PASS
cd webapp/frontend && HYDRO_APP_URL=http://127.0.0.1:8095 node scripts/verify-tabs.mjs  # 11/11 PASS
```

Canli smoke:
- `GET /api/health` 200
- Dashboard, Geometri, Katsayilar, Hava, Basinc, Profil/Saha, Raporlar, OCR, Ayarlar render
- Hava testi UI'dan hesaplandi, sonuc `BASARILI`
- Oturum kaydedildi (rev 2) ve SQLite'ta gorundu
- PDF (46 KB, 2 sayfa), XLSX (6.7 KB), TXT export alindi
- OCR sentetik PDF: `pdf-text-layer`, 1 sayfa, %90 guven, 14 karsilastirma
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

1. **Rapor formati (yarin):** OCR mapping profile `pre_extract`/`post_map` uygulanmiyor;
   profil CRUD var, alan esleme verisi eklenecek.
2. **OCR kuyrugu:** analiz senkron; DB kuyrugu + worker + iptal sonraki adim.
3. **Alembic:** tablolar `create_all` + hafif kolon migrasyonu (`init_db`); uretim migration'i eklenmeli.
4. **Auth/OIDC ve iki-kisi kurali:** MVP'de yok.
5. **Postgres:** kod uyumlu, `psycopg` kurulu degil; runtime testi yapilmadi.
7. **Frontend kod bolme:** three.js nedeniyle ana bundle ~2.2 MB; lazy load yapilmali.
8. **Frontend unit testleri:** vitest yok; sekme regresyonu `verify-tabs.mjs` ile korunuyor.
9. **3D gercek veri:** `profile_points[]`/`equipment[]` opsiyonel; yoksa yaklasik sahne.
