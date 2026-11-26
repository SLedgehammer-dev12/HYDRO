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
- `-SkipSigning` (yalnizca gelistirici icin: `.sig` uretilmez; paket updater
  tarafindan reddedilir, yayina cikacak build'lerde kullanilmaz)

macOS script ortam degiskenleri:

- `CODESIGN_IDENTITY="Developer ID Application: ... (TEAMID)"` gercek imza icin; bos ise ad-hoc imzalanir.
- `NOTARY_PROFILE="hidro-notary"` Developer ID + `notarytool` profili varsa DMG notarize edilip staple edilir.
- `HIDROSTATIK_TARGET_ARCH=universal2|arm64|x86_64|native` mimari secimi (varsayilan: evrensel Python'da universal2).
- `HYDRO_UPDATE_SIGNING_KEY=<yol>` guncelleme imza ozel anahtari (varsayilan `~/.config/hydro/update_signing_key.pem`).
- `HYDRO_SKIP_UPDATE_SIGNING=1` yalnizca gelistirici icin: DMG imzalanmaz; paket updater tarafindan reddedilir.

## Artefakt Sozlesmesi

Windows (`release/` altinda):

- `HidrostatikTest-v<surum>-windows-x64.zip`
  - Zip koku `HidrostatikTest/` klasorudur; icinde `HidrostatikTest.exe` bulunur.
  - Auto-updater bu yapiyi bekler (`stage/HidrostatikTest/HidrostatikTest.exe`).
- `HidrostatikTest-v<surum>-windows-x64.zip.sig` (Ed25519 detached imza; **zorunlu**)
- `HidrostatikTest-v<surum>-windows-x64.sha256.txt`
- `HidrostatikTest-v<surum>-windows-x64.zip.sha256.txt`
- `HidrostatikTest-v<surum>-windows-x64-RELEASE-NOTES.md`

macOS (`release/` altinda):

- `HidrostatikTest-v<surum>-macos-universal.dmg`
- `HidrostatikTest-v<surum>-macos-universal.dmg.sig` (Ed25519 detached imza; **zorunlu**)
- `HidrostatikTest-v<surum>-macos-universal.sha256.txt`
- `HidrostatikTest-v<surum>-macos-universal.dmg.sha256.txt`
- `HidrostatikTest-v<surum>-macos-universal-RELEASE-NOTES.md`

Iki checksum dosyasi ayni icerigi tasir: `<hash>  <dosya adi>`.

- `<artefakt>.sha256.txt` bicimi (ornek: `...-windows-x64.zip.sha256.txt`) updater
  tarafindan indirilir; updater checksum adresini `<asset-url>.sha256.txt` olarak kurar.
- Uzantisiz ad (`...-windows-x64.sha256.txt`) dokumante edilen yayin sozlesmesidir ve
  `sha256sum -c` ile dogrulanabilir.
- `<artefakt>.sig` bicimi: 64 baytlik ham Ed25519 imzasinin base64 (tek satir) hali.
  Updater bu dosyayi `<asset-url>.sig` adresinden indirir. `.minisig` de kabul edilir
  ancak yayin standardi `.sig`'dir.

## Guncelleme Imzasi (Ed25519)

Imza **varsayilan olarak zorunludur** (fail-closed). Uygulama imzasi indirilemeyen,
dogrulanamayan veya yanlis anahtarla uretilmis paketi kurmaz; SHA-256 dogrulamasi
tek basina yeterli sayilmaz.

### Anahtar uretimi

```bash
python3 tools/update_signing.py generate
# Ozel anahtar: ~/.config/hydro/update_signing_key.pem  (0600)
# stdout        : base64 Ed25519 public key
# stderr        : SHA-256 parmak izi (ornek 54:AA:9C:... )
```

- Ozel anahtar **repoya asla yazilmaz** ve commit edilmez (`*.pem`,
  `.hydro_signing/`, `update_signing_key*` `.gitignore` icinde).
- Uretilen public key `hidrostatik_test/app_metadata.py` icindeki
  `UPDATE_SIGNING_PUBLIC_KEY` degerine yazilir. Bu deger doluyken updater imzayi
  zorunlu tutar.
- Farkli konum: `--key <yol>` veya `HYDRO_UPDATE_SIGNING_KEY=<yol>`.

### Saklama

- Ozel anahtar yalnizca yayin yapan makinede/CI secret'inda tutulur; dosya izni 0600,
  klasor 0700 olmalidir.
- Anahtarin yedegi sifreli medyada, en az iki yetkili kiside tutulur. Kaybolursa
  mevcut istemciler yeni anahtari kabul etmez (rotasyon gerekir).
- Anahtar bir sizma suphesi varsa derhal rotasyona gidilir.

### Imzalama ve dogrulama

```bash
python3 tools/update_signing.py sign release/HidrostatikTest-v<surum>-windows-x64.zip
python3 tools/update_signing.py verify release/HidrostatikTest-v<surum>-windows-x64.zip \
    release/HidrostatikTest-v<surum>-windows-x64.zip.sig
python3 tools/update_signing.py fingerprint        # gomulu anahtarin parmak izi
```

`build_exe.ps1` ve `build_dmg.sh` imzalamayi otomatik yapar ve imzayi hemen dogrular.
Anahtar yoksa veya anahtar gomulu public key ile eslesmiyorsa build **durur**; imzasiz
artefakt uretilmez.

### Rotasyon

1. Yeni anahtar uret: `python3 tools/update_signing.py generate --force` (veya yeni
   dosya yolu). Eski `.sig` dosyalari gecersiz olur.
2. Yeni public key'i `app_metadata.py` icine yaz ve parmak izini `docs/continuity.md`
   icine not et.
3. Yeni surumu eski surumden **elle** guncelleme ile dagit; eski istemciler ancak
   `HYDRO_UPDATE_PUBKEY` override'i veya yeni surum ile yeni anahtari ogrenir.
4. `HYDRO_UPDATE_PRIVATE_KEY` CI secret'ini guncelle.
5. Gecis doneminde `HYDRO_UPDATE_PUBKEY=<yeni base64>` ortam degiskeni, gomulu
   anahtari gecersiz kilar (destek/uzaktan mudahale icin).

### CI secret'lari

- `HYDRO_UPDATE_PRIVATE_KEY`: PEM (PKCS#8) ozel anahtarin tamami. Repo
  Settings > Secrets and variables > Actions altinda tanimlanir.
- Workflow once `signing_key_check` job'i ile secret'in varligini dogrular; secret
  yoksa build baslamadan release acik mesajla durur.
- Secret runner uzerinde yalnizca gecici kullanici profiline yazilir ve build
  sonunda silinir (`if: always()` adimi).
- `.sig` dosyalari release asset'i olarak yuklenir; `publish-release` job'i yayin
  oncesi her artefaktin imzasini yeniden dogrular.

### Imzasiz guncelleme politikasi

- Uretimde imzasiz guncelleme **yoktur**; `.sig` yoksa/gecersizse updater
  `UpdateError` ile durur ve kullaniciyi release sayfasina yonlendirir.
- Yalnizca gelistirici makinelerinde, acikca istenerek kapatilir:
  `HYDRO_ALLOW_UNSIGNED_UPDATE=1` veya `HYDRO_REQUIRE_SIGNATURE=0`. Bu bayraklar
  yalnizca imza dosyasinin **yoklugunu** tolere eder; imza varsa yine dogrulanir.
- Build tarafinda karsiligi: `-SkipSigning` (PowerShell) / `HYDRO_SKIP_UPDATE_SIGNING=1`
  (macOS). Bu modda uretilen paketler kullaniciya dagitilmaz.

## Build Davranisi

- PyInstaller runtime hook (`hidrostatik_test/_pyinstaller_hook.py`) hem PowerShell
  hem spec yolunda kullanilir.
- Windows manifest surumu build sirasinda `APP_VERSION` degerinden turetilip gecici
  manifest kopyasina yazilir; `windows_manifest.xml` statik surum tutmaz.
- PyInstaller basarisiz olursa build fail eder; sessiz "plain fallback" paket
  yayinlanmaz.
- Guncelleme imza anahtari build'in basinda dogrulanir (anahtar var mi, gomulu
  public key ile eslesiyor mu); eslesmiyorsa build durur.
- macOS paketi `codesign --verify --deep --strict` ile dogrulanir; Developer ID yoksa
  ad-hoc imza uygulanir, `spctl` reddi beklenen durum olarak uyarilir ve notarization
  atlanir.
- `build_dmg.sh` spec dosyasini yamalamaz; surum bilgisi spec icinde okunur.
- macOS'ta DMG imzasi notarization/stapling **sonrasinda** atilir; boylece imza
  nihai DMG baytlarini kapsar.

## Lokal Dogrulama

Windows (PowerShell):

```powershell
Get-FileHash .\release\HidrostatikTest-v<surum>-windows-x64.zip -Algorithm SHA256
Get-Content .\release\HidrostatikTest-v<surum>-windows-x64.sha256.txt
python tools\update_signing.py verify .\release\HidrostatikTest-v<surum>-windows-x64.zip
Expand-Archive .\release\HidrostatikTest-v<surum>-windows-x64.zip -DestinationPath .\verify
Test-Path .\verify\HidrostatikTest\HidrostatikTest.exe
```

macOS:

```bash
shasum -a 256 release/HidrostatikTest-v<surum>-macos-universal.dmg
cat release/HidrostatikTest-v<surum>-macos-universal.sha256.txt
python3 tools/update_signing.py verify release/HidrostatikTest-v<surum>-macos-universal.dmg
hdiutil verify release/HidrostatikTest-v<surum>-macos-universal.dmg
codesign --verify --deep --strict --verbose=2 dist/HidrostatikTest.app
spctl -a -vv dist/HidrostatikTest.app   # ad-hoc imzada reddedilir (beklenen)
```

## GitHub Release

- Workflow: `.github/workflows/release.yml`
- Tag formati: `hidrostatik-test-v<surum>` (ornek: `hidrostatik-test-v1.7.3`)
- `version-gate` job'i `APP_VERSION` ile tag adinin birebir eslestigini dogrular;
  uyusmazsa release durur.
- `signing_key_check` job'i `HYDRO_UPDATE_PRIVATE_KEY` secret'inin varligini
  dogrular; secret yoksa build job'lari baslamadan release acik mesajla durur.
- `test` job'i Linux'ta `xvfb-run` ile UI testlerini calistirir ve kapsam esigini uygular.
- `build-windows` / `build-macos` job'lari imza anahtarini runner'a yazip artefaktlari
  uretir, zip/DMG icerigini, SHA-256 kayitlarini ve Ed25519 imzasini dogrular,
  ardindan artefakt olarak yukler. Anahtar adim sonunda silinir.
- `publish-release` job'i artefaktlari indirir, `sha256sum -c` ile hash'leri ve
  `tools/update_signing.py verify` ile imzalari yeniden dogrular; ardindan GitHub
  release'e `.zip`/`.dmg`, `.sig`, `.sha256.txt` dosyalari ve release notes ile yayinlar.
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

Guncelleme imzalama ozel anahtari da depoda tutulmaz: lokal gelistirmede
`~/.config/hydro/update_signing_key.pem`, CI'da `HYDRO_UPDATE_PRIVATE_KEY` secret'i
kullanilir. `.gitignore` `*.pem`, `.hydro_signing/` ve `update_signing_key*`
desenlerini kapsar; bu dosyalar `git status` ciktisinda gorunmemelidir.

## CI Kapilari ve Dal Korumasi

Asagidaki isler `main` icin **required status check** olarak isaretlenmelidir
(GitHub > Settings > Branches > Branch protection rule). Bu ayar repodan
kodlanamaz; yeni bir klonda veya fork'ta elle dogrulanmalidir.

| Workflow | Check adi | Kapsam |
| --- | --- | --- |
| `test.yml` | `py3.12 / ubuntu-latest` | Domain + web + OCR testleri, kapsam esigi |
| `test.yml` | `Web Backend Pytest (py3.12 / ubuntu-latest)` | FastAPI regresyonu |
| `test.yml` | `Web Backend PostgreSQL Runtime (py3.12 / ubuntu-latest)` | Postgres/Alembic runtime |
| `test.yml` | `Web Real-Browser Tab Smoke (py3.12 + Chrome)` | 12 rota + derin E2E, 4 viewport |
| `lint.yml` | `lint` (job: `lint`) | Ruff, mypy, OpenAPI, envanter, dokuman metrikleri |
| `lint.yml` | `Frontend Typecheck & Build` | Lint, typecheck, build, bundle butcesi |
| `lint.yml` | `Security Scan (pip-audit & gitleaks)` | Bagimlilik ve secret taramasi |
| `release.yml` | `release_gate --quick` adimi | Tag oncesi tam kalite kapisi |

Notlar:

- `Web Real-Browser Tab Smoke` PR'da 1440x900 hizli kosuyu, gece/manuel tetiklemede
  375/768/1024/1440 matrisini calistirir. Basarisizlikta sunucu logu artifact olarak yuklenir.
- `release.yml` tag oncesi `python3 scripts/release_gate.py --quick` calistirir; bu adim
  atlanirsa surum yayinlanmamalidir.
- Dal korumasi "Require branches to be up to date before merging" ile birlikte
  kullanilmalidir; aksi halde eski bir yesil kosu yeni degisikligi maskeleyebilir.
- 20 ardisik smoke kosusunda flake orani %2'nin altinda tutulmalidir; flake gorulurse
  once port/surec izolasyonu (R23) duzeltilir.
