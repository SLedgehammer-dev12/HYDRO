# HYDRO Web — API Sözleşmesi

**Sürüm:** v1 (taslak)
**Base URL:** `/api`
**İçerik tipi:** `application/json; charset=utf-8` (dosya uçları hariç)
**İlgili:** [architecture.md](architecture.md), [parity_matrix.md](parity_matrix.md)

> Bu doküman sözleşmedir; uygulama bu dokümana göre yazılır. Örneklerdeki sayısal
> değerler **gösterim amaçlıdır**, kabul değeri değildir. Gerçek değerler domain
> fonksiyonlarından üretilir ve parity fixture'larıyla doğrulanır.

---

## 1. Genel sözleşme

### 1.1 Başlıklar

| Başlık | Yön | Zorunlu | Açıklama |
|---|---|---|---|
| `Content-Type` | İstek | JSON uçlarında evet | `application/json` |
| `X-Session-ID` | İstek/yanıt | Önerilen | Anonim **workspace** anahtarı (UUID). Oturum kaynağının `id`'si değildir. Yoksa sunucu üretir ve yanıtta döner. |
| `X-Request-ID` | İstek/yanıt | Hayır | İstemci üretirse korunur; yoksa sunucu üretir. |
| `If-Match` | İstek | `PUT` için evet | `sessions.revision` değeri, ETag biçiminde: `"3"`. |
| `ETag` | Yanıt | Oturum GET/PUT | `"<revision>"`; `If-Match` ile aynı biçim. |
| `Idempotency-Key` | İstek | Hayır | `POST /results`, `/reports/export`, `/ocr/analyze` için önerilir. 24 saat saklanır. |
| `Retry-After` | Yanıt | 429/503 | Saniye. |
| `X-Total-Count` | Yanıt | Liste | Sayfalama toplamı (gövdede de var). |

CORS: varsayılan kapalı. `HYDRO_CORS_ORIGINS` doluysa yalnızca listelenen origin'ler;
`Access-Control-Allow-Headers: Content-Type, X-Session-ID, X-Request-ID, If-Match,
Idempotency-Key`.

### 1.2 Kaynak ve hata zarfları

Başarılı tekil kaynak: kaynak nesnesi doğrudan döner (zarf yok).
Liste:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

Hata (tek biçim):

```json
{
  "code": "domain_validation_error",
  "message": "Et kalinligi borunun ic capini sifira dusurecek kadar buyuk olamaz.",
  "details": {"field": "geometry.sections[0].wall_thickness_mm"},
  "request_id": "0f1d2c3b-4a59-4e6f-8a7b-9c0d1e2f3a4b"
}
```

`details` her zaman nesnedir (dizi değil); Pydantic hataları `details.errors[]` altına
konur. `message` kullanıcıya gösterilebilir Türkçe metindir; stack trace asla dönmez.

### 1.3 Tipler ve biçimler

| Alan tipi | Biçim | Örnek |
|---|---|---|
| ID | UUID v4 string | `"9b2f…"` |
| Zaman | ISO-8601 UTC, `Z` son eki | `"2026-11-15T19:42:11Z"` |
| Sayı | IEEE-754 double, JSON number | `44.971994` |
| Para/birim | string etiket | `"10^-6/bar"` |
| Enum | lower_snake_case string | `"volumetric"` |
| Boş değer | `null` (alan yokluğu ile karışmaz) | `"volume_m3": null` |

Yuvarlama: API **tam hassasiyet** döner; yuvarlama frontend'in işidir (gösterim:
katsayılar 6 hane, basınç 3 hane, hacim 6 hane, oran 6 hane). Karşılaştırma testleri
`rel=1e-9` kullanır.

### 1.4 Ortak enum'lar

| Enum | Değerler |
|---|---|
| `B_SOURCE` | `institutional`, `gail`, `auto` |
| `STEEL_MODEL` | `volumetric`, `linear`, `volumetric_temperature` |
| `A_MODE` / `B_MODE` | `auto`, `table`, `manual` |
| `COEFFICIENT_STATE` | `empty`, `computed`, `reference`, `manual`, `stale` |
| `DECISION_STATUS` | `BEKLIYOR`, `KATSAYI GUNCELLENMELI`, `DOGRULANAMADI`, `BASARILI`, `BASARISIZ` |
| `PIG_STATUS` | `UYGUN`, `LIMIT ASILDI`, `BILGI` |
| `SESSION_STATUS` | `draft`, `active`, `completed`, `archived` |
| `TEST_TYPE` | `air`, `pressure`, `coefficient_a`, `coefficient_b`, `profile`, `pig`, `pressurization`, `thermal_balance` |
| `OCR_STATUS` | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| `OCR_SOURCE` | `pdf-text-layer`, `ocr`, `mixed` |
| `DISCREPANCY_STATUS` | `match`, `within_tolerance`, `mismatch`, `missing_in_report`, `missing_in_calculation`, `not_comparable` |
| `SEVERITY` | `info`, `warning`, `critical` |

### 1.5 Ortak girdi şemaları

**Geometri** (tek kesit de tek elemanlı dizi olarak gönderilir):

```json
{
  "sections": [
    {
      "outside_diameter_mm": 406.4,
      "wall_thickness_mm": 8.74,
      "length_m": 1000.0,
      "nps_label": "NPS 16 (DN 400)",
      "schedule_label": "Sch 20 - 8.74 mm",
      "start_station_m": 0.0
    }
  ]
}
```

`start_station_m` opsiyoneldir (3D için); verilmezse zincirleme türetilir.

**Karar nesnesi** (hesap yanıtlarında):

```json
{
  "status": "BASARILI",
  "title": "Hava Icerik Testi",
  "summary": "Vp = 0.007834 m³, limit = 0.008304 m³, Vpa = 0.007750 m³, oran = 0.989151. Kural: Vpa < 1.06 x Vp; marj = 0.000554 m³.",
  "rule": "Vpa < 1.06 x Vp",
  "margin": 0.000554
}
```

---

## 2. Endpoint özeti

| # | Method | Path | Amaç | Dilim |
|---|---|---|---|---|
| 1 | GET | `/api/health` | Sağlık | S0 |
| 2 | GET | `/api/meta` | Sürüm/limit/katalog meta | S0 |
| 3 | GET | `/api/meta/spec` | Şartname kuralları ve kontrol noktaları | S0 |
| 4 | GET | `/api/catalog/pipes` | Boru çapları | S3 |
| 5 | GET | `/api/catalog/pipes/{nps}/schedules` | Schedule listesi | S3 |
| 6 | GET | `/api/catalog/grades` | API 5L PSL2 kaliteleri | S3 |
| 7 | GET | `/api/catalog/reference-tables` | A/B tablo aralıkları | S1 |
| 8 | POST | `/api/coefficients/a` | A hesabı | S1 |
| 9 | POST | `/api/coefficients/b` | B çözümleme | S1 |
| 10 | POST | `/api/coefficients/compare` | Üç kaynak B | S1 |
| 11 | POST | `/api/coefficients/table` | Tablo A/B noktası | S1 |
| 12 | POST | `/api/coefficients/reference-compare` | Kurum içi vs GAIL | S1 |
| 13 | POST | `/api/coefficients/backend-comparison` | Backend karşılaştırma | S1 |
| 14 | POST | `/api/calculations/geometry` | Vt/ri/elastisite | S3 |
| 15 | POST | `/api/calculations/air-content` | Hava içerik | S2 |
| 16 | POST | `/api/calculations/pressure-variation` | Basınç değişimi | S2 |
| 17 | POST | `/api/calculations/pressure-profile` | Profil/pencere | S3 |
| 18 | POST | `/api/calculations/pig-speed` | Pig hızı | S4 |
| 19 | POST | `/api/calculations/pressurization` | %0.2 kontrol | S2 |
| 20 | POST | `/api/calculations/thermal-balance` | Termal denge | S4 |
| 21 | POST | `/api/calculations/water-density` | Yoğunluk | S3 |
| 22 | GET | `/api/sessions` | Oturum listesi | S4 |
| 23 | POST | `/api/sessions` | Oturum oluştur | S4 |
| 24 | GET | `/api/sessions/{id}` | Oturum detayı | S4 |
| 25 | PUT | `/api/sessions/{id}` | Oturum güncelle | S4 |
| 26 | DELETE | `/api/sessions/{id}` | Soft delete | S4 |
| 27 | POST | `/api/sessions/{id}/duplicate` | Kopyala | S4 |
| 28 | GET | `/api/sessions/{id}/results` | Sonuç geçmişi | S4 |
| 29 | POST | `/api/sessions/{id}/results` | Hesapla + kaydet | S4 |
| 30 | GET | `/api/sessions/{id}/time-series` | Zaman serisi | S4 |
| 31 | POST | `/api/sessions/{id}/time-series` | Kayıt ekle | S4 |
| 32 | DELETE | `/api/sessions/{id}/time-series/{record_id}` | Kayıt sil | S4 |
| 33 | GET | `/api/sessions/{id}/time-series/summary` | Süre/ortalama/denge | S4 |
| 34 | GET | `/api/sessions/{id}/scene` | 3D sahne modeli | S3 |
| 35 | GET | `/api/sessions/{id}/summary` | Dashboard özeti | S4 |
| 36 | GET | `/api/sessions/{id}/audit` | Denetim izi | S5 |
| 37 | GET | `/api/sessions/{id}/export` | Oturum dışa aktarma | S4 |
| 38 | POST | `/api/reports/export` | Serbest rapor export | S4 |
| 39 | POST | `/api/import/desktop-snapshot` | Masaüstü JSON içe aktarma | S4 |
| 40 | GET | `/api/stats` | Genel istatistik | S4 |
| 41 | POST | `/api/ocr/analyze` | OCR işi başlat | S5 |
| 42 | GET | `/api/ocr/status` | OCR motoru + kuyruk | S5 |
| 43 | GET | `/api/ocr/analyses` | Analiz listesi | S5 |
| 44 | GET | `/api/ocr/analyses/{id}` | Analiz sonucu | S5 |
| 45 | POST | `/api/ocr/analyses/{id}/cancel` | İptal | S5 |
| 46 | POST | `/api/ocr/analyses/{id}/approve` | Alan onayı | S5 |
| 47 | POST | `/api/ocr/analyses/{id}/apply` | Oturuma uygula | S5 |
| 48 | GET | `/api/ocr/mapping-profiles` | Profil listesi | S5 |
| 49 | POST | `/api/ocr/mapping-profiles` | Profil oluştur | S5 |
| 50 | GET | `/api/ocr/mapping-profiles/{id}` | Profil detayı | S5 |
| 51 | PUT | `/api/ocr/mapping-profiles/{id}` | Profil güncelle | S5 |
| 52 | DELETE | `/api/ocr/mapping-profiles/{id}` | Profil sil | S5 |
| 53 | GET | `/api/projects` | Proje listesi | S4 |
| 54 | POST | `/api/projects` | Proje oluştur | S4 |
| 55 | GET | `/api/projects/{id}` | Proje detayı | S4 |
| 56 | PUT | `/api/projects/{id}` | Proje güncelle | S4 |
| 57 | DELETE | `/api/projects/{id}` | Soft delete | S4 |
| 58 | GET | `/api/sessions/{id}/snapshot` | Masaüstü uyumlu JSON indir | S4 |
| 59 | POST | `/api/sessions/{id}/snapshot` | Masaüstü JSON yükle | S4 |

