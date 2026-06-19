@echo off
REM ziprelease.bat <version> [platform]
REM Called from build.bat inside dist\ConstructionAccounting\
REM Creates a release zip containing only exe + _internal + manifest

setlocal
set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=1.0.1"
set "PLATFORM=%~2"
if "%PLATFORM%"=="" set "PLATFORM=win64"

cd /d "%~dp0..\dist\ConstructionAccounting"

echo Creating ConstructionAccounting-%VERSION%-%PLATFORM%.zip...

python "%~dp0zip_release.py" "." "%VERSION%" "%PLATFORM%"
