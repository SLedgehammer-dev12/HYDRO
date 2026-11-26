# Neler Yeni — HYDRO v2.2.0 (What's New)

**Sürüm:** `v2.2.0` (`hidrostatik-test-v2.2.0`)  
**Tarih:** 2026-11-26

---

### v2.2.0 Öne Çıkanlar
- **Daha İsabetli & Hızlı OCR Okuma:** Düşük güvenli taramalarda Otsu adaptif eşikleme + `--psm 6` ikinci geçiş, tablo kenarlığı `|` temizliği, zayıf `vision`/`windows_ocr` sayfalarında Tesseract yedeği, çok sayfalı PDF'lerde paralel OCR ve canlı `Sayfa X / Y` ilerleme çubuğu.
- **Yan Yana Belge Doğrulama:** Alan tablosundaki sayfa numarasına tıklayarak kaynak sayfanın önizlemesini açma (`PagePreviewDrawer`, yakınlaştırma ve `90°` döndürme), filtre çipleri, anlık arama, tek tıkla **"Tüm Önerileri Uygula"** ve klavye kısayolları (`Enter`/`E`, `Space`).
- **Arayüz Ergonomisi (`Ctrl/⌘ + K`):** Tüm sekmeler, 16 BOTAŞ formu ve Test Bölümleri arasında tek tuşla geçiş yapan Komut Paleti, panodan (`Ctrl/⌘+V`) görsel yapıştırma ve Dashboard üzerinden tek tıkla `OCR'dan İçe Aktar`.

---

### v2.1.1 Öne Çıkanlar (`R1–R18` + `OCR-1..4`)
- **Kurumsal Kimlik Doğrulama & İki Kişi Onayı (`R4`):** OIDC PKCE + `HttpOnly` oturum, RBAC rolleri (`operator`/`supervisor`/`admin`) ve oturum finalleştirme / `db-restore` için iki kişi onayı paneli (`ApprovalsCard`).
- **Gelişmiş Doküman & OCR Okuma (`OCR-1..4`):** Sayfa düzeyinde hibrit PDF/OCR, Pillow ön işleme + otomatik `90°`/`270°` yön düzeltme, `pdfplumber` tablo çıkarımı ve inceleme tablosunda tek tıkla ondalık hata önerileri.
- **Süreklilik & Sürüm Güvencesi (`R1–R3`, `R5–R18`):** Kalıcı DB tabanlı OCR worker, form otomatik taslak, LTTB büyük veri grafiği, `axe-core` erişilebilirlik doğrulaması, OpenAPI → TypeScript senkronu ve otomatik yedek kurtarma tatbikatı.

---

### v2.1.0 Temel Yenilikler
### 1. Faz 1–3 Arayüz Sadeleştirmesi
- **Daha Temiz Kabuk & Dashboard:** Üst barlar inceltildi, sol form ağacı varsayılan kapalı hale getirildi ve `Dashboard` 4 katmana indirildi.
- **Sekmeli Sayfalar & Katlanabilir Detaylar:** `Geometri & Saha` (`3` sekme) ve `Raporlar` (`2` sekme) düzenlendi; `Hava Testi` ve `Basınç Testi` sayfalarındaki ikincil bloklar katlanabilir alanlara taşındı; `Projeler` başlık taşması düzeltildi.

### 2. 020 / 022 Kabul Formlarında Bağımsız Program Hesabı
- `Hava İçerik Testi (020)` ve `Basınç Testi (022)` formlarında `A`, `B`, `Vp` ve `PT` değerleri formdan okunan katsayıları yansıtmak yerine `(T, P)` girdilerinden bağımsız hesaplanır.
- Değerlendirme paneli **2a. Okunan Girdi Değerleri** ve **2b. Hesaplanan Değerler** olarak ikiye ayrıldı; taranan form değerleriyle karşılaştırma bulguları (`air_a_match`, `air_vt_match`, `pa_a_match`, `pa_b_match`) eklendi.

### 3. Birleşik Su Özelliği Backendleri (`IAPWS-95` / `IAPWS-IF97 Region 1` / Referans Tabloları)
- `CoolProp EOS` → **`IAPWS-95`**, `Table Interpolation v1` → **`IAPWS-IF97 Region 1`** olarak adlandırıldı.
- `BOTAŞ / Kurumsal Tablo` ve `GAIL Referans Tablosu` hem A hem B katsayıları için doğrudan `Otomatik` backend seçimi altında hesaplama motoru olarak çalıştırılabilir hale getirildi.