---

## 3. Sistem uçları

### 3.1 `GET /api/health`

**Yanıt 200**

```json
{
  "status": "ok",
  "version": "1.7.3",
  "engine": "hidrostatik_test",
  "db": {"ok": true, "dialect": "sqlite", "migration": "0001"},
  "data_dir": {"ok": true, "writable": true},
  "ocr": {
    "available": true,
    "status": "OCR hazir (Tesseract + Pillow).",
    "queue": {"queued": 0, "running": 0}
  },
  "uptime_s": 3821
}
```

`status`: `ok` | `degraded` | `fail`. `?strict=1` ise `degraded/fail` → 503.
**Hatalar:** 503 `dependency_missing` (DB açılamıyor).

### 3.2 `GET /api/meta`

**Yanıt 200**

```json
{
  "app": {"name": "Hidrostatik Test Degerlendirme", "version": "1.7.3"},
  "spec": {
    "code": "4-NGTL 0-GN-P-002-5007 R4",
    "title": "Hidrostatik Test ve Icten Denetleme Sartnamesi"
  },
  "engine": {"domain_schema": 1, "decision_statuses": ["BEKLIYOR", "KATSAYI GUNCELLENMELI", "DOGRULANAMADI", "BASARILI", "BASARISIZ"]},
  "water_backends": [
    {"key": "table_v1", "label": "Table Interpolation v1", "distribution_ready": true, "note": "0-40 °C, 1-150 bar"},
    {"key": "coolprop", "label": "CoolProp EOS", "distribution_ready": true, "note": "Varsayilan (kuruluysa)"}
  ],
  "b_sources": [
    {"key": "institutional", "label": "Kurum ici A/B kontrol tablosu", "default": true},
    {"key": "gail", "label": "GAIL referans tablosu"},
    {"key": "auto", "label": "Otomatik beta - celik genlesmesi"}
  ],
  "steel_models": ["volumetric", "linear", "volumetric_temperature"],
  "location_classes": [
    {"class_number": 1, "label": "Class 1 - min 1.25 x dizayn basinci", "minimum_test_factor": 1.25, "spec_reference": "NGTL 5007 / 4.2, ASME B31.8 Class 1"}
  ],
  "pump_locations": ["Baslangic noktasi", "Bitis noktasi"],
  "pig_modes": [
    {"label": "Temizlik pigi", "spec_reference": "Madde 9", "max_speed_m_per_s": 2.5},
    {"label": "Serbest kontrol", "spec_reference": "Bilgi", "max_speed_m_per_s": null}
  ],
  "limits": {
    "max_file_size_bytes": 26214400,
    "max_pdf_pages": 200,
    "max_ocr_pages": 30,
    "max_test_section_length_m": 20000.0,
    "max_test_section_volume_m3": 12500.0,
    "air_acceptance_factor": 1.06,
    "pressure_variation_acceptance_bar": 0.3,
    "pressurization_volume_limit_percent": 0.2,
    "thermal_balance_min_hours": 24.0,
    "thermal_balance_threshold_c": 0.5,
    "ambient_temp_limit_c": 2.0,
    "air_pressure_rise_bar": 1.0
  },
  "features": {"ocr": true, "scene": true, "dev_backends": false, "auth": "none"},
  "units": {
    "pressure": "bar", "temperature": "°C", "length": "m", "diameter": "mm",
    "volume": "m³", "a": "10^-6/bar", "b": "10^-6/°C"
  }
}
```

**Hatalar:** —

### 3.3 `GET /api/meta/spec`

**Yanıt 200**

```json
{
  "code": "4-NGTL 0-GN-P-002-5007 R4",
  "title": "Hidrostatik Test ve Icten Denetleme Sartnamesi",
  "acceptance_rules": {
    "air": {"text": "Vpa < 1.06 x Vp", "factor": 1.06},
    "pressure": {"text": "(Pa - Pt) <= 0.3 bar", "tolerance_bar": 0.3}
  },
  "sign_convention": {
    "delta_t": "dT = Tilk - Tson",
    "pa": "Pa = Pilk - Pson"
  },
  "checks": [
    {"key": "ambient_temp", "label": "Dolum sirasinda hava sicakligi +2 °C limitine gore kontrol edildi", "reference": "10.1"},
    {"key": "forms", "label": "21.1-21.5 saha formlari dolduruldu", "reference": "21"}
  ],
  "notes": [
    "Nihai karar ASME B31.8 ve proje proseduru ile birlikte degerlendirilmelidir.",
    "OCR cikti resmi kabul raporu degildir; insan onayi zorunludur."
  ]
}
```

---

## 4. Katalog

### 4.1 `GET /api/catalog/pipes`

**Query:** `q` (opsiyonel, NPS/DN/OD araması), `limit` (varsayılan 200), `offset`.

**Yanıt 200**

```json
{
  "items": [
    {
      "nps": "16",
      "dn": "400",
      "outside_diameter_mm": 406.4,
      "option_label": "NPS 16 (DN 400) - OD 406.40 mm",
      "schedules": [
        {"label": "Sch 10 - 6.35 mm", "wall_thickness_mm": 6.35},
        {"label": "Sch 20 - 8.74 mm", "wall_thickness_mm": 8.74}
      ]
    }
  ],
  "total": 1,
  "limit": 200,
  "offset": 0
}
```

**Hatalar:** —

### 4.2 `GET /api/catalog/pipes/{nps}/schedules`

`{nps}`: `"16"` (NPS etiketi) veya `"400"` (DN).

**Yanıt 200**

```json
{"nps": "16", "dn": "400", "outside_diameter_mm": 406.4, "items": [{"label": "Sch 20 - 8.74 mm", "wall_thickness_mm": 8.74}]}
```

**Hatalar:** 404 `not_found`.

### 4.3 `GET /api/catalog/grades`

**Yanıt 200**

```json
{
  "items": [
    {"grade": "X52", "iso_label": "L360", "smys_mpa": 360.0, "option_label": "API 5L PSL2 X52 / L360 - SMYS 360 MPa"},
    {"grade": "X65", "iso_label": "L450", "smys_mpa": 450.0, "option_label": "API 5L PSL2 X65 / L450 - SMYS 450 MPa"}
  ],
  "total": 9, "limit": 50, "offset": 0
}
```

### 4.4 `GET /api/catalog/reference-tables`

**Yanıt 200**

```json
{
  "items": [
    {
      "key": "institutional",
      "label": "Kurum ici A/B kontrol tablosu",
      "option_label": "BOTAŞ referans tablosu - aktif T/P",
      "temperature": {"min": 1.0, "max": 25.0, "step": 1.0, "count": 25},
      "pressure": {"min": 30.0, "max": 120.0, "step": 1.0, "count": 91},
      "a_unit": "10^-6/bar",
      "b_unit": "10^-6/°C",
      "source_note": "A ve B Katsayisi.xlsx",
      "a_repair": {"enabled": true, "band_c": 7.0, "pressure_range_bar": [81.0, 100.0]}
    },
    {
      "key": "gail",
      "label": "GAIL referans tablosu",
      "option_label": "GAIL referans tablosu - aktif T/P",
      "temperature": {"min": 2.0, "max": 30.0, "step": 2.0, "count": 15},
      "pressure": {"min": 30.0, "max": 120.0, "step": 10.0, "count": 10},
      "a_unit": "10^-6/bar",
      "b_unit": "10^-6/°C",
      "source_note": "GAIL-STD-PL-DOC-TS-012 Table-1 ve Fig.1"
    }
  ],
  "total": 2, "limit": 20, "offset": 0
}
```

**Tablo aralığı dışı** istekler `400 reference_table_error` döner; bu uç yalnızca meta verir.

---

## 5. Katsayılar

### 5.1 `POST /api/coefficients/a`

**İstek**

```json
{"temperature_c": 20.0, "pressure_bar": 80.0, "backend": "table_v1"}
```

`backend` opsiyoneldir; yoksa `get_default_water_property_backend()`.

**Yanıt 200**

```json
{
  "a_micro_per_bar": 44.971994,
  "temperature_c": 20.0,
  "pressure_bar": 80.0,
  "backend": {"key": "table_v1", "label": "Table Interpolation v1", "distribution_ready": true},
  "state": "computed"
}
```

**Hatalar:** 400 `water_property_error` (T ≤ −273.15, P ≤ 0, aralık dışı, backend yok);
422 `validation_error`.

### 5.2 `POST /api/coefficients/b`

**İstek**

```json
{
  "source": "institutional",
  "temperature_c": 20.0,
  "pressure_bar": 80.0,
  "steel_alpha_micro_per_c": 12.0,
  "steel_model": "volumetric"
}
```

`steel_alpha_micro_per_c` varsayılan `12.0`; `steel_model` varsayılan `volumetric`.
`source=auto` için `steel_model` etkilidir; `institutional`/`gail` için yalnızca
`steel_alpha` doğrulanır (tablo değeri değişmez).

**Yanıt 200 — tablo kaynağı**

```json
{
  "b_micro_per_c": 188.661,
  "source": "institutional",
  "label": "Kurum ici A/B kontrol tablosu",
  "note": "Kurum ici A/B kontrol tablosu - bilinear interpolation",
  "repaired_table": false,
  "water_beta_micro_per_c": null,
  "steel_alpha_micro_per_c": null,
  "steel_model": ""
}
```

**Yanıt 200 — otomatik**

```json
{
  "b_micro_per_c": 182.297,
  "source": "auto",
  "label": "Otomatik beta - celik genlesmesi",
  "note": "Otomatik hesap: beta = 218.297191, celik alpha = 12.000000; B = beta - 3*alpha (hacimsel model).",
  "repaired_table": false,
  "water_beta_micro_per_c": 218.297191,
  "steel_alpha_micro_per_c": 12.0,
  "steel_model": "volumetric"
}
```

**Hatalar:** 400 `reference_table_error` (aralık dışı; ör. institutional 26 °C),
400 `domain_validation_error` (bilinmeyen model / negatif alpha), 422 `validation_error`.

### 5.3 `POST /api/coefficients/compare`

**İstek**

```json
{"temperature_c": 20.0, "pressure_bar": 80.0, "steel_alpha_micro_per_c": 12.0, "steel_model": "volumetric"}
```

**Yanıt 200**

```json
{
  "temperature_c": 20.0,
  "pressure_bar": 80.0,
  "institutional": {"b_micro_per_c": 188.661, "source": "institutional", "label": "Kurum ici A/B kontrol tablosu", "note": "...", "repaired_table": false},
  "gail": {"b_micro_per_c": 184.030, "source": "gail", "label": "GAIL referans tablosu", "note": "...", "repaired_table": false},
  "auto": {"b_micro_per_c": 182.297, "source": "auto", "label": "Otomatik beta - celik genlesmesi", "note": "...", "water_beta_micro_per_c": 218.297191, "steel_alpha_micro_per_c": 12.0, "steel_model": "volumetric"},
  "deltas": {
    "institutional_vs_gail": 4.631,
    "auto_vs_institutional": -6.364,
    "auto_vs_gail": -1.733
  }
}
```

