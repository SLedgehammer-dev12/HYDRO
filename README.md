# Hidrostatik Test Degerlendirme

[![Test](https://github.com/SLedgehammer-dev12/HYDRO/actions/workflows/test.yml/badge.svg)](https://github.com/SLedgehammer-dev12/HYDRO/actions/workflows/test.yml)
[![Lint](https://github.com/SLedgehammer-dev12/HYDRO/actions/workflows/lint.yml/badge.svg)](https://github.com/SLedgehammer-dev12/HYDRO/actions/workflows/lint.yml)
[![Release](https://github.com/SLedgehammer-dev12/HYDRO/actions/workflows/release.yml/badge.svg)](https://github.com/SLedgehammer-dev12/HYDRO/actions/workflows/release.yml)

Bu proje, `4-NGTL 0-GN-P-002-5007 R4 Hidrostatik Test ve Icten Denetleme Sartnamesi`
ile hizalanan bir masaustu hidrostatik test degerlendirme uygulamasidir.
Kod tabani build artefact'larindan ayrilmistir; kaynak kod, testler,
dokumantasyon, agent rolleri ve skill dosyalari ayri klasorlerde tutulur.

## Web Uygulamasi

Ayni domain motorunu kullanan, modern React + 3D saha sahnesi + OCR rapor kontrolu
iceren web uygulamasi `webapp/` altindadir.

```bash
python3 -m pip install -r requirements.txt -r requirements-ocr.txt -r webapp/requirements-web.txt
python3 webapp/run_web.py --host 127.0.0.1 --port 8080
# http://127.0.0.1:8080
```

- Durum ve dogrulama: `DURUM.md` ve `webapp/docs/implementation_status.md`
- Mimari / parity / API (`openapi.json`) / UX: `webapp/docs/`
- Veritabani destegi: CI tarafindan dogrulanan resmi varsayilan motor **SQLite (WAL)** modudur (`HYDRO_WEB_WORKERS=1` zorunludur); PostgreSQL (`psycopg[binary]`) harici kurulum gerektiren deneysel/opsiyonel hedeftir.
- Docker: `docker compose -f webapp/docker-compose.yml up --build` (Docker `0.0.0.0` icinde Veritabani Yonetimi ve Guncelleme uclarini kullanmak icin `HYDRO_LOCAL_ADMIN_TOKEN` tanimlayip Ayarlar ekranina `X-Hydro-Admin-Token` girin).

## Hizli Baslangic

- Uygulamayi calistir: `python Hidrostatik_Test_Chat.py`
- Gelistirme bagimliliklari: `python -m pip install -r requirements-dev.txt`
- Testleri calistir: `python -m unittest discover -s tests -p "test_*.py"`
- Kapsam raporu: `python -m coverage run --branch -m unittest discover -s tests -p "test_*.py"` ardindan `python -m coverage report`
- Lint / format: `ruff check .` ve `ruff format --check .`
- Tip kontrolu (bloklayici): `mypy hidrostatik_test/domain/` ve `mypy --ignore-missing-imports webapp/backend/app`
- Web guvenlik varsayilani: `webapp/run_web.py` varsayilan olarak yalnizca `127.0.0.1` loopback'e baglanir; kimlik dogrulamasiz `0.0.0.0` yayini engellenir (`HYDRO_ALLOW_REMOTE=1` acik onay gerektirir) ve DB/workspace yonetici uclari yerel loopback + `HYDRO_LOCAL_ADMIN_TOKEN` / kaynak `source_workspace_key` korumasi altindadir.
- Su ozelligi gridini uret: `python tools/generate_water_property_table.py`
- Windows release build al: `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`
- macOS release build al: `./build_dmg.sh`

## Klasor Yapisi

```text
HYDRO/
|-- Hidrostatik_Test_Chat.py
|-- HidrostatikTest.spec
|-- build_exe.ps1
|-- build_dmg.sh
|-- windows_manifest.xml
|-- runtime_entitlements.plist
|-- pyproject.toml
|-- requirements.txt
|-- requirements-dev.txt
|-- hidrostatik_test/
|   |-- app_metadata.py
|   |-- data/
|   |-- domain/
|   |-- services/
|   `-- ui/
|-- tests/
|-- webapp/
|   |-- backend/       # FastAPI + SQLAlchemy
|   |-- frontend/      # React 19 + Vite + Three.js
|   |-- docs/          # mimari, parity, API, UX, durum
|   |-- Dockerfile
|   `-- run_web.py
|-- docs/
|   |-- project_structure.md
|   |-- release.md
|   |-- testing.md
|   |-- codebase_map.md
|   |-- ui_ergonomics.md
|   `-- spec/
|-- agents/
|-- skills/
|-- tasks/
|-- build/          (PyInstaller calisma dizini, git'e girmez)
|-- dist/           (PyInstaller cikti dizini, git'e girmez)
`-- release/        (paketlenmis artefaktlar, git'e girmez)
```

`dist/` ve `release/` yerel build ciktilaridir: `dist/` PyInstaller'in ham
cikitisini (`dist/HidrostatikTest/` onedir, `dist/HidrostatikTest.app` macOS
bundle), `release/` ise yayina hazir `.zip`/`.dmg`, `.sha256.txt` ve release
notes dosyalarini tutar.

## Ana Bilesenler

- `hidrostatik_test/domain/`: hesap motoru, veri siniflari, kabul kriterleri
  - `hydrotest_core.py`: A/B katsayilari, hava icerik ve basinc testi degerlendirmesi
  - `water_properties.py`: A/B icin su ozelligi backend katmani; varsayilan CoolProp
  - `pressure_profile.py`, `pressurization.py`, `time_series.py`: basinc profili, %0.2 ilave su ve zaman serisi modelleri
  - `session_manager.py`, `coefficient_manager.py`, `units.py`: oturum, katsayi ve birim yonetimi
- `hidrostatik_test/data/`: ASME B36.10 katalogu, katsayi referans noktalari ve uretilmis su ozelligi grid dosyalari
- `hidrostatik_test/services/`: updater, indirme yoneticisi, SQLite veritabani ve rapor disa aktarma
  - `updater.py`: birincil `HYDRO` repo kaynagini, gecis doneminde ise `Programlar` legacy release kaynagini tarayabilir
  - `download_manager.py`: chunked indirme, duraklat/devam, SHA-256 dogrulama
  - `database.py`: SQLite (WAL) oturum ve zaman serisi kaliciligi
  - `report_export.py`: PDF (reportlab) ve Excel (openpyxl) rapor ciktilari
- `hidrostatik_test/ui/`: Tkinter arayuzu, wizard, dogrulama ve indirme dialogu
- `tools/generate_water_property_table.py`: 0-40 degC ve 1-150 bar grid uretici arac
- `tests/`: cekirdek, katalog, servis, veritabani ve arayuz regresyon testleri
- `docs/spec/`: sartname analizi, ham PDF extract'i ve dogrulama notlari
- `agents/`: proje icin onerilen agent rolleri
- `skills/`: bu repo icin hazirlanan Codex skill paketleri

## Onemli Dokumanlar

- `docs/spec/ngtl_5007_hydrostatic_analysis.md`: PDF hidrostatik test kisimlarinin derin analiz ve gap matrisi
- `docs/ui_ergonomics.md`: operator akisina yonelik ergonomi bulgulari ve oneriler
- `docs/project_structure.md`: neden bu klasor yapisinin secildigi
- `docs/release.md`: build, artefakt ve GitHub release sozlesmesi
- `docs/testing.md`: test protokolu, CI ve Xvfb notlari
- `docs/codebase_map.md`: uretilen sembol/bagimlilik/test haritasi
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
- Oturumlari SQLite ve JSON olarak kaydedip geri yukleyebilir; PDF/Excel rapor uretir
- Windows `.zip` ve macOS `.dmg` paketleri icin SHA-256 dogrulamali self-update akisina sahiptir
- `HYDRO` repo ayrisma gecisi icin legacy `Programlar` release kaynagina fallback destekler
- 253 web backend pytest testi (`%83` web kapsamı, CI `--fail-under=80` kapısı), 63 frontend Vitest testi (`21` dosya) ve `tests.test_report_ocr` (76 unittest, 1 skipped; Tk diyalog sınıfı hariç tam masaüstü paketi: 725 unittest OK) ile dogrulanir

Mevcut kod henuz sunlari tam modellememektedir:

- Web arayüzü 14.2 basınc-hacim/ilave su zaman serisini (`Form 018`), 16–17 boşaltma/basınç düşürme akışını (`Form 023`) ve 21. bölüm BOTAŞ saha formları setini (`015`–`023`, `KUR-001/002` + 5 ek form) modeller; bu akışların **masaüstü Tkinter UI** entegrasyonu ertelenmiştir.
- Kurum ici A/B tablosundaki 7 degC / 90-98 bar anomalisinin çalışma zamanı lineer köprü onarımı aktiftir; resmi veri güncellemesi kurum onayı beklemektedir.

## Muhendislik Notu

Bu arac, hesap ve on-kontrol destek araci olarak ele alinmalidir.
Saha karari veya nihai kabul oncesinde sirkete ozel prosedur,
ASME B31.8 ve resmi test kayitlari ile tekrar dogrulama gereklidir.
