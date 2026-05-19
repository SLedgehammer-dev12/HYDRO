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
    ],
    hiddenimports=['CoolProp.CoolProp'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['CoolProp.GUI', 'CoolProp.Plots', 'CoolProp.tests', 'matplotlib', 'pandas', 'scipy', 'pytest', 'PyQt5', 'PyQt6', 'PySide6', 'openpyxl', 'lxml', 'pyarrow'],
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