**Hatalar:** 400 `reference_table_error` (T > 25 °C ise institutional/GAIL birlikte
hesaplanamaz; GAIL tek başına 30 °C'ye kadar geçerlidir — bu uç üçlü karşılaştırma
olduğu için 400 döner), 422.

### 5.4 `POST /api/coefficients/table`

Tek tablodan A/B noktası (onarım bilgisiyle).

**İstek**

```json
{"table": "institutional", "temperature_c": 7.0, "pressure_bar": 90.0, "repair_anomalies": true}
```

`table`: `institutional` | `gail`.

**Yanıt 200**

```json
{
  "table": "institutional",
  "table_label": "Kurum ici A/B kontrol tablosu",
  "requested": {"temperature_c": 7.0, "pressure_bar": 90.0},
  "a_micro_per_bar": 47.115048,
  "b_micro_per_c": 32.663,
  "source_note": "BOTAŞ referans tablosu - exact grid - onarilmis A",
  "repaired": true,
  "repair_note": "onarilmis A degeri: ham 45.515000 -> 47.115048 (10^-6 / bar). A hucreleri ayni T satirinda komsu gecerli basinclardan lineer interpolasyonla onarildi; B ham tablodan alindi."
}
```

**Hatalar:** 400 `reference_table_error`.

### 5.5 `POST /api/coefficients/reference-compare`

**İstek** `{"temperature_c": 20.0, "pressure_bar": 80.0, "repair_anomalies": true}`

**Yanıt 200**

```json
{
  "temperature_c": 20.0,
  "pressure_bar": 80.0,
  "control_point": {"a_micro_per_bar": 44.637, "b_micro_per_c": 188.661, "source_note": "...", "repaired": false},
  "gail_point": {"a_micro_per_bar": 44.656254, "b_micro_per_c": 184.030, "source_note": "...", "repaired": false},
  "a_delta": -0.019254,
  "b_delta": 4.631
}
```

**Hatalar:** 400 `reference_table_error`.

### 5.6 `POST /api/coefficients/backend-comparison`

**İstek** `{"temperature_c": 20.0, "pressure_bar": 80.0, "include_dev_backends": false}`

**Yanıt 200**

```json
{
  "temperature_c": 20.0,
  "pressure_bar": 80.0,
  "items": [
    {
      "backend": {"key": "table_v1", "label": "Table Interpolation v1", "distribution_ready": true},
      "a_micro_per_bar": 44.971994,
      "beta_micro_per_c": 218.297191,
      "density_kg_per_m3": 1001.795,
      "error": null
    },
    {
      "backend": {"key": "coolprop", "label": "CoolProp EOS", "distribution_ready": true},
      "a_micro_per_bar": 44.971993,
      "beta_micro_per_c": 218.297191,
      "density_kg_per_m3": 1001.795,
      "error": null
    }
  ]
}
```

`error` doluysa diğer alanlar `null` olabilir; uç 200 döner (kısmi başarı).
**Hatalar:** 422.

---

## 6. Hesaplamalar

Tüm hesap uçları **durumsuzdur**; hiçbir şey kaydetmez. Kalıcı kayıt için
`POST /api/sessions/{id}/results` kullanılır. Her yanıt `decision` nesnesi içerir
(sunucuda domain sonucundan türetilir).

### 6.1 `POST /api/calculations/geometry`

**İstek**

```json
{"geometry": {"sections": [{"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1000.0}]}}
```

**Yanıt 200**

```json
{
  "section_count": 1,
  "total_length_m": 1000.0,
  "internal_volume_m3": 118.806,
  "internal_radius_mm": 194.46,
  "elasticity_term": 19.668,
  "sections": [
    {
      "index": 1,
      "outside_diameter_mm": 406.4,
      "wall_thickness_mm": 8.74,
      "length_m": 1000.0,
      "internal_radius_mm": 194.46,
      "internal_volume_m3": 118.806,
      "elasticity_term": 19.668
    }
  ]
}
```

**Hatalar:** 400 `domain_validation_error` (`OD ≤ 0`, `WT ≤ 0`, `L ≤ 0`, `2·WT ≥ OD`,
boş segment listesi), 422.

### 6.2 `POST /api/calculations/air-content`

**İstek**

```json
{
  "geometry": {"sections": [{"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1000.0}]},
  "a_micro_per_bar": 44.971994,
  "pressure_rise_bar": 1.0,
  "k_factor": 1.02,
  "actual_added_water_m3": 0.00775
}
```

**Yanıt 200**

```json
{
  "theoretical_added_water_m3": 0.007834,
  "acceptance_limit_m3": 0.008304,
  "actual_added_water_m3": 0.00775,
  "ratio": 0.989151,
  "passed": true,
  "geometry": {"total_length_m": 1000.0, "internal_volume_m3": 118.806, "internal_radius_mm": 194.46, "elasticity_term": 19.668},
  "decision": {
    "status": "BASARILI",
    "title": "Hava Icerik Testi",
    "summary": "Vp = 0.007834 m³, limit = 0.008304 m³, Vpa = 0.007750 m³, oran = 0.989151. Kural: Vpa < 1.06 x Vp; marj = 0.000554 m³.",
    "rule": "Vpa < 1.06 x Vp",
    "margin": 0.000554
  }
}
```

**Hatalar:** 400 `domain_validation_error` (`P ≠ 1.0`, `A ≤ 0`, `K ≤ 0`, `Vpa < 0`,
teorik hacim hesaplanamıyor), 422. Tam `Vpa = 1.06·Vp` → `passed: false`.

### 6.3 `POST /api/calculations/pressure-variation`

**İstek**

```json
{
  "geometry": {"sections": [{"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1000.0}]},
  "a_micro_per_bar": 44.971994,
  "b_micro_per_c": 188.661,
  "delta_t_c": 2.0,
  "actual_pressure_change_bar": 5.95
}
```

**Yanıt 200**

```json
{
  "theoretical_pressure_change_bar": 5.838,
  "allowable_upper_pressure_change_bar": 6.138,
  "actual_pressure_change_bar": 5.95,
  "margin_bar": 0.112,
  "passed": true,
  "negative_b": false,
  "geometry": {"total_length_m": 1000.0, "internal_volume_m3": 118.806, "internal_radius_mm": 194.46, "elasticity_term": 19.668},
  "decision": {
    "status": "BASARILI",
    "title": "Basinc Degisim Testi",
    "summary": "Pt = 5.838000 bar, ust sinir = 6.138000 bar, Pa = 5.950000 bar, fark = 0.112000 bar. Kural: (Pa - Pt) <= 0.3 bar; marj = 0.112000 bar.",
    "rule": "(Pa - Pt) <= 0.3 bar",
    "margin": 0.112
  }
}
```

**Hatalar:** 400 `domain_validation_error` (`A ≤ 0`, `2·WT ≥ OD`, payda ≤ 0), 422.

### 6.4 `POST /api/calculations/pressure-profile`

**İstek**

```json
{
  "geometry": {"sections": [{"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 12000.0}]},
  "design_pressure_bar": 80.0,
  "smys_mpa": 450.0,
  "location_class": "Class 1 - min 1.25 x dizayn basinci",
  "highest_elevation_m": 320.0,
  "lowest_elevation_m": 180.0,
  "start_elevation_m": 200.0,
  "end_elevation_m": 310.0,
  "pump_location": "Baslangic noktasi",
  "monitored_pressure_bar": 112.0
}
```

**Yanıt 200**

```json
{
  "location_class": {
    "label": "Class 1 - min 1.25 x dizayn basinci",
    "class_number": 1,
    "minimum_test_factor": 1.25,
    "spec_reference": "NGTL 5007 / 4.2, ASME B31.8 Class 1"
  },
  "required_minimum_pressure_at_high_point_bar": 100.0,
  "maximum_allowable_pressure_at_low_point_bar": 193.55,
  "hydraulic_span_bar": 13.717,
  "required_pressure_with_span_bar": 113.717,
  "start_window": {
    "location_label": "Baslangic noktasi",
    "location_elevation_m": 200.0,
    "hydraulic_head_to_high_point_bar": 11.757,
    "hydraulic_head_to_low_point_bar": 1.960,
    "minimum_required_pressure_bar": 111.757,
    "maximum_allowable_pressure_bar": 191.590
  },
  "end_window": {
    "location_label": "Bitis noktasi",
    "location_elevation_m": 310.0,
    "hydraulic_head_to_high_point_bar": 0.980,
    "hydraulic_head_to_low_point_bar": 12.737,
    "minimum_required_pressure_bar": 100.980,
    "maximum_allowable_pressure_bar": 180.813
  },
  "selected_window": {
    "location_label": "Baslangic noktasi",
    "location_elevation_m": 200.0,
    "hydraulic_head_to_high_point_bar": 11.757,
    "hydraulic_head_to_low_point_bar": 1.960,
    "minimum_required_pressure_bar": 111.757,
    "maximum_allowable_pressure_bar": 191.590
  },
  "limiting_pressure_at_100_smys_bar": 193.55,
  "limiting_pipe_description": "Tek kesit | OD=406.40 mm | Et=8.74 mm",
  "total_length_m": 12000.0,
  "total_internal_volume_m3": 1425.674,
  "within_length_limit": true,
  "within_volume_limit": true,
  "within_100_smys_span_limit": true,
  "feasible": true,
  "monitored_pressure_bar": 112.0,
  "monitored_meets_minimum": true,
  "monitored_under_maximum": true,
  "decision": {
    "status": "BASARILI",
    "title": "Test Bolumu Basinc Penceresi",
    "summary": "Secili pompa noktasi icin izlenen basinc 112.000 bar; pencere 111.757 - 191.590 bar.",
    "rule": "min <= P <= max; L <= 20000 m; Vt <= 12500 m³",
    "margin": 0.0
  }
}
```

**Hatalar:** 400 `domain_validation_error` (`dizayn ≤ 0`, `SMYS ≤ 0`, `highest < lowest`,
start/end aralık dışı, pompa konumu geçersiz, monitored < 0, bilinmeyen class), 422.

### 6.5 `POST /api/calculations/pig-speed`

**İstek**

```json
{"mode": "Temizlik pigi", "distance_m": 5000.0, "travel_time_min": 45.0}
```

**Yanıt 200**

```json
{
  "distance_m": 5000.0,
  "travel_time_min": 45.0,
  "speed_m_per_s": 1.851852,
  "speed_km_per_h": 6.666667,
  "limit": {"label": "Temizlik pigi", "spec_reference": "Madde 9", "max_speed_m_per_s": 2.5, "max_speed_km_per_h": 9.0},
  "passed": true,
  "status": "UYGUN",
  "summary": "Hesaplanan pig hizi = 1.851852 m/s (6.666667 km/sa). Madde 9 icin limit asilmadi.",
  "decision": {"status": "BASARILI", "title": "Pig Hiz Hesabi", "rule": "hiz <= limit", "margin": 0.648148}
}
```

Limitsiz modda (`Serbest kontrol`) `passed: null`, `status: "BILGI"`.
**Hatalar:** 400 (`mesafe ≤ 0`, `süre ≤ 0`, geçersiz mod), 422.

### 6.6 `POST /api/calculations/pressurization`

**İstek**

