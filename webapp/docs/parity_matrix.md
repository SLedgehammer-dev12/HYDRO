# HYDRO Web — Parity Matrisi

**Amaç:** Tkinter masaüstü uygulamasındaki her girdi, hesap, sonuç, oturum ve rapor
davranışının web karşılığını izlemek.
**Kaynak:** `hidrostatik_test/ui/app.py` (v1.7.3), `hidrostatik_test/domain/*`,
`hidrostatik_test/data/*`, `hidrostatik_test/services/*`, `docs/spec/ab_methods_and_units.md`,
`docs/ocr_report_pipeline.md`, `docs/ui_ergonomics.md`.

## Durum sütunları

| Sütun | Anlam |
|---|---|
| `desktop` | Masaüstünde mevcut mu ve kaynağı |
| `web-planned` | Hangi teslim diliminde (S0–S6) planlandı |
| `web-implemented` | Uygulandı mı; **başlangıçta tümü `—`** |

İşaretler: `✅` var, `◐` kısmi, `—` yok. Dilim tanımları `architecture.md` §17.

> **Anahtar kuralı:** Tablolardaki `field key` değerleri **API `inputs` anahtarlarıdır**.
> Masaüstü `field_meta` anahtarları bazı alanlarda `geometry.*` öneki taşır; eşleme:
> `geometry.material_grade` → `material_grade`, `geometry.location_class` →
> `location_class`, `geometry.pump_location` → `pump_location`,
> `geometry.highest_elevation_m` … `geometry.design_pressure_bar` →
> `section_profile.*`, `geometry.size_option`/`schedule_option` → `geometry_catalog.*`.
> Değerler ve doğrulamalar aynıdır; yalnızca adlandırma hizalanmıştır.
> Mod alanlarında tabloda masaüstü etiketi, API'de enum anahtarı kullanılır:
> `Otomatik`↔`auto`, `Tablo`↔`table`, `Manuel`↔`manual`; B kaynağı
> `Kurum ici tablo`↔`institutional`, `GAIL`↔`gail`, `Otomatik`↔`auto`.

> **Kural:** `web-implemented` ancak parity fixture'ı ve API testi yeşile döndüğünde
> güncellenir. Kod yazıldı diye değil, test geçti diye.

---

## 1. Genel / ayarlar

| # | Alan anahtarı | Masaüstü etiketi | Birim | Varsayılan | Zorunlu | Doğrulama | Sekme / API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.1 | `water_backend` | Su Özelliği Backend'i | — | `table_v1` (CoolProp kuruluysa `coolprop`) | Hayır | `get_available_water_property_backends()` listesinde olmalı | Ayarlar / `POST /api/coefficients/a` içinde `backend` | ✅ menü `Hesap > Su Ozelligi Backend'i` | S1 | — |
| 1.2 | `dev_mode` | Geliştirici Modu (Dev Backends) | — | `false` | Hayır | Yalnızca `include_dev_backends=true` | Ayarlar / `/api/meta` `features.dev_backends` | ✅ `dev_mode_var` | S1 | — |
| 1.3 | `locale.number_format` | (örtük) | — | `tr-TR` | — | Ondalık virgül/nokta, binlik ayırıcı | Tüm formlar | ✅ `ui/validators.py` | S0 | — |
| 1.4 | `active_tab` | Aktif sekme | — | `air` | — | `air` \| `pressure` \| `field` | Oturum `/api/sessions` `inputs.active_tab` | ✅ `_active_tab_key()` | S4 | — |

**Backend seçenekleri:** `table_v1` (Table Interpolation v1, 0–40 °C / 1–150 bar,
bilinear), `table_v1_bicubic` (scipy varsa), `coolprop` (CoolProp EOS), `iapws95_dev`
(GPL, yalnız dev modu).

---

## 2. Geometri

Kaynak: `app.py:1514-1822`, `geometry_vars`, `section_profile_vars`, `geometry_catalog_vars`.

| # | Alan anahtarı | Masaüstü etiketi | Birim | Varsayılan | Zorunlu | Doğrulama | Sekme / API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|---|---|
| 2.1 | `geometry_catalog.size_option` | ASME B36.10 NPS | — | boş | Hayır | `get_pipe_size_options()` içinde | Geometri / `GET /api/catalog/pipes` | ✅ combo | S3 | — |
| 2.2 | `geometry_catalog.schedule_option` | Schedule / Et kalinligi | — | boş | Hayır | Seçili NPS'in `get_schedule_options()` listesinde | Geometri / `GET /api/catalog/pipes/{nps}/schedules` | ✅ combo | S3 | — |
| 2.3 | `geometry.outside_diameter_mm` | Dis cap (mm) | mm | boş | **Evet** | Sonlu, `1.0 ≤ x ≤ 5000.0`, `> 0` | Hava, Basınç, Profil / tüm hesaplamalar | ✅ `FIELD_VALUE_RANGES` | S2 | — |
| 2.4 | `geometry.wall_thickness_mm` | Et kalinligi (mm) | mm | boş | **Evet** | Sonlu, `0.1 ≤ x ≤ 200.0`, `2·wt < OD` | Hava, Basınç, Profil | ✅ | S2 | — |
| 2.5 | `geometry.length_m` | Hat uzunlugu (m) | m | boş | **Evet** | Sonlu, `0.1 ≤ x ≤ 1 000 000`, `> 0` | Hava, Basınç, Profil | ✅ | S2 | — |
| 2.6 | `material_grade` | Boru malzeme kalitesi | — | boş | Profil için **Evet** | `get_api_5l_psl2_grade_options()` içinde | Profil / `GET /api/catalog/grades` | ✅ combo | S3 | — |
| 2.7 | `section_profile.smys_mpa` | SMYS (MPa) | MPa | boş (kaliteden türetilir) | Profil için **Evet** | Sonlu, `> 0`; kalite seçilince readonly dolar | Profil | ✅ readonly | S3 | — |
| 2.8 | `location_class` | Location Class | — | `Class 1 - min 1.25 x dizayn basinci` | Profil için **Evet** | `get_location_class_rule(label)`; 4 seçenek | Profil / `GET /api/meta` | ✅ combo | S3 | — |
| 2.9 | `pump_location` | Pompa konumu | — | boş | Profil için **Evet** | `Baslangic noktasi` \| `Bitis noktasi` | Profil | ✅ combo | S3 | — |
| 2.10 | `section_profile.highest_elevation_m` | En yuksek nokta kotu (m) | m | boş | Profil için **Evet** | Sonlu | Profil | ✅ | S3 | — |
| 2.11 | `section_profile.lowest_elevation_m` | En dusuk nokta kotu (m) | m | boş | Profil için **Evet** | Sonlu, `≤ highest` | Profil | ✅ | S3 | — |
| 2.12 | `section_profile.start_elevation_m` | Baslangic noktasi kotu (m) | m | boş | Profil için **Evet** | `lowest ≤ x ≤ highest` | Profil | ✅ | S3 | — |
| 2.13 | `section_profile.end_elevation_m` | Bitis noktasi kotu (m) | m | boş | Profil için **Evet** | `lowest ≤ x ≤ highest` | Profil | ✅ | S3 | — |
| 2.14 | `section_profile.design_pressure_bar` | Dizayn basinci (bar) | bar | boş | Profil için **Evet** | Sonlu, `> 0` | Profil | ✅ | S3 | — |
| 2.15 | `segments[]` | Segment listesi | — | `[]` (tek kesit modu) | Hayır | Her satır `PipeSection` kurallarına uyar | Geometri / `PUT /api/sessions/{id}` (`inputs.segments`) | ✅ Treeview + ekle/sil/temizle | S3 | — |
| 2.15.1 | `segments[].outside_diameter_mm` | OD (mm) | mm | — | Satır varsa **Evet** | `> 0`, `2·wt < OD` | Geometri | ✅ | S3 | — |
| 2.15.2 | `segments[].wall_thickness_mm` | Et (mm) | mm | — | Satır varsa **Evet** | `> 0` | Geometri | ✅ | S3 | — |
| 2.15.3 | `segments[].length_m` | Uzunluk (m) | m | — | Satır varsa **Evet** | `> 0` | Geometri | ✅ | S3 | — |
| 2.15.4 | `segments[].nps_label` | NPS / DN | — | `-` | Hayır | Metin | Geometri | ✅ | S3 | — |
| 2.15.5 | `segments[].schedule_label` | Schedule | — | `Elle giris` | Hayır | Metin | Geometri | ✅ | S3 | — |
| 2.16 | `segments[].start_station_m` | — | m | türetilir | — | **Yeni (web-only)**; boşsa zincirleme | 3D / `GET /api/sessions/{id}/scene` | — | S3 (parity+) | — |
| 2.17 | `profile_points[]` | — | m | türetilir (4 nokta) | Hayır | **Yeni (web-only)**; `station_m` artan, `elevation_m` sonlu | 3D | — | S3 (parity+) | — |
| 2.18 | `equipment[]` | — | — | türetilir | Hayır | **Yeni (web-only)**; `{station_m, kind, label, state}` | 3D | — | S3 (parity+) | — |

