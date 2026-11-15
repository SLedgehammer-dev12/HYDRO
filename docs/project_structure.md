# Proje Yapisi

## Amac

Bu klasor yapisi, kaynak kod ile dagitim artefact'larini ayirarak
bakimi kolaylastirmak ve yeni bir gelistiricinin ya da agent'in
dogru dosyaya hizli ulasmasini saglamak icin kuruldu.

## Tasarim Kararlari

- Koddaki asil mantik `hidrostatik_test/` paketi altinda toplandi.
- Klasor kokunde sadece baslatici, build dosyalari ve ust seviye dokumanlar birakildi.
- Testler `tests/` altina tasinip runtime kodundan ayrildi.
- PDF kaynakli muhendislik analizleri `docs/spec/` altinda toplandi.
- Agent rolleri ve Codex skill'leri kaynak koddan ayri ama proje ile birlikte surdurulecek sekilde eklendi.
- Eski tek dosyali prototip ve eski calisma notlari `docs/legacy/` altina arsivlendi.
- Build ciktilari surum kontrolune alinmaz: `build/`, `dist/` ve `release/` `.gitignore` icindedir.
- Gelistirme araclarinin ayarlari `pyproject.toml` icinde; mypy ayarlari geriye donuk
  uyumluluk icin `mypy.ini` dosyasinda tutulur.

## Build Cikti Yapisi

PyInstaller ve paketleme scriptleri su dizinleri uretir (hepsi git disi):

```text
build/                                  PyInstaller calisma dizini
dist/
|-- HidrostatikTest/                   onedir cikti (spec/COLLECT)
|   |-- HidrostatikTest
|   `-- _internal/
`-- HidrostatikTest.app/               macOS bundle (BUNDLE)
    `-- Contents/
release/                                yayina hazir artefaktlar
|-- HidrostatikTest-v<surum>-windows-x64.zip
|-- HidrostatikTest-v<surum>-windows-x64.sha256.txt
|-- HidrostatikTest-v<surum>-windows-x64.zip.sha256.txt
|-- HidrostatikTest-v<surum>-windows-x64-RELEASE-NOTES.md
|-- HidrostatikTest-v<surum>-macos-universal.dmg
|-- HidrostatikTest-v<surum>-macos-universal.sha256.txt
|-- HidrostatikTest-v<surum>-macos-universal.dmg.sha256.txt
|-- HidrostatikTest-v<surum>-macos-universal-RELEASE-NOTES.md
|-- raw-dist-<run-id>/                  PyInstaller onefile cikti dongusu (Windows)
`-- build-temp-<run-id>/                version_info.txt ve gecici manifest
```

Windows paketinde zip koku `HidrostatikTest/` klasorudur; updater bu yapiyi bekler.
Ayrintili sozlesme icin `docs/release.md`.

## Hedef Veri Akisi

1. Operator arayuzu `Hidrostatik_Test_Chat.py` uzerinden acilir.
2. Baslatici `hidrostatik_test.ui.app.main()` fonksiyonunu cagirir.
3. UI, `domain/` altindaki hesap motoruna yalnizca dogrulanmis girdileri yollar.
4. Katalog ve referans veriler `data/` altindan alinir.
5. Update ve dagitim isleri `services/` katmaninda kalir.
6. Sonuclar UI karar karti, oturum kaydi (SQLite/JSON) ve rapor ciktilarina (PDF/Excel) yansitilir.

## Neden Bu Yapi Daha Az Kafa Karistirir

- `dist/` ve `release/` altindaki dosyalar artik kaynak kod zannedilmez.
- UI, hesap cekirdegi, katalog verisi ve servis mantigi fiziksel olarak ayridir.
- Test dosyalari ayni klasorde daginik durmadigi icin degisiklik etkisi daha kolay takip edilir.
- Agent ve skill dosyalari proje ici kurallari tekrar kullanilabilir hale getirir.
- `docs/spec/` altindaki analizler, formuller ve gap'ler ayni yerde bulunur.