```json
{"initial_volume_m3": 10.0, "added_volume_m3": 0.5, "theoretical_volume_m3": 10.48, "pressure_bar": 80.05, "expected_pressure_bar": 80.0}
```

**Yanıt 200**

```json
{
  "volume_deviation_percent": 0.191,
  "pressure_deviation_bar": 0.05,
  "within_volume_limit": true,
  "within_pressure_limit": true,
  "passed": true,
  "volume_limit_percent": 0.2,
  "pressure_tolerance_bar": 0.08,
  "underfilled": false,
  "volume_shortfall_percent": 0.0,
  "decision": {"status": "BASARILI", "title": "Basinclandirma Kontrolu", "rule": "hacim sapmasi <= %0.2 ve |dP| <= tolerans", "margin": 0.009}
}
```

**Hatalar:** 400 (`başlangıç ≤ 0`, `ilave < 0`, `teorik ≤ 0`, `P ≤ 0`, `Pbeklenen ≤ 0`), 422.

### 6.7 `POST /api/calculations/thermal-balance`

**İstek**

```json
{
  "records": [
    {"timestamp": "2026-11-14T08:00:00Z", "pressure_bar": 80.0, "temperature_c": 18.2, "volume_m3": 10.4, "notes": ""},
    {"timestamp": "2026-11-15T08:00:00Z", "pressure_bar": 80.0, "temperature_c": 18.1, "volume_m3": 10.4, "notes": ""},
    {"timestamp": "2026-11-15T12:00:00Z", "pressure_bar": 80.0, "temperature_c": 18.15, "volume_m3": 10.4, "notes": ""}
  ]
}
```

**Yanıt 200**

```json
{
  "record_count": 3,
  "duration_hours": 28.0,
  "balanced": false,
  "temp_diff_c": null,
  "reason": "Son 4 saat ile onceki 4 saat karsilastirmasi icin yeterli kayit yok.",
  "average_temperature_last_4h_c": 18.125,
  "decision": {"status": "DOGRULANAMADI", "title": "Termal Denge", "rule": "sure >= 24 h ve |dT_4h| <= 0.5 °C", "margin": null}
}
```

`temp_diff_c` domain'de `inf` dönerse JSON'da `null` + `reason` kullanılır (JSON'da
`Infinity` geçersizdir).
**Hatalar:** 422 (geçersiz timestamp/eksik alan).

### 6.8 `POST /api/calculations/water-density`

**İstek** `{"temperature_c": 15.0, "pressure_bar": 1.0}`

**Yanıt 200** `{"density_kg_per_m3": 999.1, "temperature_c": 15.0, "pressure_bar": 1.0}`

**Hatalar:** 400 `water_property_error`, 422.

---

## 7. Oturumlar

### 7.1 Oturum nesnesi

```json
{
  "id": "7c1e5a52-2f6b-4d4b-9d3a-1f0c2b3a4d5e",
  "project_id": null,
  "name": "Oturum 1",
  "status": "draft",
  "revision": 3,
  "inputs": {
    "schema_version": 1,
    "active_tab": "air",
    "water_backend": "table_v1",
    "geometry": {"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1000.0},
    "geometry_catalog": {"size_option": "", "schedule_option": ""},
    "segments": [],
    "section_profile": {
      "highest_elevation_m": null, "lowest_elevation_m": null,
      "start_elevation_m": null, "end_elevation_m": null,
      "design_pressure_bar": null, "smys_mpa": null
    },
    "material_grade": "",
    "location_class": "Class 1 - min 1.25 x dizayn basinci",
    "pump_location": "",
    "air": {
      "temperature_c": 20.0, "pressure_bar": 80.0, "a_micro_per_bar": 44.971994,
      "pressure_rise_bar": 1.0, "k_factor": 1.02, "actual_added_water_m3": 0.00775
    },
    "pressure": {
      "temperature_c": null, "pressure_bar": null, "a_micro_per_bar": null,
      "b_micro_per_c": null, "delta_t_c": null, "actual_pressure_change_bar": null
    },
    "field": {
      "ambient_temperature_c": 5.0, "pig_distance_m": null, "pig_travel_time_min": null,
      "pig_speed_m_per_s": null, "pig_speed_km_per_h": null
    },
    "helper": {"steel_alpha_micro_per_c": 12.0, "water_beta_micro_per_c": null},
    "modes": {
      "air_a_mode": "auto", "air_a_reference": "",
      "pressure_a_mode": "auto", "pressure_a_reference": "",
      "pressure_b_mode": "table", "pressure_b_reference": "BOTAŞ referans tablosu - aktif T/P",
      "pressure_b_source": "institutional", "steel_model": "volumetric",
      "k_preset": "Kaynakli boru - 1.02", "steel_preset": "Karbon celik - 12.0",
      "pig_mode": "Temizlik pigi"
    },
    "checks": {"ambient_temp": true, "temp_probes": false, "fill_air_entry": false, "fill_records": false, "thermal_balance": false, "air_content_limit": false, "pressurization_volume": false, "two_hour_hold": false, "pressure_records": false, "depressurize_discharge": false, "forms": false},
    "coefficients": {
      "air_a": {"state": "computed", "source": "auto"},
      "pressure_a": {"state": "empty", "source": "empty"},
      "pressure_b": {"state": "empty", "source": "empty"}
    },
    "report_entries": []
  },
  "wizard_state": {"active": false, "step": 0, "completed": []},
  "result_summary": {
    "air": {"status": "BASARILI", "computed_at": "2026-11-15T19:40:00Z"},
    "pressure": {"status": "BEKLIYOR", "computed_at": null},
    "checklist": {"checked": 1, "total": 11},
    "last_computed_at": "2026-11-15T19:40:00Z"
  },
  "created_at": "2026-11-15T19:35:00Z",
  "updated_at": "2026-11-15T19:40:12Z",
  "deleted_at": null
}
```

`inputs` alanları **kanonik tipli**dir (number/null/string/enum). Masaüstü snapshot'ı
string taşır; içe aktarma dönüşümü `POST /api/import/desktop-snapshot` ile yapılır ve
dönüştürülemeyen değerler `inputs.legacy.invalid_fields` altında saklanır.

### 7.2 `GET /api/sessions`

**Query:** `limit` (1–200, varsayılan 50), `offset`, `status`, `q`, `project_id`,
`include_deleted` (varsayılan `false`).

**Yanıt 200**

