# NGTL 5007 Hidrostatik Test Analizi

## Kaynak

- Ana kaynak: `4-NGTL 0-GN-P-002-5007 R4 Hidrostatik Test ve Icten Denetleme Sartnamesi`
- Ham metin extract'i: `docs/spec/ngtl_5007_raw_extract.txt`
- Kritik bolumler: PDF sayfa 7-10; dokuman bolumleri 10-17

## Yonetici Ozeti

Mevcut uygulama, sartnamenin hesap cekirdegi acisindan en kritik iki kismi olan
`13. Hava Icerik Testi` ve `15. Basinc Testi` formullerini ve kabul esiklerini
uyguluyor. Buna karsin saha operasyonuna ait hazirlik, doldurma, 24 saatlik
kayit toplama, basinc-hacim izleme, basinc dusurme ve bosaltma is akislari
heniz sayisal ya da prosedel olarak modellenmis degil.

## Derin Bulgular

### 1. Hesaplanan kisimlar dogru eksene oturuyor

- `13. Hava Icerik Testi`: `Vp = ((0.884 x ri / s) + A) x 10^-6 x Vt x K`
  formulu uygulanmis.
- Basarisizlik kosulu, `Vpa`'nin teorik hacimden `%6 veya daha fazla` buyuk
  olmasi olarak sartnamede yaziyor.
- Kodda kabul siniri `1.06 * Vp` olarak modellenmis; bu, pratikte ayni sinira
  karsilik gelir.
- `15.2. Basinc Testi`: `dP = (B x dT) / ((0.884 x ri / S) + A)` formulu uygulanmis.
- Kabul kriteri `(Pa - dP) <= 0.3 bar` olarak kodda da yer aliyor.

### 2. Dokuman birim tarafinda tutarsizlik barindiriyor

- Bolum 13'te `A` aciklamasi `1/K` olarak geciyor.
- Bolum 15 sayfa devami `A` icin `1/bar` tanimi veriyor.
- Kod tabani bu belirsizligi `micro per bar` olceginde normalize ederek cozuyor.
- Bu karar teknik olarak savunulabilir, ancak saha oncesi prosedur veya kurum ici tablo ile son kez teyit edilmelidir.

### 3. Segmentli geometri muhendislik acisindan kullanisli, dokuman acisindan yaklasiktir

- Sartname formulde tek bir `ri` ve `s` kabul ediyor.
- Uygulama farkli et kalinligina sahip segmentleri tek test bolumu icinde modelleyebiliyor.
- Kod, `ri` ve `0.884*ri/s` terimini hacim agirlikli ortalama ile indirger.
- Bu, saha uygulamasinda kullanisli bir muhendislik yaklasimidir; ancak dokuman dogrudan bu indirgemeyi tarif etmez.
- Kritik projelerde bu yaklasim icin kurum ici metod notu yazilmasi gerekir.

### 4. Operasyonel bolumler buyuk oranda eksik

- `10. Hazirlik`: dis hava sicakligi `< +2 degC` ise dolum kisiti mevcut kodda izlenmiyor.
- `10.4`: boru ve toprak probu yerlesimi, mesafeler ve raporlama yapida yok.
- `11`: doldurma pigi, doldurma hizi, saatlik hacim ve sicaklik kaydi yok.
- `12`: minimum 24 saatlik termal dengeleme ve son iki ortalama arasinda `0.5 degC` kosulu yok.
- `14.2`: basinc-hacim iliskisi takibi ve `%0.2` ilave su esigi yok.
- `14.3`: iki saatlik bekleme ve 15 dakikalik kayit akisi yok.
- `16-17`: basinc dusurme ve bosaltma akislari yalnizca dokumante edilmeli backlog'unda duruyor.
- `21`: form bazli rapor ciktisi ve kabul raporu seti uretilmiyor.

## Gap Matrisi

| Sartname bolumu | Istek | Mevcut durum | Yorum |
| --- | --- | --- | --- |
| 5.5 | A ve B tablolari 1 bar / 1 degC artislara gore hazirlanmali | Kismi | Referans noktalar var, tam tablo uretimi yok |
| 10.1 | +2 degC altinda dolum kisiti | Yok | UI validasyonu eklenmeli |
| 10.4 | Boru/toprak probu yerlestirme ve araliklar | Yok | Sayisal rapor yapisi gerekir |
| 11.3-11.4 | Saatlik doldurma hacmi ve sicakligi kaydi | Yok | Zaman serisi modeli gerekir |
| 12 | 24 saat termal dengeleme ve `0.5 degC` kosulu | Yok | Yeni test adimi gerekir |
| 13 | Hava icerik testi formulu ve `%6` kabul esigi | Var | En iyi kapsanan kisim |
| 14.2 | Basinc-hacim iliskisi, `%0.2` esigi | Yok | Onemli operasyonel eksik |
| 14.3 | 2 saat bekleme, 15 dk kayit | Yok | Zaman damgali kayit gerekir |
| 15.2 | Basinc degisim formulu ve `(Pa-dP)<=0.3` | Var | Isaret tanimi UI'de gosteriliyor |
| 16 | Basinc dusurme | Yok | Surec ve check-list gerekli |
| 17 | Bosaltma, cevresel onlemler, raporlama | Yok | Surec ve rapor modulu gerekli |
| 21 | Form bazli saha dokumantasyonu | Yok | Raporlama backlog'u |

## Kodla Eslesen Noktalar

- `hidrostatik_test/domain/hydrotest_core.py`
  - Hava icerik testi denklemi
  - Basinc degisim testi denklemi
  - A ve B katsayilarinin olceklenmesi
  - `1.06` ve `0.3 bar` kabul sinirlari
- `hidrostatik_test/ui/app.py`
  - `dT = Tilk - Tson`
  - `Pa = Pilk - Pson`
  - aktif test akis rehberligi
  - karar karti ve rapor metni

## Gelistirme Onceligi

1. Termal dengeleme ve 24 saatlik test kayit yapisini veri modeli olarak eklemek
2. 14.2 basinc-hacim izleme ve `%0.2` alarm mantigini modele katmak
3. Bosaltma ve raporlama akislarini ayri servis olarak tanimlamak
4. Segmentli geometri indirgemesi icin kurum ici metod notu yazmak
5. A/B tablo uretimini otomatik referans tablo ciktilari ile desteklemek

## Not

Kod tabanina eklenen `Saha Kontrol` sekmesi, yukaridaki operasyonel bosluklari
heniz sayisal model olarak kapatmaz; ancak operatorun kritik kontrol noktalarini
tek tek isaretlemesine ve pig hizi limitini hizlica kontrol etmesine yardim eder.

A/B katsayilari icin ikinci dogrulama motoru arastirmasi, dagitim karari ve
CSV grid semasi `docs/spec/ab_backend_research.md` ile
`docs/spec/water_property_table_schema.md` icinde ayri olarak dokumante edilmistir.
