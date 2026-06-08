#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "=== macOS Build Verification ==="
echo "Project root: $PROJECT_DIR"

echo -e "\n[1/5] Cleaning previous builds..."
RELEASE_DIR="$PROJECT_DIR/release"
rm -rf "$RELEASE_DIR"/*

echo -e "\n[2/5] Running unit tests..."
python3 -m unittest discover -s tests -p "test_*.py" -v

echo -e "\n[3/5] Running build_dmg.sh..."
bash "$PROJECT_DIR/build_dmg.sh"

echo -e "\n[4/5] Verifying build artifacts..."
DMG_FILES=("$RELEASE_DIR"/*.dmg)
if [ ${#DMG_FILES[@]} -eq 0 ]; then
    echo "ERROR: No .dmg file found in release directory."
    exit 1
fi

DMG="${DMG_FILES[-1]}"
echo "Found DMG: $(basename "$DMG")"
SIZE_MB=$(du -sm "$DMG" | cut -f1)
echo "Size: ${SIZE_MB} MB"

if [ "$SIZE_MB" -lt 10 ]; then
    echo "ERROR: DMG too small (${SIZE_MB} MB). Expected at least 10 MB."
    exit 1
fi

echo -e "\n[5/5] Verifying release artifacts..."
SHA_FILES=("$RELEASE_DIR"/*.sha256.txt)
if [ ${#SHA_FILES[@]} -eq 0 ]; then
    echo "WARNING: No SHA-256 file found."
else
    EXPECTED=$(cat "${SHA_FILES[-1]}" | tr -d '\n\r')
    ACTUAL=$(shasum -a 256 "$DMG" | cut -d' ' -f1)
    if [ "$EXPECTED" != "$ACTUAL" ]; then
        echo "ERROR: SHA-256 mismatch!"
        echo "  Expected: $EXPECTED"
        echo "  Actual:   $ACTUAL"
        exit 1
    fi
    echo "SHA-256 verified: $ACTUAL"
fi

echo -e "\n=== macOS Build Verification PASSED ==="
