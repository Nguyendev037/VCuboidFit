# Mở cầu nối cho Colab chạy Tầng 1 — MỘT lệnh, không cần cài cloudflared.
#   .\model\scripts\colab_bridge.ps1            # worker chạy bằng Docker (mặc định)
#   .\model\scripts\colab_bridge.ps1 -Python    # worker chạy bằng Python venv (model\worker\.venv)
# Script: tự tải cloudflared.exe (nếu máy chưa có) -> tạo TOKEN -> khởi động lại worker có token
#         -> mở tunnel -> in URL + TOKEN (và chép vào clipboard) để dán vào notebook Colab.
# Tắt cầu nối: .\model\scripts\colab_bridge.ps1 -Stop
param([switch]$Python, [switch]$Stop, [int]$Port = $(if ($env:VCF_PORT) { [int]$env:VCF_PORT } else { 8001 }))
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$Ws = Join-Path $Repo "model\workspace"
$Tools = Join-Path $Ws "tools"
$Log = Join-Path $Tools "cloudflared.log"
$Compose = Join-Path $Repo "model\docker\worker\docker-compose.yml"
New-Item -ItemType Directory -Force $Tools | Out-Null

function Stop-Tunnel { Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue }

if ($Stop) {
    Stop-Tunnel
    Write-Host "Đã tắt tunnel. Worker vẫn chạy; muốn tắt hẳn cầu nối thì khởi động lại worker không có VCF_REMOTE_TOKEN."
    exit 0
}

# 1. cloudflared: dùng bản đã cài, không có thì tải bản chính thức (một file .exe) vào model\workspace\tools
$Cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $Cf) {
    $Cf = Join-Path $Tools "cloudflared.exe"
    if (-not (Test-Path $Cf)) {
        Write-Host "[1/4] Tải cloudflared (~60 MB, một lần)..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $Cf
    }
}
Write-Host "[1/4] cloudflared: $Cf"

# 2. TOKEN: giữ token đang đặt trong cửa sổ này, không có thì sinh mới
if (-not $env:VCF_REMOTE_TOKEN) {
    $b = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    $env:VCF_REMOTE_TOKEN = [Convert]::ToBase64String($b).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}
$Token = $env:VCF_REMOTE_TOKEN

# 3. Worker có token. Worker cũ (không token) đang giữ cổng sẽ che mất worker mới -> tắt trước.
$env:VCF_PORT = "$Port"
$owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $owners) {
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -like "python*") {
        Write-Host "[2/4] Tắt worker Python cũ đang giữ cổng $Port (PID $procId)"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}
if ($Python) {
    Write-Host "[2/4] Khởi động worker (Python) ở cửa sổ mới..."
    $env:WORKSPACE = $Ws
    $Py = Join-Path $Repo "model\worker\.venv\Scripts\python.exe"
    if (-not (Test-Path $Py)) { throw "Chưa có $Py — làm mục 'Cách 2' trong docs\getting-started.md trước." }
    Start-Process -FilePath $Py -WorkingDirectory (Join-Path $Repo "model\worker") `
        -ArgumentList "-m", "uvicorn", "service.main:create_app", "--factory", "--port", "$Port"
} else {
    Write-Host "[2/4] Khởi động lại worker (Docker) có token..."
    $env:WORKSPACE_DIR = $Ws
    $ErrorActionPreference = "Continue"   # docker ghi tiến trình ra stderr
    docker compose -f $Compose up -d --force-recreate worker
    if ($LASTEXITCODE -ne 0) { throw "docker compose lỗi (exit $LASTEXITCODE). Docker Desktop đã bật chưa?" }
    $ErrorActionPreference = "Stop"
}
$ok = $false
foreach ($i in 1..30) {
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) { $ok = $true; break } } catch { }
    Start-Sleep 1
}
if (-not $ok) { throw "Worker không trả lời ở cổng $Port sau 30 s." }
try {
    Invoke-WebRequest "http://127.0.0.1:$Port/remote/t1/t1_000000000000/bundle" -UseBasicParsing `
        -Headers @{ Authorization = "Bearer $Token" } -TimeoutSec 5 | Out-Null
} catch {
    $body = ""
    try { $body = (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() } catch { }
    if ($body -notmatch "not_found") { throw "Worker ở cổng $Port không nhận TOKEN ($body). Có worker khác đang chạy? Tắt nó rồi chạy lại script." }
}
Write-Host "[2/4] Worker OK (cổng $Port, token OK)"

# 4. Tunnel
Stop-Tunnel
Remove-Item $Log -ErrorAction SilentlyContinue
Write-Host "[3/4] Mở tunnel..."
Start-Process -FilePath $Cf -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port" `
    -RedirectStandardError $Log -RedirectStandardOutput "$Log.out" -WindowStyle Hidden
$Url = $null
foreach ($i in 1..60) {
    Start-Sleep 1
    if (Test-Path $Log) {
        $m = Select-String -Path $Log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
        if ($m) { $Url = $m.Matches[0].Value; break }
    }
}
if (-not $Url) { throw "Không lấy được URL tunnel sau 60 s. Xem log: $Log" }
Write-Host "[4/4] Đợi tunnel thông..."
$reach = $false
foreach ($i in 1..30) {
    try { if ((Invoke-WebRequest "$Url/health" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) { $reach = $true; break } } catch { }
    Start-Sleep 2
}

try { Set-Clipboard -Value "SERVER_URL = $Url`r`nTOKEN = $Token" } catch { }
Write-Host ""
Write-Host "================ DÁN 2 DÒNG NÀY VÀO Ô 1 CỦA NOTEBOOK COLAB ================" -ForegroundColor Green
Write-Host "SERVER_URL = $Url" -ForegroundColor Yellow
Write-Host "TOKEN      = $Token" -ForegroundColor Yellow
Write-Host "===========================================================================" -ForegroundColor Green
if (-not $reach) { Write-Host "Lưu ý: tunnel chưa trả lời /health — đợi thêm 30 s rồi mới Run all trên Colab." -ForegroundColor Red }
Write-Host "(Đã chép vào clipboard.) Tunnel chạy nền; giữ máy bật. Tắt: .\model\scripts\colab_bridge.ps1 -Stop"
Write-Host "ĐỪNG khởi động lại worker bằng lệnh khác khi Colab đang chạy: worker mới không có TOKEN -> Colab báo 'worker chua bat VCF_REMOTE_TOKEN'. Cần khởi động lại thì chạy lại script này." -ForegroundColor Cyan
