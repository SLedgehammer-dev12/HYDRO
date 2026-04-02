# UI Ergonomi Notlari

## Gozlenen Mevcut Gucler

- Geometri, katsayi, karar ve oturum kaydi ayni ekranda gorulebiliyor.
- A/B katsayi modlari operatoru otomatik, manuel ve referans akislari arasinda yonlendirebiliyor.
- Karar karti sonucu `BASARILI / BASARISIZ / DOGRULANAMADI` olarak ayri renklerle veriyor.
- Segmentli geometri tablosu, tek kesit varsayiminin yetmedigi sahalarda ise yariyor.

## Mevcut Zorluklar

- Operator once hangi alanlari doldurmasi gerektigini her zaman tek bakista anlayamayabilir.
- Isaret konvansiyonlari (`dT`, `Pa`) unutulursa yanlis veri girisi riski dogar.
- Sartname operasyonel olarak doldurma, dengeleme, basinclandirma ve test seklinde ilerlerken,
  mevcut arayuz daha cok iki hesap ekranina odaklaniyor.
- 24 saatlik kayitlar ve saha form mantigi olmadigi icin hesap ile saha adimi arasinda bosluk var.

## Simdi Uygulanan Iyilestirmeler

- Arayuze aktif sekmeye gore degisen bir `Akis Kontrol Listesi` eklendi.
- Ayrica yeni bir `Saha Kontrol` sekmesi eklendi.
- Bu sekmede:
  - sartnameden turetilmis operasyonel kontrol noktalarinin isaretlenebildigi bir kontrol tablosu,
  - pig hizi hesaplayicisi,
  - A/B tespit yontemlerinin kisa ozeti bulunur.
- Kok ekran ve tum sekmeler artik kaydirilabilir; buyuk ama dikey olarak uzun ekranlarda tasma sorunu azaltilir.
- `Boru Kesiti` bolumu sikistirildi; `Hat uzunlugu` ust satira alindi ve segment tablosu varsayilan olarak gizlendi.
- `Uygulama / Guncelleme` paneli ana ekrandan kaldirildi; ayni islevler menude birakildi.
- Sag yardimci alan tek uzun kolon yerine `Rehber / Durum / Kayit` sekmeleriyle parcali hale getirildi; dikey yigilma azaltildi.
- Hava, basinc ve saha sekmeleri yatay alani daha etkin kullanacak sekilde iki kolonlu duzene yaklastirildi.
- `Yan Paneli Gizle/Goster` kontrolu eklendi; hesap girisine odaklanmak isteyen operator calisma alanini tek kolon moduna alabilir.
- `Bilgi Notlarini Goster/Gizle` kontrolu eklendi; varsayilan ekranda statik aciklama metinleri gizlenerek gereksiz dikey yuk azaltildi.
- Sag panelde `Canli Sema` eklendi:
  - aktif sekmeye gore hesap akisini cizer,
  - sekmeler arasi tiklanabilir gezinme sunar,
  - geometri hazirsa segmentleri gosterir,
  - saha sekmesinde checklist ilerlemesi ve pig hizini yansitir.
- Guncelleme paketinin indirilecegi klasor secilebilir hale getirildi ve secili yol UI'de ozetlenir.
- Manuel update kontrolunde `yeni surum bulundu` akisi artik tek seferde `indir/uygula` teklifine gider; ayrica kullaniciya hedef indirme klasorunu secme veya mevcut klasorle devam etme secenegi sunulur.
- Saha checklisti icin ilerleme cubugu eklendi; operator tum maddeleri ne kadar tamamladigini tek bakista gorur.

Bu iyilestirmeler operatora her test icin hangi sirayla ilerlemesi gerektigini
tek bakista gosterir ve testin uygulanma safhasindaki kritik adimlarin
unutulmasini azaltir:

- Hava icerik testi icin: geometri -> A -> P/K/Vpa -> degerlendirme
- Basinc testi icin: geometri -> A/B -> dT/Pa -> degerlendirme

Bu degisiklikler hesap mantigina dokunmadan kullanim belirsizligini azaltir.

## Sonraki Ergonomi Adimlari

### Yuksek deger / dusuk risk

- Zorunlu alanlar tamamlanmadan `Degerlendir` butonunu pasiflestir.
- `Pa` ve `dT` alanlarinin hemen altina isaret formullerini sabit metin olarak koy.
- Katsayi alanlarinda son hesaplanan kaynak bilgisini goster.
- `Raporu Kaydet` icin hava/basinc testine ozel hazir basliklar kullan.
- `Canli Sema` icinde hesap oncesi / hesaplandi / stale durumunu renkli durum rozetleriyle goster.
- `Guncelleme` menusu acildiginda secili indirme klasorunu ilk satirda pasif bilgi olarak goster.

### Yuksek deger / orta risk

- Akisi dort safhali bir wizard haline getir:
  `Geometri -> Doldurma/Dengeleme -> Hesap -> Kabul`
- 24 saatlik test verisini satir satir girilen bir tabloya tasima
- PDF'deki form numaralarina gore rapor sablonu uretme
- Segment ekleme ekranina toplu paste veya CSV iceri alma
- Sekme bazli kayit setleri olusturup ayni oturumda birden fazla test kaydini acik tutma
- `Canli Sema` panelini mini trend grafikleri ile destekleme: `P`, `T`, `Vpa`, `Pa`

### Guvenlik ve operator hatasi acisindan kritik

- `10.1` icin dis hava sicakligi `< +2 degC` ise uyari / blokaj
- `13` icin `P=1.0 bar` zorunlulugunu alan seviyesinde kilitleme
- `15` icin `Pa` ve `dT` isaret hatasini anomali kontrolu ile yakalama
- Sonuc kartinda kabul kriterinin matematiksel ifadesini her zaman gostermek
- Update uygulamasi oncesi hedef klasor ve kaynak repo bilgisini ikinci bir onay penceresinde netlestirmek

## Tasarim Ilkesi

Bu uygulama genel amacli bir hesap makinesi gibi degil,
operatorde prosedure sadik kalma davranisi olusturan bir denetimli akis gibi
tasarlanmalidir. Yani sadece sonuc gostermek yetmez; kullaniciyi dogru siraya,
dogru birime ve dogru isaret tanimina zorlamak gerekir.
