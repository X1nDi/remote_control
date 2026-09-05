# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
import os
import sys
from pathlib import Path

# Resolve Windows system DLLs instead of unrelated SDK/Poppler DLLs from PATH.
# Qt expects the Windows ICU API; a third-party icuuc.dll breaks QtCore imports.
if sys.platform == 'win32':
    windows = Path(os.environ['SystemRoot'])
    os.environ['PATH'] = os.pathsep.join(map(str, [
        Path(sys.executable).parent, Path(sys.base_prefix), windows / 'System32', windows,
    ]))

datas = [
    ('pc_controller/icon.png', 'pc_controller'),
    ('pc_controller/app_icon.ico', 'pc_controller'),
]
binaries = []
hiddenimports = collect_submodules('winsdk')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PCController',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='pc_controller/app_icon.ico',
)
