# Changelog

## 1.5.4 - 2026-04-03

- Manuel guncelleme kontrolunde yeni surum bulundugunda kurulum akisi artik dogrudan teklif ediliyor; sadece acilista degil, kullanici talebinde de `indir/uygula` akisi basliyor.
- Guncelleme paketi hedef klasoru icin `farkli klasor sec / mevcut klasorle devam / iptal` secenekleri netlestirildi; onceki sessiz varsayilan davranis kaldirildi.
- Sag yardimci alan `Rehber / Durum / Kayit` sekmelerine ayrildi; uzun tek kolon nedeniyle olusan dikey yigilma azaltildi.
- Hava, basinc ve saha sekmeleri genis ekranlarda yatay alani daha iyi kullanacak sekilde iki kolonlu duzene yaklastirildi.
- UI ve updater testleri genisletildi; otomatik test paketi 73 teste cikarildi.

## 1.5.3 - 2026-04-02

- Arayuz kok seviyede ve sekme seviyesinde kaydirilabilir hale getirildi; buyuk ama dikey olarak uzun ekranlarda tasma davranisi azaltildi.
- `Boru Kesiti` bolumu sikistirildi; `Hat uzunlugu` ust satira alindi ve segment tablosu varsayilan olarak gizlendi.
- Ayrik `Uygulama / Guncelleme` paneli kaldirildi; guncelleme akisi menu uzerinden korunarak ana ekran sadeletirildi.
- `Canli Sema` paneli aktif sekme, segment geometri, checklist ilerlemesi, katsayi durumu ve pig hizina gore dinamik guncellenir hale getirildi.
- Guncelleme paketi icin kullanici secimli indirme klasoru ve kurulum onayi eklendi; updater bu klasoru dogrudan kullanir hale getirildi.
- UI ve updater regresyon testleri genisletildi; otomatik test paketi 71 teste cikarildi.

## 1.5.1 - 2026-03-31

- `pipe_catalog.py` icindeki ASME B36.10 katalogu, Wermac uzerindeki `part-a`...`part-k` tablolarina gore NPS `1/8`-`80` araliginda yeniden uretildi.
- Daha once eksik kalan buyuk cap aileleri (`48`, `52`, `56`, `60`, `64`, `68`, `72`, `76`, `80`) ve ara et kalinliklari dropdown seceneklerine eklendi.
- Schedule adi olmayan ama B36.10 tablosunda bulunan ara et kalinliklari UI'de `WT ... mm (B36.10)` biciminde secilebilir hale getirildi.
- Katalog testleri buyutulerek buyuk cap kapsamasi ve unlabeled wall-thickness satirlari otomatik olarak dogrulanir hale getirildi.
- Otomatik test paketi 42 teste cikarildi.

## 1.5.0 - 2026-03-31

- `A` ve `B` katsayilari icin `referans - hazir dogrulanmis nokta` secenegi eklendi.
- Hava testi ve basinc testi ekranlarina referans nokta acilir listeleri baglandi.
- Referans modunda secilen noktanin `A` degeri dogrudan, `B` degeri ise secili su beta referansi ve celik alpha ile olusturulur.
- Alan ipuclari, durum mesajlari ve rapor icerigi secilen referans noktasini gosterecek sekilde genisletildi.
- Basinc testi icin `A referans` akisi da otomatik test kapsamına alindi.
- Otomatik test paketi 41 teste cikarildi.

## 1.4.0 - 2026-03-31

- A katsayisi icin hava testi ve basinc testi ekranlarina `otomatik` ve `manuel` secenekleri eklendi.
- B katsayisi icin secim modeli checkbox yerine daha acik `otomatik` ve `manuel` secenegine donusturuldu.
- A ve B alanlarinin kilitli/duzenlenebilir davranisi secilen moda gore dinamik hale getirildi.
- Alan mesajlari ve aciklayici bilgi satirlari, secilen katsayi kaynagina gore guncellenecek sekilde zenginlestirildi.
- Rapor metnine A/B secenekleri de eklendi.
- UI regresyon testleri manuel A ve manuel B akislari ile genisletildi.
- Otomatik test paketi 38 teste cikarildi.

## 1.3.1 - 2026-03-30

- `4-NGTL 0-GN-P-002-5007 R4` sartnamesindeki hava icerik ve basinc testi veri giris tanimlari arayuze acikca yansitildi.
- Hava icerik testi icin `P = 1.0 bar` kosulu cekirdek seviyede dogrulanir hale getirildi.
- Basinc testinde `dT = Tilk - Tson` ve `Pa = Pilk - Pson` isaret tanimi UI ve rapora eklendi.
- `A` ve `B` katsayilari icin IAPWS-95 capraz kontrol noktalarini koruyan yeni cekirdek testleri eklendi.
- GitHub updater modulu, Python TLS zinciri hata verdiginde Windows PowerShell fallback'i kullanacak sekilde guclendirildi.
- `NGTL_5007_Validation.md` ile sartname, katsayi ve updater ariza notlari proje icine kaydedildi.
- Otomatik test paketi 36 teste cikarildi.

## 1.3.0 - 2026-03-30

- UI form temizleme ve karar karti sifirlama davranisi duzeltildi.
- `K` ve celik preset geri yukleme davranislari tutarli hale getirildi.
- Canli validasyon aktif sekmeye gore daraltildi.
- Rapor metni surum ve giris ozetleriyle genisletildi.
- `0 bar` su ozellik hesaplari cekirdek seviyede reddedildi.
- ASME B36.10 tabanli cap ve schedule secim listesi eklendi.
- Farkli et kalinliklarina sahip segmentli geometri modeli eklendi.
- Ust menu yapisi `Dosya`, `Rapor`, `Guncelleme`, `Hakkinda` olarak duzenlendi.
- GitHub Releases tabanli updater modulu eklendi.
- Acilista otomatik guncelleme kontrolu ve manuel guncelleme kontrolu eklendi.
- Windows `.exe` icin indir ve uygula akisi eklendi.
- Repo-ozel `hidrostatik-test-v*` release tag duzeni eklendi.
- Otomatik test paketi 33 teste cikarildi.
- Windows manifest, uygulama metadata'si ve release build scripti iyilestirildi.
- GitHub release'e uygun zip, checksum ve release note uretimi eklendi.
- Monorepo ve bagimsiz repo icin GitHub Actions workflow dosyalari eklendi.
