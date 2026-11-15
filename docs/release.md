# Release Akisi

## Surum Kaynagi

Tek kaynak `hidrostatik_test/app_metadata.py` icindeki `APP_VERSION` degeridir.
Build scriptleri, PyInstaller spec dosyasi, Windows manifesti ve GitHub release
tag'i bu degerden turetilir. Surum artirilirken yalnizca bu dosya guncellenir.

## Komutlar

- Windows: `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`
- macOS: `./build_dmg.sh`

Windows script bayraklari:

- `-SkipTests` (unit test + import smoke check atlanir)
- `-SkipArchive` (yalnizca PyInstaller ciktisi uretilir, zip/checksum/notes yazilmaz)

macOS script ortam degiskenleri:

- `CODESIGN_IDENTITY="Developer ID Application: ... (TEAMID)"` gercek imza icin; bos ise ad-hoc imzalanir.
- `NOTARY_PROFILE="hidro-notary"` Developer ID + `notarytool` profili varsa DMG notarize edilip staple edilir.
- `HIDROSTATIK_TARGET_ARCH=universal2|arm64|x86_64|native` mimari secimi (varsayilan: evrensel Python'da universal2).

## Artefakt Sozlesmesi

Windows (`release/` altinda):

- `HidrostatikTest-v<surum>-windows-x64.zip`
  - Zip koku `HidrostatikTest/` klasorudur; icinde `HidrostatikTest.exe` bulunur.
  - Auto-updater bu yapiyi bekler (`stage/HidrostatikTest/HidrostatikTest.exe`).
- `HidrostatikTest-v<surum>-windows-x64.sha256.txt`
- `HidrostatikTest-v<surum>-windows-x64.zip.sha256.txt`
- `HidrostatikTest-v<surum>-windows-x64-RELEASE-NOTES.md`

macOS (`release/` altinda):

- `HidrostatikTest-v<surum>-macos-universal.dmg`
- `HidrostatikTest-v<surum>-macos-universal.sha256.txt`
- `HidrostatikTest-v<surum>-macos-universal.dmg.sha256.txt`
- `HidrostatikTest-v<surum>-macos-universal-RELEASE-NOTES.md`

Iki checksum dosyasi ayni icerigi tasir: `<hash>  <dosya adi>`.

- `<artefakt>.sha256.txt` bicimi (ornek: `...-windows-x64.zip.sha256.txt`) updater
  tarafindan indirilir; updater checksum adresini `<asset-url>.sha256.txt` olarak kurar.
- Uzantisiz ad (`...-windows-x64.sha256.txt`) dokumante edilen yayin sozlesmesidir ve
  `sha256sum -c` ile dogrulanabilir.

## Build Davranisi

- PyInstaller runtime hook (`hidrostatik_test/_pyinstaller_hook.py`) hem PowerShell
  hem spec yolunda kullanilir.
- Windows manifest surumu build sirasinda `APP_VERSION` degerinden turetilip gecici
  manifest kopyasina yazilir; `windows_manifest.xml` statik surum tutmaz.
- PyInstaller basarisiz olursa build fail eder; sessiz "plain fallback" paket
  yayinlanmaz.
- macOS paketi `codesign --verify --deep --strict` ile dogrulanir; Developer ID yoksa
  ad-hoc imza uygulanir, `spctl` reddi beklenen durum olarak uyarilir ve notarization
  atlanir.
- `build_dmg.sh` spec dosyasini yamalamaz; surum bilgisi spec icinde okunur.

## Lokal Dogrulama

Windows (PowerShell):

```powershell
Get-FileHash .\release\HidrostatikTest-v<surum>-windows-x64.zip -Algorithm SHA256
Get-Content .\release\HidrostatikTest-v<surum>-windows-x64.sha256.txt
Expand-Archive .\release\HidrostatikTest-v<surum>-windows-x64.zip -DestinationPath .\verify
Test-Path .\verify\HidrostatikTest\HidrostatikTest.exe
```

macOS:

```bash
shasum -a 256 release/HidrostatikTest-v<surum>-macos-universal.dmg
cat release/HidrostatikTest-v<surum>-macos-universal.sha256.txt
hdiutil verify release/HidrostatikTest-v<surum>-macos-universal.dmg
codesign --verify --deep --strict --verbose=2 dist/HidrostatikTest.app
spctl -a -vv dist/HidrostatikTest.app   # ad-hoc imzada reddedilir (beklenen)
```

## GitHub Release

- Workflow: `.github/workflows/release.yml`
- Tag formati: `hidrostatik-test-v<surum>` (ornek: `hidrostatik-test-v1.7.3`)
- `version-gate` job'i `APP_VERSION` ile tag adinin birebir eslestigini dogrular;
  uyusmazsa release durur.
- `test` job'i Linux'ta `xvfb-run` ile UI testlerini calistirir ve kapsam esigini uygular.
- `build-windows` / `build-macos` job'lari artefaktlari uretir, zip/DMG icerigini ve
  SHA-256 kayitlarini dogrular, ardindan artefakt olarak yukler.
- `publish-release` job'i artefaktlari indirir, `sha256sum -c` ile yeniden dogrular ve
  GitHub release'e `.zip`/`.dmg`, `.sha256.txt` dosyalari ve release notes ile yayinlar.
- Release body, build scriptlerinin urettigi `*-RELEASE-NOTES.md` dosyalarindan birlestirilir.
- Yetkiler job bazinda tanimlidir: test/build job'lari `contents: read`,
  yalnizca `publish-release` `contents: write`.

## Dagitim Notu

Kaynak kod ile paketlenmis artefakt ayrilmistir:

- `dist/` PyInstaller'in ham cikitisidir (`dist/HidrostatikTest/` onedir,
  `dist/HidrostatikTest.app` macOS bundle) ve git'e girmez.
- `release/` yayina hazir paketleri tutar ve git'e girmez.
- Release paketleri her zaman build scriptleri ile yeniden uretilir.

Kod imzalama sertifikasi ve notarization anahtarlari depoda tutulmaz; saglanana kadar
Windows SmartScreen ve macOS Gatekeeper uyarilari beklenen davranistir.
