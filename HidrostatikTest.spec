# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Hidrostatik_Test_Chat.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('hidrostatik_test/data/ab_control_table_v1.csv', 'hidrostatik_test/data'),
        ('hidrostatik_test/data/ab_control_table_v1.meta.json', 'hidrostatik_test/data'),
        ('hidrostatik_test/data/gail_reference_table_v1.csv', 'hidrostatik_test/data'),
        ('hidrostatik_test/data/gail_reference_table_v1.meta.json', 'hidrostatik_test/data'),
        ('hidrostatik_test/data/water_property_table_v1.csv', 'hidrostatik_test/data'),
        ('hidrostatik_test/data/water_property_table_v1.meta.json', 'hidrostatik_test/data'),
        ('hidrostatik_test/_pyinstaller_hook.py', 'hidrostatik_test'),
    ],
    hiddenimports=[
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
    ],
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
    name='HidrostatikTest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='release\\build-temp\\version_info.txt',
    manifest='windows_manifest.xml',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='HidrostatikTest',
)

import sys
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='HidrostatikTest.app',
        icon=None,
        bundle_identifier='com.hidrostatik.degerlendirme',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            'CFBundleDisplayName': 'Hidrostatik Test Degerlendirme',
            'CFBundleName': 'HidrostatikTest',
            'CFBundleShortVersionString': '1.7.0',
            'CFBundleVersion': '1.7.0',
            'NSHighResolutionCapable': True,
            'NSSupportsAutomaticGraphicsSwitching': True,
            'NSAppTransportSecurity': {'NSAllowsArbitraryLoads': True},
        }
    )
