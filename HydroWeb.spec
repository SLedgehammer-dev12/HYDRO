# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file for HYDRO Web standalone desktop launcher
# (FastAPI + static React frontend + local browser/controller GUI).
# Reads APP_VERSION dynamically from hidrostatik_test/app_metadata.py.

import importlib.util
import os
import pathlib
import platform
import subprocess
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

PROJECT_ROOT = pathlib.Path(SPECPATH).resolve()
BACKEND_ROOT = PROJECT_ROOT / 'webapp' / 'backend'
WEBAPP_ROOT = PROJECT_ROOT / 'webapp'
FRONTEND_DIST = PROJECT_ROOT / 'webapp' / 'frontend' / 'dist'

if not (FRONTEND_DIST / 'index.html').is_file():
    raise SystemExit(
        f'webapp/frontend/dist/index.html bulunamadi ({FRONTEND_DIST}). '
        'Once "cd webapp/frontend && npm ci && npm run build" calistirin.'
    )


def _load_app_metadata():
    metadata_path = PROJECT_ROOT / 'hidrostatik_test' / 'app_metadata.py'
    spec = importlib.util.spec_from_file_location('hidrostatik_test_app_metadata', metadata_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f'app_metadata.py yuklenemedi: {metadata_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_collect_submodules(pkg_name):
    try:
        return collect_submodules(pkg_name)
    except Exception as exc:
        print(f'[HydroWeb.spec] collect_submodules({pkg_name}) atlandi: {exc}')
        return []


def _safe_collect_data_files(pkg_name):
    try:
        return collect_data_files(pkg_name)
    except Exception as exc:
        print(f'[HydroWeb.spec] collect_data_files({pkg_name}) atlandi: {exc}')
        return []


def _safe_collect_all(pkg_name):
    try:
        return collect_all(pkg_name)
    except Exception as exc:
        print(f'[HydroWeb.spec] collect_all({pkg_name}) atlandi: {exc}')
        return [], [], []


def _target_arch():
    """Target Apple Silicon arm64 by default on M1+ compatible Python installs."""
    if sys.platform != 'darwin':
        return None

    override = os.environ.get('HYDROWEB_TARGET_ARCH', '').strip().lower()
    if override:
        return None if override == 'native' else override

    try:
        completed = subprocess.run(
            ['lipo', '-archs', sys.executable],
            capture_output=True,
            text=True,
            check=False,
        )
        archs = set(completed.stdout.split())
    except OSError:
        archs = set()

    if 'arm64' in archs or platform.machine().lower() == 'arm64':
        return 'arm64'
    return None


APP_METADATA = _load_app_metadata()
APP_VERSION = APP_METADATA.APP_VERSION
WEB_BINARY_NAME = 'HydroWeb'
WEB_DISPLAY_NAME = 'HYDRO Web'
WEB_BUNDLE_IDENTIFIER = 'com.hidrostatik.web'

datas = [
    ('hidrostatik_test/data/ab_control_table_v1.csv', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/ab_control_table_v1.meta.json', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/gail_reference_table_v1.csv', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/gail_reference_table_v1.meta.json', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/water_property_table_v1.csv', 'hidrostatik_test/data'),
    ('hidrostatik_test/data/water_property_table_v1.meta.json', 'hidrostatik_test/data'),
    (str(FRONTEND_DIST), 'webapp_frontend_dist'),
]

binaries = []

hiddenimports = [
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
    'defusedxml',
    'reportlab',
    'xlrd',
]

_SUBMODULE_PACKAGES = [
    'app',
    'hidrostatik_test',
    'uvicorn',
    'fastapi',
    'starlette',
    'pydantic',
    'pydantic_core',
    'anyio',
    'h11',
    'sqlalchemy',
    'multipart',
    'python_multipart',
    'pdfminer',
    'pypdf',
    'pdfplumber',
    'xlrd',
    'PIL',
    'pytesseract',
    'reportlab',
    'openpyxl',
    'defusedxml',
    'pint',
    'cryptography',
    'CoolProp',
]

if sys.platform == 'darwin':
    _SUBMODULE_PACKAGES.extend(['ocrmac', 'objc', 'Foundation', 'Vision', 'Quartz', 'AppKit'])

for _pkg in _SUBMODULE_PACKAGES:
    hiddenimports.extend(_safe_collect_submodules(_pkg))

for _data_pkg in ('pdfminer', 'pypdfium2', 'pypdfium2_raw', 'certifi'):
    datas.extend(_safe_collect_data_files(_data_pkg))

for _full_pkg in ('pypdfium2', 'pypdfium2_raw') + (('ocrmac',) if sys.platform == 'darwin' else ()):
    _d, _b, _h = _safe_collect_all(_full_pkg)
    datas.extend(_d)
    binaries.extend(_b)
    hiddenimports.extend(_h)

if sys.platform == 'win32':
    for _win_pkg in ('numpy', 'scipy'):
        _d, _b, _h = _safe_collect_all(_win_pkg)
        datas.extend(_d)
        binaries.extend(_b)
        hiddenimports.extend(_h)

hiddenimports = sorted(set(hiddenimports))

EXE_KWARGS = {
    'name': WEB_BINARY_NAME,
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

if sys.platform == 'win32':
    env_manifest = os.environ.get('HYDROWEB_WINDOWS_MANIFEST', '').strip()
    manifest_candidate = pathlib.Path(env_manifest) if env_manifest else (PROJECT_ROOT / 'windows_manifest.xml')
    if manifest_candidate.is_file():
        EXE_KWARGS['manifest'] = str(manifest_candidate)
    env_version = os.environ.get('HYDROWEB_WINDOWS_VERSION_FILE', '').strip()
    if env_version and pathlib.Path(env_version).is_file():
        EXE_KWARGS['version'] = env_version

a = Analysis(
    [str(WEBAPP_ROOT / 'desktop_launcher.py')],
    pathex=[str(PROJECT_ROOT), str(BACKEND_ROOT), str(WEBAPP_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hidrostatik_test/_pyinstaller_hook.py'],
    excludes=[
        'CoolProp.GUI',
        'CoolProp.Plots',
        'CoolProp.tests',
        'matplotlib',
        'pandas',
        'pytest',
        'PyQt5',
        'PyQt6',
        'PySide6',
        'lxml',
        'pyarrow',
        'iapws',
    ],
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
    name=WEB_BINARY_NAME,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name=f'{WEB_BINARY_NAME}.app',
        icon=None,
        bundle_identifier=WEB_BUNDLE_IDENTIFIER,
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            'CFBundleDisplayName': WEB_DISPLAY_NAME,
            'CFBundleName': WEB_BINARY_NAME,
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleVersion': APP_VERSION,
            'LSMinimumSystemVersion': '11.0',
            'NSHighResolutionCapable': True,
            'NSSupportsAutomaticGraphicsSwitching': True,
            'NSAppTransportSecurity': {'NSAllowsArbitraryLoads': True},
        },
    )
