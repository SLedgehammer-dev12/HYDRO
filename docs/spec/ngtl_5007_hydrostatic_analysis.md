# NGTL 5007 Hidrostatik Test Analizi

> **Tarihsel Analiz ve Güncel Uyum Notu (Kasım 2026):** Bu doküman ilk aşama şartname boşluk analizini belgelemektedir. Sonraki iterasyonlarda `+2 °C` dolum kısıtı (`10.1`), 24 saatlik termal dengeleme (`12`, `domain/time_series.py`), basınçlandırma rampası ve 2 saatlik bekleme (`14.1–14.3`, `domain/pressurization_monitor.py`), basınç düşürme/boşaltma (`16–17`, `domain/post_test_operations.py`) ve 21. bölüm BOTAŞ saha formları (`015`–`023`, `KUR-001/002` + 5 ek form) **domain motoru ve web uygulamasında tamamlanmıştır** (masaüstü Tkinter UI kapsam dışı bırakılmıştır). Güncel doğrulama durumu için bkz. [DURUM.md](../../DURUM.md).

## Kaynak

- Ana kaynak: `4-NGTL 0-GN-P-002-5007 R4 Hidrostatik Test ve Icten Denetleme Sartnamesi`
- Ham metin extract'i: `docs/spec/ngtl_5007_raw_extract.txt`
- Kritik bolumler: PDF sayfa 7-10; dokuman bolumleri 10-17

## Yonetici Ozeti

Uygulama, sartnamenin hesap cekirdegi acisindan en kritik iki kismi olan
`13. Hava Icerik Testi` ve `15. Basinc Testi` formullerini ve kabul esiklerini
uyguladigi gibi, domain ve web katmaninda `+2 °C` hazirlik kontrolu (`10.1`),
24 saatlik termal dengeleme (`12`), basinc-hacim/bekleme izleme (`14.1-14.3`),
basinc dusurme/bosaltma (`16-17`) ve 16 BOTAŞ saha formu (`21`) is akislarini da
modellemektedir (masaustu Tkinter istemcisinde bu ek operasyon panelleri bagli degildir).

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

### 4. Operasyonel bolumlerin durum ozeti (Domain + Web vs Masaustu)

- `10.1 Hazirlik`: dis hava sicakligi `< +2 degC` dolum kisiti `evaluate_fill_temperature` ile domain ve web rapor/arayuzunde izlenmektedir.
- `10.4`: boru ve toprak probu yerlesimi saha kontrol listesi ve BOTAŞ form alanlari uzerinden takip edilir.
- `11`: doldurma pigi hizi (`evaluate_pig_speed`) ve su dolum raporu (`Form 017`) web uygulamasinda modellenmistir.
- `12`: minimum 24 saatlik termal dengeleme ve son iki ortalama arasinda `0.5 degC` kosulu `domain/time_series.py` ve `/api/calculations/thermal-balance` (`Form 018`) ile web'de aktif calisir.
- `14.1-14.3`: `domain/pressurization_monitor.py` ile modellendi (artis hizi <= 1 bar/dk, %95 SMYS sonrasi %0.2 basilan su siniri + durdurma, 2 saatlik bekleme/15 dk kayit). Web arayuzunde Basinc Degisim sayfasindaki Operasyonlar paneli kullanir; masaustu arayuzu bagli degil.
- `16-17`: `domain/post_test_operations.py` ile kontrol listesi olarak modellendi (16: vana <= 2 inc ve on kosullar; 17: pig, onay, cevre, 17.6 raporu, `Form 023`). Sartname bu bolumlerde baska sayisal kriter vermez.
- `21`: Web uygulamasinda 16 BOTAŞ saha formu (`015`–`023`, `KUR-001/002` + 5 ek form) ve OCR dossier aktarım matrisi aktif olarak uretilir ve kontrol edilir; masaustu UI kapsami disindadir.

## Gap Matrisi

| Sartname bolumu | Istek | Mevcut durum | Yorum |
| --- | --- | --- | --- |
| 5.5 | A ve B tablolari 1 bar / 1 degC artislara gore hazirlanmali | Var (`table_v1`) | Offline uretilen CSV grid (`0-40 degC`, `1-150 bar`) + kurumsal/GAIL referans tablolari |
| 10.1 | +2 degC altinda dolum kisiti | Domain + Web UI | `evaluate_fill_temperature` ile dogrulaniyor |
| 10.4 | Boru/toprak probu yerlestirme ve araliklar | Kismi (Checklist/Form) | Saha kontrol listesi ve BOTAŞ form alanlarinda izleniyor |
| 11.3-11.4 | Saatlik doldurma hacmi ve sicakligi kaydi | Web (`Form 017` + Zaman Serisi) | Masaustu Tkinter UI kapsami disi |
| 12 | 24 saat termal dengeleme ve `0.5 degC` kosulu | Domain + API (`/api/calculations/thermal-balance`) | Web `TimeSeriesPanel` ve `Form 018` ile bagli |
| 13 | Hava icerik testi formulu ve `%6` kabul esigi | Var | Domain + Web + Masaustu tam parity |
| 14.2 | Basinc-hacim iliskisi, `%0.2` esigi | Domain + API (`/api/calculations/pressurization-ramp`) | Web UI paneli ve oturum sonuc kaydi var; masaustu UI bagli degil |
| 14.3 | 2 saat bekleme, 15 dk kayit | Domain + API (`/api/calculations/pressure-hold`) | Web UI paneli ve oturum sonuc kaydi var; masaustu UI bagli degil |
| 15.2 | Basinc degisim formulu ve `(Pa-dP)<=0.3` | Var | Domain + Web + Masaustu tam parity |
| 16 | Basinc dusurme | Domain + API (`/api/calculations/depressurization`) | Web UI paneli ve `Form 023` bagli; masaustu UI bagli degil |
| 17 | Bosaltma, cevresel onlemler, raporlama | Domain + API (`/api/calculations/discharge`) | Web UI paneli ve `Form 023` bagli; masaustu UI bagli degil |
| 21 | Form bazli saha dokumantasyonu | Web (`16` BOTAŞ Formu + OCR Dossier) | `BOTAS_FORM_CATALOG` (`11` zorunlu + `5` ek form); masaustu UI kapsami disi |

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
