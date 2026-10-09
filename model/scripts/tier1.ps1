# Tầng 1 trên Windows + Docker Desktop (L2 · RTX 4060) — tương đương scripts/tier1.sh.
#   .\model\scripts\tier1.ps1 -Data H:\ -Exp .\model\workspace\experiments\mini [-Sweeps 10] [-Epochs 20] [-Batch 2]
# Yêu cầu: <Exp>\index.parquet đã có (chạy Tầng 0 trước) và image vcuboidfit_pointpillars đã build:
#   docker compose -f model/docker/tier1/docker-compose.yml build
# Cách tương đương bằng compose: xem đầu file model/docker/tier1/docker-compose.yml (service train / infer / tier1).
param(
    [Parameter(Mandatory = $true)][string]$Data,
    [Parameter(Mandatory = $true)][string]$Exp,
    [int]$Sweeps = 10, [int]$Epochs = 20, [int]$Batch = 2,
    [string]$Image = $(if ($env:VCF_TIER1_IMAGE) { $env:VCF_TIER1_IMAGE } else { "vcuboidfit_pointpillars:0.1" })
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..").Path
$DataAbs = (Resolve-Path $Data).Path
New-Item -ItemType Directory -Force $Exp | Out-Null
$ExpAbs = (Resolve-Path $Exp).Path
if (-not (Test-Path "$ExpAbs\index.parquet")) { [Console]::Error.WriteLine("thiếu $ExpAbs\index.parquet — chạy Tầng 0 trước"); exit 4 }

function Invoke-Tier1([string[]]$ModuleArgs) {
    $ErrorActionPreference = "Continue"  # PS 5.1 coi stderr của docker là lỗi — chỉ tin exit code
    docker run --rm --gpus all --shm-size 8g `
        -v "${DataAbs}:/nusc:ro" -v "${ExpAbs}:/exp" -v "${Repo}\worker:/work/worker" `
        -w /work/worker $Image python -m @ModuleArgs
    if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine("$($ModuleArgs[0]) thoát $LASTEXITCODE"); exit $LASTEXITCODE }
}
$t = [Diagnostics.Stopwatch]::StartNew()
Invoke-Tier1 @("c4.lidar.tier1.train_seed", "--sweeps", "$Sweeps", "--epochs", "$Epochs", "--batch", "$Batch")
Write-Host "train_seed: $([int]$t.Elapsed.TotalSeconds) s"
Invoke-Tier1 @("c4.lidar.tier1.infer_t1", "--batch", "$Batch")
Write-Host "tổng: $([int]$t.Elapsed.TotalSeconds) s → $ExpAbs\t1"
