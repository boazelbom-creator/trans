@echo off
rem Builds dist\setup.exe: tests, then PyInstaller (dist\JobAds\), then Inno Setup (dist\setup.exe).
rem Run from Windows: double-click, or "build.bat" in a command prompt.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Creating the Python environment...
    python -m venv .venv || goto :error
)
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r requirements-dev.txt || goto :error

echo Running tests...
.venv\Scripts\python -m pytest -q -p no:cacheprovider tests || goto :error

echo Building JobAds.exe...
.venv\Scripts\pyinstaller --noconfirm --clean --distpath dist --workpath .pyinstaller-work packaging\jobads.spec || goto :error

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo.
    echo Inno Setup 6 was not found, so setup.exe was not created.
    echo The program itself is ready in dist\JobAds\.
    echo Install Inno Setup from https://jrsoftware.org/isinfo.php and run build.bat again.
    exit /b 1
)

echo Building setup.exe...
"%ISCC%" /Q packaging\installer.iss || goto :error
echo.
echo Done: dist\setup.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
