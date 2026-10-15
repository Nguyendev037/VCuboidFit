param(
  [Parameter(Mandatory=$true)][string]$Location,
  [string]$Tag = ""
)
$ErrorActionPreference = "Stop"
if (-not $Tag) { $Tag = (git rev-parse --short HEAD).Trim() }
$rg = "rg-vcuboidfit-demo"
$namesPath = Join-Path $PSScriptRoot ".names.json"
if (Test-Path $namesPath) {
  $names = Get-Content $namesPath -Raw | ConvertFrom-Json
  $acr = $names.acr
  $st = $names.storage
} else {
  $acr = "acrvcf" + ((Get-Random -Minimum 100000 -Maximum 999999).ToString())
  $st = "stvcf" + ((Get-Random -Minimum 100000 -Maximum 999999).ToString())
}
az group create -n $rg -l $Location --tags project=vcuboidfit owner=nguyendev037 expires=2026-11-01 | Out-Null
if ($LASTEXITCODE) { throw "az group create failed" }
$subscription = (az account show --query id -o tsv).Trim()
if ($LASTEXITCODE -or -not $subscription) { throw "az account show failed" }
az consumption budget create --budget-name budget-vcuboidfit-demo --amount 100 --category Cost `
  --time-grain Monthly --time-period start=2026-10-15 end=2026-11-01 `
  --scope "/subscriptions/$subscription" `
  --notifications '{"actual25":{"enabled":true,"operator":"GreaterThanOrEqual","threshold":25,"contactEmails":["nguyenndev037@gmail.com"]},"actual50":{"enabled":true,"operator":"GreaterThanOrEqual","threshold":50,"contactEmails":["nguyenndev037@gmail.com"]},"actual75":{"enabled":true,"operator":"GreaterThanOrEqual","threshold":75,"contactEmails":["nguyenndev037@gmail.com"]},"forecast100":{"enabled":true,"operator":"GreaterThanOrEqual","threshold":100,"contactEmails":["nguyenndev037@gmail.com"]}}' | Out-Null
if ($LASTEXITCODE) { throw "az consumption budget create failed; create the budget in Portal if Students blocks the CLI" }
az acr create -n $acr -g $rg --sku Basic --admin-enabled false --tags project=vcuboidfit owner=nguyendev037 expires=2026-11-01 | Out-Null
if ($LASTEXITCODE) { throw "az acr create failed" }
az acr build -r $acr -t "vcf:$Tag" -f deploy/azure/Dockerfile . 
if ($LASTEXITCODE) { throw "az acr build failed" }
az storage account create -n $st -g $rg -l $Location --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false
if ($LASTEXITCODE) { throw "az storage account create failed" }
az storage share-rm create -g $rg --storage-account $st --name workspace --quota 100
if ($LASTEXITCODE) { throw "az storage share-rm create failed" }
@{ resourceGroup=$rg; acr=$acr; storage=$st; tag=$Tag } |
  ConvertTo-Json | Set-Content -Encoding utf8 deploy/azure/.names.json
Write-Output "Preflight complete. Continue with the Container Apps environment after budget approval."
