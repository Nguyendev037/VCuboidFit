param(
  [Parameter(Mandatory = $true)][string]$Location,
  [string]$Tag = "",
  # ACR Tasks (`az acr build`) is not offered in every region (e.g. malaysiawest has no
  # registries/runs); the registry may live elsewhere, the app pulls cross-region.
  [string]$AcrLocation = "japaneast",
  # Image vcf:$Tag already pushed (e.g. by an earlier run) => skip docker build/push.
  [switch]$SkipBuild,
  # First create without an operator: lock the app with an unknown random password; set the
  # real one later with set-demo-password.ps1.
  [switch]$DeferDemoPassword
)

$ErrorActionPreference = "Stop"
# az preview warnings go to stderr; under PS 5.1 + Stop a redirected stderr line is fatal.
$env:AZURE_CORE_ONLY_SHOW_ERRORS = "true"
if (-not $Tag) { $Tag = (git rev-parse --short HEAD).Trim() }

$rg = "rg-vcuboidfit-demo"
$budget = "budget-vcuboidfit-demo"
$namesPath = Join-Path $PSScriptRoot ".names.json"
$tags = "project=vcuboidfit owner=nguyendev037 expires=2026-11-01"

function Invoke-Az {
  param([Parameter(Mandatory = $true)][string[]]$Arguments)
  $ErrorActionPreference = "Continue"  # judge az by exit code, not by stderr text
  & az @Arguments
  if ($LASTEXITCODE -ne 0) {
    # Never echo secrets: mask the value after any *-key / *-password / *-token flag.
    $shown = for ($i = 0; $i -lt $Arguments.Count; $i++) {
      if ($i -gt 0 -and $Arguments[$i - 1] -match '-(key|password|token)$') { "***" } else { $Arguments[$i] }
    }
    throw "az $($shown -join ' ') failed with exit code $LASTEXITCODE"
  }
}

function Test-AzResource {
  param([Parameter(Mandatory = $true)][string[]]$Arguments)
  $ErrorActionPreference = "Continue"
  & az @Arguments *> $null
  return $LASTEXITCODE -eq 0
}

# App/job are created by ARM PUT: `az containerapp create --yaml` (api 2025-07-01) sends an
# envelope full of nulls that a WorkloadProfiles environment rejects (400 "could not be
# converted to System.Boolean"). The body holds secrets => temp file, never echoed, deleted.
$armApi = "2026-07-01"
$tagMap = @{ project = "vcuboidfit"; owner = "nguyendev037"; expires = "2026-11-01" }
function Invoke-ArmPut {
  param([Parameter(Mandatory = $true)][string]$Uri, [Parameter(Mandatory = $true)]$Body)
  $file = Join-Path $env:TEMP ("vcf-arm-" + [guid]::NewGuid().ToString() + ".json")
  try {
    $Body | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $file
    Invoke-Az @("rest", "--method", "put", "--uri", $Uri, "--body", "@$file", "-o", "none")
  } finally { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }
}
function Wait-ArmSucceeded {
  param([Parameter(Mandatory = $true)][string]$Uri)
  for ($i = 0; $i -lt 40; $i++) {
    $state = (& az rest --method get --uri $Uri --query properties.provisioningState -o tsv)
    if ($state) { $state = $state.Trim() }
    if ($state -eq "Succeeded") { return }
    if ($state -eq "Failed" -or $state -eq "Canceled") { throw "provisioning $state for $Uri" }
    Start-Sleep -Seconds 30
  }
  throw "timed out waiting for $Uri"
}

if (Test-Path $namesPath) {
  $names = Get-Content $namesPath -Raw | ConvertFrom-Json
  $acr = $names.acr
  $st = $names.storage
} else {
  $acr = "acrvcf" + ((Get-Random -Minimum 100000 -Maximum 999999).ToString())
  $st = "stvcf" + ((Get-Random -Minimum 100000 -Maximum 999999).ToString())
  # Persist at once: a failed run must not mint new names (and duplicate resources) on rerun.
  @{ resourceGroup = $rg; acr = $acr; storage = $st } | ConvertTo-Json | Set-Content -Encoding utf8 $namesPath
}

# RG location is metadata only; an existing RG in another region is reused as-is.
if ((& az group exists -n $rg).Trim() -ne "true") {
  Invoke-Az @("group", "create", "-n", $rg, "-l", $Location, "--tags", $tags, "-o", "none")
}

