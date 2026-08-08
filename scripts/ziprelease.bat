@echo off
setlocal

rem Usage: ziprelease.bat <build_dir> <version> [platform]
set "SCRIPT_DIR=%~dp0"
set "BUILD_DIR=%~1"
set "VERSION=%~2"
set "PLATFORM=%~3"
if "%PLATFORM%"=="" set "PLATFORM=win64"

if not defined BUILD_DIR (
    set "BUILD_DIR=%SCRIPT_DIR%..\dist\ConstructionAccounting"
)
if not exist "%BUILD_DIR%\." (
    echo [ERROR] Release directory not found: %BUILD_DIR%
    endlocal & exit /b 1
)

if not defined PYTHON if exist "%SCRIPT_DIR%..\.venv\Scripts\python.exe" set "PYTHON=%SCRIPT_DIR%..\.venv\Scripts\python.exe"
if not defined PYTHON for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON set "PYTHON=%%P"
if not defined PYTHON (
    echo [ERROR] Python was not found for release ZIP creation.
    endlocal & exit /b 1
)

echo Creating ConstructionAccounting-%VERSION%-%PLATFORM%.zip...
"%PYTHON%" "%SCRIPT_DIR%zip_release.py" "%BUILD_DIR%" "%VERSION%" "%PLATFORM%"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo [ERROR] ZIP creation failed with exit code %EXIT_CODE%.
endlocal & exit /b %EXIT_CODE%
