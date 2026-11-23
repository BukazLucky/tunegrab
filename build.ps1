# Builds dist\Tunegrab.exe  (run:  powershell -ExecutionPolicy Bypass -File build.ps1)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m pip install -q -r requirements.txt pyinstaller
python tools\make_icon.py
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name Tunegrab `
  --icon assets\icon.ico `
  --version-file tools\version_info.txt `
  --add-data "assets;assets" `
  --add-data "tunegrab\locales;tunegrab\locales" `
  --collect-data customtkinter `
  --exclude-module numpy --exclude-module matplotlib --exclude-module pytest `
  tunegrab.pyw
Write-Host "Done: dist\Tunegrab.exe"
