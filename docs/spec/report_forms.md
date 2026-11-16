# Resmî Hidrostatik Test Formları — Envanter ve OCR Kalibrasyonu

**Durum:** Gerçek saha dosyalarıyla kalibre edildi (2026-11-16).
**Kaynaklar:**

- 9 adet resmî `.xls` şablonu: `BOT-FRM-İNB-001-0{15..23}*.xls`
- 74 sayfalık taranmış saha raporu: `ERCİŞ - H.TEST RAPORLARI.pdf` (metin katmanı yok)
- Metin katmanlı plan-profil: `Kağızman DGBH Hidrostatik Test Profili-Model A0.pdf`

> Not: Şablon **dosya adları** `BOT-FRM-İNB-...` yazar; basılı form
> numaraları gerçekte `BOT-FRM-CDB-001-0xx` biçimindedir. OCR, form
> numarasını sayfa altından okur ve `report_no` alanına yazar.

---

## 1. Form envanteri

| Kod | Şablon dosyası | Sayfa (sheet) | Rapor başlığı |
|---|---|---|---|
| 015 | Hidrostatik Test Verileri | `hydrostatic test data` | HİDROSTATİK TEST VERİLERİ |
| 016 | Temizlik Kabul Raporu | `cleaning report` | TEMİZLİK KABUL RAPORU |
| 017 | Su Dolum Raporu | `filling report` | SU DOLUM RAPORU |
| 018 | Dengeleme İçin Kaçak Test Raporu | `leak stabilizaation report` | DENGELEME İÇİN KAÇAK TEST RAPORU |
| 019 | Mukavemet Test Raporu | `hydrostatic test data`, `strength test report` | MUKAVEMET TEST RAPORU |
| 020 | Hava İçerik Testi Kabul Raporu | `hydrostatic test data`, `acceptance air test report` | HAVA İÇERİK TESTİ KABUL RAPORU |
| 021 | Basınç Testi Raporu | `leak test report` | BASINÇ TESTİ RAPORU |
| 022 | Basınç Testi Kabul Raporu | `hydrostatic test data`, `dewatering report`, `cleaning report`, `filling report`, `strength test report`, `leak test acceptance report` | BASINÇ TESTİ KABUL RAPORU |
| 023 | Boşaltma Kabul Raporu | `dewatering report` | BOŞALTMA KABUL RAPORU |

Bir test bölümü sahada tipik olarak şu sırayla doldurulur (her biri ~1
sayfa): **Boşaltma → Ön Kurutma → Su Dolum → Mukavemet → Dengeleme →
Hava İçerik → Basınçlandırma → Basınç Testi → Basınç Kabul**.

---

## 2. Ortak başlık bloğu

`015` ve türevlerinde ilk blok neredeyse aynıdır:

| Etiket | Alan (şema) | Birim / biçim | Örnek |
|---|---|---|---|
| Tarih | `date` | `GG.AA.YYYY` | `05.10.2026` |
| Test Bölüm No | `section_id` | metin | `BÖLÜM 5`, `BÖLÜM 3B` |
| Test Bölüm Boyu | `length_m` | `m` | `8.802,34` |
| Test Bölüm Hacmi | `section_volume_m3` | `m³` | `823,66` |
| Boru Dış Çapı | `pipe_od_mm` | `mm` | `355,60` |
| Boru İç Çapı | `pipe_id_mm` | `mm` | `345,20` |
| Boru Et Kalınlığı | `wall_mm` | `mm` | `5,20` |
| 1.Başlık No / Yeri | — | metin | `TB-02` / `25+404` |
| 2.Başlık No / Yeri | — | metin | `TB-01` / `34+203` |
| Maks. İşletme Basıncı | `max_operating_pressure_bar` | `bar` | `75,00` |
| Maks. Test Basıncı | `test_pressure_bar` | `bar` | `131,68` |
| Boru Akma Dayanımı (SMYS) | `smys_mpa` | `MPa` | `415` |

`Test Bölümünün Başlangıç Noktası` / `Bitiş Noktası` alanları
`start_kp` / `end_kp` olarak okunur. Sahada bu değerler çoğu zaman
`1.Başlık Yeri` / `2.Başlık Yeri` ile aynıdır.

---

## 3. Hava içerik testi (form 020)

Formül: `Vp = (0,884·(ri/S) + A) · 10⁻⁶ · Vt · K`

| Etiket | Alan | Birim | Örnek |
|---|---|---|---|
| Vp — Basıncı 1 bar değiştirmek için gerekli teorik su | `air_test.vp` | `m³` | `0,0625` |
| Vpa — Basıncı 1 bar değiştirmek için kullanılan su | `air_test.vpa` | `m³` | `0,0640` |
| Test Bölümünün Geometrik Hacmi | `air_test.vt` | `m³` | `823,66` |
| Ölçülen Basınç Değişimi | (hava formu girdisi) | `bar` | `1,00` |
| Boru İç Yarıçapı | — | `mm` | `172,60` |
| Boru Et Kalınlığı | `wall_mm` | `mm` | `5,20` |
| Suyun İzotermal Sıkışabilirlik Katsayısı (A) | `air_test.a` | `10⁻⁶/bar` | `45,106` |
| Katsayı K | `air_test.k` | — | `1,02` |
| `(Vpa/Vp)-1` | `air_test.ratio` | — | `0,023` |
| Sonuç | `result` | `PASS`/`FAIL` | `PASS` |

