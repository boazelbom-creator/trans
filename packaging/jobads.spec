# PyInstaller recipe for JobAds.exe (one folder: JobAds.exe + _internal\).
# Run through build.bat, from the project folder.
# config.json, api_key.json and communities\ are NOT bundled here: the installer places them
# next to JobAds.exe so the user can edit them (PRD §4, §15).

from pathlib import Path

ROOT = Path(SPECPATH).parent

# Qt modules the app does not use (keeps the installer smaller).
EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts",
    "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtSvg",
    "tkinter", "pytest",
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JobAds",
    console=False,  # a window app: no black console window
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="JobAds", upx=False)
