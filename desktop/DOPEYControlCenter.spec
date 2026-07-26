# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata


DESKTOP_ROOT = Path(SPECPATH).resolve()
REPO_ROOT = DESKTOP_ROOT.parent
ENTRYPOINT = REPO_ROOT / "dopey_dashboard" / "desktop_app.py"
FRONTEND_ROOT = DESKTOP_ROOT / "dist"
ASSETS_ROOT = DESKTOP_ROOT / "assets"
ICON_PATH = ASSETS_ROOT / "dopey-control-center.ico"

if not ENTRYPOINT.is_file():
    raise FileNotFoundError(f"Desktop entrypoint is missing: {ENTRYPOINT}")
if not (FRONTEND_ROOT / "index.html").is_file():
    raise FileNotFoundError(
        f"Compiled frontend is missing: {FRONTEND_ROOT / 'index.html'}"
    )
if not ICON_PATH.is_file():
    raise FileNotFoundError(f"Desktop icon is missing: {ICON_PATH}")

datas = [
    (str(FRONTEND_ROOT), "desktop/dist"),
    (str(ASSETS_ROOT), "desktop/assets"),
]
datas += copy_metadata("pystray")
datas += copy_metadata("pywebview")

analysis = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pystray._win32",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "cefpython3",
        "gi",
        "gtk",
        "kivy",
        "tkinter",
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="DOPEY Control Center",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH),
)
