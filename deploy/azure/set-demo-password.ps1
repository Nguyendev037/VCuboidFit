# Set (or rotate) the demo password of ca-vcuboidfit without it touching disk, logs or history.
# Needed after `deploy.ps1 -DeferDemoPassword`, which locks the app with an unknown password.
$ErrorActionPreference = "Stop"
$env:AZURE_CORE_ONLY_SHOW_ERRORS = "true"
$rg = "rg-vcuboidfit-demo"
$app = "ca-vcuboidfit"

$s1 = Read-Host "New demo password" -AsSecureString
$s2 = Read-Host "Repeat" -AsSecureString
$p1 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s1)
$p2 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s2)
try {
  $pw = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p1)
  $pw2 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p2)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p1)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p2)
}
if ($pw -ne $pw2) { throw "Passwords differ." }
if ($pw.Length -lt 8) { throw "Use at least 8 characters." }
# az.cmd runs through cmd.exe, which mangles these characters inside arguments.
if ($pw -match '[\s"&|<>^%!]') { throw "Avoid spaces and the characters "" & | < > ^ % ! (cmd.exe would mangle them)." }

$ErrorActionPreference = "Continue"
& az containerapp secret set -n $app -g $rg --secrets "demo-password=$pw" -o none *> $null
$code = $LASTEXITCODE
$pw = $null; $pw2 = $null
if ($code -ne 0) { throw "az containerapp secret set failed with exit code $code (value not shown)" }

# Secrets are read at container start: restart the active revision to apply.
$rev = (& az containerapp show -n $app -g $rg --query properties.latestRevisionName -o tsv).Trim()
& az containerapp revision restart -n $app -g $rg --revision $rev -o none
if ($LASTEXITCODE -ne 0) { throw "revision restart failed with exit code $LASTEXITCODE" }
Write-Output "Demo password updated; revision $rev restarted."
