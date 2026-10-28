# -*- mode: python ; coding: utf-8 -*-

from pathlib import PurePath


def without_foreign_icu(entries):
    """Remove PATH-injected ICU binaries that break Qt on Windows.

    Some development environments expose Poppler's ICU DLLs through PATH.
    PyInstaller may collect them for Qt6Core even though PySide6 expects the
    Windows ICU forwarder. The resulting executable fails with WinError 127.
    """
    blocked = {"icuuc.dll", "icudt78.dll"}
    return [entry for entry in entries if PurePath(entry[0]).name.casefold() not in blocked]


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets"), ("data", "data"), ("scripts/create_desktop_shortcut.ps1", "scripts"), ("update_channel.json", ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.binaries = without_foreign_icu(a.binaries)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Astra Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=["assets/astra.ico"],
)

collect = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Astra Studio",
)
