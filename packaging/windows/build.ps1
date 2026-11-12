# Make KentoGo.exe on Windows (see README.md). Run it in PowerShell in the KentoGo folder:
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
#
# It makes dist\KentoGo.exe (the program in one file), dist\KentoGo (the program as a folder: start
# dist\KentoGo\KentoGo.exe) and dist\KentoGo-windows.zip (the folder).

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

# The libraries, with those of the AI commentary and PyInstaller.
uv sync --extra ai --group build
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }

# Newer NVIDIA display drivers put the folders of CUDA in PATH. PyInstaller looks for the DLLs of the
# program in PATH too, and could take one from there, which needs CUDA and TensorRT. KentoGo does not use
# them, so those folders are left out of PATH while the program is made (only in this script).
$env:PATH = ($env:PATH -split ";" | Where-Object { $_ -and $_ -notmatch "NVIDIA|CUDA|TensorRT|cuDNN" }) -join ";"

uv run --no-sync pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\windows\kentogo.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Compress-Archive -Path dist\KentoGo -DestinationPath dist\KentoGo-windows.zip -Force
Write-Host "Made dist\KentoGo.exe, dist\KentoGo\KentoGo.exe and dist\KentoGo-windows.zip"
