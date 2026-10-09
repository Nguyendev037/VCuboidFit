# Native worker for local Tier 1. Never stop an existing listener.
param(
    [ValidateRange(1, 65535)][int]$Port = 8001,
    [string]$Exp
)
$ErrorActionPreference = "Stop"
$Repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$Worker = Join-Path $Repo "model\worker"
$env:WORKSPACE = Join-Path $Repo "model\workspace"
$env:VCF_PORT = [string]$Port

if ($Exp) {
    $env:VCF_T1_EXP = (Resolve-Path -LiteralPath $Exp).Path
} else {
    $Experiments = Join-Path $env:WORKSPACE "experiments"
    $Seed = $null
    if (Test-Path -LiteralPath $Experiments -PathType Container) {
        $Seed = Get-ChildItem -LiteralPath $Experiments -Directory |
            Where-Object {
                (Test-Path -LiteralPath (Join-Path $_.FullName "t1\ckpt\seed_latest.pth") -PathType Leaf) -and
                (Test-Path -LiteralPath (Join-Path $_.FullName "t1\cfg\pp_seed.yaml") -PathType Leaf) -and
                (Test-Path -LiteralPath (Join-Path $_.FullName "index.parquet") -PathType Leaf)
            } |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
    }
    $env:VCF_T1_EXP = if ($Seed) { $Seed.FullName } else { $null }
}
# VCF_REMOTE_TOKEN is inherited unchanged from the caller.
$SeedLabel = if ($env:VCF_T1_EXP) { $env:VCF_T1_EXP } else { "không có" }
Write-Host "Cổng: $Port | workspace: $env:WORKSPACE | seed: $SeedLabel"

$Listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
    Where-Object { $_.LocalPort -eq $Port })
if ($Listeners.Count -gt 0) {
    foreach ($OwnerId in ($Listeners.OwningProcess | Sort-Object -Unique)) {
        $Owner = Get-Process -Id $OwnerId -ErrorAction SilentlyContinue
        $OwnerName = if ($Owner) { $Owner.ProcessName } else { "không xác định" }
        Write-Host "Cổng $Port đang bận: $OwnerName (PID $OwnerId)."
    }
    exit 3
}

$Python = Join-Path $Worker ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    [Console]::Error.WriteLine("Chưa có Python venv; xem docs/getting-started.md.")
    exit 4
}
Push-Location -LiteralPath $Worker
try {
    & $Python -m uvicorn service.main:create_app --factory --host 127.0.0.1 --port $Port
    $WorkerExit = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $WorkerExit
