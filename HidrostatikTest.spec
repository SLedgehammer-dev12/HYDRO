# -*- mode: python ; coding: utf-8 -*-
#
# macOS paketleme spec dosyasi (build_dmg.sh tarafindan kullanilir).
# Surum bilgisi tek kaynaktan, hidrostatik_test/app_metadata.py dosyasindan okunur;
# bu dosyada sabit surum string'i tutulmaz.

import importlib.util
import os
import pathlib
import subprocess
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

PROJECT_ROOT = pathlib.Path(SPECPATH)


def _safe_collect_data_files(pkg_name):
    try:
        return collect_data_files(pkg_name)
    except Exception as exc:
        print(f'[HidrostatikTest.spec] collect_data_files({pkg_name}) atlandi: {exc}')
        return []


def _safe_collect_all(pkg_name):
    try:
        return collect_all(pkg_name)
    except Exception as exc:
        print(f'[HidrostatikTest.spec] collect_all({pkg_name}) atlandi: {exc}')
        return [], [], []


def _load_app_metadata():
    metadata_path = PROJECT_ROOT / 'hidrostatik_test' / 'app_metadata.py'
    spec = importlib.util.spec_from_file_location('hidrostatik_test_app_metadata', metadata_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f'app_metadata.py yuklenemedi: {metadata_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _target_arch():
    """macOS icin universal2'yi dener, mimari uygun degilse yerel mimariye duser.

    PyInstaller universal2 hedefi, evrensel (arm64 + x86_64) bir Python yorumlayicisi
    gerektirir. CI'da kurulan Python genellikle tek mimaridir; bu durumda build'i
    kirmak yerine yerel mimari kullanilir. Zorlamak icin:
      HIDROSTATIK_TARGET_ARCH=universal2|arm64|x86_64|native
    """
    if sys.platform != 'darwin':
        return None

    override = os.environ.get('HIDROSTATIK_TARGET_ARCH', '').strip().lower()
    if override:
        return None if override == 'native' else override

    try:
        completed = subprocess.run(
            ['lipo', '-archs', sys.executable],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    archs = set(completed.stdout.split())
    if {'arm64', 'x86_64'}.issubset(archs):
        for mod_name in (
            'CoolProp.CoolProp',
            'PIL._imaging',
            'PIL._webp',
            'numpy._core._multiarray_umath',
            'numpy.core._multiarray_umath',
        ):
            spec = importlib.util.find_spec(mod_name)
            origin = getattr(spec, 'origin', None) if spec is not None else None
            if not origin:
                continue
            ext_completed = subprocess.run(
                ['lipo', '-archs', origin],
                capture_output=True,
                text=True,
                check=False,
            )
            ext_archs = set(ext_completed.stdout.split())
            if ext_archs and not {'arm64', 'x86_64'}.issubset(ext_archs):
                print(
                    '[HidrostatikTest.spec] Bagimli C eklentisi universal2 degil '
                    f'({mod_name}: {sorted(ext_archs)}); yerel mimari kullanilacak.'
                )
                return None
        pdfium_spec = importlib.util.find_spec('pypdfium2_raw')
        pdfium_locs = getattr(pdfium_spec, 'submodule_search_locations', None) if pdfium_spec else None
        if pdfium_locs:
            libpdfium = pathlib.Path(pdfium_locs[0]) / 'libpdfium.dylib'
            if libpdfium.is_file():
                ext_completed = subprocess.run(
                    ['lipo', '-archs', str(libpdfium)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                ext_archs = set(ext_completed.stdout.split())
                if ext_archs and not {'arm64', 'x86_64'}.issubset(ext_archs):
                    print(
                        '[HidrostatikTest.spec] libpdfium.dylib universal2 degil '
                        f'({sorted(ext_archs)}); yerel mimari kullanilacak.'
                    )
                    return None
        return 'universal2'

    print(
        '[HidrostatikTest.spec] Python yorumlayicisi evrensel degil (mimari: '
        f'{sorted(archs) or "bilinmiyor"}); universal2 yerine yerel mimari kullanilacak.'
    )
    return None


APP_METADATA = _load_app_metadata()
APP_VERSION = APP_METADATA.APP_VERSION
BINARY_NAME = APP_METADATA.BINARY_NAME
APP_DISPLAY_NAME = APP_METADATA.APP_TITLE
BUNDLE_IDENTIFIER = 'com.hidrostatik.degerlendirme'

# windows_manifest.xml surum alanini build_exe.ps1 build sirasinda gunceller;
# burada yalnizca mevcut dosya varsa kullanilir (macOS/Linux build'inde etkisiz).
EXE_KWARGS = {
    'name': BINARY_NAME,
    'debug': False,
    'bootloader_ignore_signals': False,
    'strip': False,
    'upx': False,
    'console': False,
    'disable_windowed_traceback': False,
    'argv_emulation': False,
    'target_arch': _target_arch(),
    'codesign_identity': None,
    'entitlements_file': None,
}

MANIFEST_PATH = PROJECT_ROOT / 'windows_manifest.xml'
if sys.platform == 'win32' and MANIFEST_PATH.exists():
    # Windows release build'i build_exe.ps1 uzerinden yapilir; manifest surumu
    # orada gecici kopyaya yazilir. Burada yalnizca dogrudan spec build'i icin
    # mevcut manifest kullanilir.
    EXE_KWARGS['manifest'] = str(MANIFEST_PATH)

_extra_datas = [
    ('hidrostatik_test/data/ab_control_table_v1.csv', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/ab_control_table_v1.meta.json', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/gail_reference_table_v1.csv', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/gail_reference_table_v1.meta.json', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/water_property_table_v1.csv', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/water_property_table_v1.meta.json', 'hidrostatik_test/data'),
]
_extra_binaries = []
_extra_hidden = [
    'CoolProp.CoolProp',
    'numpy.core._multiarray_umath',
    'numpy.core._multiarray_tests',
    'numpy.core._umath_tests',
    'numpy.lib.utils',
    'numpy.lib.format',
    'numpy.compat.py3k',
    'scipy.interpolate',
    'scipy.linalg',
    'pint',
    'openpyxl',
    'reportlab',
    'pypdf',
    'pdfplumber',
    'xlrd',
    'PIL',
    'pytesseract',
]

_extra_datas.extend(_safe_collect_data_files('pdfminer'))
for _pkg in ('pypdfium2', 'pypdfium2_raw') + (('ocrmac',) if sys.platform == 'darwin' else ()):
    _d, _b, _h = _safe_collect_all(_pkg)
    _extra_datas.extend(_d)
    _extra_binaries.extend(_b)
    _extra_hidden.extend(_h)

if sys.platform == 'darwin':
    for _apple_pkg in ('ocrmac', 'objc', 'Foundation', 'Vision', 'Quartz', 'CoreFoundation'):
        try:
            _extra_hidden.extend(collect_submodules(_apple_pkg))
        except Exception:
            pass

a = Analysis(
    ['Hidrostatik_Test_Chat.py'],
    pathex=[],
    binaries=_extra_binaries,
    datas=_extra_datas,
    hiddenimports=sorted(set(_extra_hidden)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hidrostatik_test/_pyinstaller_hook.py'],
    excludes=['CoolProp.GUI', 'CoolProp.Plots', 'CoolProp.tests', 'matplotlib', 'pandas', 'pytest', 'PyQt5', 'PyQt6', 'PySide6', 'lxml', 'pyarrow', 'iapws'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    **EXE_KWARGS,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=BINARY_NAME,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name=f'{BINARY_NAME}.app',
        icon=None,
        bundle_identifier=BUNDLE_IDENTIFIER,
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            'CFBundleDisplayName': APP_DISPLAY_NAME,
            'CFBundleName': BINARY_NAME,
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleVersion': APP_VERSION,
            'NSHighResolutionCapable': True,
            'NSSupportsAutomaticGraphicsSwitching': True,
            'NSAppTransportSecurity': {'NSAllowsArbitraryLoads': True},
        },
    )
