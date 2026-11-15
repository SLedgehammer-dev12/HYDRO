#!/usr/bin/env bash
set -euo pipefail

# macOS build + DMG paketleme.
# Gereksinimler: python3, pyinstaller, hdiutil, codesign.
#
# Imzalama:
#   CODESIGN_IDENTITY="Developer ID Application: ... (TEAMID)" ile gercek imza,
#   bos birakilirsa ad-hoc imza uygulanir (dagitim oncesi notarization gerekir).
# Notarization (yalnizca Developer ID + profil varsa):
#   NOTARY_PROFILE="hidro-notary" ./build_dmg.sh
# Mimari:
#   HIDROSTATIK_TARGET_ARCH=universal2|arm64|x86_64|native (varsayilan: uygunsa universal2)

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

APP_VERSION=$(python3 -c '
import pathlib
import re

text = pathlib.Path("hidrostatik_test/app_metadata.py").read_text(encoding="utf-8")
match = re.search(r"^APP_VERSION\s*=\s*\"([^\"]+)\"", text, re.M)
if not match:
    raise SystemExit("APP_VERSION okunamadi")
print(match.group(1))
')

BINARY_NAME="HidrostatikTest"
APP_PATH="dist/${BINARY_NAME}.app"
SIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"

echo "Release build hazirlaniyor..."
echo "Project root: $PROJECT_ROOT"
echo "Version: $APP_VERSION"

# Temizlik
rm -rf build dist release
mkdir -p release

# Otomatik testler
echo "Otomatik testler calistiriliyor..."
if ! TEST_OUTPUT=$(python3 -m unittest discover -s tests -p "test_*.py" -v 2>&1); then
    echo "$TEST_OUTPUT"
    echo "HATA: Otomatik testler basarisiz; paketleme durduruldu."
    exit 1
fi
echo "$TEST_OUTPUT"
TEST_COUNT=$(printf '%s\n' "$TEST_OUTPUT" | grep -oE '^Ran [0-9]+' | grep -oE '[0-9]+' | tail -n 1 || true)
TEST_COUNT=${TEST_COUNT:-bilinmiyor}

# PyInstaller ile derleme (surum spec icinde app_metadata.py'den okunur)
echo "PyInstaller derlemesi baslatiliyor..."
python3 -m PyInstaller HidrostatikTest.spec

if [ ! -d "$APP_PATH" ]; then
    echo "Hata: Beklenen macOS uygulama paketi (.app) olusmadi: $APP_PATH"
    exit 1
fi

# --- Imzalama ---------------------------------------------------------------
ENTITLEMENTS_APPLIED=1
if [ -n "$SIGN_IDENTITY" ]; then
    SIGN_ARG="$SIGN_IDENTITY"
    SIGNED_MODE="developer-id"
    echo "Developer ID ile imzalaniyor: $SIGN_IDENTITY"
else
    SIGN_ARG="-"
    SIGNED_MODE="ad-hoc"
    echo "UYARI: CODESIGN_IDENTITY tanimli degil. Ad-hoc imzalama yapiliyor; bu paket dagitima hazir degildir."
fi

if ! codesign --force --deep --options runtime \
    --entitlements runtime_entitlements.plist \
    --sign "$SIGN_ARG" "$APP_PATH"; then
    echo "UYARI: entitlement ile imzalama basarisiz; entitlement olmadan tekrar denenecek."
    codesign --force --deep --options runtime --sign "$SIGN_ARG" "$APP_PATH"
    ENTITLEMENTS_APPLIED=0
fi

echo "Imza dogrulaniyor (codesign --verify --deep --strict)..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

APP_ARCHS=$(lipo -archs "$APP_PATH/Contents/MacOS/$BINARY_NAME" 2>/dev/null || echo "bilinmiyor")
echo "Mimari: $APP_ARCHS"
if [ "$APP_ARCHS" != "x86_64 arm64" ] && [ "$APP_ARCHS" != "arm64 x86_64" ]; then
    echo "UYARI: Paket evrensel degil (mimari: $APP_ARCHS). Artefakt adi sozlesme geregi 'macos-universal' kaliyor."
fi

if [ "$SIGNED_MODE" = "developer-id" ]; then
    codesign --display --verbose=2 "$APP_PATH" 2>&1 | sed -n '1,12p'
fi

# --- DMG -------------------------------------------------------------------
DMG_NAME="${BINARY_NAME}-v${APP_VERSION}-macos-universal.dmg"
DMG_PATH="release/${DMG_NAME}"
HASH_PATH="release/${BINARY_NAME}-v${APP_VERSION}-macos-universal.sha256.txt"
DMG_HASH_PATH="release/${BINARY_NAME}-v${APP_VERSION}-macos-universal.dmg.sha256.txt"
NOTES_PATH="release/${BINARY_NAME}-v${APP_VERSION}-macos-universal-RELEASE-NOTES.md"

echo "DMG paketi olusturuluyor..."
hdiutil create -volname "Hidrostatik Test Degerlendirme" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"

# --- Gatekeeper / notarization ---------------------------------------------
SPCTL_STATUS=0
SPCTL_OUTPUT=$(spctl -a -vv "$APP_PATH" 2>&1) || SPCTL_STATUS=$?
if [ "$SPCTL_STATUS" -eq 0 ]; then
    echo "Gatekeeper dogrulamasi: kabul edildi."
else
    echo "$SPCTL_OUTPUT"
    if [ "$SIGNED_MODE" = "developer-id" ]; then
        echo "HATA: Developer ID imzasina ragmen Gatekeeper reddetti. Notarization/stapling eksik olabilir."
        exit 1
    fi
    echo "UYARI: Paket unsigned/ad-hoc. Gatekeeper reddi beklenen bir durumdur;"
    echo "        dagitim icin Developer ID sertifikasi ve notarization gerekir."
fi

NOTARIZED="no"
if [ "$SIGNED_MODE" = "developer-id" ] && [ -n "$NOTARY_PROFILE" ]; then
    echo "Notarization baslatiliyor (profil: $NOTARY_PROFILE)..."
    xcrun notarytool submit "$DMG_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG_PATH"
    xcrun stapler validate "$DMG_PATH"
    NOTARIZED="yes"
elif [ "$SIGNED_MODE" = "developer-id" ]; then
    echo "UYARI: NOTARY_PROFILE tanimli degil; notarization atlandi."
else
    echo "UYARI: unsigned/ad-hoc build; notarization uygulanamaz."
fi

# --- Checksum --------------------------------------------------------------
echo "SHA256 checksum hesaplaniyor..."
HASH_VAL=$(shasum -a 256 "$DMG_PATH" | awk '{print $1}')
HASH_RECORD="${HASH_VAL}  ${DMG_NAME}"
# Iki ad: sha256sum -c ile dogrulanabilir kayit ve updater'in bekledigi <dmg>.sha256.txt
printf '%s\n' "$HASH_RECORD" > "$HASH_PATH"
printf '%s\n' "$HASH_RECORD" > "$DMG_HASH_PATH"

echo "macOS Release Notes yaziliyor..."
cat << EOF > "$NOTES_PATH"
# Hidrostatik Test Degerlendirme v${APP_VERSION} (macOS)

## Included Artifacts
- ${DMG_NAME}
- ${BINARY_NAME}-v${APP_VERSION}-macos-universal.sha256.txt
- ${BINARY_NAME}-v${APP_VERSION}-macos-universal.dmg.sha256.txt

## Verification Summary
- SHA256 Checksum: ${HASH_VAL}
- Passed all ${TEST_COUNT} automated test cases
- codesign --verify --deep --strict: OK
- Imzalama modu: ${SIGNED_MODE}
- Notarization: ${NOTARIZED}

## macOS Build Notes
- macOS standalone bundle (.app) generated with PyInstaller
- Packaged into a read-only DMG disk image using hdiutil
- Built architecture: ${APP_ARCHS}
- Version read from hidrostatik_test/app_metadata.py (spec is not patched)
- CoolProp dependency bundled into the application distribution
- Minimum entitlements: disable-library-validation + allow-unsigned-executable-memory

## Installation
1. DMG dosyasini acin ve uygulamayi Applications klasorune surukleyin.
2. Ilk acilista macOS "unidentified developer" uyarisi verebilir:
   Finder'da uygulamaya sag tiklayip "Open" secin.
EOF

echo ""
echo "macOS Build tamamlandi."
echo "DMG Yolu: $DMG_PATH"
echo "SHA256 Checksum Yolu: $HASH_PATH"
echo "Release Notes Yolu: $NOTES_PATH"
if [ "$SIGNED_MODE" != "developer-id" ]; then
    echo "UYARI: Bu paket ad-hoc imzali ve notarize edilmemis (unsigned/ad-hoc)."
fi
if [ "$ENTITLEMENTS_APPLIED" -eq 0 ]; then
    echo "UYARI: runtime_entitlements.plist uygulanamadi."
fi
