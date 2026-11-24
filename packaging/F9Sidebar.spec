# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller --onedir build specification for F9Sidebar (Windows 11)."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent

ICON_PATH = REPO_ROOT / "assets" / "f9sidebar.ico"
VERSION_FILE = SPEC_DIR / "version_info.txt"

if not ICON_PATH.is_file():
    raise FileNotFoundError(
        f"Missing app icon at {ICON_PATH}. Run scripts/generate_icon.py first."
    )

# Bundled read-only runtime assets resolved via database.get_resource_path() -> sys._MEIPASS
datas = []
datas += collect_data_files("qtawesome")
datas.append((str(ICON_PATH), "assets"))

# Include read-only helper binaries under bin/ (e.g., bin/ahk/) if present in the repo
bin_root = REPO_ROOT / "bin"
if bin_root.is_dir():
    for file_path in bin_root.rglob("*"):
        if file_path.is_file():
            rel_parent = file_path.relative_to(bin_root).parent
            dest_dir = str(Path("bin") / rel_parent) if str(rel_parent) != "." else "bin"
            datas.append((str(file_path), dest_dir))

hiddenimports = [
    "PySide6.QtNetwork",
    "PySide6.QtSvg",
    "shiboken6",
    "qtawesome",
    "qtpy",
]

# Exclude unused heavy Qt and stdlib modules so dist/ stays fast and lean
excludes = [
    "PyQt5",
    "PyQt6",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtDBus",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
    "tkinter",
    "_tkinter",
    "unittest",
    "doctest",
    "pydoc",
]

a = Analysis(
    [str(REPO_ROOT / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# Prune unused Qt plugins and their transitive DLLs pulled in automatically by hook-PySide6.QtGui
_PRUNE_BINARIES = (
    "qpdf.dll",
    "qt6pdf.dll",
    "qtvirtualkeyboardplugin.dll",
    "qt6virtualkeyboard.dll",
    "qt6quick",
    "qt6qml",
    "qt6opengl",
    "opengl32sw.dll",
    "qtuiotouchplugin.dll",
    "qdirect2d.dll",
)
a.binaries = [
    entry
    for entry in a.binaries
    if not any(token in entry[0].lower() for token in _PRUNE_BINARIES)
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="F9Sidebar",
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
    icon=str(ICON_PATH),
    version=str(VERSION_FILE),
    contents_directory="_internal",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="F9Sidebar",
)