**Alan bazlı anlamsal geri bildirim** (masaüstü `_semantic_field_feedback`; web'de aynı
kurallar istemci + sunucuda uygulanır):

| Kural | Alan(lar) | Seviye |
|---|---|---|
| `FIELD_VALUE_RANGES` dışı | A, B, K, dT, Pa, OD, WT, L | error |
| `2·WT ≥ OD` | OD / WT (karşılıklı) | error |
| `L > 20 000 m` | `geometry.length_m` | warning |
| `highest < lowest` | kot alanları | error |
| `start/end` min–max dışında | kot alanları | error |
| `dizayn ≤ 0`, `SMYS ≤ 0` | profil | error |
| `P ≠ 1.0` | `air.pressure_rise_bar` | warning |
| `K ≤ 0` | `air.k_factor` | error |
| `Vpa < 0` | `air.actual_added_water_m3` | error |
| T < −5 veya > 60 °C | hava/basınç su sıcaklığı | warning |
| Ortam T < +2 °C | `field.ambient_temperature_c` | error (10.1; buton kapısı değil) |
| 0 ≤ T < 4 °C | `pressure.temperature_c` | info (negatif B geçerli) |
| Su basıncı ≤ 0 | hava/basınç | error |
| `Pa < 0` | `pressure.actual_pressure_change_bar` | warning (işaret kontrolü) |
| `alpha ≤ 0` | `helper.steel_alpha_micro_per_c` | error |
| Mesafe/süre ≤ 0 | pig | error |
| Profil alanı dolu, kalite boş | `material_grade` | warning |
| Profil alanı dolu, pompa boş | `pump_location` | warning |
| Tablo modu, referans boş | A/B referans | warning |

**Segment davranışı:** Segment listesi doluysa `PipeGeometry` kullanılır ve üstteki tek
kesit alanları yok sayılır. Boşsa `PipeSection` kullanılır. Bu kural domain'de değil,
`app.py:_build_pipe_section` içindedir; web servisinde aynı öncelik uygulanır ve parity
testiyle sabitlenir.

---

## 3. Katsayı modları ve referans tabloları

Kaynak: `app.py:1824-2165`, `domain/coefficient_sources.py`,
`domain/coefficient_manager.py`, `data/ab_control_table.py`, `botas_reference_table.py`,
`gail_reference_table.py`.

