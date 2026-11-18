# Neler Yeni — HYDRO v1.9.1 (What's New)

**Sürüm:** `v1.9.1` (`hidrostatik-test-v1.9.1`)  
**Tarih:** 2026-11-18

---

### 1. Kurumsal Windows 10/11 Uyumluluğu & Yerleşik WinRT OCR / PDF Motoru
- **Süreç-içi Windows 10/11 OCR (`Windows.Media.Ocr`):** Kurumsal antivirüs, EDR ve AppLocker politikalarının harici `tesseract.exe` veya rasterizer alt süreçlerini engellediği bilgisayarlarda doğrudan Windows'un yerleşik WinRT API'si üzerinden ek alt süreç başlatmadan OCR yapılır (`tr-TR` Türkçe öncelikli, çok sütunlu BOTAŞ form tablo satır eşlemeli).
- **Yerleşik PDF Sayfa Görüntüleme (`Windows.Data.Pdf` / `Quartz`):** `pypdfium2` yerel DLL yüklemesi engellendiğinde Windows üzerinde otomatik `Windows.Data.Pdf`, macOS üzerinde `Quartz` yedek rasterizer devreye girer.
- **Akıllı OCR Durum Yoklaması:** `/api/ocr/status` yoklamaları TTL önbellekli ve sıkı zaman aşımlı çalışır; `yenile` (`refresh=true`) ile manuel yeniden tarama yapılabilir.
- **Kurumsal Başlatıcı & SQLite Sertleştirmesi (`HydroWeb`):**
  - Kurumsal proxy (`HTTP_PROXY` / `HTTPS_PROXY`) ayarlarını atlatan yerel `127.0.0.1` + `instance_id` sağlık doğrulaması.
  - Çakışmasız varsayılan port aralığı (`18790–18829`, `SO_EXCLUSIVEADDRUSE`), şifreli veya ağ klasörlerinde otomatik SQLite `WAL → DELETE` geçişi.
  - Başlatıcı penceresine **Küçült** düğmesi ve yanlışlıkla kapatmaya karşı onay penceresi eklendi; Inno Setup kurulumunda yönetici izni olmadan kullanıcı bazlı (`CURRENTUSER`) kurulum desteklenir.

### 2. Yeni Program İkonu & Marka Sistemi
- Hidrostatik boru hattı testini temsil eden yeni vektörel ikon tasarımı (çelik boru kesiti, hidrostatik su seviyesi ve yüksek basınç manometresi):
  - macOS `.icns`, Windows `.ico`, PWA `site.webmanifest`, tarayıcı `favicon.svg` ve uygulama içi `<HydroLogo />` bileşeni.

### 3. BOTAŞ Form Denetimi, Yapışkan Tablolar & Excel'den Çoklu Satır Yapıştırma
- Sol menüdeki **BOTAŞ Test Bölümü Formları** ağacına `Tümü | Bulgulu | Eksik` hızlı filtre sekmeleri, üst karar şeridine `Formlar · Dolu/11` rozeti ve sağ panele `BOTAŞ Form Dosyası` ilerleme kartı eklendi.
- Geniş kabul ve izleme tablolarında (`FormBodyEditor`) yatay/dikey kaydırmada sabit kalan başlık ve ilk sütun, klavye erişilebilirliği (`role="region"`, `tabIndex`) ve Excel / Google Sheets'ten (`TSV`) çoklu satır/hücre yapıştırma desteği eklendi.
- Form sayfalarına kaydedilmemiş değişiklik uyarısı ve yükleme iskeleti eklendi.

### 4. Web Arayüzü & Erişilebilirlik İyileştirmeleri
- Tüm modal pencereler ve mobil yan menü çekmecesi yerel HTML `<dialog>` (`showModal()`, odak tuzağı, `Escape` ve arka plan tıklaması) altyapısına geçirildi.
- **Dashboard** üzerinde 3 adımlı denetim iş akışı çubuğu ve **OCR** sayfasında çevrimdışı sahte demo verisi yerine gerçek zamanlı bağlantı / zaman aşımı / HTTP tanı mesajları eklendi.
