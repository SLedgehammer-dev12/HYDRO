#!/usr/bin/env bash
set -euo pipefail

# HYDRO Web macOS (Apple Silicon M1+ arm64) build + DMG paketleme.
# Gereksinimler: python3, pyinstaller, node/npm, hdiutil, codesign.

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

BINARY_NAME="HydroWeb"
APP_PATH="dist/${BINARY_NAME}.app"
SIGN_IDENTITY="${APPLE_SIGNING_IDENTITY:-${CODESIGN_IDENTITY:-}}"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"

SIGNING_SCRIPT="tools/update_signing.py"
SIGNING_KEY_PATH="${HYDRO_UPDATE_SIGNING_KEY:-$HOME/.config/hydro/update_signing_key.pem}"
SKIP_SIGNING="${HYDRO_SKIP_UPDATE_SIGNING:-0}"
SKIP_FRONTEND_BUILD="${HYDRO_SKIP_FRONTEND_BUILD:-0}"

require_signing_key() {
    if [ "$SKIP_SIGNING" = "1" ]; then
        echo "UYARI: HYDRO_SKIP_UPDATE_SIGNING=1 etkin. Paket IMZASIZ olacaktir."
        return 0
    fi
    if [ ! -f "$SIGNING_SCRIPT" ]; then
        echo "HATA: Imzalama araci bulunamadi: $SIGNING_SCRIPT"
        exit 1
    fi
    if [ ! -f "$SIGNING_KEY_PATH" ]; then
        echo "HATA: Guncelleme imzalama anahtari bulunamadi: $SIGNING_KEY_PATH"
        exit 1
    fi

    EMBEDDED_PUBKEY=$(python3 -c '
import pathlib, re
text = pathlib.Path("hidrostatik_test/app_metadata.py").read_text(encoding="utf-8")
match = re.search(r"^UPDATE_SIGNING_PUBLIC_KEY\s*=\s*\"([^\"]*)\"", text, re.M)
print(match.group(1) if match else "")
')
    KEY_PUBKEY=""
    if ! KEY_PUBKEY=$(python3 "$SIGNING_SCRIPT" fingerprint --key "$SIGNING_KEY_PATH" 2>/dev/null | sed -n 's/^Public key (base64): //p'); then
        echo "HATA: Ozel anahtar okunamadi: $SIGNING_KEY_PATH"
        exit 1
    fi
    if [ -z "$EMBEDDED_PUBKEY" ] || [ -z "$KEY_PUBKEY" ] || [ "$KEY_PUBKEY" != "$EMBEDDED_PUBKEY" ]; then
        echo "HATA: Ozel anahtar app_metadata.UPDATE_SIGNING_PUBLIC_KEY ile eslesmiyor."
        exit 1
    fi
    echo "Imzalama anahtari hazir: $SIGNING_KEY_PATH"
}

echo "HYDRO Web macOS release build hazirlaniyor..."
echo "Project root: $PROJECT_ROOT"
echo "Version     : $APP_VERSION"

require_signing_key

# --- Frontend derlemesi -----------------------------------------------------
if [ "$SKIP_FRONTEND_BUILD" = "1" ] && [ -f "webapp/frontend/dist/index.html" ]; then
    echo "Frontend derlemesi atlandi (HYDRO_SKIP_FRONTEND_BUILD=1)."
else
    echo "Frontend derleniyor (webapp/frontend)..."
    (cd webapp/frontend && npm ci && npm run build)
fi

if [ ! -f "webapp/frontend/dist/index.html" ]; then
    echo "HATA: webapp/frontend/dist/index.html olusmadi."
    exit 1
fi

# --- Temizlik & PyInstaller build -------------------------------------------
rm -rf build/HydroWeb dist/HydroWeb dist/HydroWeb.app
mkdir -p release

echo "PyInstaller derlemesi baslatiliyor (HydroWeb.spec)..."
python3 -m PyInstaller --noconfirm --clean HydroWeb.spec

if [ ! -d "$APP_PATH" ]; then
    echo "HATA: Beklenen macOS uygulama paketi (.app) olusmadi: $APP_PATH"
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
    echo "UYARI: APPLE_SIGNING_IDENTITY tanimli degil; ad-hoc imzalama yapiliyor."
fi

if ! codesign --force --deep --options runtime \
    --entitlements runtime_entitlements.plist \
    --sign "$SIGN_ARG" "$APP_PATH"; then
    echo "UYARI: runtime entitlement imzalamasi basarisiz; temel ad-hoc imzalama denenecek."
    codesign --force --deep --entitlements runtime_entitlements.plist --sign "$SIGN_ARG" "$APP_PATH" || {
        codesign --force --deep --sign "$SIGN_ARG" "$APP_PATH"
        ENTITLEMENTS_APPLIED=0
    }
fi

echo "Imza dogrulaniyor (codesign --verify --deep --strict)..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

APP_ARCHS=$(lipo -archs "$APP_PATH/Contents/MacOS/$BINARY_NAME" 2>/dev/null || echo "")
echo "Mimari: ${APP_ARCHS:-bilinmiyor}"
if [[ " $APP_ARCHS " != *" arm64 "* ]]; then
    echo "HATA: HydroWeb binary arm64 mimarisi icermiyor (M1+ uyumlulugu zorunlu). Bulunan: '$APP_ARCHS'"
    exit 1
fi

# --- Canli ikili dosya smoke testi (--self-test) ----------------------------
echo "Paketli uygulama --self-test calistiriliyor..."
SELF_TEST_OUT=$("$APP_PATH/Contents/MacOS/$BINARY_NAME" --self-test 2>&1) || {
    echo "$SELF_TEST_OUT"
    echo "HATA: HydroWeb --self-test basarisiz."
    exit 1
}
echo "$SELF_TEST_OUT"
if ! printf '%s\n' "$SELF_TEST_OUT" | grep -q "SELF_TEST_OK"; then
    echo "HATA: --self-test ciktisi SELF_TEST_OK icermiyor."
    exit 1
fi

# --- DMG Olusturma ----------------------------------------------------------
DMG_NAME="${BINARY_NAME}-v${APP_VERSION}-macos-arm64.dmg"
DMG_PATH="release/${DMG_NAME}"
HASH_PATH="release/${BINARY_NAME}-v${APP_VERSION}-macos-arm64.sha256.txt"
DMG_HASH_PATH="release/${BINARY_NAME}-v${APP_VERSION}-macos-arm64.dmg.sha256.txt"
NOTES_PATH="release/${BINARY_NAME}-v${APP_VERSION}-macos-arm64-RELEASE-NOTES.md"

STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hydroweb-dmg.XXXXXX")"
trap 'rm -rf "$STAGE_DIR"' EXIT

cp -R "$APP_PATH" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

rm -f "$DMG_PATH"
echo "DMG paketi olusturuluyor: $DMG_PATH"
hdiutil create \
    -volname "HYDRO Web v${APP_VERSION}" \
    -srcfolder "$STAGE_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

rm -rf "$STAGE_DIR"
trap - EXIT

NOTARIZED="no"
if [ "$SIGNED_MODE" = "developer-id" ] && [ -n "$NOTARY_PROFILE" ]; then
    echo "Notarization baslatiliyor (profil: $NOTARY_PROFILE)..."
    xcrun notarytool submit "$DMG_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG_PATH"
    xcrun stapler validate "$DMG_PATH"
    NOTARIZED="yes"
fi

# --- SHA-256 & Ed25519 Imza -------------------------------------------------
echo "SHA256 checksum hesaplaniyor..."
HASH_VAL=$(shasum -a 256 "$DMG_PATH" | awk '{print $1}')
HASH_RECORD="${HASH_VAL}  ${DMG_NAME}"
printf '%s\n' "$HASH_RECORD" > "$HASH_PATH"
printf '%s\n' "$HASH_RECORD" > "$DMG_HASH_PATH"

SIG_PATH="${DMG_PATH}.sig"
if [ "$SKIP_SIGNING" = "1" ]; then
    SIG_NAME="(imza uretilmedi - HYDRO_SKIP_UPDATE_SIGNING=1)"
else
    echo "Guncelleme imzasi uretiliyor (Ed25519)..."
    python3 "$SIGNING_SCRIPT" sign "$DMG_PATH" --key "$SIGNING_KEY_PATH"
    python3 "$SIGNING_SCRIPT" verify "$DMG_PATH" "$SIG_PATH" --key "$SIGNING_KEY_PATH"
    SIG_NAME="$(basename "$SIG_PATH")"
fi

cat << EOF > "$NOTES_PATH"
# HYDRO Web v${APP_VERSION} (macOS Apple Silicon M1+ arm64)

## Included Artifacts
- ${DMG_NAME}
- ${SIG_NAME}
- ${BINARY_NAME}-v${APP_VERSION}-macos-arm64.sha256.txt
- ${BINARY_NAME}-v${APP_VERSION}-macos-arm64.dmg.sha256.txt

## Verification Summary
- SHA256 Checksum: ${HASH_VAL}
- Built architecture: ${APP_ARCHS} (Apple Silicon M1 / M2 / M3 / M4 native)
- Live binary smoke test (--self-test): PASS
- codesign --verify --deep --strict: OK (${SIGNED_MODE}, entitlements=${ENTITLEMENTS_APPLIED})
- Notarization: ${NOTARIZED}
- Ed25519 Signature: ${SIG_NAME}

## Installation (macOS M1+)
1. \`${DMG_NAME}\` dosyasini acin ve \`HydroWeb.app\` uygulamasini \`Applications\` klasorune surukleyin.
2. Ilk acilista Gatekeeper uyarisi cikarsa Finder'da sag tik -> Ac (veya Sistem Ayarlari -> Gizlilik ve Guvenlik -> Yine de Ac) ile calistirin.
3. Uygulama yerel sunucuyu baslatip varsayilan tarayicinizda HYDRO Web arayuzunu otomatik acar.
EOF

echo ""
echo "HYDRO Web macOS DMG build tamamlandi: $DMG_PATH"