| # | Alan anahtarı | Masaüstü etiketi | Birim | Varsayılan | Zorunlu | Doğrulama | Sekme / API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|---|---|
| 3.1 | `modes.air_a_mode` | A secenegi (hava) | — | `Otomatik` | **Evet** | `Otomatik` \| `Tablo` \| `Manuel` | Hava | ✅ | S2 | — |
| 3.2 | `modes.air_a_reference` | A referans tablosu | — | boş | Yalnız `Tablo` modunda | `BOTAŞ referans tablosu - aktif T/P` \| `GAIL referans tablosu - aktif T/P` | Hava | ✅ combo | S2 | — |
| 3.3 | `modes.pressure_a_mode` | A secenegi (basınç) | — | `Otomatik` | **Evet** | Aynı 3 seçenek | Basınç | ✅ | S2 | — |
| 3.4 | `modes.pressure_a_reference` | A referans tablosu (micro/bar) | — | boş | Yalnız `Tablo` modunda | BOTAŞ \| GAIL | Basınç | ✅ | S2 | — |
| 3.5 | `modes.pressure_b_mode` | B secenegi | — | `Tablo` | **Evet** | `Otomatik` \| `Tablo` \| `Manuel` | Basınç | ✅ | S2 | — |
| 3.6 | `modes.pressure_b_source` | B kaynagi | — | `Kurum ici tablo (varsayilan)` | **Evet** | `institutional` \| `gail` \| `auto` | Basınç / `POST /api/coefficients/b` `source` | ✅ | S2 | — |
| 3.7 | `modes.pressure_b_reference` | B referans tablosu (micro/K) | — | `BOTAŞ referans tablosu - aktif T/P` | Yalnız `Tablo` modunda | BOTAŞ \| GAIL | Basınç | ✅ | S2 | — |
| 3.8 | `modes.steel_model` | Celik modeli (otomatik B) | — | `Hacimsel 3*alpha (varsayilan)` | `auto` kaynağında **Evet** | `volumetric` \| `linear` \| `volumetric_temperature` | Basınç / `steel_model` | ✅ combo (auto'da aktif) | S2 | — |
| 3.9 | `modes.steel_preset` | Celik preset | — | `Karbon celik - 12.0` | Hayır | `Karbon 12.0` \| `Dusuk alasimli 12.5` \| `Paslanmaz 16.0` \| `Ozel` | Basınç | ✅ | S2 | — |
| 3.10 | `modes.k_preset` | K faktor preset | — | `Kaynakli boru - 1.02` | Hayır | `Kaynakli 1.02` \| `Dikissiz 1.00` \| `Ozel` | Hava | ✅ | S2 | — |
| 3.11 | `helper.steel_alpha_micro_per_c` | Celik alpha (micro/K = 10^-6/°C) | 10⁻⁶/°C | `12.0` | `auto` kaynağında **Evet** | Sonlu, `> 0` (masaüstü UI) | Basınç | ✅ | S2 | — |
| 3.12 | `helper.water_beta_micro_per_c` | Su beta hacimsel (micro/K) | 10⁻⁶/°C | boş (auto'da dolar) | Hayır | Sonlu; readonly | Basınç | ✅ readonly | S2 | — |
| 3.13 | `helper.visible` | (B helper paneli) | — | `false` | Hayır | UI görünürlüğü | Basınç / Ayarlar | ✅ `use_b_helper_var` | S2 | — |

**Mod semantiği (masaüstü):**

- `Otomatik` A/B → backend hesabı; `CoefficientState.COMPUTED`.
- `Tablo` → seçili referans tablosundan A/B; `CoefficientState.REFERENCE`.
- `Manuel` → kullanıcı değeri; `CoefficientState.MANUAL`; aralık kontrolü.
- Girdi değişince otomatik/tablo kaynaklı katsayı `STALE` olur; karar şeridi
  `KATSAYI GUNCELLENMELI` gösterir. Web'de bu durum sunucuda `coefficients.state` ile
  taşınır (`empty|computed|reference|manual|stale`).
- Varsayılan B kaynağı **kurum içi A/B kontrol tablosudur**; tablo B'si ham workbook
  değeridir, `beta - 3·alpha` ile yeniden kurulmaz.
- Mod değiştirilirse eski katsayı değeri temizlenir ve yeni modun değeri yeniden
  üretilmelidir (masaüstü davranışı; parity testiyle sabitlenir).

**Referans tablo aralıkları:**

| Tablo | Sıcaklık | Basınç | Not |
|---|---|---|---|
| Kurum içi / BOTAŞ (`ab_control_table_v1`) | 1–25 °C, adım 1 | 30–120 bar, adım 1 | 2 275 satır; 7 °C / 81–100 bar A anomalisi çalışma zamanında onarılır |
| GAIL (`gail_reference_table_v1`) | 2–30 °C, adım 2 | 30–120 bar, adım 10 | 150 satır; B metin, A grafik dijitalizasyonu |

---

## 4. Hava içerik testi

Kaynak: `app.py:1824-1944`, `domain/hydrotest_core.py:234-302`.

| # | Alan anahtarı | Masaüstü etiketi | Birim | Varsayılan | Zorunlu | Doğrulama | Sekme / API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|---|---|
| 4.1 | `air.temperature_c` | Su sicakligi (°C) | °C | boş | A otomatik/tablo için **Evet** | `> -273.15`; backend aralığında | Hava / `POST /api/coefficients/a` | ✅ | S2 | — |
| 4.2 | `air.pressure_bar` | Su basinci (bar) | bar | boş | A otomatik/tablo için **Evet** | `> 0`; backend aralığında | Hava | ✅ | S2 | — |
| 4.3 | `air.a_micro_per_bar` | A (micro/bar = 10^-6/bar) | 10⁻⁶/bar | boş (otomatik dolar) | Test kapısı **Evet**; yalnız `Manuel` modda kullanıcı girer | `1.0 ≤ x ≤ 200.0`; otomatik/tabloda readonly | Hava / `POST /api/calculations/air-content` | ✅ readonly (manuelde düzenlenebilir) | S2 | — |
| 4.4 | `air.pressure_rise_bar` | Basinc artisi P (bar, sartname: 1.0) | bar | `1.0` | **Evet** | Tam `1.0 ± 1e-9`; aksi halde domain reddeder | Hava | ✅ | S2 | — |
| 4.5 | `air.k_factor` | K faktor | — | `1.02` (kaynaklı boru) | **Evet** | `1.0 ≤ x ≤ 1.1`; `> 0` | Hava | ✅ | S2 | — |
| 4.6 | `air.actual_added_water_m3` | Fiili ilave su Vpa (m³) | m³ | boş | **Evet** | Sonlu, `≥ 0` | Hava | ✅ | S2 | — |
| 4.7 | `field.ambient_temperature_c` | Ortam hava sicakligi (10.1) [°C] | °C | boş | Hayır | Sonlu; `< +2 °C` error (10.1), buton kapısı değil | Hava / Saha | ✅ (`air` panelinde) | S2 | — |

**Hesap:** `Vp = ((0.884·ri/s) + A) · 1e-6 · Vt · K`; `Vt` = iç hacim (segmentliyse toplam);
kabul `Vpa < 1.06·Vp` (tam sınır **FAIL**); `ratio = Vpa / Vp`.

---

## 5. Basınç değişim testi

Kaynak: `app.py:1945-2165`, `domain/hydrotest_core.py:305-352`.

| # | Alan anahtarı | Masaüstü etiketi | Birim | Varsayılan | Zorunlu | Doğrulama | Sekme / API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|---|---|
| 5.1 | `pressure.temperature_c` | Su sicakligi (°C) | °C | boş | A/B hazırlamak için **Evet** | `> -273.15`; backend aralığında | Basınç | ✅ | S2 | — |
| 5.2 | `pressure.pressure_bar` | Su basinci (bar) | bar | boş | A/B hazırlamak için **Evet** | `> 0` | Basınç | ✅ | S2 | — |
| 5.3 | `pressure.a_micro_per_bar` | A (micro/bar = 10^-6/bar) | 10⁻⁶/bar | boş | Test kapısı **Evet**; yalnız `Manuel` modda kullanıcı girer | `1.0 ≤ x ≤ 200.0`; otomatik/tabloda readonly | Basınç | ✅ (manuelde düzenlenebilir) | S2 | — |
| 5.4 | `pressure.b_micro_per_c` | B (micro/K = 10^-6/°C) | 10⁻⁶/°C | boş | **Evet** | `-200.0 ≤ x ≤ 500.0`; negatif B geçerli | Basınç | ✅ | S2 | — |
| 5.5 | `pressure.delta_t_c` | Su sicaklik degisimi dT = Tilk - Tson (°C) | °C | boş | **Evet** | `-20.0 ≤ x ≤ 20.0` | Basınç | ✅ | S2 | — |
| 5.6 | `pressure.actual_pressure_change_bar` | Fiili basinc degisimi Pa = Pilk - Pson (bar) | bar | boş | **Evet** | `-50.0 ≤ x ≤ 50.0` | Basınç | ✅ | S2 | — |

**Hesap:** `Pt = (B · dT) / (0.884·ri/s + A)`; `Pa` gözlenen; `marj = Pa − Pt`;
kabul `marj ≤ 0.3 bar` (`1e-9` tolerans). `B < 0` ise dP işareti döner ve bu geçerlidir.
A/B `PipeGeometry.elasticity_term` hacim-ağırlıklı ortalamadır.

**İşaret sözleşmesi:** `dT = Tilk − Tson`, `Pa = Pilk − Pson`. UI'da alan altında
sabit açıklama gösterilir; web'de de aynı metin korunur.

---

## 6. Saha kontrol ve pig

Kaynak: `app.py:2167-2246`, `ui/constants.py:FIELD_CHECK_DEFINITIONS`,
`domain/operations.py`, `domain/time_series.py`.

### 6.1 Operasyonel kontrol noktaları (boolean)

| # | Alan anahtarı | Etiket | Referans | Varsayılan | Sekme / API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|
| 6.1.1 | `checks.ambient_temp` | Dolum sirasinda hava sicakligi +2 °C limitine gore kontrol edildi | 10.1 | `false` | Saha / `POST /api/sessions/{id}/results` | ✅ | S4 | — |
| 6.1.2 | `checks.temp_probes` | Boru ve toprak sicaklik problari uygun yerlere yerlestirildi | 10.4 | `false` | Saha | ✅ | S4 | — |
| 6.1.3 | `checks.fill_air_entry` | Su dolumu sirasinda sisteme hava girmesi engellendi | 11.2 | `false` | Saha | ✅ | S4 | — |
| 6.1.4 | `checks.fill_records` | Doldurulan su hacmi ve sicakligi saatlik olarak kaydedildi | 11.3-11.4 | `false` | Saha | ✅ | S4 | — |
| 6.1.5 | `checks.thermal_balance` | Minimum 24 saat termal dengeleme ve 0.5 °C kosulu kontrol edildi | 12 | `false` | Saha | ✅ | S4 | — |
| 6.1.6 | `checks.air_content_limit` | Hava icerik testi %6 kabul sinirina gore teyit edildi | 13 | `false` | Saha | ✅ | S4 | — |
| 6.1.7 | `checks.pressurization_volume` | 14.2 icin basinc-hacim ve %0.2 ilave su limiti izlendi | 14.2 | `false` | Saha | ✅ | S4 | — |
| 6.1.8 | `checks.two_hour_hold` | 14.3 icin 2 saat bekleme ve 15 dakikalik okumalar alindi | 14.3 | `false` | Saha | ✅ | S4 | — |
| 6.1.9 | `checks.pressure_records` | 24 saatlik basinc ve sicaklik kayitlari duzenli tutuldu | 15.1 | `false` | Saha | ✅ | S4 | — |
| 6.1.10 | `checks.depressurize_discharge` | Basinc dusurme ve bosaltma islemleri kontrollu ve raporlu yapildi | 16-17 | `false` | Saha | ✅ | S4 | — |
| 6.1.11 | `checks.forms` | 21.1-21.5 saha formlari dolduruldu | 21 | `false` | Saha | ✅ | S4 | — |

Türetilen: `check_summary` ("n/11 tamam"), `check_progress` (0–11), checklist satırları
raporda `[X]`/`[ ]` olarak.

### 6.2 Pig hızı

| # | Alan anahtarı | Masaüstü etiketi | Birim | Varsayılan | Zorunlu | Doğrulama | Sekme / API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|---|---|
| 6.2.1 | `field.pig_mode` | Pig modu | — | `Temizlik pigi` | **Evet** | 4 seçenek (`get_pig_speed_limit_options()`) | Saha / `POST /api/calculations/pig-speed` | ✅ | S4 | — |
| 6.2.2 | `field.pig_distance_m` | Pig mesafesi (m) | m | boş | **Evet** | Sonlu, `> 0` | Saha | ✅ | S4 | — |
| 6.2.3 | `field.pig_travel_time_min` | Varis suresi (dakika) | dk | boş | **Evet** | Sonlu, `> 0` | Saha | ✅ | S4 | — |
| 6.2.4 | `field.pig_speed_m_per_s` | Pig hizi (m/s) | m/s | boş | Hayır (türetilir) | readonly | Saha | ✅ readonly | S4 | — |
| 6.2.5 | `field.pig_speed_km_per_h` | Pig hizi (km/sa) | km/sa | boş | Hayır (türetilir) | readonly | Saha | ✅ readonly | S4 | — |

**Limitler:** Temizlik 2.5 m/s (Madde 9); Ön kurutma 8.0/3.6 ≈ 2.222 m/s (Madde 18.3);
Nihai kurutma sünger 1.2 m/s (Madde 20.5); Serbest kontrol limitsiz (`passed=null`).

### 6.3 Zaman serisi girdileri

| # | Alan anahtarı | Etiket | Birim | Varsayılan | Zorunlu | Doğrulama | Sekme / API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|---|---|
| 6.3.1 | `time_series.timestamp` | (otomatik) | ISO-8601 | `now` | Hayır | Geçerli tarih; web'de UTC | Kayıt / `POST /api/sessions/{id}/time-series` | ✅ | S4 | — |
| 6.3.2 | `time_series.pressure_bar` | Basinc (bar) | bar | boş | **Evet** | Sonlu | Kayıt | ✅ | S4 | — |
| 6.3.3 | `time_series.temperature_c` | Sicaklik (°C) | °C | boş | **Evet** | Sonlu | Kayıt | ✅ | S4 | — |
| 6.3.4 | `time_series.volume_m3` | Hacim (m³) | m³ | boş | Hayır | Sonlu veya boş | Kayıt | ✅ | S4 | — |
| 6.3.5 | `time_series.notes` | (sabit) | — | `Manuel kayit` | Hayır | Metin | Kayıt | ✅ | S4 | — |

---

## 7. Hesaplamalar

Her satır domain'deki gerçek fonksiyonu ve sabitini gösterir. Web bu fonksiyonları
**çağırır**, yeniden yazmaz.

| # | Hesap | Girdi | Domain API | Sonuç alanları | Kural / sabit | API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|---|---|
| 7.1 | Geometri türetimi | `sections[]` | `PipeSection`, `PipeGeometry` | `total_length_m`, `internal_volume_m3`, `internal_radius_mm`, `elasticity_term` | `ri=(OD/2)−WT`; `Vt=π·ri²·L`; `0.884·ri/WT` | `POST /api/calculations/geometry` | ✅ dolaylı | S3 | — |
| 7.2 | A katsayısı | `temperature_c`, `pressure_bar`, `backend` | `calculate_water_compressibility_a(temp_c, pressure_bar, backend)` | `a_micro_per_bar`, backend bilgisi | `1/bar → 10⁻⁶/bar` (`×1e11` Pa bazlı) | `POST /api/coefficients/a` | ✅ | S1 | — |
| 7.3 | A — referans tablo | `temperature_c`, `pressure_bar`, tablo | `lookup_botas_reference_point`, `lookup_gail_reference_point` | `a_micro_per_bar`, `source_note`, `repaired`, `repair_note` | Tablo aralığı; 7 °C anomalisi onarımı | `POST /api/coefficients/table` | ✅ | S1 | — |
| 7.4 | B katsayısı — kaynak seçimi | `source`, `T`, `P`, `steel_alpha`, `steel_model` | `resolve_b_value(...)` | `b_micro_per_c`, `source`, `label`, `note`, `repaired_table`, `water_beta_micro_per_c`, `steel_alpha_micro_per_c`, `steel_model` | `institutional` \| `gail` \| `auto` | `POST /api/coefficients/b` | ✅ | S1 | — |
| 7.5 | B — otomatik model | `beta`, `alpha`, `model`, `T` | `calculate_b_coefficient(beta, alpha, steel_model, temp_c)` | `b_micro_per_c` | `linear: β−α`; `volumetric: β−3α`; `volumetric_temperature: β−3α(T)`, `α(T)=10.8+0.012·T` | `POST /api/coefficients/b` (`auto`) | ✅ | S1 | — |
| 7.6 | B — üç kaynak karşılaştırma | `T`, `P`, `alpha`, `model` | `compare_b_sources(...)` | `institutional`, `gail`, `auto`, `institutional_vs_gail`, `auto_vs_institutional`, `auto_vs_gail` | Aynı düğümde üç kaynak | `POST /api/coefficients/compare` | ✅ | S1 | — |
| 7.7 | Backend karşılaştırma | `T`, `P` | `get_available_water_property_backends`, `get_water_property_backend` | Backend başına `A`, `β`, `ρ`, hata | Kurulu backend'ler | `POST /api/coefficients/backend-comparison` | ✅ | S1 | — |
| 7.8 | Su yoğunluğu | `T`, `P` | `calculate_water_density(temp_c, pressure_bar)` | `density_kg_m3` | Hidrolik kotta 15 °C | `POST /api/calculations/water-density` | ◐ dolaylı | S3 | — |
| 7.9 | Hava içerik | `pipe`, `A`, `P`, `K`, `Vpa` | `AirContentInputs` + `evaluate_air_content_test` | `theoretical_added_water_m3`, `acceptance_limit_m3`, `actual_added_water_m3`, `ratio`, `passed` | `Vp=((0.884·ri/s)+A)·1e-6·Vt·P·K`; limit `1.06·Vp`; tam sınır FAIL | `POST /api/calculations/air-content` | ✅ | S2 | — |
| 7.10 | Basınç değişimi | `pipe`, `A`, `B`, `dT`, `Pa` | `PressureVariationInputs` + `evaluate_pressure_variation_test` | `theoretical_pressure_change_bar`, `allowable_upper_pressure_change_bar`, `actual_pressure_change_bar`, `margin_bar`, `passed` | `Pt=(B·dT)/(0.884·ri/s+A)`; `marj ≤ 0.3` | `POST /api/calculations/pressure-variation` | ✅ | S2 | — |
| 7.11 | Basınç profili | `pipe`, `design_p`, `SMYS`, `location_class`, 4 kot, `pump_location`, `monitored_p` | `SectionPressureProfileInputs` + `evaluate_section_pressure_profile` | 20 alan (aşağıda §8.3) | `1.25/1.50 × dizayn`; `100% SMYS = 20·SMYS·t/OD`; `≤20 000 m`; `≤12 500 m³` | `POST /api/calculations/pressure-profile` | ✅ | S3 | — |
| 7.12 | Pig hızı | `distance`, `time`, `limit` | `evaluate_pig_speed(...)` | `speed_m_per_s`, `speed_km_per_h`, `limit`, `passed` | Limit tablosu | `POST /api/calculations/pig-speed` | ✅ | S4 | — |
| 7.13 | Basınçlandırma | `initial_volume`, `added_volume`, `theoretical_volume`, `p`, `expected_p` | `PressurizationInputs` + `evaluate_pressurization` | `volume_deviation_percent`, `pressure_deviation_bar`, `within_volume_limit`, `within_pressure_limit`, `passed`, `volume_limit_percent`, `pressure_tolerance_bar`, `underfilled`, `volume_shortfall_percent` | `%0.2` tek taraflı; basınç toleransı `max(0.05, 0.001·Pbeklenen)` | `POST /api/calculations/pressurization` | ◐ domain var, UI yok | S2 | — |
| 7.14 | Termal denge | `records[]` | `TimeSeriesStore.from_dict` + `check_thermal_balance()` | `balanced`, `temp_diff_c`, `duration_hours` | `≥24 h`; son 4 h vs önceki 4 h; `≤0.5 °C`; referans canlı saat değil **son kayıt** | `POST /api/calculations/thermal-balance` | ✅ (Kayıt sekmesi butonu) | S4 | — |
| 7.15 | Zaman serisi özeti | `records[]` | `get_duration_hours`, `get_average_temperature(last_n_hours)` | `duration_hours`, `average_temperature_c` | Son N saat | `GET /api/sessions/{id}/time-series/summary` | ✅ | S4 | — |
| 7.16 | A/B tablo karşılaştırması | `T`, `P` | `compare_reference_b_sources(...)` | `control_point`, `gail_point`, `a_delta`, `b_delta` | BOTAŞ vs GAIL | `POST /api/coefficients/reference-compare` | ✅ | S1 | — |
| 7.17 | 100% SMYS limiti | `pipe`, `SMYS` | `_pressure_at_100_smys_bar` (dolaylı) | `limiting_pressure_at_100_smys_bar`, `limiting_pipe_description` | `20·SMYS·t/OD`; segmentliyse minimum | profil sonucu | ✅ | S3 | — |
| 7.18 | Hidrolik kot farkı | `Δh` | `_hydraulic_head_bar` (dolaylı) | `hydraulic_span_bar`, pencere head'leri | `ρ(15 °C)·g·Δh/1e5` | profil sonucu | ✅ | S3 | — |

---

## 8. Sonuçlar, kararlar ve rapor alanları

### 8.1 Karar modeli

| # | Alan | Değerler | Kaynak | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|
| 8.1.1 | `decision.status` (hava) | `BEKLIYOR`, `KATSAYI GUNCELLENMELI`, `DOGRULANAMADI`, `BASARILI`, `BASARISIZ` | `_decisions["air"]` | ✅ | S2 | — |
| 8.1.2 | `decision.status` (basınç) | aynı | `_decisions["pressure"]` | ✅ | S2 | — |
| 8.1.3 | `decision.title` | Test adı + kısa durum | `_update_decision_card` | ✅ | S2 | — |
| 8.1.4 | `decision.summary` | Sayısal özet + marj (240 karakterde kısaltılır) | aynı | ✅ | S2 | — |
| 8.1.5 | `decision.rule` | `Vpa < 1.06 x Vp` / `(Pa - Pt) <= 0.3 bar` | `AIR_ACCEPTANCE_RULE`, `PRESSURE_ACCEPTANCE_RULE` | ✅ | S2 | — |
| 8.1.6 | `header.status_text` | "Karar durumu: … - …" | `header_status_var` | ✅ | S2 | — |
| 8.1.7 | `pig.status` | `UYGUN`, `LIMIT ASILDI`, `BILGI` | `_calculate_pig_speed` | ✅ | S4 | — |
| 8.1.8 | `profile.status` | `BEKLIYOR` / `UYGUN` / `UYGUN DEGIL` + monitored | `_update_section_pressure_status_card` | ✅ | S3 | — |

### 8.2 Hava içerik sonuç alanları

| # | Alan | Birim | Açıklama | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|
| 8.2.1 | `theoretical_added_water_m3` (Vp) | m³ | Teorik ilave su | ✅ | S2 | — |
| 8.2.2 | `acceptance_limit_m3` | m³ | `1.06·Vp` | ✅ | S2 | — |
| 8.2.3 | `actual_added_water_m3` (Vpa) | m³ | Fiili ilave | ✅ | S2 | — |
| 8.2.4 | `ratio` | — | `Vpa/Vp` | ✅ | S2 | — |
| 8.2.5 | `passed` | bool | Katı kabul | ✅ | S2 | — |
| 8.2.6 | `margin_m3` | m³ | `limit − Vpa` (yalnız UI/rapor) | ✅ | S2 | — |
| 8.2.7 | Girdi özeti | — | T, P, A, P, K, ri, Vt | ✅ | S2 | — |

### 8.3 Basınç değişim sonuç alanları

| # | Alan | Birim | Açıklama | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|
| 8.3.1 | `theoretical_pressure_change_bar` (Pt) | bar | Teorik değişim | ✅ | S2 | — |
| 8.3.2 | `allowable_upper_pressure_change_bar` | bar | `Pt + 0.3` | ✅ | S2 | — |
| 8.3.3 | `actual_pressure_change_bar` (Pa) | bar | Gözlenen | ✅ | S2 | — |
| 8.3.4 | `margin_bar` | bar | `Pa − Pt` | ✅ | S2 | — |
| 8.3.5 | `passed` | bool | `marj ≤ 0.3 + 1e-9` | ✅ | S2 | — |
| 8.3.6 | `b_interpretation` | metin | Negatif B notu | ✅ | S2 | — |

### 8.4 Basınç profili sonuç alanları

| # | Alan | Birim | Açıklama | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|
| 8.4.1 | `location_class` | — | Seçili kural (label, class, factor, spec) | ✅ | S3 | — |
| 8.4.2 | `required_minimum_pressure_at_high_point_bar` | bar | `dizayn × 1.25/1.50` | ✅ | S3 | — |
| 8.4.3 | `maximum_allowable_pressure_at_low_point_bar` | bar | 100% SMYS limiti | ✅ | S3 | — |
| 8.4.4 | `hydraulic_span_bar` | bar | `highest − lowest` kot farkı | ✅ | S3 | — |
| 8.4.5 | `required_pressure_with_span_bar` | bar | Min + span | ✅ | S3 | — |
| 8.4.6 | `start_window` | — | `PressureWindow` (6 alan) | ✅ | S3 | — |
| 8.4.7 | `end_window` | — | `PressureWindow` | ✅ | S3 | — |
| 8.4.8 | `selected_window` | — | Pompa konumuna göre | ✅ | S3 | — |
| 8.4.9 | `limiting_pressure_at_100_smys_bar` | bar | Kritik kesit limiti | ✅ | S3 | — |
| 8.4.10 | `limiting_pipe_description` | metin | "Limit segment n \| OD \| Et" | ✅ | S3 | — |
| 8.4.11 | `total_length_m` | m | Segment toplamı | ✅ | S3 | — |
| 8.4.12 | `total_internal_volume_m3` | m³ | Toplam hacim | ✅ | S3 | — |
| 8.4.13 | `within_length_limit` | bool | `≤ 20 000 m` | ✅ | S3 | — |
| 8.4.14 | `within_volume_limit` | bool | `≤ 12 500 m³` | ✅ | S3 | — |
| 8.4.15 | `within_100_smys_span_limit` | bool | Gerekli ≤ limit | ✅ | S3 | — |
| 8.4.16 | `feasible` | bool | Üç limitin ve'ü | ✅ | S3 | — |
| 8.4.17 | `monitored_pressure_bar` | bar | Aktif sekmedeki su basıncı | ✅ | S3 | — |
| 8.4.18 | `monitored_meets_minimum` | bool? | Pencere alt sınırı | ✅ | S3 | — |
| 8.4.19 | `monitored_under_maximum` | bool? | Pencere üst sınırı | ✅ | S3 | — |
| 8.4.20 | `PressureWindow.*` | bar/m | `location_label`, `location_elevation_m`, `hydraulic_head_to_high_point_bar`, `hydraulic_head_to_low_point_bar`, `minimum_required_pressure_bar`, `maximum_allowable_pressure_bar` | ✅ | S3 | — |

### 8.5 Pig sonuç alanları

| # | Alan | Birim | Açıklama | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|
| 8.5.1 | `distance_m` | m | Girdi | ✅ | S4 | — |
| 8.5.2 | `travel_time_min` | dk | Girdi | ✅ | S4 | — |
| 8.5.3 | `speed_m_per_s` | m/s | Hesap | ✅ | S4 | — |
| 8.5.4 | `speed_km_per_h` | km/sa | Hesap | ✅ | S4 | — |
| 8.5.5 | `limit.label`, `limit.spec_reference`, `limit.max_speed_m_per_s` | — | Seçili limit | ✅ | S4 | — |
| 8.5.6 | `passed` | bool? | Limitsiz modda `null` | ✅ | S4 | — |
| 8.5.7 | `status`, `summary` | metin | UI metni | ✅ | S4 | — |

### 8.6 Katsayı durum/provenance alanları

| # | Alan | Değerler | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|
| 8.6.1 | `coefficients.air_a.state` | `empty/computed/reference/manual/stale` | ✅ | S2 | — |
| 8.6.2 | `coefficients.pressure_a.state` | aynı | ✅ | S2 | — |
| 8.6.3 | `coefficients.pressure_b.state` | aynı | ✅ | S2 | — |
| 8.6.4 | `coefficients.*.source` | `BEKLIYOR` / `HESAP` / `TABLO` / `MANUEL` / `BAYAT` | ✅ badge | S2 | — |
| 8.6.5 | `b_source.label` | `Kurum ici tablo (varsayilan)` / `GAIL referans tablosu` / `Otomatik (beta - 3*alpha)` / `Manuel B` | ✅ | S1 | — |
| 8.6.6 | `b_source.note` | Tablo/onarım/model açıklaması | ✅ | S1 | — |
| 8.6.7 | `b_source.repaired_table` | bool | ✅ | S1 | — |
| 8.6.8 | `backend_comparison` (hava/basınç) | Backend başına A/B/ρ | ✅ | S1 | — |
| 8.6.9 | `control_table_summary` | A/B tablo değeri + delta | ✅ | S1 | — |
| 8.6.10 | `ab_repaired_cell_count` | int | ✅ | S1 | — |

### 8.7 Rapor içeriği (TXT bölümleri)

Masaüstü `_build_report_text()` sırasıyla; web `export_service.build_report_text()` aynı
bölümleri üretir.

| # | Bölüm | Alanlar | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|
| 8.7.1 | Başlık | Uygulama adı, sürüm, şartname kodu/başlığı, oluşturma zamanı | ✅ | S4 | — |
| 8.7.2 | Boru Kesiti | OD, WT, uzunluk, liste/schedule seçimi, 4 kot, dizayn basıncı, kalite, SMYS, Location Class, pompa konumu, basınç penceresi | ✅ | S4 | — |
| 8.7.3 | Segment Listesi | n, NPS, schedule, OD, WT, L | ✅ | S4 | — |
| 8.7.4 | Hava Girdileri | T, P, ortam T, A modu, backend, backend özeti, referans tablo, A, backend karşılaştırması, kontrol tablosu, P, K, Vpa | ✅ | S4 | — |
| 8.7.5 | Basınç Girdileri | T, P, A modu, referans, A, B modu, B kaynağı, B referans, B, kaynak özeti, negatif B notu, backend karşılaştırması, kontrol tablosu, dT, Pa, helper, alpha, beta, traceability | ✅ | S4 | — |
| 8.7.6 | Operasyon Kontrol Noktaları | Özet + 11 satır (`[X]`/`[ ]`, referans) | ✅ | S4 | — |
| 8.7.7 | Pig Hız Hesabı | Mod, mesafe, süre, m/s, km/sa, durum | ✅ | S4 | — |
| 8.7.8 | Nihai Karar | İki kural + iki testin durum/kural/başlık/özet | ✅ | S4 | — |
| 8.7.9 | Oturum Sonuçları | Zaman damgalı kayıt günlüğü | ✅ | S4 | — |
| 8.7.10 | Not | B31.8/prosedür uyarısı, işaret sözleşmesi | ✅ | S4 | — |

### 8.8 Dışa aktarma ve OCR payload alanları

| # | Alan | Format | Açıklama | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|
| 8.8.1 | PDF | A4, DejaVu, metadata/geometri/sonuç/checklist tabloları | Rapor PDF'i | ✅ `export_pdf_report` | S4 | — |
| 8.8.2 | XLSX | Tek sayfa, bölüm başlıkları, formül nötralizasyonu | Rapor Excel'i | ✅ `export_excel_report` | S4 | — |
| 8.8.3 | TXT | §8.7 | Rapor metni | ✅ | S4 | — |
| 8.8.4 | `calculated.pipe_od_mm` | float | OCR karşılaştırma | ✅ | S5 | — |
| 8.8.5 | `calculated.wall_mm` | float | aynı | ✅ | S5 | — |
| 8.8.6 | `calculated.length_m` | float | Segment toplamı | ✅ | S5 | — |
| 8.8.7 | `calculated.test_pressure_bar` | float | Basınç testi P | ✅ | S5 | — |
| 8.8.8 | `calculated.air_test.vp_m3` | float | Hava Vp | ✅ | S5 | — |
| 8.8.9 | `calculated.air_test.vpa_m3` | float | Hava Vpa | ✅ | S5 | — |
| 8.8.10 | `calculated.air_test.a_micro_per_bar` | float | Hava A | ✅ | S5 | — |
| 8.8.11 | `calculated.pressure_test.t_initial_c`, `t_final_c` | float | **Masaüstü göndermiyor** (yalnız dT) | ◐ | S5 | — |
| 8.8.12 | `calculated.pressure_test.delta_t_c` | float | dT | ✅ | S5 | — |
| 8.8.13 | `calculated.pressure_test.pa_bar` | float | Pa | ✅ | S5 | — |
| 8.8.14 | `calculated.pressure_test.a_micro_per_bar`, `b_micro_per_c` | float | A/B | ✅ | S5 | — |
| 8.8.15 | `calculated.result` | `PASS`/`FAIL`/`UNKNOWN` | Karar durumlarından | ✅ | S5 | — |

Kural: yalnızca sonlu, sıfır/negatif olmayan (alanına göre) değerler payload'a yazılır.
Segmentli geometride OD/WT yalnızca tüm segmentlerde aynıysa tek değer olarak gönderilir;
uzunluk her zaman toplanır.

### 8.9 OCR çıkarılan alanlar (`HydrotestReport`)

| # | Alan anahtarı | Etiket | Birim | Zorunluluk | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|---|
| 8.9.1 | `report_no` | Rapor No | — | Önerilen | ✅ | S5 | — |
| 8.9.2 | `date` | Tarih | ISO tarih | Önerilen | ✅ | S5 | — |
| 8.9.3 | `operator` | Operatör | — | Opsiyonel | ✅ | S5 | — |
| 8.9.4 | `section_id` | Bölüm No | — | Opsiyonel | ✅ | S5 | — |
| 8.9.5 | `pipe_od_mm` | Dış çap | mm | **Zorunlu** | ✅ | S5 | — |
| 8.9.6 | `wall_mm` | Et kalınlığı | mm | **Zorunlu** | ✅ | S5 | — |
| 8.9.7 | `length_m` | Hat uzunluğu | m | **Zorunlu** | ✅ | S5 | — |
| 8.9.8 | `test_pressure_bar` | Test basıncı | bar | **Zorunlu** | ✅ | S5 | — |
| 8.9.9 | `air_test.vp` | Hava testi Vp | m³ | Önerilen | ✅ | S5 | — |
| 8.9.10 | `air_test.vpa` | Hava testi Vpa | m³ | Önerilen | ✅ | S5 | — |
| 8.9.11 | `air_test.a` | Hava testi A | 10⁻⁶/bar | Opsiyonel | ✅ | S5 | — |
| 8.9.12 | `pressure_test.t_initial` | Başlangıç sıcaklığı | °C | Önerilen | ✅ | S5 | — |
| 8.9.13 | `pressure_test.t_final` | Bitiş sıcaklığı | °C | Önerilen | ✅ | S5 | — |
| 8.9.14 | `pressure_test.delta_t` | Sıcaklık farkı | °C | Önerilen | ✅ | S5 | — |
| 8.9.15 | `pressure_test.pa` | Basınç düşüşü | bar | Önerilen | ✅ | S5 | — |
| 8.9.16 | `pressure_test.a` | Basınç testi A | 10⁻⁶/bar | Opsiyonel | ✅ | S5 | — |
| 8.9.17 | `pressure_test.b` | Basınç testi B | 10⁻⁶/°C | Opsiyonel | ✅ | S5 | — |
| 8.9.18 | `result` | Sonuç | PASS/FAIL | Önerilen | ✅ | S5 | — |
| 8.9.19 | `notes` | Notlar | — | Opsiyonel | ✅ | S5 | — |

Alan alt bilgisi (her biri): `value`, `unit`, `confidence` (0–1), `raw_text`, `page`,
`bbox`. Karşılaştırma durumları: `match`, `within_tolerance`, `mismatch`,
`missing_in_report`, `missing_in_calculation`, `not_comparable`; önem:
`info`/`warning`/`critical`.

---

## 9. Oturum, kayıt ve OCR davranışları

| # | Özellik | Masaüstü davranışı | API | desktop | web-planned | web-implemented |
|---|---|---|---|---|---|---|
| 9.1 | Yeni oturum | `Oturum N`, girdiler temizlenir | `POST /api/sessions` | ✅ | S4 | — |
| 9.2 | Oturum listesi | Son güncellemeye göre sıralı | `GET /api/sessions` | ✅ | S4 | — |
| 9.3 | Oturum seçme | Aktif oturum değişir, UI snapshot uygulanır | `GET /api/sessions/{id}` + `X-Session-ID` | ✅ | S4 | — |
| 9.4 | Oturum kaydetme | `Kaydet` + 500 ms debounce otomatik kayıt + 60 s timer | `PUT /api/sessions/{id}` | ✅ | S4 | — |
| 9.5 | Son oturumu geri yükleme | Açılışta en son oturum | `GET /api/sessions?limit=1` | ✅ | S4 | — |
| 9.6 | Oturum geçmişi | Treeview: ID, ad, test sayısı, tarihler | `GET /api/sessions` | ✅ | S4 | — |
| 9.7 | İstatistikler | Toplam oturum/test, durum ve tip dağılımı, time series | `GET /api/stats` | ✅ | S4 | — |
| 9.8 | Girdi snapshot kaydet/yükle | JSON dosyası (`schema_version: 1`) | `GET/POST /api/sessions/{id}/snapshot` | ✅ | S4 | — |
| 9.9 | Test sonucu kaydı | `test_entries` (tip, girdi, sonuç, karar) | `POST /api/sessions/{id}/results` | ✅ | S4 | — |
| 9.10 | Zaman serisi ekleme | Basınç/sıcaklık/hacim/not | `POST /api/sessions/{id}/time-series` | ✅ | S4 | — |
| 9.11 | Son 20 kayıt | Mesaj kutusu | `GET /api/sessions/{id}/time-series?limit=20` | ✅ | S4 | — |
| 9.12 | Termal denge kontrolü | ≥24 h, 4 h vs 4 h, ≤0.5 °C | `POST /api/calculations/thermal-balance` | ✅ | S4 | — |
| 9.13 | Wizard | 4 adım: Geometri → Parametreler → Uygulama → Rapor; adım durumu oturumda | `inputs.wizard_state` | ✅ | S4 | — |
| 9.14 | OCR rapor kontrolü | Dosya seç → arka plan → özet/alanlar/uyuşmazlık/uyarı sekmeleri | `POST /api/ocr/analyze` + poll | ✅ | S5 | — |
| 9.15 | OCR alan onayı | **Yok** (yalnız görüntüleme) | `POST /api/ocr/analyses/{id}/approve` | — | S5 (yeni) | — |
| 9.16 | OCR alan eşleme profili | Gömülü `FIELD_ALIASES` | `GET/POST/PUT /api/ocr/mapping-profiles` | ◐ sabit | S5 (yeni) | — |
| 9.17 | OCR sonucu oturuma uygulama | **Yok** | `POST /api/ocr/analyses/{id}/apply` | — | S5 (yeni) | — |
| 9.18 | Denetim izi | **Yok** | `audit_events` + `GET /api/sessions/{id}/audit` | — | S5 (yeni) | — |
| 9.19 | Rapor kilidi | **Yok** | `status=completed` + approver (auth sonrası) | — | S6 | — |
| 9.20 | Oturum silme | Menüde yok; DB'de `delete_session` var | `DELETE /api/sessions/{id}` (soft) | ◐ API var, UI yok | S4 | — |

**Kapsam dışı (bilinçli):** masaüstü otomatik güncelleme/indirme yöneticisi
(`services/updater.py`, `download_manager.py`) web'e taşınmaz; sürüm yönetimi konteyner
imajı ve dağıtım hattına devredilir (architecture §13). "Hakkında" ve güncelleme menüsü
yerine Ayarlar'da sürüm/şartname bilgisi gösterilir.

---

## 10. Eksik ve karar gereken noktalar

Aşağıdakiler parity'yi **doğrudan etkiler**; karar verilmeden ilgili dilim kapatılmaz.

| # | Konu | Mevcut durum | Etki | Öneri / karar |
|---|---|---|---|---|
| 10.1 | **Gerçek kot profili** | Masaüstünde yalnızca 4 kot var (start/end/highest/lowest); istasyon bilgisi yok | "Tam saha" 3D profili yaklaşık olur; basınç renkleri yaklaşık | `profile_points[]` (station, elevation) opsiyonel girdisi ekle; yoksa parçalı doğrusal + "yaklaşık" uyarısı |
| 10.2 | **Ekipman konumları** | Vana/pompa/test başlığı koordinatı yok | 3D'de sembolik yerleşim | `equipment[]` opsiyonel girdisi; yoksa varsayılan yerleşim |
| 10.3 | **Segment istasyonu** | Yalnızca uzunluk var | 3D zincirleme türetilir | Türetim yeterli; kullanıcı override'ı opsiyonel |
| 10.4 | **Basınç profilinde ara kotlar** | Domain yalnızca uç/min/max ile pencere hesaplar | 3D'de ara nokta basıncı hidrostatik türetim | Türetim formülü dokümante; mühendislik onayı gerekir |
| 10.5 | **Hidrolik hesapta sabit 15 °C yoğunluk** | `_hydraulic_head_bar` `water_temp_c=15.0` sabit | Test sıcaklığı 15 °C değilse küçük sapma | Parity için **koru**; web'de "15 °C varsayımı" notu göster |
| 10.6 | **SMYS manuel override** | Kalite seçilince readonly | Proje spesifikasyonu farklı SMYS verebilir | Web'de "override" opsiyonu + gerekçe zorunlu; parity dışı işaretle |
| 10.7 | **Basınçlandırma UI'da yok** | Domain `evaluate_pressurization` var; UI yok | Web'de yeni sekme/hesap | Basınç sekmesinde kart olarak ekle (parity+) |
| 10.8 | **Zaman serisi zaman damgası** | `datetime.now()` naive yerel | UTC'ye geçişte sıralama farkı | Web'de UTC sakla, `tr-TR` göster; içe aktarmada yerel→UTC dönüşümü |
| 10.9 | **OCR rapor formatı** | Gömülü alias sözlüğü; gerçek form yok | Alan eşlemesi yanlış olabilir | `ocr_mapping_profiles` + yarın gelecek formatla profil; `pre_extract` alias + `post_map` |
| 10.10 | **OCR onayı oturuma uygulanması** | Masaüstünde yok | Çift giriş riski | Onay ve uygulamayı ayır; uygulama audit'li ve alan-bazlı olsun |
| 10.11 | **`t_initial`/`t_final` payload'da yok** | Masaüstü yalnız dT gönderir | OCR'ın Tilk/Tson karşılaştırması eksik kalır | Web'de basınç sekmesine Tilk/Tson opsiyonel alanları ekle (dT'yi türet veya doğrula) |
| 10.12 | **Rapor kimliği alanları** | `report_no`, `operator`, `date` yalnız OCR'dan | Web raporunda boş kalabilir | Raporlar sekmesinde opsiyonel metadata alanları |
| 10.13 | **Auth/rol** | Yok | Onay/rapor kilidi anlamsız | MVP'de uyarı bandı; S6'da OIDC iskeleti |
| 10.14 | **Eşzamanlı düzenleme** | Tek kullanıcı varsayımı | İki sekme çakışabilir | `revision` + `If-Match`; çakışmada 409 ve diff |
| 10.15 | **Masaüstü JSON içe aktarma** | Dosya kaydet/yükle var | Kullanıcı geçmişi kaybolmasın | `POST /api/import/desktop-snapshot` (S4) + doğrulama raporu |
| 10.16 | **Sayı ayrıştırma farkı** | UI virgül ondalık; OCR farklı kurallar | Aynı metin farklı sayı olabilir | Web'de tek `parseNumber`; OCR servis kuralları ayrı kalır, UI'da kaynak gösterilir |
| 10.17 | **PDF fontu** | DejaVu varsa; yoksa Helvetica | Türkçe karakter kaybı | Konteynerde `fonts-dejavu-core`; build testi |
| 10.18 | **CoolProp sürümü** | `requirements.txt` 7.0.0; araştırma 7.2.0 | A değerlerinde küçük fark | Tek sürüm kaynağı; parity fixture'ları kurulu sürümle üretilir |
| 10.19 | **Tam 1.06 sınırı** | Domain `strict_acceptance_limit` ile FAIL | Web'de `<=` yazılırsa parity bozulur | Domain'i çağır; frontend'de karar hesabı yok |
| 10.20 | **OCR düşük güven eşikleri** | 0.6 amber, 0.4 kırmızı; onay zorunlu | Web'de farklı eşik | Sabitleri `GET /api/ocr/status` ile paylaş; tek kaynak |
| 10.21 | **Uzun OCR işleri** | Masaüstünde thread + queue | Web'de timeout/queue | 300 s timeout, tek worker, polling |
| 10.22 | **Çoklu dil** | Yalnız Türkçe | — | MVP Türkçe; metinler i18n anahtarına hazır |
| 10.23 | **Segment bazlı SMYS/kalite** | Tek kalite tüm segmentler | Farklı kaliteli hat modellenemez | Parity koru; ileride segment alanı |
| 10.24 | **Basınç profili `location_class` 1/2 ayrımı** | İkisi de 1.25 | Sadece etiket farkı | Parity koru; şartname gerekiyorsa ayrı faktör |
| 10.25 | **Rapor dili** | Türkçe/ASCII karışık | Web'de tutarlılık | Türkçe karakterli metin; alan anahtarları İngilizce |
| 10.26 | **Taranmış PDF rasterizer** | `requirements-ocr.txt` PyMuPDF/pdf2image'i opsiyonel bırakır | Metin katmanı olmayan PDF OCR edilemez | Varsayılan: metin PDF + görsel. Taranmış PDF için lisans onayıyla `poppler-utils` + `pdf2image` (veya PyMuPDF) |
| 10.27 | **3D kot/ekipman verisi** | Masaüstünde yok | Sahne yaklaşık | `profile_points[]` ve `equipment[]` opsiyonel girdileri; yoksa `warnings` |
| 10.28 | **Canlı sonuç otomatik kaydı** | Masaüstü, canlı karar `BASARILI/BASARISIZ` olunca debounce ile sonuç kaydeder | Web'de her tuş vuruşunda kayıt gürültü üretir | Öneri: yalnızca **Değerlendir** kaydeder; istenirse Ayarlar'da "otomatik kaydet" (varsayılan kapalı) |

---

## 11. Parity doğrulama kontrol listesi

Bir dilim "tamam" sayılmadan önce:

- [ ] İlgili tüm `desktop ✅` satırları için API alanı var.
- [ ] `webapp/backend/tests/parity/cases/` altında en az bir fixture var.
- [ ] API yanıtı domain çıktısıyla `1e-9` bağıl toleransta eşleşiyor.
- [ ] Hata yolları test edildi (400/422/404/413/415/503).
- [ ] Frontend alan anahtarları bu tablodaki anahtarlarla birebir.
- [ ] Boş / yükleniyor / hata / kısmi veri durumları UX planına uygun.
- [ ] `web-implemented` sütunu test kanıtıyla güncellendi.
