# Neler Yeni — HYDRO v2.4.0 (What's New)

**Sürüm:** `v2.4.0` (`hidrostatik-test-v2.4.0`)  
**Tarih:** 2026-11-27

---

### v2.4.0 Öne Çıkanlar
- **Test Raporu Çoklu Dosya Ekleme & Toplu Analiz Kuyruğu:** Test Raporu Kontrolü ekranında birden fazla `.xlsx`/`.pdf`/görsel dosya aynı anda yüklenip sıralı kuyrukla analiz edilir; tamamlanan tüm test bölümleri kuyruk kartından seçilip incelenebilir.
- **Excel Test Raporu Okuma Doğruluğu (`8` Düzeltme):** Gece yarısı sonrası saat satırları, `DOLUM R` / `018` / `021` boş hücre ve çoklu sıcaklık probu sütun hizaları, `VERİ` çoklu segment/ölçüm aktarımı, `X60` SMYS (`415 MPa`), `KmS`/`KmE` KP'leri, `ÇİĞLENME NOKTASI` (`KUR-002`) ve boş `(2/2)` şablon filtresi düzeltildi.
- **Didim Revize Paftaları & Taranmış PDF Dolum Logları:** Revize prosedür PDF'lerinden `406.4 mm` çap, `75 bar` tasarım basıncı ve `1-A/1-B`, `2-A/2-B` alt kesit kotları doğru çıkarılır; taranmış PDF dolum tablolarında `"1. Pig Gönderildi"` sıra numarası artık sıcaklık olarak okunmaz.

---

### v2.3.0 Öne Çıkanlar
- **Veri Kaybı & Bayat Rapor Koruması:** Sayısal alanlarda (`NumberField`, segment tablosu) hatalı girişler odaktan çıkınca sessizce geri alınmaz; bölüm değiştirirken kaydedilmemiş değişiklik uyarısı ve PDF/Excel indirmeden önce otomatik kaydetme çalışır.
- **Basınç Testinde `Pilk − Pson` Türetme & İşaret Netliği:** Doğrudan `ΔT` modunda yanıltıcı `Tilk`/`Tson` alanları gizlenir; `Pa` için isteğe bağlı `Pilk − Pson ile türet` modu ve canlı basınç düşüşü/artışı yön etiketi eklendi.
- **WCAG AA Kontrast, CSS Token Bütünlüğü & `<1536px` Canlı Özet:** Şeffaf açılan `⌘K` komut paleti/önizleme çekmecesi ve açık tema uyarı bandı düzeltildi, `--text-faint` kontrastı `≥4.5:1` seviyesine taşındı, `<1536px` ekranlara açılır `Canlı Özet` çekmecesi ve klavye odak iadeli native `<dialog>` desteği eklendi.

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