Kabul koşulu: `(Vpa/Vp)-1 ≤ 0,06`.

> **Tuzak:** `Ölçülen Basınç Değişimi` hava formunda testin basınç adımıdır
> (`1,00 bar`); basınç testi formundaki `PA` ile karıştırılmamalıdır.
> OCR, hava bölümünde `pressure_test.*` alanlarını yazmaz.

---

## 4. Basınç testi kabul (form 022)

Formül: `ΔP = ΔT · B / (0,884·(ri/S) + A)`

| Etiket | Alan | Birim | Örnek |
|---|---|---|---|
| Ölçülen Basınç Değişimi (PA) | `pressure_test.pa` | `bar` | `0,400` |
| ΔP — Sıcaklık değişiminden kaynaklanan basınç değişimi | `pressure_test.p_delta` | `bar` | `0,435` |
| ΔT — Testin başı ve sonunda su sıcaklığında oluşan değişim | `pressure_test.delta_t` | `°C` | `0,200` |
| B — Su ve çeliğin ısıl genleşme katsayıları farkı | `pressure_test.b` | `10⁻⁶/°C` | `161,497` |
| A — Suyun izotermal sıkışabilirlik katsayısı | `pressure_test.a` | `10⁻⁶/bar` | `44,892` |
| Boru İç Yarıçapı | — | `mm` | `172,6` |
| Boru Et Kalınlığı | `wall_mm` | `mm` | `5,20` |
| PL — Test boyunca izin verilebilir basınç değişimi | `pressure_test.pl` | `bar` | `0,300` |
| `(PA-ΔP)` | — | `bar` | `-0,035` |
| Sonuç | `result` | `PASS`/`FAIL` | `TEST KABUL EDİLMİŞTİR` |

Kabul koşulu: `(PA - ΔP) ≤ PL`.

> **OCR tuzağı:** `ΔP` bazı taramalarda `PA` veya `AP` olarak okunur.
> Aynı formda `Pa/PA` ikinci kez görülürse konum gereği `p_delta` kabul
> edilir (ilk `Pa` = ölçülen basınç değişimi).

---

## 5. Sayı, tarih ve KP biçimleri

| Tür | Biçim | Örnek | Not |
|---|---|---|---|
| Sayı | binlik `.`, ondalık `,` | `3.722,21` | Tek `,` ondalıktır |
| Tarih | `GG.AA.YYYY` | `19.10.2026` | `GG/AA/YYYY` de görülür |
| KP | `K+MMM` | `25+404`, `18+143` | km + metre; `34+203` = 34.203 m |
| Şablon | `BOT-FRM-CDB-001-0xx` | `BOT-FRM-CDB-001-023` | Sayfa altında |

---

## 6. Önemli bulgu: `Bölüm Uzunluğu` ≠ ΔKP

Sahadaki `Bölüm Uzunluğu` **boru metresi**dir; KP aralığı ise güzergâh
zinciridir. Fitting/elbow ve güzergâh eğrileri nedeniyle ikisi birebir
eşit değildir:

| Test Bölümü | Bölüm Uzunluğu | ΔKP | Fark |
|---|---|---|---|
| BÖLÜM 3B | `3.722,21 m` | `3.697 m` | ~25 m |
| BÖLÜM 5 | `8.802,34 m` | `8.799 m` (25+404 → 34+203) | ~3,3 m |
| (uzun bölüm) | `7.264,90 m` | `7.261 m` | ~3,9 m |

Bu nedenle uygulamada:

- `Σ Segment uzunluğu` ↔ `Section uzunluğu / KP aralığı` denetimi
  **`max(0,5 m, %0,5)`** tolerans kullanır.
- Ardışık iki test bölümünün **KP sürekliliği** (önceki bitiş ↔ sonraki
  başlangıç) **0,5 m** toleransta kalır.
- `Test Bölüm Boyu` ile `ΔKP` arasındaki fark otomatik olarak
  "uyarı" değil, bilgi notu olarak gösterilir.

---

## 7. OCR kalitesi (macOS Vision)

- Motor: `ocrmac` (Apple Vision), dil tercihi `tr-TR`, `en-US`.
- Vision blokları `[x, y, w, h]` normalize kutusuyla gelir (y ekseni
  alttan). Etiket ve değer ayrı hücrelerde olduğu için bloklar:
  1. Dar dikey toleransla (`0,005`) **form satırlarına** ayrılır,
  2. Her satırda etiketler sağındaki en yakın **kullanılmamış** değere
     bağlanır,
  3. Birim blokları (`mm`, `(bar)`, `(1/bar)` …) etiket veya değer
     sayılmaz.
- OCR kaynaklı küçük yazım hataları (`Test Bölüm acmi`) için uzun
  etiketlerde bulanık eşleşme (`difflib`, eşik `0.88`) devrededir.
- Formül satırları (`Vp = (0,884 x …)`) ile gerçek değer satırları
  (`Vp : 0,0625`) ayırt edilir; formülden sayı çıkarılmaz.

Kalibrasyon referansı (BÖLÜM 5, sayfa 8 ve 11): tüm alanlar yukarıdaki
örnek değerlerle birebir okunur.
