# Neler Yeni — HYDRO v1.10.0 (What's New)

**Sürüm:** `v1.10.0` (`hidrostatik-test-v1.10.0`)  
**Tarih:** 2026-11-23

---

### 1. Şartname 12, 14, 15, 16 ve 17 Operasyon & Zaman Serisi Modelleri
- **24 Saatlik Termal Dengeleme & Basınç Tutma İzleme:** `TimeSeriesPanel` / `TimeSeriesChart` ve `OperationsPanel` ile ardışık 4 saatlik sıcaklık dengesi (`0,5 °C`), `%95 SMYS` sonrası `%0,2` ilave su durdurma kuralı, 2 saatlik bekleme ve basınç düşürme/boşaltma kontrolleri (`Form 018`, `021`, `023` senkronizasyonu) üretime alındı.
- **Segment Bazlı SMYS & Gerçek 3D Saha Verisi:** Boru segmentlerine bağımsız malzeme kalitesi/SMYS atama, gerçek kot profili (`profile_points[]`), ekipman konumları (`equipment[]`) ve masaüstü JSON snapshot içe aktarma eklendi.

### 2. Raporlar, OCR, CAD ve BOTAŞ Form Güvenilirliği
- **Raporlara Ham OCR Özeti Eki (`include_raw_ocr`):** Raporlar ekranından TXT, PDF ve XLSX çıktısına kaynak dosya ve ham OCR özeti (`OCR_Ham_Metin` sayfasında formül enjeksiyonu korumasıyla) eklenebilir.
- **Form Eşzamanlılık Koruması:** BOTAŞ saha formlarında `ETag` / `If-Match` revizyon denetimi ve `409` çakışma çözme akışı eklendi; sekme değişikliğinde devam eden sunucu OCR analizi bozulmadan istemci yoklaması temizlenir.
- **Geliştirilmiş PDF/CAD Ayrıştırma & Docker Tesseract:** Noktalı ondalık ayrıştırma, PDF satır hizalama, CAD boru dış çapı okuma ve Docker imajında Türkçe/İngilizce Tesseract OCR desteği eklendi.

### 3. Güvenlik, Performans ve Operasyon Sertleştirmesi
- **Docker Veritabanı & Güncelleme Yöneticisi Token Desteği:** Ayarlar paneline yalnızca oturum belleğinde (`sessionStorage`) tutulan `X-Hydro-Admin-Token` girişi eklendi.
- **Çevrimdışı & Bellek Korumaları:** Geçici ağ hatalarında sessiz demo düşüşü engellendi; `localStorage` kota aşımı uyarısı, akışlı dosya yükleme/arşiv indirme, `24` saatlik eski rapor temizliği, SQLite tek-işçi kilidi (`HYDRO_WEB_WORKERS=1`) ve veritabanı geri yüklemede `503` bakım bariyeri eklendi.
- **Makine Doğrulanabilir API & CI Kalite Kapıları:** `openapi.json` (`87` yol, `101` operasyon) ve web backend için `%80` kapsam kapısı devreye alındı.
