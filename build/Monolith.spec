# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec Reproduzível — Monolith RC 0.1 (--onedir)
Gera a pasta portátil Monolith/ contendo Monolith.exe e todas as dependências nativas.
"""

import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hidden_imports = [
    "win32gui",
    "win32con",
    "win32event",
    "win32api",
    "win32process",
    "win32ui",
    "winerror",
    "pywintypes",
    "win32timezone",
    "psutil",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.sip",
    "xml.sax.saxutils",
    "logging.handlers",
    "faulthandler",
]
hidden_imports += [m for m in collect_submodules("comtypes") if not m.startswith("comtypes.test")]

added_datas = [
    (os.path.join(ROOT, "core", "radio_worker.ps1"), "core"),
    (os.path.join(ROOT, "config", "appearance.json"), "config"),
    (os.path.join(ROOT, "build", "monolith.ico"), "build"),
]

excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "unittest",
    "pytest",
    "PyQt6.QtQml",
    "PyQt6.QtQuick",
    "PyQt6.QtMultimedia",
    "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtSql",
    "PyQt6.QtTest",
    "PyQt6.QtBluetooth",
    "PyQt6.QtNfc",
    "PyQt6.QtPositioning",
    "PyQt6.QtSensors",
    "PyQt6.QtSerialPort",
    "PyQt6.QtWebSockets",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=added_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Monolith",
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
    icon=os.path.join(ROOT, "build", "monolith.ico"),
    version=os.path.join(ROOT, "build", "version_info.txt"),
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Monolith",
)
