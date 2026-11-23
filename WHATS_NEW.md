# Neler Yeni — HYDRO v2.0.0 (What's New)

**Sürüm:** `v2.0.0` (`hidrostatik-test-v2.0.0`)  
**Tarih:** 2026-11-23

---

### 1. Sadeleştirilmiş & İçgüdüsel Yeni Arayüz
- **3 Fazlı Mühendislik Menüsü:** Sol gezinme **Başlangıç**, **Denetim & Hesap** ve **Çıktı & Araçlar** gruplarıyla sadeleştirildi; `Katsayılar` ve `Ayarlar` katlanabilir **Gelişmiş & Ayarlar** alanına alındı (`Alt+1..9` kısayolları korundu).
- **Daha Geniş Çalışma Alanı & 4 Adımlı İlerleme:** Çift sabit üst çubuk yığılması kaldırıldı (`DecisionStrip` yalnızca hesap ve form sekmelerinde görünür), sağ panel isteğe bağlı hale getirildi ve **Dashboard** üzerinde doğrudan tıklanabilir **4 adımlı ilerleme çubuğu** eklendi.

### 2. İlk Kullanım Rehberi & 5 Adımlı Demo Turu
- **Kullanıcı Onaylı Başlangıç Kartı:** İlk açılışta ekranı kilitlemeden **"Rehberli Demo Turunu Başlat"**, **"Kendi Projemle Başla"** veya **"Şimdi değil"** seçeneklerini sunar.
- **Etkileşimli Demo Turu:** Tek tıkla örnek boru hattı projesi oluşturarak **Proje → Geometri & 3D → OCR → Hava/Basınç Testi → Raporlar** adımlarını uygulamalı tanıtır; tur sonunda örnek projeyi tek tıkla tutabilir veya temizleyebilirsiniz (`?` Yardım penceresinden dilediğiniz zaman tekrar açılır).

### 3. Altyapı, TLS Güvenilirliği & Şartname Uyumu
- Şartname 12, 14.1–14.3, 15, 16 ve 17 operasyon/zaman serisi modelleri, segment bazlı SMYS, `include_raw_ocr` rapor eki, form `If-Match`/`409` eşzamanlılık koruması, Docker `X-Hydro-Admin-Token` ve macOS/Windows `truststore` + `certifi` güncelleyici TLS sertifika doğrulaması dahildir.
