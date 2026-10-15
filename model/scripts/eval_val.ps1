# Chấm một bộ trọng số PointPillars trên split T (602 frame VAL giữ lại) bằng Docker + GPU.
#   .\model\scripts\eval_val.ps1 -Nusc E:\nuscenes_trainval [-Weights .\model\weights\pointpillars-trainval-e6] [-Out <thư mục>]
# Yêu cầu: Docker Desktop đang chạy và image vcuboidfit_pointpillars:0.1 đã build
#   (docker compose -f model/docker/tier1/docker-compose.yml build). Xem docs/model-workflow.md §10.
param(
    [Parameter(Mandatory = $true)][string]$Nusc,
    [string]$Weights = "$PSScriptRoot\..\weights\pointpillars-trainval-e6",
    [string]$Index,
    [string]$Out,
    [int]$Batch = 2,
    [string]$Image = $(if ($env:VCF_TIER1_IMAGE) { $env:VCF_TIER1_IMAGE } else { "vcuboidfit_pointpillars:0.1" })
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..").Path
$NuscAbs = (Resolve-Path $Nusc).Path
$W = (Resolve-Path $Weights).Path
$Ckpt = if (Test-Path "$W\seed_latest.pth") { "seed_latest.pth" } else { "t1/ckpt/seed_latest.pth" }
$Cfg = if (Test-Path "$W\pp_seed.yaml") { "pp_seed.yaml" } else { "t1/cfg/pp_seed.yaml" }
$IdxAbs = (Resolve-Path $(if ($Index) { $Index } else { "$Repo\weights\pointpillars-trainval-e6\index.parquet" })).Path
if (-not $Out) { $Out = "$Repo\workspace\experiments\eval-val602\$(Split-Path $W -Leaf)" }
New-Item -ItemType Directory -Force $Out | Out-Null
$OutAbs = (Resolve-Path $Out).Path
docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine("chưa có image $Image (Docker chưa chạy hoặc chưa build)"); exit 4 }
$t = [Diagnostics.Stopwatch]::StartNew()
$ErrorActionPreference = "Continue"  # PS 5.1 coi stderr của docker là lỗi — chỉ tin exit code
docker run --rm --gpus all --shm-size 8g `
    -v "${NuscAbs}:/nusc:ro" -v "${W}:/w:ro" -v "${IdxAbs}:/idx/index.parquet:ro" -v "${OutAbs}:/out" `
    -v "${Repo}\worker:/work/worker" -w /work/worker -e PYTHONPATH=/work/worker:/opt/OpenPCDet $Image `
    python -m c4.lidar.tier1.eval_ckpt --ckpt "/w/$Ckpt" --cfg "/w/$Cfg" --index /idx/index.parquet `
    --nusc /nusc --out /out --batch $Batch 2>&1 | Out-File -Encoding utf8 "$OutAbs\eval.log"
$code = $LASTEXITCODE
if ($code -ne 0) { [Console]::Error.WriteLine("eval_ckpt thoát $code — xem $OutAbs\eval.log"); exit $code }
Get-Content "$OutAbs\eval.txt" | Select-String "mean AP|mAP|NDS"
Write-Host "xong sau $([int]$t.Elapsed.TotalSeconds) s → $OutAbs (eval.txt, eval_summary.json)"
