# Neler Yeni — HYDRO v1.10.1 (What's New)

**Sürüm:** `v1.10.1` (`hidrostatik-test-v1.10.1`)  
**Tarih:** 2026-11-23

---

### 1. Güncelleyici TLS Sertifika Doğrulama Düzeltmesi
- **İşletim Sistemi Güven Deposu (`truststore` + `certifi`):** Paketli macOS (`.app`/`.dmg`) ve kurumsal Windows ortamlarında yeni sürümü listeledikten sonra indirme veya imza/checksum çekme sırasında yaşanan `CERTIFICATE_VERIFY_FAILED` hatası giderildi; indirme yöneticisi ve güncelleyici sıkı doğrulanmış (`CERT_REQUIRED`) macOS Keychain, Windows Certificate Store ve `certifi` CA zincirini kullanır.
- **Kurumsal Windows Yedek İndirme Hattı:** Şirket proxy/TLS denetimi altında Python `urlopen` başarısız olduğunda kurulum paketi, `.sha256.txt` ve Ed25519 `.sig` dosyaları da Windows TLS doğrulamalı PowerShell hattından indirilir.

### 2. v1.10.0 İçeriği (Özet)
- Şartname 12, 14.1–14.3, 15, 16 ve 17 operasyon/zaman serisi modelleri, segment bazlı SMYS ve gerçek 3D saha verileri.
- Raporlara `include_raw_ocr` eki (TXT/PDF/XLSX), form `If-Match`/`409` eşzamanlılık koruması, Docker `X-Hydro-Admin-Token` desteği ve `openapi.json` sözleşme kapısı.
