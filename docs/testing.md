# Test Protokolu

## Otomatik Dogrulama

Her anlamli degisiklikten sonra (Windows PowerShell'de `python`, macOS/Linux'ta `python3`):

- `python -m unittest discover -s tests -p "test_*.py"`
- `python -m coverage run --branch -m unittest discover -s tests -p "test_*.py"` ve
  `python -m coverage report`
  - Kapsam `pyproject.toml` icindeki `[tool.coverage.run]` ayariyla yalnizca
    `hidrostatik_test` kaynagini olcer; esik `fail_under = 65` (branch dahil olcum ~%70).
- `ruff check hidrostatik_test tests`
- `ruff format --check hidrostatik_test tests`
- `mypy hidrostatik_test/domain/` (bloklayici tip kapisi)
- `python tools/generate_water_property_table.py`
- `python -m py_compile` ile degisen moduller (build scriptleri tam listeyi calistirir)
- `python -c "import sys; sys.path.insert(0, r'.'); import Hidrostatik_Test_Chat; import hidrostatik_test.app_metadata; import hidrostatik_test.domain.hydrotest_core; import hidrostatik_test.domain.water_properties; import hidrostatik_test.data.pipe_catalog; import hidrostatik_test.services.updater; print('import-ok')"`

Test paketi 651 otomatik test icerir. Yeni modul eklenirken
`build_exe.ps1` icindeki `py_compile` listesi ve `HidrostatikTest.spec` veri
girdileri de guncellenmelidir.

## CI (GitHub Actions)

- `.github/workflows/test.yml`: `ubuntu-latest`, `macos-latest`, `windows-latest`
  x Python `3.12`, `3.13` matrisi.
  - Linux'ta testler `xvfb-run --auto-servernum` ile calisir; Tkinter UI testleri
    sanal ekran olmadan acilmaz.
  - Windows/macOS'ta shell'e ozel bash sozdizimi kullanilmaz; adimlar ayridir.
  - Kapsam raporu `coverage.xml` artefakti olarak yuklenir.
- `.github/workflows/lint.yml`: ruff lint + format kontrolu, domain mypy (bloklayici)
  ve tam paket mypy (bilgilendirici, JUnit raporu artefakt olarak yuklenir).
- `.github/workflows/release.yml`: testler Linux'ta Xvfb ile kosar, ardindan Windows
  ve macOS build job'lari artefakt sozlesmesini ve SHA-256 kayitlarini dogrular.

Araclarin surumleri `requirements-dev.txt` icinde pinlidir (ruff 0.15.15, mypy 2.1.0);
CI ile yerel ortam ayni davranir.

## Build Kontrolu

Windows:

- `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`
- `release\HidrostatikTest-v<surum>-windows-x64.zip` olusmali
- Zip icinde `HidrostatikTest\HidrostatikTest.exe` bulunmali (updater sozlesmesi)
- `release\HidrostatikTest-v<surum>-windows-x64.sha256.txt` olusmali
- `release\HidrostatikTest-v<surum>-windows-x64.zip.sha256.txt` olusmali
- `release\HidrostatikTest-v<surum>-windows-x64-RELEASE-NOTES.md` olusmali
- Checksum dogrulamasi: `Get-FileHash .\release\*.zip -Algorithm SHA256`

macOS:

- `./build_dmg.sh`
- `release/HidrostatikTest-v<surum>-macos-universal.dmg` olusmali
- `release/HidrostatikTest-v<surum>-macos-universal.sha256.txt` ve
  `...-macos-universal.dmg.sha256.txt` olusmali
- `codesign --verify --deep --strict dist/HidrostatikTest.app` gecmeli
- `hdiutil verify release/*.dmg` gecmeli

## Manuel Smoke Test

1. Hava icerik testinde A hesapla, P=1.0 bar ve Vpa ile degerlendirme yap.
2. Basinc testinde helper ile B hesapla, `dT` ve `Pa` girip sonucu kontrol et.
3. Sekmeler arasi gecince akis kontrol listesinin dogru guncellendigini kontrol et.
4. Segment ekleme/silme ile geometri ozetinin dogru degistigini kontrol et.
5. Guncelleme menusu komutlarinin beklenen pencere ve durum metinlerini verdigini kontrol et.
6. Zip paketini bos bir klasore acip `HidrostatikTest.exe` ile uygulamanin acildigini dogrula.

## Not

Windows'ta `py_compile` gecici dosya kilidi nedeniyle nadiren problem cikarabilir.
Bu durumda unit test + import smoke check + PyInstaller build sonucu ana kriterdir.
`py_compile` basarisizligi build'i durdurmaz; PyInstaller basarisizligi durdurur.
