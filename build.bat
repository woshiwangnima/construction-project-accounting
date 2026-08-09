@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
pushd "%ROOT%" >nul
if errorlevel 1 goto :fail

set "PYTHON="
if exist "%ROOT%.venv\Scripts\python.exe" set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not defined PYTHON for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON set "PYTHON=%%P"
if not defined PYTHON (
    echo [ERROR] Python 3.10+ was not found.
    echo Install Python or create .venv and install requirements-dev.txt.
    goto :fail
)

if not exist "%ROOT%main.py" (
    echo [ERROR] main.py was not found under %ROOT%.
    goto :fail
)
if not exist "%ROOT%config\app_config.json" (
    echo [ERROR] config\app_config.json is missing.
    goto :fail
)
if not exist "%ROOT%assets\audio\." (
    echo [ERROR] assets\audio is missing.
    goto :fail
)

"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer is required.
    goto :fail
)
"%PYTHON%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pip is not available for %PYTHON%.
    goto :fail
)
"%PYTHON%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed for this interpreter.
    echo Install it with: %PYTHON% -m pip install -r requirements-dev.txt
    goto :fail
)
"%PYTHON%" -m pip check
if errorlevel 1 (
    echo [ERROR] Installed dependencies are inconsistent.
    goto :fail
)

set "PLATFORM=%~1"
if "%PLATFORM%"=="" set "PLATFORM=win64"
set "VERSION="
set "VERSION_OUTPUT=%TEMP%\cpa_version_%RANDOM%_%RANDOM%.txt"
"%PYTHON%" "%ROOT%scripts\read_app_version.py" > "%VERSION_OUTPUT%"
if errorlevel 1 (
    del /q "%VERSION_OUTPUT%" >nul 2>nul
    goto :fail
)
set /p VERSION=<"%VERSION_OUTPUT%"
del /q "%VERSION_OUTPUT%" >nul 2>nul
if not defined VERSION (
    echo [ERROR] Could not read APP_VERSION from src\versioning.py.
    goto :fail
)

set "DIST_DIR=%ROOT%dist"
set "APP_DIR=%DIST_DIR%\ConstructionAccounting"
set "WORK_DIR=%ROOT%build"
if not exist "%DIST_DIR%\." mkdir "%DIST_DIR%"
if errorlevel 1 goto :fail

echo ============================================
echo   Building Construction Accounting
echo   Version: %VERSION%
echo   Target: %PLATFORM%
echo ============================================
echo.

echo [1/5] Preparing generated build directories...
if exist "%APP_DIR%\." rmdir /s /q "%APP_DIR%"
if exist "%APP_DIR%\." (
    echo [ERROR] Could not replace %APP_DIR%.
    goto :fail
)
if exist "%WORK_DIR%\." rmdir /s /q "%WORK_DIR%"
if exist "%WORK_DIR%\." (
    echo [ERROR] Could not clean the temporary build directory.
    goto :fail
)

echo [2/5] Building with PyInstaller (onedir)...
"%PYTHON%" -m PyInstaller --noconfirm --clean --onedir --windowed --name "ConstructionAccounting" --icon "%ROOT%assets\icon.ico" --add-data "%ROOT%config;config" --add-data "%ROOT%assets;assets" --hidden-import pyttsx3 --hidden-import comtypes --hidden-import comtypes.gen --hidden-import pythoncom --hidden-import pywintypes --hidden-import qtawesome --hidden-import qfluentwidgets --distpath "%DIST_DIR%" --workpath "%WORK_DIR%" --specpath "%WORK_DIR%\spec" "%ROOT%main.py"
set "PYINSTALLER_EXIT=%ERRORLEVEL%"
if not "%PYINSTALLER_EXIT%"=="0" (
    echo [ERROR] PyInstaller build failed.
    goto :fail
)
if not exist "%APP_DIR%\ConstructionAccounting.exe" (
    echo [ERROR] PyInstaller did not produce ConstructionAccounting.exe.
    goto :fail
)

echo [3/5] Copying bundled config files...
if not exist "%APP_DIR%\config\." mkdir "%APP_DIR%\config"
if errorlevel 1 goto :fail
xcopy /e /i /q /y "config\*" "%APP_DIR%\config\" >nul
if errorlevel 4 (
    echo [ERROR] Could not copy config files into the release directory.
    goto :fail
)
if not exist "%APP_DIR%\config\app_config.json" (
    echo [ERROR] The release directory is missing config\app_config.json.
    goto :fail
)
if not exist "%APP_DIR%\_internal\assets\audio\0.wav" if not exist "%APP_DIR%\assets\audio\0.wav" (
    echo [ERROR] The release directory is missing bundled audio assets.
    goto :fail
)

echo [4/5] Generating and validating the file manifest...
"%PYTHON%" "%ROOT%scripts\generate_manifest.py" "%APP_DIR%" --version "%VERSION%" --platform "%PLATFORM%"
if errorlevel 1 goto :fail

echo [5/5] Creating and validating release ZIP...
call "%ROOT%scripts\ziprelease.bat" "%APP_DIR%" "%VERSION%" "%PLATFORM%"
if errorlevel 1 (
    echo [ERROR] Release ZIP creation failed.
    goto :fail
)
set "ZIP_PATH=%DIST_DIR%\ConstructionAccounting-%VERSION%-%PLATFORM%.zip"
if not exist "%ZIP_PATH%" (
    echo [ERROR] Expected release ZIP was not created: %ZIP_PATH%
    goto :fail
)

echo Cleaning temporary build files...
if exist "%WORK_DIR%\." rmdir /s /q "%WORK_DIR%"
if exist "%WORK_DIR%\." (
    echo [ERROR] Could not remove the temporary build directory.
    goto :fail
)

echo.
echo ============================================
echo   Build complete!
echo   Output: %APP_DIR%\
echo   Release: %ZIP_PATH%
echo ============================================
goto :success

:success
popd >nul
endlocal & exit /b 0

:fail
if /i not "%CPA_NO_PAUSE%"=="1" pause
popd >nul 2>nul
endlocal & exit /b 1