```json
{
  "items": [
    {"id": "7c1e…", "name": "Oturum 1", "status": "draft", "revision": 3, "updated_at": "2026-11-15T19:40:12Z", "result_summary": {"air": {"status": "BASARILI"}, "pressure": {"status": "BEKLIYOR"}}}
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**Hatalar:** 422 (limit aralığı).

### 7.3 `POST /api/sessions`

**İstek**

```json
{"name": "Oturum 1", "project_id": null, "inputs": {"geometry": {"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1000.0}}}
```

`name` yoksa `"Oturum N"`. `inputs` kısmi olabilir; eksik alanlar null/boş varsayılana
tamamlanır. `Idempotency-Key` önerilir.

**Yanıt 201** — oturum nesnesi. `Location: /api/sessions/{id}`.

**Hatalar:** 422, 429.

### 7.4 `GET /api/sessions/{id}`

**Yanıt 200** — oturum nesnesi.
**Hatalar:** 404 `not_found`, 403 `forbidden` (workspace uyuşmazlığı; auth sonrası).

### 7.5 `PUT /api/sessions/{id}`

**Başlık:** `If-Match: "3"` (zorunlu; ETag biçimi).

**İstek** (kısmi güncelleme; gönderilmeyen alan değişmez)

```json
{
  "name": "Bölüm 12-13",
  "status": "active",
  "inputs": {"air": {"actual_added_water_m3": 0.0078}},
  "wizard_state": {"active": true, "step": 1, "completed": [0]}
}
```

`inputs` **merge** edilir (derin birleştirme); `null` göndermek alanı temizler.
`revision` sunucuda artar; istemci göndermez.

**Yanıt 200** — güncel oturum.
**Hatalar:** 404, 409 `revision_conflict` (`details.current` güncel oturumu içerir), 422,
428 `precondition_required` (`If-Match` yok).

### 7.6 `DELETE /api/sessions/{id}`

**Query:** `hard=false` (varsayılan soft).
**Yanıt 204.**
**Hatalar:** 404, 409 `session_completed` (auth sonrası approver onayı yoksa).

### 7.7 `POST /api/sessions/{id}/duplicate`

**İstek** `{"name": "Bölüm 12-13 (kopya)"}`
**Yanıt 201** — yeni oturum (`status=draft`, `revision=1`).
**Hatalar:** 404, 422.

### 7.8 `GET /api/sessions/{id}/results`

**Query:** `test_type`, `limit`, `offset`.

**Yanıt 200**

```json
{
  "items": [
    {
      "id": "a1b2…",
      "test_type": "air",
      "inputs": {
        "payload": {"geometry": {"sections": [{"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1000.0}]}, "a_micro_per_bar": 44.971994, "pressure_rise_bar": 1.0, "k_factor": 1.02, "actual_added_water_m3": 0.00775},
        "session_snapshot": {"schema_version": 1, "air": {"temperature_c": 20.0, "pressure_bar": 80.0, "a_micro_per_bar": 44.971994}}
      },
      "result": {"theoretical_added_water_m3": 0.007834, "acceptance_limit_m3": 0.008304, "actual_added_water_m3": 0.00775, "ratio": 0.989151, "passed": true},
      "decision": {"status": "BASARILI", "title": "Hava Icerik Testi", "summary": "…", "rule": "Vpa < 1.06 x Vp"},
      "computed_at": "2026-11-15T19:40:00Z"
    }
  ],
  "total": 1, "limit": 50, "offset": 0
}
```

### 7.9 `POST /api/sessions/{id}/results`

Hesaplamayı **sunucuda yeniden çalıştırır**, sonucu ve kararı saklar. Böylece istemci
hesap yapmaz; kayıt ile gösterim aynı kaynaktan gelir.

**İstek**

```json
{
  "test_type": "air",
  "payload": {
    "geometry": {"sections": [{"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1000.0}]},
    "a_micro_per_bar": 44.971994,
    "pressure_rise_bar": 1.0,
    "k_factor": 1.02,
    "actual_added_water_m3": 0.00775
  }
}
```

`payload` şeması `test_type`'a göre ilgili hesap ucunun isteğiyle aynıdır:

| `test_type` | `payload` şeması |
|---|---|
| `air` | `AirContentRequest` |
| `pressure` | `PressureVariationRequest` |
| `coefficient_a` | `CoefficientARequest` |
| `coefficient_b` | `CoefficientBRequest` |
| `profile` | `PressureProfileRequest` |
| `pig` | `PigSpeedRequest` |
| `pressurization` | `PressurizationRequest` |
| `thermal_balance` | `{"records": [TimeSeriesRecordIn]}` |

Sunucu, kayıt sırasında oturumun güncel `inputs` kopyasını da
`test_results.inputs.session_snapshot` altına yazar; böylece rapor ve denetim, hesabın
yapıldığı andaki T/P, mod ve katsayı kaynağını görür. `Idempotency-Key` önerilir.

**Yanıt 201**

```json
{
  "id": "a1b2…",
  "test_type": "air",
  "result": {"theoretical_added_water_m3": 0.007834, "acceptance_limit_m3": 0.008304, "actual_added_water_m3": 0.00775, "ratio": 0.989151, "passed": true},
  "decision": {"status": "BASARILI", "title": "Hava Icerik Testi", "summary": "…", "rule": "Vpa < 1.06 x Vp"},
  "computed_at": "2026-11-15T19:40:00Z",
  "session_revision": 4
}
```

Yan etki: `sessions.result_summary` ve `updated_at` güncellenir; `audit_events` yazılır.
**Hatalar:** 400 `domain_validation_error`, 404, 409 `revision_conflict`, 422.

### 7.10 `GET /api/sessions/{id}/time-series`

**Query:** `limit` (1–1000), `offset`, `from`, `to`.

**Yanıt 200**

```json
{
  "items": [
    {"id": "ts1", "timestamp": "2026-11-15T12:00:00Z", "pressure_bar": 80.0, "temperature_c": 18.15, "volume_m3": 10.4, "notes": "Manuel kayit", "source": "manual"}
  ],
  "total": 1, "limit": 1000, "offset": 0
}
```

### 7.11 `POST /api/sessions/{id}/time-series`

**İstek**

```json
{"timestamp": "2026-11-15T12:00:00Z", "pressure_bar": 80.0, "temperature_c": 18.15, "volume_m3": 10.4, "notes": "Manuel kayit"}
```

`timestamp` yoksa sunucu UTC now kullanır.

**Yanıt 201**

```json
{
  "record": {"id": "ts1", "timestamp": "2026-11-15T12:00:00Z", "pressure_bar": 80.0, "temperature_c": 18.15, "volume_m3": 10.4, "notes": "Manuel kayit", "source": "manual"},
  "summary": {"record_count": 1, "duration_hours": 0.0, "balanced": false, "temp_diff_c": null}
}
```

**Hatalar:** 404, 422.

### 7.12 `DELETE /api/sessions/{id}/time-series/{record_id}`

**Yanıt 204.** **Hatalar:** 404.
**Yan etki:** audit kaydı.

### 7.13 `GET /api/sessions/{id}/time-series/summary`

**Yanıt 200**

```json
{
  "record_count": 26,
  "duration_hours": 26.5,
  "balanced": true,
  "temp_diff_c": 0.21,
  "average_temperature_last_4h_c": 18.12,
  "average_temperature_c": 18.4,
  "first_timestamp": "2026-11-14T06:00:00Z",
  "last_timestamp": "2026-11-15T08:30:00Z"
}
```

### 7.14 `GET /api/sessions/{id}/scene`

**Yanıt 200** — `SceneModel` (bkz. architecture.md §12). Kritik alanlar:

```json
{
  "schema_version": 1,
  "units": {"length": "m", "elevation": "m", "pressure": "bar", "diameter": "mm"},
  "extent": {"station_start_m": 0.0, "station_end_m": 12000.0, "elevation_min_m": 180.0, "elevation_max_m": 320.0, "bounding_radius_m": 6000.0},
  "profile": [
    {"station_m": 0.0, "elevation_m": 200.0},
    {"station_m": 6000.0, "elevation_m": 320.0},
    {"station_m": 12000.0, "elevation_m": 310.0}
  ],
  "segments": [
    {
      "id": "seg-1", "index": 1, "nps_label": "NPS 16 (DN 400)", "schedule_label": "Sch 20 - 8.74 mm",
      "station_start_m": 0.0, "station_end_m": 12000.0, "length_m": 12000.0,
      "elevation_start_m": 200.0, "elevation_end_m": 310.0,
      "od_mm": 406.4, "wt_mm": 8.74, "id_mm": 388.92,
      "grade": "API 5L PSL2 X65 / L450 - SMYS 450 MPa", "smys_mpa": 450.0,
      "pressure_at_100_smys_bar": 193.55, "pressure_bar": 112.0, "utilization": 0.579,
      "status": "ok"
    }
  ],
  "equipment": {
    "valves": [
      {"id": "v-1", "station_m": 0.0, "elevation_m": 200.0, "kind": "mainline", "label": "Baslangic vanasi", "state": "open"}
    ],
    "pump": {"station_m": 0.0, "elevation_m": 200.0, "side": "start", "monitored_pressure_bar": 112.0},
    "test_head": {"station_m": 1.0, "elevation_m": 200.0, "label": "Test basligi", "pressure_bar": 112.0},
    "pig": {"station_m": 5000.0, "speed_m_per_s": 1.85, "travel_time_min": 45.0, "label": "Temizlik pigi", "limit_status": "ok"}
  },
  "ranges": {"pressure_bar": {"min": 101.2, "max": 112.0}, "utilization": {"min": 0.523, "max": 0.579}},
  "layers": ["ground", "pipe", "valves", "pump", "test_head", "pig", "elevation_profile", "pressure_colors", "labels"],
  "warnings": ["Kot profili start/highest/lowest/end noktalarindan yaklasik turetildi."]
}
```

**Hatalar:** 404; 422 `incomplete_geometry` (`details.missing` alan listesi). Sahne
eksik veriyle de üretilebilir; bu durumda 200 + `warnings` döner, yalnızca geometri hiç
yoksa 422.

### 7.15 `GET /api/sessions/{id}/summary`

**Yanıt 200**

```json
{
  "session_id": "7c1e…",
  "status": "active",
  "tests": {"air": {"status": "BASARILI", "count": 2}, "pressure": {"status": "BEKLIYOR", "count": 0}},
  "checklist": {"checked": 3, "total": 11, "progress": 0.2727},
  "coefficients": {"air_a": "computed", "pressure_a": "empty", "pressure_b": "empty"},
  "profile": {"feasible": true, "window": {"min_bar": 111.757, "max_bar": 191.590}},
  "scene": {"segment_count": 1, "total_length_m": 12000.0, "volume_m3": 1425.674, "approximate_profile": true},
  "last_computed_at": "2026-11-15T19:40:00Z"
}
```

### 7.16 `GET /api/sessions/{id}/audit`

**Query:** `limit`, `offset`, `action`.

**Yanıt 200**

```json
{
  "items": [
    {"id": "ev1", "action": "result.create", "actor": "anonymous:3f2a1b9c", "entity_type": "test_result", "entity_id": "a1b2…", "request_id": "…", "created_at": "2026-11-15T19:40:00Z"}
  ],
  "total": 1, "limit": 50, "offset": 0
}
```

### 7.17 `GET /api/sessions/{id}/export`

**Query:** `format=pdf|xlsx|txt` (zorunlu), `include_raw_ocr` (varsayılan `false`),
`preview` (varsayılan `false`).

`preview=true` yalnız `format=txt` ile kullanılır ve binary yerine
`{"format":"txt","content":"…"}` döner (Raporlar sekmesi önizlemesi).

**Yanıt 200:** binary; `Content-Type` ilgili MIME; `Content-Disposition:
attachment; filename="hidrostatik_test_raporu_YYYYMMDD_HHMMSS.<ext>"`.

**Hatalar:** 404, 422 `unsupported_format`. Sonuç yoksa da 200 döner; rapor "Kaydedilecek sonuc yok." bölümüyle üretilir (masaüstü parity).

### 7.18 `GET /api/sessions/{id}/snapshot`

Masaüstü "Girdileri Kaydet" dosyasıyla **birebir uyumlu** JSON üretir (sayısal alanlar
string, modlar masaüstü etiketi). Amaç: web'de üretilen oturumun masaüstünde açılabilmesi
ve ters yön içe aktarma.

**Yanıt 200**

```json
{
  "schema_version": 1,
  "saved_at_utc": "2026-11-15T20:10:00Z",
  "app_version": "1.7.3",
  "active_tab": "pressure",
  "water_backend_option": "Table Interpolation v1",
  "geometry": {"outside_diameter_mm": "406.4", "wall_thickness_mm": "8.74", "length_m": "12000"},
  "section_profile": {"highest_elevation_m": "320", "lowest_elevation_m": "180", "start_elevation_m": "200", "end_elevation_m": "310", "design_pressure_bar": "80", "smys_mpa": "450"},
  "geometry_catalog": {"size_option": "NPS 16 (DN 400) - OD 406.40 mm", "schedule_option": "Sch 20 - 8.74 mm"},
  "material_grade": "API 5L PSL2 X65 / L450 - SMYS 450 MPa",
  "location_class": "Class 1 - min 1.25 x dizayn basinci",
  "pump_location": "Baslangic noktasi",
  "air": {"temperature_c": "20", "pressure_bar": "80", "a_micro_per_bar": "44.971994", "pressure_rise_bar": "1.0", "k_factor": "1.02", "actual_added_water_m3": "0.00775"},
  "pressure": {"temperature_c": "20", "pressure_bar": "80", "a_micro_per_bar": "44.971994", "b_micro_per_c": "188.661", "delta_t_c": "2", "actual_pressure_change_bar": "5.95"},
  "field": {"ambient_temperature_c": "5", "pig_distance_m": "5000", "pig_travel_time_min": "45", "pig_speed_m_per_s": "1.851852", "pig_speed_km_per_h": "6.666667"},
  "helper": {"steel_alpha_micro_per_c": "12.0", "water_beta_micro_per_c": ""},
  "modes": {"air_a_mode": "Otomatik", "pressure_a_mode": "Otomatik", "pressure_b_mode": "Tablo", "pressure_b_source": "Kurum ici tablo (varsayilan)", "steel_model": "Hacimsel 3*alpha (varsayilan)", "air_a_reference": "", "pressure_a_reference": "", "pressure_b_reference": "BOTAŞ referans tablosu - aktif T/P", "k_preset": "Kaynakli boru - 1.02", "steel_preset": "Karbon celik - 12.0", "pig_mode": "Temizlik pigi"},
  "checks": {"ambient_temp": true},
  "geometry_segments": [],
  "report_entries": ["[2026-11-15 19:40:00] Hava Icerik Testi\nDurum: BASARILI"]
}
```

`Content-Disposition: attachment; filename="hidrostatik_test_girdileri_YYYYMMDD_HHMMSS.json"`.

**Hatalar:** 404.

### 7.19 `POST /api/sessions/{id}/snapshot`

Masaüstü JSON'unu mevcut oturuma uygular.

**İstek**

```json
{"snapshot": {"schema_version": 1}, "mode": "merge"}
```

`mode`: `merge` (varsayılan; dolu alanları ezer, boşları korur) | `replace` (tüm inputs
değişir). `If-Match` önerilir.

**Yanıt 200** — güncel oturum + `mapping` (converted/skipped/invalid_fields/warnings).
**Hatalar:** 400 `invalid_snapshot`, 404, 409 `revision_conflict`, 422.

---

## 8. Rapor dışa aktarma (serbest)

### 8.1 `POST /api/reports/export`

Oturumdan bağımsız, verilen içerikle rapor üretir. Frontend önizlemeden indirmeye
geçerken kullanır; PDF/XLSX üretimi `report_export` servisine delege edilir.

**İstek**

```json
{
  "format": "pdf",
  "title": "Hidrostatik Test Degerlendirme Raporu",
  "metadata": {
    "Surum": "1.7.3",
    "Referans sartname": "4-NGTL 0-GN-P-002-5007 R4 - Hidrostatik Test ve Icten Denetleme Sartnamesi",
    "Olusturma zamani": "2026-11-15 22:40:00",
    "Su backend'i": "Table Interpolation v1",
    "B kaynagi": "Kurum ici A/B kontrol tablosu"
  },
  "geometry_data": {
    "Dis cap (mm)": "406.40",
    "Et kalinligi (mm)": "8.74",
    "Hat uzunlugu (m)": "12000.00",
    "Location Class": "Class 1 - min 1.25 x dizayn basinci"
  },
  "test_results": {
    "Hava Karar": "BASARILI",
    "Hava Karar Ozeti": "Vp = …",
    "Basinc Karar": "BEKLIYOR",
    "Basinc Karar Ozeti": "…"
  },
  "checklist": [
    {"checked": true, "label": "Dolum sirasinda hava sicakligi +2 °C limitine gore kontrol edildi", "ref": "10.1"}
  ]
}
```

`format`: `pdf` | `xlsx` | `txt`.
`metadata`, `geometry_data`, `test_results` anahtar-değer nesneleridir; TXT'de bölüm
metni, PDF/XLSX'te tablo olarak kullanılır.

**Yanıt 200:** binary (`application/pdf`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `text/plain; charset=utf-8`).

**Hatalar:** 422 (boş içerik, desteklenmeyen format), 500 `report_generation_failed`
(`details.reason`).

---

## 9. İçe aktarma ve istatistik

### 9.1 `POST /api/import/desktop-snapshot`

Masaüstü "Girdileri Kaydet" JSON'unu (`schema_version: 1`) içe aktarır.

**İstek**

```json
{
  "name": "Masaüstü — Bölüm 12",
  "snapshot": {
    "schema_version": 1,
    "saved_at_utc": "2026-11-15T18:00:00Z",
    "app_version": "1.7.3",
    "active_tab": "pressure",
    "water_backend_option": "Table Interpolation v1 (0-40 °C / 1-150 bar)",
    "geometry": {"outside_diameter_mm": "406.4", "wall_thickness_mm": "8.74", "length_m": "1000"},
    "section_profile": {"highest_elevation_m": "320", "lowest_elevation_m": "180", "start_elevation_m": "200", "end_elevation_m": "310", "design_pressure_bar": "80", "smys_mpa": "450"},
    "material_grade": "API 5L PSL2 X65 / L450 - SMYS 450 MPa",
    "location_class": "Class 1 - min 1.25 x dizayn basinci",
    "pump_location": "Baslangic noktasi",
    "air": {"temperature_c": "20", "pressure_bar": "80", "a_micro_per_bar": "44.971994", "pressure_rise_bar": "1.0", "k_factor": "1.02", "actual_added_water_m3": "0.00775"},
    "pressure": {"temperature_c": "20", "pressure_bar": "80", "a_micro_per_bar": "44.971994", "b_micro_per_c": "188.661", "delta_t_c": "2", "actual_pressure_change_bar": "5.95"},
    "field": {"ambient_temperature_c": "5", "pig_distance_m": "5000", "pig_travel_time_min": "45", "pig_speed_m_per_s": "", "pig_speed_km_per_h": ""},
    "helper": {"steel_alpha_micro_per_c": "12.0", "water_beta_micro_per_c": ""},
    "modes": {"air_a_mode": "Otomatik", "pressure_a_mode": "Otomatik", "pressure_b_mode": "Tablo", "pressure_b_source": "Kurum ici tablo (varsayilan)", "steel_model": "Hacimsel 3*alpha (varsayilan)", "air_a_reference": "", "pressure_a_reference": "", "pressure_b_reference": "BOTAŞ referans tablosu - aktif T/P", "k_preset": "Kaynakli boru - 1.02", "steel_preset": "Karbon celik - 12.0", "pig_mode": "Temizlik pigi"},
    "checks": {"ambient_temp": true},
    "geometry_segments": [],
    "report_entries": []
  }
}
```

**Yanıt 201**

```json
{
  "session": {"id": "…", "name": "Masaüstü — Bölüm 12", "status": "draft", "revision": 1},
  "mapping": {
    "converted": 42,
    "skipped": ["field.pig_speed_m_per_s", "field.pig_speed_km_per_h"],
    "invalid_fields": [],
    "warnings": ["Masaüstü zaman damgalari yerel kabul edildi; UTC'ye cevrildi."]
  }
}
```

**Hatalar:** 400 `invalid_snapshot` (`details.errors[]`), 422.

### 9.2 `GET /api/stats`

**Yanıt 200**

```json
{
  "total_sessions": 12,
  "total_tests": 31,
  "time_series_records": 420,
  "by_status": {"BASARILI": 18, "BASARISIZ": 2, "BEKLIYOR": 8, "DOGRULANAMADI": 3},
  "by_type": {"air": 14, "pressure": 12, "field": 5},
  "ocr": {"queued": 0, "running": 0, "succeeded": 6, "failed": 1}
}
```

---

## 10. OCR

### 10.1 `POST /api/ocr/analyze`

`multipart/form-data`:

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `file` | binary | Evet | PDF/JPG/PNG/TIFF/BMP/WEBP, ≤25 MB |
| `calculated` | string (JSON) | Hayır | Karşılaştırma payload'ı (`compare_with_calculated` şeması) |
| `session_id` | string | Hayır | Analizi oturuma bağlar |
| `mapping_profile_id` | string | Hayır | Alan eşleme profili; yoksa default |
| `language` | string | Hayır | `tur+eng` (varsayılan) |

`calculated` örneği (string olarak):

```json
{
  "pipe_od_mm": 406.4,
  "wall_mm": 8.74,
  "length_m": 12000.0,
  "test_pressure_bar": 80.0,
  "air_test": {"vp_m3": 0.007834, "vpa_m3": 0.00775, "a_micro_per_bar": 44.971994},
  "pressure_test": {"t_initial_c": 20.0, "t_final_c": 22.0, "delta_t_c": 2.0, "pa_bar": 5.95, "a_micro_per_bar": 44.971994, "b_micro_per_c": 188.661},
  "result": "PASS"
}
```

**Yanıt 202**

```json
{
  "analysis_id": "c2d3…",
  "status": "queued",
  "poll_url": "/api/ocr/analyses/c2d3…",
  "estimated_wait_s": 15
}
```

Aynı oturumda aynı SHA-256 ile daha önce yüklenmiş dosya için `200` ve
`{"analysis_id": "...", "status": "succeeded|queued", "reused": true}` döner.

**Hatalar:** 413 `file_too_large`, 415 `unsupported_format`, 422 `empty_file`,
503 `ocr_unavailable` (taranmış PDF/görsel ve OCR yok), 409 `ocr_already_running`,
429 `rate_limited`.

### 10.2 `GET /api/ocr/status`

**Yanıt 200**

```json
{
  "available": true,
  "status_text": "OCR hazir (Tesseract + Pillow).",
  "engine": {"name": "tesseract", "version": "5.3.4", "languages": ["tur", "eng"], "default_language": "tur+eng"},
  "pdf_rasterizer": {"available": false, "engine": null, "note": "Taranmis PDF icin PyMuPDF veya pdf2image + Poppler gerekir."},
  "limits": {"max_file_size_bytes": 26214400, "max_pdf_pages": 200, "max_ocr_pages": 30, "supported_extensions": [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"]},
  "queue": {"queued": 0, "running": 1, "max_concurrency": 1},
  "thresholds": {"auto_fill": 0.85, "low_confidence": 0.6, "critical_confidence": 0.4, "human_review_required": true},
  "mapping_profiles": {"default_id": null, "count": 0}
}
```

**Hatalar:** —

### 10.3 `GET /api/ocr/analyses`

**Query:** `session_id`, `status`, `limit`, `offset`.

**Yanıt 200**

```json
{
  "items": [
    {"id": "c2d3…", "status": "succeeded", "source": "pdf-text-layer", "confidence": 0.91, "page_count": 2, "created_at": "2026-11-15T20:00:00Z", "finished_at": "2026-11-15T20:00:03Z", "warnings_count": 1, "discrepancies_count": 3, "blocking_count": 1}
  ],
  "total": 1, "limit": 50, "offset": 0
}
```

### 10.4 `GET /api/ocr/analyses/{id}`

**Yanıt 200 — tamamlandı**

```json
{
  "id": "c2d3…",
  "status": "succeeded",
  "source": "pdf-text-layer",
  "page_count": 2,
  "character_count": 4210,
  "confidence": 0.91,
  "needs_human_review": true,
  "metrics": {"low_confidence_fields": 2, "critical_confidence_fields": 0},
  "report": {
    "schema_version": 1,
    "report_no": {"value": "BOT-2026-0142", "unit": "", "confidence": 0.93, "raw_text": "BOT-2026-0142", "page": 1},
    "pipe_od_mm": {"value": 406.4, "unit": "mm", "confidence": 0.95, "raw_text": "406,4 mm", "page": 1},
    "air_test": {
      "vp": {"value": 0.00768, "unit": "m³", "confidence": 0.88, "raw_text": "0,00768", "page": 2},
      "vpa": {"value": 0.00775, "unit": "m³", "confidence": 0.87, "raw_text": "0,00775", "page": 2}
    },
    "pressure_test": {
      "delta_t": {"value": 2.0, "unit": "°C", "confidence": 0.9, "raw_text": "2,0", "page": 2},
      "pa": {"value": 0.55, "unit": "bar", "confidence": 0.9, "raw_text": "0,55", "page": 2}
    },
    "result": {"value": "PASS", "unit": "", "confidence": 0.92, "raw_text": "PASS", "page": 2},
    "warnings": []
  },
  "discrepancies": [
    {
      "field": "air_test.vpa", "label": "Hava testi Vpa",
      "reported": 0.00775, "calculated": 0.00775, "unit": "m³",
      "delta": 0.0, "tolerance": "%1 veya 1 mL",
      "status": "match", "severity": "info", "message": "Deger hesaplanan degerle uyusuyor."
    },
    {
      "field": "test_pressure_bar", "label": "Test basinci",
      "reported": 80.0, "calculated": 90.0, "unit": "bar",
      "delta": -10.0, "tolerance": "±0.05 bar",
      "status": "mismatch", "severity": "critical",
      "message": "Rapor degeri hesaplanan degerden 10.000 bar dusuk."
    }
  ],
  "issues": [
    {"field": "operator", "code": "missing_required", "message": "Zorunlu alan eksik: Operator.", "severity": "critical"}
  ],
  "warnings": ["OCR kullanildi; tum alanlar insan onayindan gecmelidir."],
  "approved_fields": null,
  "error": null,
  "created_at": "2026-11-15T20:00:00Z",
  "started_at": "2026-11-15T20:00:01Z",
  "finished_at": "2026-11-15T20:00:03Z"
}
```

**Yanıt 200 — devam ediyor**

```json
{"id": "c2d3…", "status": "running", "progress": {"stage": "extracting", "elapsed_s": 12}, "error": null}
```

**Yanıt 200 — hata**

```json
{
  "id": "c2d3…", "status": "failed",
  "error": {"code": "encrypted_pdf", "message": "PDF sifreli; once sifre kaldirilmalidir.", "detail": ""}
}
```

**Hatalar:** 404 `not_found`.

### 10.5 `POST /api/ocr/analyses/{id}/cancel`

**Yanıt 202** `{"id": "c2d3…", "status": "cancelled"}`
**Hatalar:** 404; 409 `not_cancellable` (zaten bitmiş).

### 10.6 `POST /api/ocr/analyses/{id}/approve`

**İstek**

```json
{
  "fields": {
    "test_pressure_bar": {"value": 80.0, "unit": "bar", "approved": true},
    "air_test.vpa": {"value": 0.00775, "unit": "m³", "approved": true}
  },
  "approve_all": false,
  "reviewer_note": "Saha formu kontrol edildi."
}
```

Kurallar:

- Analiz `succeeded` olmalı.
- `approve_all=true` ise düşük güvenli (`< 0.6`) her alan için açık onay gerekir; aksi
  halde `422 low_confidence_unreviewed` + `details.fields`.
- Onaylanan değer `report` içindeki ham değeri **değiştirmez**; `approved_fields`'a yazılır.

**Yanıt 200**

```json
{
  "id": "c2d3…",
  "approved_count": 2,
  "pending_low_confidence": [],
  "audit_event_id": "ev9",
  "approved_at": "2026-11-15T20:05:00Z"
}
```

**Hatalar:** 404; 409 `analysis_not_succeeded`; 422 `low_confidence_unreviewed`,
`unknown_field`.

### 10.7 `POST /api/ocr/analyses/{id}/apply`

Onaylı alanları oturum girdilerine yazar.

**İstek**

```json
{"session_id": "7c1e…", "fields": ["test_pressure_bar", "air_test.vpa"], "overwrite": false}
```

**Yanıt 200**

```json
{
  "session_id": "7c1e…",
  "applied": [{"field": "test_pressure_bar", "from": 80.0, "to": 80.0}],
  "skipped": [{"field": "air_test.vpa", "reason": "already_set"}],
  "conflicts": [],
  "session_revision": 5
}
```

**Hatalar:** 404; 409 `session_revision_conflict`; 422 `field_not_approved`.

### 10.8 `GET /api/ocr/mapping-profiles`

**Yanıt 200**

```json
{
  "items": [
    {
      "id": "mp1", "name": "BOT-FRM-CDB-001-021 R2", "format_key": "bot-frm-cdb-001-021",
      "schema_version": 1, "is_default": true, "mode": "pre_extract",
      "created_at": "2026-11-16T08:00:00Z", "updated_at": "2026-11-16T08:00:00Z"
    }
  ],
  "total": 1, "limit": 50, "offset": 0
}
```

### 10.9 `POST /api/ocr/mapping-profiles`

**İstek**

```json
{
  "name": "BOT-FRM-CDB-001-021 R2",
  "format_key": "bot-frm-cdb-001-021",
  "mode": "pre_extract",
  "is_default": true,
  "mapping": {
    "schema_version": 1,
    "sections": [
      {"name": "air", "heading_aliases": ["Hava İçerik Testi", "Air Content Test"], "before": "pressure"}
    ],
    "fields": {
      "test_pressure_bar": {
        "aliases": ["Test Basıncı", "Hidrostatik Test Basıncı", "Ptest"],
        "unit": "bar",
        "required": true
      },
      "air_test.vpa": {
        "aliases": ["Fiili İlave Su", "Gerçek Hacim", "Vpa"],
        "canonical_field": "air_test.vpa",
        "unit": "m3",
        "required": false
      }
    },
    "table_hints": {"column_count": 2, "label_value_layout": "same_line"}
  }
}
```

**Yanıt 201** — profil nesnesi + `mapping`.
**Hatalar:** 409 `format_key_exists`; 422 `invalid_mapping` (`details.errors[]`:
bilinmeyen kanonik alan, geçersiz birim, boş alias listesi).

### 10.10 `GET /api/ocr/mapping-profiles/{id}`

**Yanıt 200** — profil nesnesi + tam `mapping`.
**Hatalar:** 404.

### 10.11 `PUT /api/ocr/mapping-profiles/{id}`

Kısmi güncelleme; `mapping` gönderilirse **tam değiştirilir** (merge edilmez).
**Yanıt 200.** **Hatalar:** 404, 409 (default kaldırma tek default kuralı), 422.

### 10.12 `DELETE /api/ocr/mapping-profiles/{id}`

**Yanıt 204.** Default profil silinemez → `409 default_profile`.
**Yan etki:** audit.

---

## 11. Projeler

### 11.1 `GET /api/projects`

**Yanıt 200**

```json
{"items": [{"id": "p1", "name": "Doğu Hattı 2026", "code": "PRJ-DOGU-12", "client": "BOTAŞ", "description": "", "section_count": 4, "created_at": "2026-11-01T08:00:00Z", "updated_at": "2026-11-15T19:00:00Z"}], "total": 1, "limit": 50, "offset": 0}
```

### 11.2 `POST /api/projects`

**İstek** `{"name": "Doğu Hattı 2026", "code": "PRJ-DOGU-12", "client": "BOTAŞ", "description": "12-16. bölümler"}`
**Yanıt 201** — proje nesnesi (`section_count` dahil). **Hatalar:** 422.

### 11.3 `GET/PUT/DELETE /api/projects/{id}`

- `GET` → proje + `section_count` (`sessions.project_id` üzerinden sayılır).
- `PUT` → kısmi güncelleme (`name`, `code`, `client`, `description`); 200.
- `DELETE` → soft delete; bağlı kesit oturumları silinmez, `project_id=null` olur; 204.
**Hatalar:** 404, 422.

Not: Kesit kimliği (`section_no`, `description`, `location`, `start_kp`, `end_kp`, `test_date`, `test_type`, `notes`) oturumun `inputs.section_meta` alanı içinde saklanır ve `GET /api/sessions` yanıtındaki her öğenin `section_meta` alanında da döner; oturumlar `GET /api/sessions?project_id={id}` ile projeye göre filtrelenir.

---

## 12. Pydantic şema önerileri

`webapp/backend/app/schemas/` altında; `extra="forbid"` ve `strict` alan bazında.

```python
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

B_SOURCE = Literal["institutional", "gail", "auto"]
STEEL_MODEL = Literal["volumetric", "linear", "volumetric_temperature"]
A_MODE = Literal["auto", "table", "manual"]
DECISION_STATUS = Literal[
    "BEKLIYOR", "KATSAYI GUNCELLENMELI", "DOGRULANAMADI", "BASARILI", "BASARISIZ"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PipeSectionIn(StrictModel):
    outside_diameter_mm: float = Field(gt=0, le=5000)
    wall_thickness_mm: float = Field(gt=0, le=200)
    length_m: float = Field(gt=0, le=1_000_000)
    nps_label: str | None = None
    schedule_label: str | None = None
    start_station_m: float | None = Field(default=None, ge=0)

    @field_validator("wall_thickness_mm")
    @classmethod
    def wall_less_than_radius(cls, v: float, info):
        od = info.data.get("outside_diameter_mm")
        if od is not None and v * 2 >= od:
            raise ValueError("Et kalinligi ic capi sifira dusurecek kadar buyuk olamaz.")
        return v


class GeometryIn(StrictModel):
    sections: list[PipeSectionIn] = Field(min_length=1, max_length=500)


class Decision(StrictModel):
    status: DECISION_STATUS
    title: str
    summary: str
    rule: str
    margin: float | None = None


class CoefficientARequest(StrictModel):
    temperature_c: float
    pressure_bar: float
    backend: str | None = None


class CoefficientBRequest(StrictModel):
    source: B_SOURCE = "institutional"
    temperature_c: float
    pressure_bar: float
    steel_alpha_micro_per_c: float = Field(default=12.0, gt=0)
    steel_model: STEEL_MODEL = "volumetric"


class AirContentRequest(StrictModel):
    geometry: GeometryIn
    a_micro_per_bar: float = Field(gt=0, le=200)
    pressure_rise_bar: float = Field(gt=0)
    k_factor: float = Field(gt=0, ge=1.0, le=1.1)
    actual_added_water_m3: float = Field(ge=0)

    @field_validator("pressure_rise_bar")
    @classmethod
    def exactly_one_bar(cls, v: float) -> float:
        if abs(v - 1.0) > 1e-9:
            raise ValueError("Hava icerik testi tam 1.0 bar basinc artisi ile yapilmalidir.")
        return v


class PressureVariationRequest(StrictModel):
    geometry: GeometryIn
    a_micro_per_bar: float = Field(gt=0, le=200)
    b_micro_per_c: float = Field(ge=-200, le=500)
    delta_t_c: float = Field(ge=-20, le=20)
    actual_pressure_change_bar: float = Field(ge=-50, le=50)


class PressureProfileRequest(StrictModel):
    geometry: GeometryIn
    design_pressure_bar: float = Field(gt=0)
    smys_mpa: float = Field(gt=0)
    location_class: str
    highest_elevation_m: float
    lowest_elevation_m: float
    start_elevation_m: float
    end_elevation_m: float
    pump_location: Literal["Baslangic noktasi", "Bitis noktasi"]
    monitored_pressure_bar: float | None = Field(default=None, ge=0)


class PigSpeedRequest(StrictModel):
    mode: str
    distance_m: float = Field(gt=0)
    travel_time_min: float = Field(gt=0)


class PressurizationRequest(StrictModel):
    initial_volume_m3: float = Field(gt=0)
    added_volume_m3: float = Field(ge=0)
    theoretical_volume_m3: float = Field(gt=0)
    pressure_bar: float = Field(gt=0)
    expected_pressure_bar: float = Field(gt=0)


class TimeSeriesRecordIn(StrictModel):
    timestamp: datetime | None = None
    pressure_bar: float
    temperature_c: float
    volume_m3: float | None = None
    notes: str = ""


class SessionInputs(StrictModel):
    schema_version: Literal[1] = 1
    active_tab: Literal["air", "pressure", "field"] = "air"
    water_backend: str = "table_v1"
    geometry: dict = Field(default_factory=dict)
    geometry_catalog: dict = Field(default_factory=dict)
    section_profile: dict = Field(default_factory=dict)
    material_grade: str = ""
    location_class: str = ""
    pump_location: str = ""
    segments: list[PipeSectionIn] = Field(default_factory=list)
    air: dict = Field(default_factory=dict)
    pressure: dict = Field(default_factory=dict)
    field: dict = Field(default_factory=dict)
    helper: dict = Field(default_factory=dict)
    modes: dict = Field(default_factory=dict)
    checks: dict[str, bool] = Field(default_factory=dict)
    coefficients: dict = Field(default_factory=dict)
    report_entries: list[str] = Field(default_factory=list)
    legacy: dict | None = None


class SessionCreate(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    inputs: SessionInputs | None = None


class SessionUpdate(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    status: Literal["draft", "active", "completed", "archived"] | None = None
    inputs: dict | None = None          # derin merge
    wizard_state: dict | None = None


class ResultCreate(StrictModel):
    test_type: Literal[
        "air", "pressure", "coefficient_a", "coefficient_b",
        "profile", "pig", "pressurization", "thermal_balance",
    ]
    payload: dict


class ReportExportRequest(StrictModel):
    format: Literal["pdf", "xlsx", "txt"]
    title: str = Field(min_length=1, max_length=200)
    metadata: dict[str, str] = Field(default_factory=dict)
    geometry_data: dict[str, str] = Field(default_factory=dict)
    test_results: dict[str, str] = Field(default_factory=dict)
    checklist: list[dict] = Field(default_factory=list)


class OcrApproveField(StrictModel):
    value: float | str | None
    unit: str = ""
    approved: bool = True


class OcrApproveRequest(StrictModel):
    fields: dict[str, OcrApproveField] = Field(default_factory=dict)
    approve_all: bool = False
    reviewer_note: str = Field(default="", max_length=2000)
```

Notlar:

- Domain'de `PipeSection` doğrulaması tekrar çalışır; Pydantic erken geri bildirim içindir,
  **tek doğruluk kaynağı değildir**.
- `pressure_rise_bar` kontrolü domain'de de vardır; iki katman bilinçlidir.
- `SessionInputs` alanları başlangıçta `dict` bırakılmıştır; S4'te alan bazlı modellere
  ayrıştırılır (frontend zod şemasıyla eşlenir).

---

## 13. TypeScript tipleri

`webapp/frontend/src/lib/types.ts` için öneri:

```ts
export type DecisionStatus =
  | "BEKLIYOR" | "KATSAYI GUNCELLENMELI" | "DOGRULANAMADI"
  | "BASARILI" | "BASARISIZ";

export type BSource = "institutional" | "gail" | "auto";
export type SteelModel = "volumetric" | "linear" | "volumetric_temperature";
export type AMode = "auto" | "table" | "manual";
export type CoefficientState = "empty" | "computed" | "reference" | "manual" | "stale";

export interface Decision {
  status: DecisionStatus;
  title: string;
  summary: string;
  rule: string;
  margin?: number | null;
}

export interface PipeSectionIn {
  outside_diameter_mm: number;
  wall_thickness_mm: number;
  length_m: number;
  nps_label?: string | null;
  schedule_label?: string | null;
  start_station_m?: number | null;
}

export interface GeometryIn { sections: PipeSectionIn[] }

export interface BackendInfo {
  key: string;
  label: string;
  distribution_ready: boolean;
  note?: string;
}

export interface CoefficientAResponse {
  a_micro_per_bar: number;
  temperature_c: number;
  pressure_bar: number;
  backend: BackendInfo;
  state: CoefficientState;
}

export interface BSourceResult {
  b_micro_per_c: number;
  source: BSource;
  label: string;
  note: string;
  repaired_table: boolean;
  water_beta_micro_per_c: number | null;
  steel_alpha_micro_per_c: number | null;
  steel_model: string;
}

export interface BComparisonResponse {
  temperature_c: number;
  pressure_bar: number;
  institutional: BSourceResult;
  gail: BSourceResult;
  auto: BSourceResult;
  deltas: {
    institutional_vs_gail: number;
    auto_vs_institutional: number;
    auto_vs_gail: number;
  };
}

export interface AirContentResponse {
  theoretical_added_water_m3: number;
  acceptance_limit_m3: number;
  actual_added_water_m3: number;
  ratio: number;
  passed: boolean;
  geometry: GeometrySummary;
  decision: Decision;
}

export interface PressureVariationResponse {
  theoretical_pressure_change_bar: number;
  allowable_upper_pressure_change_bar: number;
  actual_pressure_change_bar: number;
  margin_bar: number;
  passed: boolean;
  negative_b: boolean;
  geometry: GeometrySummary;
  decision: Decision;
}

export interface GeometrySummary {
  total_length_m: number;
  internal_volume_m3: number;
  internal_radius_mm: number;
  elasticity_term: number;
}

export interface PressureWindow {
  location_label: "Baslangic noktasi" | "Bitis noktasi";
  location_elevation_m: number;
  hydraulic_head_to_high_point_bar: number;
  hydraulic_head_to_low_point_bar: number;
  minimum_required_pressure_bar: number;
  maximum_allowable_pressure_bar: number;
}

export interface PressureProfileResponse {
  location_class: { label: string; class_number: number; minimum_test_factor: number; spec_reference: string };
  required_minimum_pressure_at_high_point_bar: number;
  maximum_allowable_pressure_at_low_point_bar: number;
  hydraulic_span_bar: number;
  required_pressure_with_span_bar: number;
  start_window: PressureWindow;
  end_window: PressureWindow;
  selected_window: PressureWindow;
  limiting_pressure_at_100_smys_bar: number;
  limiting_pipe_description: string;
  total_length_m: number;
  total_internal_volume_m3: number;
  within_length_limit: boolean;
  within_volume_limit: boolean;
  within_100_smys_span_limit: boolean;
  feasible: boolean;
  monitored_pressure_bar: number | null;
  monitored_meets_minimum: boolean | null;
  monitored_under_maximum: boolean | null;
  decision: Decision;
}

export interface PigSpeedResponse {
  distance_m: number;
  travel_time_min: number;
  speed_m_per_s: number;
  speed_km_per_h: number;
  limit: { label: string; spec_reference: string; max_speed_m_per_s: number | null; max_speed_km_per_h: number | null };
  passed: boolean | null;
  status: "UYGUN" | "LIMIT ASILDI" | "BILGI";
  summary: string;
  decision: Decision;
}

export interface SceneSegment {
  id: string;
  index: number;
  nps_label: string | null;
  schedule_label: string | null;
  station_start_m: number;
  station_end_m: number;
  length_m: number;
  elevation_start_m: number;
  elevation_end_m: number;
  od_mm: number;
  wt_mm: number;
  id_mm: number;
  grade: string | null;
  smys_mpa: number | null;
  pressure_at_100_smys_bar: number | null;
  pressure_bar: number | null;
  utilization: number | null;
  status: "ok" | "warning" | "critical" | "unknown";
}

export interface SceneModel {
  schema_version: 1;
  units: { length: "m"; elevation: "m"; pressure: "bar"; diameter: "mm" };
  extent: { station_start_m: number; station_end_m: number; elevation_min_m: number; elevation_max_m: number; bounding_radius_m: number };
  profile: Array<{ station_m: number; elevation_m: number }>;
  segments: SceneSegment[];
  equipment: {
    valves: Array<{ id: string; station_m: number; elevation_m: number; kind: string; label: string; state: "open" | "closed" | "unknown" }>;
    pump: { station_m: number; elevation_m: number; side: "start" | "end"; monitored_pressure_bar: number | null };
    test_head: { station_m: number; elevation_m: number; label: string; pressure_bar: number | null };
    pig: { station_m: number; speed_m_per_s: number | null; travel_time_min: number | null; label: string; limit_status: "ok" | "exceeded" | "info" | "unknown" };
  };
  ranges: { pressure_bar: { min: number; max: number }; utilization: { min: number; max: number } };
  layers: string[];
  warnings: string[];
}

export interface Session {
  id: string;
  project_id: string | null;
  name: string;
  status: "draft" | "active" | "completed" | "archived";
  revision: number;
  inputs: Record<string, unknown>;
  wizard_state: Record<string, unknown> | null;
  result_summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface OcrDiscrepancy {
  field: string;
  label: string;
  reported: number | string | null;
  calculated: number | string | null;
  unit: string;
  delta: number | null;
  tolerance: string;
  status: "match" | "within_tolerance" | "mismatch" | "missing_in_report" | "missing_in_calculation" | "not_comparable";
  severity: "info" | "warning" | "critical";
  message: string;
}

export interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string;
}
```

> Uygulama sırasında tek kaynak OpenAPI şeması olacaktır; bu blok onun önerisidir.

---

## 14. Hata kodu kataloğu

| Kod | HTTP | Anlam | `details` |
|---|---|---|---|
| `validation_error` | 422 | Pydantic doğrulama | `errors[]` |
| `domain_validation_error` | 400 | Domain fizik/geometri kuralı | `field`, `rule` |
| `water_property_error` | 400 | T/P aralığı, backend yok | `backend`, `temperature_c`, `pressure_bar` |
| `reference_table_error` | 400 | Tablo aralığı dışı | `table`, `range` |
| `invalid_calculated` | 400 | OCR karşılaştırma payload'ı | `field` |
| `invalid_snapshot` | 400 | Masaüstü JSON bozuk | `errors[]` |
| `unauthorized` | 401 | Auth yok/geçersiz | — |
| `forbidden` | 403 | Workspace/rol uyuşmazlığı | `required_role` |
| `not_found` | 404 | Kaynak yok | `resource`, `id` |
| `file_not_found` | 404 | OCR dosyası yok | `filename` |
| `invalid_path` | 400 | Geçersiz/izin verilmeyen yol | `reason` |
| `revision_conflict` | 409 | `If-Match` uyuşmuyor | `current` |
| `precondition_required` | 428 | `If-Match` yok | — |
| `ocr_already_running` | 409 | Aynı dosya işleniyor | `analysis_id` |
| `not_cancellable` | 409 | İş bitmiş | `status` |
| `analysis_not_succeeded` | 409 | Onay/uygulama erken | `status` |
| `low_confidence_unreviewed` | 422 | Düşük güven onaylanmadı | `fields[]` |
| `unknown_field` | 422 | Onayda bilinmeyen alan | `fields[]` |
| `field_not_approved` | 422 | Uygulanacak alan onaysız | `fields[]` |
| `format_key_exists` | 409 | Profil anahtarı var | `format_key` |
| `invalid_mapping` | 422 | Eşleme şeması bozuk | `errors[]` |
| `default_profile` | 409 | Default profil silinemez | `id` |
| `unsupported_format` | 422/415 | Format yok | `format`, `supported[]` |
| `file_too_large` | 413 | > 25 MB | `max_bytes` |
| `empty_file` | 422 | 0 bayt | — |
| `empty_text` | 422 | Metin çıkmadı | `source` |
| `encrypted_pdf` | 422 | Şifreli PDF | — |
| `corrupt_document` | 422 | PDF bozuk | `detail` |
| `corrupt_image` | 422 | Görsel bozuk | `detail` |
| `ocr_unavailable` | 503 | Tesseract/Pillow yok | `status_text` |
| `dependency_missing` | 503 | Genel bağımlılık | `dependency` |
| `ocr_timeout` | 504 | 300 s aşıldı | `analysis_id` |
| `rate_limited` | 429 | Limit | `retry_after_s` |
| `report_generation_failed` | 500 | Export hatası | `reason` |
| `internal_error` | 500 | Beklenmeyen | — |

---

## 15. Sürümleme ve uyumluluk

- Yol tabanlı sürüm: `/api` = v1. Kırıcı değişiklikte `/api/v2`; v1 en az 6 ay yaşar.
- JSON içinde `schema_version` taşıyan nesneler (`SessionInputs`, `HydrotestReport`,
  `SceneModel`, `mapping`) kendi sürümlerini taşır.
- Kaldırılacak alanlar önce `Deprecation: true` + `Sunset` başlığıyla duyurulur.
- OpenAPI şeması CI'da üretilir ve `webapp/docs/openapi.json` olarak commit edilir;
  frontend tipleri bu şemadan doğrulanır (`openapi-typescript` önerilir).
- Alan adları `snake_case`; frontend'de dönüşüm yapılmaz (kopya anahtar üretmemek için).
