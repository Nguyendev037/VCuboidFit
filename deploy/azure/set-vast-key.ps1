# Store an account API key as a Container App secret; never write its value to disk.
$ErrorActionPreference = "Stop"
$env:AZURE_CORE_ONLY_SHOW_ERRORS = "true"
$rg = "rg-vcuboidfit-demo"
$app = "ca-vcuboidfit"
$secure = Read-Host "Vast API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
try {
  if (-not $key -or $key -match '[\s"&|<>^%!]') {
    throw "Empty key or characters unsupported by az.cmd."
  }
  $ErrorActionPreference = "Continue"
  & az containerapp secret set -n $app -g $rg --secrets "vast-api-key=$key" -o none *> $null
  $code = $LASTEXITCODE
  if ($code -ne 0) { throw "Vast secret update failed with exit code $code (value not shown)." }
} finally { $key = $null; $secure = $null }
Write-Output "Vast secret stored. Rerun deploy.ps1 -SkipBuild to configure GPU environment."
