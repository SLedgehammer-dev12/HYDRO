from __future__ import annotations

APP_NAME = "Hidrostatik Test Degerlendirme"
APP_TITLE = "Hidrostatik Test Degerlendirme"
APP_VERSION = "1.9.0"
BINARY_NAME = "HidrostatikTest"
PUBLISHER_NAME = "Hidrostatik Test Project"
COPYRIGHT_NOTICE = "Copyright (c) 2026"
SPEC_DOCUMENT_CODE = "4-NGTL 0-GN-P-002-5007 R4"
SPEC_DOCUMENT_TITLE = "Hidrostatik Test ve Icten Denetleme Sartnamesi"
GITHUB_OWNER = "SLedgehammer-dev12"
GITHUB_REPO = "HYDRO"
LEGACY_GITHUB_REPOS = ("Programlar",)
RELEASE_TAG_PREFIX = "hidrostatik-test-v"
RELEASE_ASSET_TEMPLATE = f"{BINARY_NAME}-v{{version}}-windows-x64.zip"
RELEASE_ASSET_TEMPLATE_MACOS = f"{BINARY_NAME}-v{{version}}-macos-universal.dmg"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

# Guncelleme imzasi (Ed25519) public key'i, base64 (32 bayt ham anahtar).
# Bu deger dolu oldugu surece updater imzayi VARSAYILAN OLARAK ZORUNLU tutar:
# imzasi olmayan/gecersiz paketler kurulmaz (fail-closed).
#
# Ozel anahtar repoda tutulmaz; varsayilan konum:
#   ~/.config/hydro/update_signing_key.pem  (0600)
# Uretim/rotasyon: python3 tools/update_signing.py generate [--force]
# Parmak izi (SHA-256): 54:AA:9C:60:A1:9B:80:0D:B1:D6:A7:59:53:60:D9:78:21:21:6E:9B:EF:47:30:27:05:96:1B:FA:FE:10:6D:98
UPDATE_SIGNING_PUBLIC_KEY = "POWM4KdY6ciBetXmVkyWQmTCAB3SRhVKtkY0TR6IPWU="
