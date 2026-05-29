# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# ── ctranslate2 native libs ──────────────────────────────────
import ctranslate2
_ct2_dir = os.path.dirname(ctranslate2.__file__)
_ct2_binaries = []
for f in os.listdir(_ct2_dir):
    fpath = os.path.join(_ct2_dir, f)
    if f.endswith(('.dll', '.pyd', '.so')):
        _ct2_binaries.append((fpath, 'ctranslate2'))

# ── Collect PyQt5 QtWebEngine resources ──────────────────────
# QtWebEngineProcess.exe is required for QWebEngineView
_qt_binaries = []
try:
    import PyQt5
    _qt_dir = os.path.dirname(PyQt5.__file__)
    _qt_prefix = os.path.join(_qt_dir, 'Qt5')
    if os.path.isdir(_qt_prefix):
        for root, dirs, files in os.walk(_qt_prefix):
            for f in files:
                fpath = os.path.join(root, f)
                rel = os.path.relpath(root, _qt_prefix)
                dest = os.path.join('PyQt5', 'Qt5', rel)
                _qt_binaries.append((fpath, dest))
except Exception:
    pass

# ── Analysis ─────────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_ct2_binaries + _qt_binaries,
    datas=[],
    hiddenimports=[
        'PyQt5.QtWebEngine',
        'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebChannel',
        'sounddevice',
        'soundfile',
        'numpy',
        'PIL',
        'faster_whisper',
        'ctranslate2',
        'pyttsx3.drivers.sapi5',
        'keyboard',
        'json',
    ],
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
    name='LinguaSnap',
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
    icon=None,
)
