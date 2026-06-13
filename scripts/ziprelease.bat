@echo off
REM ziprelease.bat <version>
REM Called from build.bat inside dist\ConstructionAccounting\
REM Creates a release zip containing only exe + _internal + manifest

setlocal
set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=1.0.1"

cd /d "%~dp0..\dist\ConstructionAccounting"

echo Creating ConstructionAccounting-%VERSION%.zip...

python "%~dp0zip_release.py" "." "%VERSION%"
