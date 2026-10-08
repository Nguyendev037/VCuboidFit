# Build dist/vcf-pack.exe (PyInstaller --onefile) and smoke-test it.
# Run from tools/vcf-pack:  powershell -File build_exe.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) { python -m venv .venv }
& .venv\Scripts\pip install -q -e ".[dev]"

& .venv\Scripts\pyinstaller --onefile --clean --noconfirm --name vcf-pack `
    --distpath dist --workpath build --specpath build `
    vcf_pack\__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

& dist\vcf-pack.exe --help
if ($LASTEXITCODE -ne 0) { throw "vcf-pack.exe --help failed ($LASTEXITCODE)" }
Write-Host "OK: dist\vcf-pack.exe"
