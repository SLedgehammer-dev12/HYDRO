# Web Uygulamasi - Alinan Kararlar

Tarih: 2026-11-15
Kaynak: `architecture.md` §18 acik kararlar.

1. **Kot profili ve ekipman konumlari:** Opsiyonel `profile_points[]` ve `equipment[]`
   web-only girdi olarak eklenecek. Yoksa 4 kot noktasindan yaklasik sahne uretilir ve
   `warnings` ile "yaklasik sahne" etiketi gosterilir.
2. **Taranmis PDF rasterizer:** `pdf2image + Poppler` opsiyonel; AGPL `PyMuPDF`
   kullanilmayacak. Metin katmani yoksa ve rasterizer yoksa kodlu hata.
3. **SMYS manuel override:** Izinli; gerekce zorunlu ve `audit_events`'e yazilir.
4. **Hidrolik yogunluk:** Masaustu parity icin 15 °C sabit yogunluk korunur; UI'da not.
5. **t_initial / t_final:** Basinc sekmesinde ayri alanlar; `dT = t_initial - t_final`
   turetilir, kullanici dT'yi override edebilir.
6. **Canli otomatik kayit:** Web'de varsayilan kapali; kullanici "Kaydet" der veya
   oturum bazli otomatik kayit ayari acar.
7. **OCR onayi:** Otomatik uygulama yok; alan bazli onay + ayri "Uygula" adimi + audit.
8. **Rapor kimligi:** `report_no`, `operator`, `date`, `section_id` oturum bazli
   Raporlar sekmesinde girilir; export payload'ina eklenir.
9. **Auth/rol:** MVP'de yok; OIDC ve iki-kisi kurali sonraki faz. Simdilik anonim
   workspace anahtari.
10. **Parity fixture surumu:** CI'da `CoolProp==7.0.0`; yerel 7.2.0 farki icin
    `rel_tol=1e-6` ve gerekli yerlerde 1e-9 saf aritmetik toleransi.
