# Hidrostatik Test Degerlendirme

Bu proje, `4-NGTL 0-GN-P-002-5007 R4 Hidrostatik Test ve Icten Denetleme Sartnamesi`
ile hizalanan bir masaustu hidrostatik test degerlendirme uygulamasidir.
Kod tabani artik build artefact'larindan ayrilmistir; kaynak kod, testler,
dokumantasyon, agent rolleri ve skill dosyalari ayri klasorlerde tutulur.

## Hizli Baslangic

- Uygulamayi calistir: `python Hidrostatik_Test_Chat.py`
- Testleri calistir: `python -m unittest discover -s tests -p "test_*.py"`
- Su ozelligi gridini uret: `python tools/generate_water_property_table.py`
- Windows release build al: `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`

## Klasor Yapisi

```text
Hidrostatik_Test/
|-- Hidrostatik_Test_Chat.py
|-- hidrostatik_test/
|   |-- app_metadata.py
|   |-- data/
|   |-- domain/
|   |-- services/
|   `-- ui/
|-- tests/
|-- docs/
|   |-- project_structure.md
|   |-- ui_ergonomics.md
|   `-- spec/
|-- agents/
|-- skills/
|-- tasks/
`-- dist/
```

## Ana Bilesenler

- `hidrostatik_test/domain/`: hesap motoru, veri siniflari, kabul kriterleri
- `hidrostatik_test/domain/water_properties.py`: A/B icin su ozelligi backend katmani; varsayilan CoolProp kullanilir
- `hidrostatik_test/data/`: ASME B36.10 katalogu, katsayi referans noktalari ve uretilmis su ozelligi grid dosyalari
- `hidrostatik_test/services/`: updater ve servis islemleri
- `hidrostatik_test/services/updater.py`: birincil `HYDRO` repo kaynagini, gecis doneminde ise `Programlar` legacy release kaynagini tarayabilir
- `hidrostatik_test/ui/`: Tkinter arayuzu
- `tools/generate_water_property_table.py`: 0-40 degC ve 1-150 bar grid uretici arac
- `tests/`: cekirdek, katalog, arayuz ve updater regresyon testleri
- `docs/spec/`: sartname analizi, ham PDF extract'i ve dogrulama notlari
- `agents/`: proje icin onerilen agent rolleri
- `skills/`: bu repo icin hazirlanan Codex skill paketleri

## Onemli Dokumanlar

- `docs/spec/ngtl_5007_hydrostatic_analysis.md`: PDF hidrostatik test kisimlarinin derin analiz ve gap matrisi
- `docs/ui_ergonomics.md`: operator akisina yonelik ergonomi bulgulari ve oneriler
- `docs/project_structure.md`: neden bu klasor yapisinin secildigi
- `docs/spec/ab_backend_research.md`: A/B ikinci dogrulama motoru arastirmasi ve dagitim karari
- `docs/spec/water_property_table_schema.md`: CSV semasi ve table/interpolation backend akisi
- `tasks/todo.md`: aktif teknik backlog ve dogrulama kaydi
- `tasks/lessons.md`: tekrar eden hata kaliplari ve korunma notlari

## Uygulama Kapsami

Mevcut kod:

- Hava icerik testini degerlendirir
- Basinc degisim testini degerlendirir
- `Saha Kontrol` sekmesinde kritik uygulama kontrol noktalarini checklist olarak izletir
- Pig hizi hesaplayip secili sartname limitine gore asim kontrolu yapar
- A ve B katsayilari icin otomatik, manuel ve referans modlari sunar
- `BOTAS referans tablosu` ve `GAIL referans tablosu` seceneklerini tablo modunda ayri veri kaynaklari olarak sunar
- A ve B icin backend soyutlamasi ile gelecekte dagitima uygun ikinci dogrulama motoru eklenmesine hazirdir
- `table_v1` backend ile offline uretilen CSV grid uzerinden interpolasyon yapabilir
- Kurum ici `A/B` kontrol tablosu ile hesaplanan katsayilari ayni noktada karsilastirabilir
- Segmentli geometri modelini destekler
- API 5L PSL2 malzeme secimi ile SMYS degerini otomatik atar ve basinc penceresini buna gore hesaplar
- Canli basinc kontrolu, kot semasi ve 5007 tek kesit limit uyari mantigina sahiptir
- Windows self-update akisina sahiptir
- `HYDRO` repo ayrisma gecisi icin legacy `Programlar` release kaynagina fallback destekler
- 120 otomatik test ile dogrulanir

Mevcut kod henuz sunlari tam modellememektedir:

- 24 saatlik saha kayitlarinin zaman serisi olarak tutulmasi
- 14.2'deki basinc-hacim izleme ve `%0.2` esigi
- 16-17. bolum bosaltma ve basinc dusurme operasyonlarinin sayisal/surecsel akisi
- 21. bolum form bazli saha rapor seti

## Muhendislik Notu

Bu arac, hesap ve on-kontrol destek araci olarak ele alinmalidir.
Saha karari veya nihai kabul oncesinde sirkete ozel prosedur,
ASME B31.8 ve resmi test kayitlari ile tekrar dogrulama gereklidir.
