@echo off
chcp 65001 >nul
setlocal

pushd "%~dp0" >nul
if errorlevel 1 goto :directory_error

set "APP_ROOT=%CD%"
set "PYTHON="
set "PYTHON_ARGS="
set "PYTHON_KIND="

rem Prefer the project virtual environment so the installed dependencies are used.
if exist "%APP_ROOT%\.venv\Scripts\pythonw.exe" (
    set "PYTHON=%APP_ROOT%\.venv\Scripts\pythonw.exe"
    set "PYTHON_KIND=pythonw (.venv)"
)
if not defined PYTHON if exist "%APP_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON=%APP_ROOT%\.venv\Scripts\python.exe"
    set "PYTHON_KIND=python (.venv fallback)"
)

rem Fall back to a PATH installation when the project environment is absent.
if not defined PYTHON for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined PYTHON (
    set "PYTHON=%%P"
    set "PYTHON_KIND=pythonw (PATH)"
)
if not defined PYTHON for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON (
    set "PYTHON=%%P"
    set "PYTHON_KIND=python (PATH fallback)"
)
if not defined PYTHON for /f "delims=" %%P in ('where py.exe 2^>nul') do if not defined PYTHON (
    set "PYTHON=%%P"
    set "PYTHON_ARGS=-3"
    set "PYTHON_KIND=py launcher"
)

if not exist "%APP_ROOT%\main.py" goto :main_missing
if not defined PYTHON goto :python_missing

echo [INFO] Launching with %PYTHON_KIND%.
if defined PYTHON_ARGS (
    start "" "%PYTHON%" %PYTHON_ARGS% "%APP_ROOT%\main.py"
) else (
    start "" "%PYTHON%" "%APP_ROOT%\main.py"
)
if errorlevel 1 goto :launch_failed

popd >nul
exit /b 0

:directory_error
echo [ERROR] Cannot open the application directory: %~dp0
goto :fail

:main_missing
echo [ERROR] main.py was not found under: %APP_ROOT%
goto :fail

:python_missing
echo [ERROR] Python 3.10+ was not found.
echo Install Python, or create .venv and install requirements.txt first.
goto :fail

:launch_failed
echo [ERROR] Failed to create the application process.
goto :fail

:fail
if /i not "%CPA_NO_PAUSE%"=="1" pause
popd >nul 2>nul
exit /b 1