# `az consumption budget` has no --scope flag; without -g it targets the subscription.
if (-not (Test-AzResource @("consumption", "budget", "show", "--budget-name", $budget, "-o", "none"))) {
  try {
    Invoke-Az @("consumption", "budget", "create", "--budget-name", $budget, "--amount", "100",
      "--category", "Cost", "--time-grain", "Monthly",
      "--start-date", "2026-10-01", "--end-date", "2026-11-30")
  } catch {
    Write-Error "Budget creation failed. Create budget-vcuboidfit-demo manually in Azure Portal (Cost Management > Budgets), then rerun this script."
    exit 1
  }
}
if (-not (Test-AzResource @("consumption", "budget", "show", "--budget-name", $budget, "-o", "none"))) {
  Write-Error "Budget $budget was not found; no chargeable resources will be created."
  exit 1
}

if (-not (Test-AzResource @("acr", "show", "-n", $acr, "-g", $rg, "-o", "none"))) {
  Invoke-Az @("acr", "create", "-n", $acr, "-g", $rg, "-l", $AcrLocation, "--sku", "Basic",
    "--admin-enabled", "false", "--tags", $tags, "-o", "none")
}
$acrId = (& az acr show -n $acr -g $rg --query id -o tsv).Trim()

# One user-assigned identity with AcrPull, granted BEFORE the app/job exist so the first
# revision can pull (a system identity only exists after create => first pull is 401).
$identity = "id-vcuboidfit"
if (-not (Test-AzResource @("identity", "show", "-n", $identity, "-g", $rg, "-o", "none"))) {
  Invoke-Az @("identity", "create", "-n", $identity, "-g", $rg, "-l", $Location, "--tags", $tags, "-o", "none")
}
$idId = (& az identity show -n $identity -g $rg --query id -o tsv).Trim()
$idPrincipal = (& az identity show -n $identity -g $rg --query principalId -o tsv).Trim()
# No parentheses in --query: az.bat goes through cmd.exe, which mis-parses "length(@)".
$pullIds = @(& az role assignment list --assignee $idPrincipal --scope $acrId --role AcrPull --query "[].id" -o tsv)
if ($pullIds.Count -eq 0 -or -not $pullIds[0]) {
  Invoke-Az @("role", "assignment", "create", "--assignee-object-id", $idPrincipal,
    "--assignee-principal-type", "ServicePrincipal", "--role", "AcrPull", "--scope", $acrId, "-o", "none")
}
# Local `docker build` + push: Azure for Students rejects ACR Tasks (`az acr build` =>
# TasksOperationsNotAllowed). Build from a staged context holding only what the Dockerfile
# COPYs (the repo carries ~21 GB of model/workspace + .venv).
$acrServer = (& az acr show -n $acr -g $rg --query loginServer -o tsv).Trim()
$image = "$acrServer/vcf:$Tag"
if (-not $SkipBuild) {
$tmpRoot = if (Test-Path "E:\") { "E:\" } else { $env:TEMP }
$ctx = Join-Path $tmpRoot ("vcf-ctx-" + $Tag)
if (Test-Path $ctx) { Remove-Item -LiteralPath $ctx -Recurse -Force }
$repo = (git rev-parse --show-toplevel).Trim()
$stage = @(
  @{ src = "web"; xd = @("node_modules", ".next", "test-results", "mock-media") },
  @{ src = "model/worker/c4"; xd = @("__pycache__") },
  @{ src = "model/worker/service"; xd = @("__pycache__") },
  @{ src = "model/worker/configs"; xd = @() },
  @{ src = "deploy/azure"; xd = @() }
)
try {
  foreach ($s in $stage) {
    $rcArgs = @((Join-Path $repo $s.src), (Join-Path $ctx $s.src), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    if ($s.xd.Count) { $rcArgs += "/XD"; $rcArgs += $s.xd }
    $rcArgs += "/XF"; $rcArgs += @(".env.local", ".env.*.local")  # local config never ships
    & robocopy @rcArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy $($s.src) failed with exit code $LASTEXITCODE" }
  }
  Copy-Item (Join-Path $repo "model/worker/pyproject.toml") (Join-Path $ctx "model/worker/pyproject.toml")
  Copy-Item (Join-Path $repo ".dockerignore") (Join-Path $ctx ".dockerignore")
  $ctxMb = [math]::Round(((Get-ChildItem $ctx -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
  Write-Output "Build context: $ctx ($ctxMb MB)"
  $ErrorActionPreference = "Continue"  # docker writes progress to stderr
  & docker build -f (Join-Path $ctx "deploy/azure/Dockerfile") -t $image $ctx
  if ($LASTEXITCODE -ne 0) { throw "docker build failed with exit code $LASTEXITCODE" }
  Invoke-Az @("acr", "login", "-n", $acr)
  & docker push $image
  if ($LASTEXITCODE -ne 0) { throw "docker push failed with exit code $LASTEXITCODE" }
  $ErrorActionPreference = "Stop"
} finally {
  Remove-Item -LiteralPath $ctx -Recurse -Force -ErrorAction SilentlyContinue
}
}

if (-not (Test-AzResource @("storage", "account", "show", "-n", $st, "-g", $rg, "-o", "none"))) {
  Invoke-Az @("storage", "account", "create", "-n", $st, "-g", $rg, "-l", $Location,
    "--sku", "Standard_LRS", "--kind", "StorageV2", "--min-tls-version", "TLS1_2",
    "--allow-blob-public-access", "false", "--tags", $tags, "-o", "none")
}
if (-not (Test-AzResource @("storage", "share-rm", "show", "-g", $rg, "--storage-account", $st,
      "--name", "workspace", "-o", "none"))) {
  Invoke-Az @("storage", "share-rm", "create", "-g", $rg, "--storage-account", $st,
    "--name", "workspace", "--quota", "100", "--access-tier", "TransactionOptimized", "-o", "none")
}
$storageKey = (& az storage account keys list -g $rg -n $st --query "[0].value" -o tsv).Trim()
if ($LASTEXITCODE -ne 0 -or -not $storageKey) { throw "storage account key lookup failed" }

# `az containerapp env create` (CLI 2.91) yields an Express environment here (no Azure Files,
# no jobs: ExpressEnvironmentResourceNotSupported) and has no mode flag. Create it via ARM with
# an explicit mode; only api >= 2026-07-01 exposes environmentMode (older ones return null).
# Valid modes: WorkloadProfiles, ConsumptionOnly, Reserved, Express ("Standard" is rejected).
$subId = (& az account show --query id -o tsv).Trim()
$envUri = "https://management.azure.com/subscriptions/$subId/resourceGroups/$rg/providers/Microsoft.App/managedEnvironments/cae-vcuboidfit?api-version=2026-07-01"
if (-not (Test-AzResource @("containerapp", "env", "show", "-n", "cae-vcuboidfit", "-g", $rg, "-o", "none"))) {
  $envBody = Join-Path $env:TEMP ("vcf-env-" + [guid]::NewGuid().ToString() + ".json")
  @{
    location   = $Location
    tags       = @{ project = "vcuboidfit"; owner = "nguyendev037"; expires = "2026-11-01" }
    properties = @{
      environmentMode       = "WorkloadProfiles"
      workloadProfiles      = @(@{ name = "Consumption"; workloadProfileType = "Consumption" })
      zoneRedundant         = $false
    }
  } | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $envBody
  try { Invoke-Az @("rest", "--method", "put", "--uri", $envUri, "--body", "@$envBody", "-o", "none") }
  finally { Remove-Item -LiteralPath $envBody -Force -ErrorAction SilentlyContinue }
  for ($i = 0; $i -lt 40; $i++) {
    $envState = (& az containerapp env show -n "cae-vcuboidfit" -g $rg --query properties.provisioningState -o tsv).Trim()
    if ($envState -eq "Succeeded") { break }
    if ($envState -eq "Failed") { throw "environment cae-vcuboidfit provisioning failed" }
    Start-Sleep -Seconds 30
  }
}
$envMode = (& az rest --method get --uri $envUri --query properties.environmentMode -o tsv)
if ($envMode -and $envMode.Trim() -eq "Express") {
  throw "cae-vcuboidfit is an Express environment (no Azure Files / jobs). Delete it and rerun."
}
Invoke-Az @("containerapp", "env", "storage", "set", "-n", "cae-vcuboidfit", "-g", $rg,
  "--storage-name", "vcfws", "--azure-file-account-name", $st,
  "--azure-file-account-key", $storageKey, "--azure-file-share-name", "workspace",
  "--access-mode", "ReadWrite", "-o", "none")

@{ resourceGroup = $rg; acr = $acr; storage = $st; tag = $Tag } |
  ConvertTo-Json | Set-Content -Encoding utf8 $namesPath
$envId = (& az containerapp env show -n "cae-vcuboidfit" -g $rg --query id -o tsv).Trim()
$armBase = "https://management.azure.com/subscriptions/$subId/resourceGroups/$rg/providers/Microsoft.App"

if (-not (Test-AzResource @("containerapp", "show", "-n", "ca-vcuboidfit", "-g", $rg, "-o", "none"))) {
  if ($DeferDemoPassword) {
    # Unattended run: a random password nobody sees locks the app until the operator runs
    # set-demo-password.ps1; the token goes to a file outside the repo, never to the console.
    $demoPassword = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object { [char]$_ })
  } else {
    $demoSecure = Read-Host "Demo password" -AsSecureString
    $demoPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($demoSecure)
    try { $demoPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($demoPtr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($demoPtr) }
  }
  $remoteToken = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
  if ($DeferDemoPassword) {
    $tokenDir = Join-Path $env:USERPROFILE ".vcuboidfit"
    New-Item -ItemType Directory -Force $tokenDir | Out-Null
    Set-Content -Encoding ascii -Value $remoteToken (Join-Path $tokenDir "remote-token.txt")
    Write-Output "remote-token written to $tokenDir\remote-token.txt (outside the repo)"
  } else {
    Write-Output "Copy this remote-token once for the GPU agent: $remoteToken"
  }
  $vol = @(@{ name = "vcfws"; storageType = "AzureFile"; storageName = "vcfws" })
  $mount = @(@{ volumeName = "vcfws"; mountPath = "/data/workspace" })
  $app = @{
    location   = $Location
    tags       = $tagMap
    identity   = @{ type = "UserAssigned"; userAssignedIdentities = @{ $idId = @{} } }
    properties = @{
      environmentId = $envId
      configuration = @{
        activeRevisionsMode = "Single"
        ingress    = @{ external = $true; targetPort = 3000; transport = "auto" }
        registries = @(@{ server = $acrServer; identity = $idId })
        secrets    = @(@{ name = "demo-password"; value = $demoPassword },
                       @{ name = "remote-token"; value = $remoteToken })
      }
      template = @{
        containers = @(@{
          name = "vcuboidfit"; image = $image
          resources = @{ cpu = 2.0; memory = "4Gi" }
          env = @(
            @{ name = "VCF_DEMO_PASSWORD"; secretRef = "demo-password" },
            @{ name = "VCF_REMOTE_TOKEN"; secretRef = "remote-token" },
            @{ name = "VCF_SESSIONS"; value = "1" },
            @{ name = "NEXT_PUBLIC_VCF_SESSIONS"; value = "1" },
            @{ name = "WORKSPACE"; value = "/data/workspace" },
            @{ name = "MAX_UPLOAD_GB"; value = "20" })
          volumeMounts = $mount
        })
        scale   = @{ minReplicas = 0; maxReplicas = 1 }
        volumes = $vol
      }
    }
  }
  Invoke-ArmPut "$armBase/containerApps/ca-vcuboidfit?api-version=$armApi" $app
  Wait-ArmSucceeded "$armBase/containerApps/ca-vcuboidfit?api-version=$armApi"
} else {
  Invoke-Az @("containerapp", "update", "-n", "ca-vcuboidfit", "-g", $rg, "--image", $image, "-o", "none")
}

if (-not (Test-AzResource @("containerapp", "job", "show", "-n", "job-vcf-sweep", "-g", $rg, "-o", "none"))) {
  $job = @{
    location   = $Location
    tags       = $tagMap
    identity   = @{ type = "UserAssigned"; userAssignedIdentities = @{ $idId = @{} } }
    properties = @{
      environmentId = $envId
      configuration = @{
        registries            = @(@{ server = $acrServer; identity = $idId })
        triggerType           = "Schedule"
        scheduleTriggerConfig = @{ cronExpression = "0 * * * *"; replicaCompletionCount = 1; parallelism = 1 }
        replicaRetryLimit     = 0
        replicaTimeout        = 600
      }
      template = @{
        containers = @(@{
          name = "vcf-sweep"; image = $image
          resources = @{ cpu = 0.5; memory = "1Gi" }
          command = @("python", "-m", "service.sweep")
          env = @(
            @{ name = "WORKSPACE"; value = "/data/workspace" },
            @{ name = "VCF_SESSIONS"; value = "1" },
            @{ name = "VCF_SESSION_TTL_H"; value = "24" })
          volumeMounts = $mount
        })
        volumes = $vol
      }
    }
  }
  Invoke-ArmPut "$armBase/jobs/job-vcf-sweep?api-version=$armApi" $job
  Wait-ArmSucceeded "$armBase/jobs/job-vcf-sweep?api-version=$armApi"
} else {
  Invoke-Az @("containerapp", "job", "update", "-n", "job-vcf-sweep", "-g", $rg, "--image", $image, "-o", "none")
}

$fqdn = (& az containerapp show -n "ca-vcuboidfit" -g $rg --query properties.configuration.ingress.fqdn -o tsv).Trim()
Write-Output "Container App FQDN: $fqdn"
