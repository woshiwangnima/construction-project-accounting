@echo off
chcp 65001 >nul

setlocal enabledelayedexpansion

echo ============================================
echo   Building Construction Accounting
echo   Target: Windows 10 64-bit
echo ============================================
echo.

rem ── 从 versioning.py 中读取版本号 ────────────────────
for /f "tokens=2 delims== " %%a in ('findstr /b "APP_VERSION" src\versioning.py') do set "VERSION=%%~a"
set "VERSION=%VERSION:"=%"
if "%VERSION%"=="" set "VERSION=1.0.0"
echo Version: %VERSION%

echo [1/4] Cleaning old builds...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist *.spec del /q *.spec

echo [2/4] Building with PyInstaller (onedir)...
pyinstaller --onedir --windowed --name "ConstructionAccounting" --add-data "config;config" --add-data "assets;assets" --hidden-import pyttsx3 --hidden-import comtypes --hidden-import comtypes.gen --hidden-import pythoncom --hidden-import pywintypes --distpath dist --workpath build --specpath . main.py

if errorlevel 1 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo [3/5] Copying config files...
if not exist "dist\ConstructionAccounting\config" mkdir "dist\ConstructionAccounting\config"
xcopy /s /y config\* "dist\ConstructionAccounting\config\" >nul

echo [4/5] Generating file manifest...
python scripts\generate_manifest.py "dist\ConstructionAccounting" --version "%VERSION%"

echo [5/5] Creating release zip...
cd dist\ConstructionAccounting
..\..\scripts\ziprelease.bat "%VERSION%"
cd ..\..

echo Cleaning temp files...
if exist build rmdir /s /q build
if exist *.spec del /q *.spec

echo.
echo ============================================
echo   Build complete!
echo   Output: dist\ConstructionAccounting\
echo   Release: dist\ConstructionAccounting-%VERSION%.zip
echo ============================================
pause
