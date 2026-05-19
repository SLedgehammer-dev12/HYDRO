# Release Akisi

## Komut

- `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`

Opsiyonel bayraklar:

- `-SkipTests`
- `-SkipArchive`

## Uretilen Ciktilar

- `release\HidrostatikTest-v<surum>-windows-x64.zip`
- `release\HidrostatikTest-v<surum>-windows-x64.sha256.txt`
- `release\HidrostatikTest-v<surum>-windows-x64-RELEASE-NOTES.md`
- `release\raw-dist-<run-id>-primary\HidrostatikTest\HidrostatikTest.exe`

## Kaynak Dosyalar

- Build girisi: `Hidrostatik_Test_Chat.py`
- Metadata: `hidrostatik_test/app_metadata.py`
- Manifest: `windows_manifest.xml`
- Testler: `tests/`

## GitHub Release

- Tag formati: `hidrostatik-test-v<surum>`
- Workflow: `.github/workflows/windows-release.yml`
- Release body icin build script'in urettigi release note dosyasi kullanilir.

## Dagitim Notu

Kaynak kod ile paketlenmis artefact ayrilmistir.
Runtime build ornegi `dist/windows/` altinda tutulur; asıl release paketleri ise
`build_exe.ps1` ile `release/` altinda yeniden uretilir.
