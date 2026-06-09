@echo off
REM ziprelease.bat <version>
REM Called from build.bat inside dist\ConstructionAccounting\
REM Creates a release zip containing only exe + _internal + manifest

setlocal
set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=1.0.0"

cd /d "%~dp0..\dist\ConstructionAccounting"

echo Creating ConstructionAccounting-%VERSION%.zip...

REM Create zip with only: exe, _internal, and manifest
powershell -NoProfile -Command ^
    "$srcdir = Resolve-Path '.'; " ^
    "$zip = Join-Path (Resolve-Path '..') ('ConstructionAccounting-' + '%VERSION%' + '.zip'); " ^
    "if (Test-Path $zip) { Remove-Item $zip -Force }; " ^
    "Add-Type -AssemblyName System.IO.Compression.FileSystem; " ^
    "$archive = [System.IO.Compression.ZipFile]::Open($zip, 'Create'); " ^
    "try { " ^
    "    $files = @(Get-ChildItem -File -Recurse | Where-Object { $_.Name -ne 'file_manifest.json' -or $_.Directory.FullName -eq $srcdir.FullName }); " ^
    "    foreach ($f in $files) { " ^
    "        $rel = $f.FullName.Substring($srcdir.FullName.Length + 1); " ^
    "        $entry = $archive.CreateEntryFromFile($f.FullName, $rel); " ^
    "    } " ^
    "} finally { $archive.Dispose() }; " ^
    "Write-Output ('Created: ' + $zip)"
