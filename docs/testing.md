# Test Protokolu

## Otomatik Dogrulama

Her anlamli degisiklikten sonra:

- `python -m unittest discover -s tests -p "test_*.py"`
- `python tools/generate_water_property_table.py`
- `python -m py_compile Hidrostatik_Test_Chat.py hidrostatik_test\\app_metadata.py hidrostatik_test\\data\\coefficient_reference.py hidrostatik_test\\data\\pipe_catalog.py hidrostatik_test\\data\\water_property_table.py hidrostatik_test\\domain\\hydrotest_core.py hidrostatik_test\\domain\\operations.py hidrostatik_test\\domain\\water_properties.py hidrostatik_test\\services\\updater.py hidrostatik_test\\services\\water_property_table_builder.py hidrostatik_test\\ui\\app.py tools\\generate_water_property_table.py tests\\test_hydrotest_core.py tests\\test_operations.py tests\\test_pipe_catalog.py tests\\test_ui_workflow.py tests\\test_water_properties.py tests\\test_water_property_table.py tests\\test_updater.py`
- `python -c "import sys; sys.path.insert(0, r'.'); import Hidrostatik_Test_Chat; import hidrostatik_test.app_metadata; import hidrostatik_test.domain.hydrotest_core; import hidrostatik_test.domain.water_properties; import hidrostatik_test.data.pipe_catalog; import hidrostatik_test.services.updater; print('import-ok')"`

## Build Kontrolu

- `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`
- `release\HidrostatikTest-v<surum>-windows-x64.zip` olusmali
- `release\HidrostatikTest-v<surum>-windows-x64.sha256.txt` olusmali
- `release\HidrostatikTest-v<surum>-windows-x64-RELEASE-NOTES.md` olusmali

## Manuel Smoke Test

1. Hava icerik testinde A hesapla, P=1.0 bar ve Vpa ile degerlendirme yap.
2. Basinc testinde helper ile B hesapla, `dT` ve `Pa` girip sonucu kontrol et.
3. Sekmeler arasi gecince akis kontrol listesinin dogru guncellendigini kontrol et.
4. Segment ekleme/silme ile geometri ozetinin dogru degistigini kontrol et.
5. Guncelleme menusu komutlarinin beklenen pencere ve durum metinlerini verdigini kontrol et.

## Not

Windows'ta `py_compile` gecici dosya kilidi nedeniyle nadiren problem cikarabilir.
Bu durumda unit test + import smoke check + PyInstaller build sonucu ana kriterdir.
