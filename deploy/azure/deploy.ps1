param(
  [Parameter(Mandatory = $true)][string]$Location,
  [string]$Tag = ""
)

$ErrorActionPreference = "Stop"
if (-not $Tag) { $Tag = (git rev-parse --short HEAD).Trim() }

$rg = "rg-vcuboidfit-demo"
$budget = "budget-vcuboidfit-demo"
$namesPath = Join-Path $PSScriptRoot ".names.json"
$tags = "project=vcuboidfit owner=nguyendev037 expires=2026-11-01"

function Invoke-Az {
  param([Parameter(Mandatory = $true)][string[]]$Arguments)
  & az @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "az $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
}

function Test-AzResource {
  param([Parameter(Mandatory = $true)][string[]]$Arguments)
  & az @Arguments *> $null
  return $LASTEXITCODE -eq 0
}

if (Test-Path $namesPath) {
  $names = Get-Content $namesPath -Raw | ConvertFrom-Json
  $acr = $names.acr
  $st = $names.storage
} else {
  $acr = "acrvcf" + ((Get-Random -Minimum 100000 -Maximum 999999).ToString())
  $st = "stvcf" + ((Get-Random -Minimum 100000 -Maximum 999999).ToString())
}

Invoke-Az @("group", "create", "-n", $rg, "-l", $Location, "--tags", $tags, "-o", "none")
$subscription = (& az account show --query id -o tsv).Trim()
if ($LASTEXITCODE -ne 0 -or -not $subscription) { throw "az account show failed" }
$scope = "/subscriptions/$subscription"

if (-not (Test-AzResource @("consumption", "budget", "show", "--budget-name", $budget,
      "--scope", $scope, "-o", "none"))) {
  try {
    Invoke-Az @("consumption", "budget", "create", "--budget-name", $budget, "--amount", "100",
      "--category", "Cost", "--time-grain", "Monthly",
      "--time-period", "start=2026-10-01", "end=2026-11-01", "--scope", $scope,
      "--notifications", '{"actual25":{"enabled":true,"operator":"GreaterThanOrEqual","threshold":25,"contactEmails":["nguyenndev037@gmail.com"]},"actual50":{"enabled":true,"operator":"GreaterThanOrEqual","threshold":50,"contactEmails":["nguyenndev037@gmail.com"]},"actual75":{"enabled":true,"operator":"GreaterThanOrEqual","threshold":75,"contactEmails":["nguyenndev037@gmail.com"]},"forecast100":{"enabled":true,"operator":"GreaterThanOrEqual","threshold":100,"contactEmails":["nguyenndev037@gmail.com"]}}')
  } catch {
    Write-Error "Budget creation failed. Create budget-vcuboidfit-demo manually in Azure Portal (Cost Management > Budgets), then rerun this script."
    exit 1
  }
}
if (-not (Test-AzResource @("consumption", "budget", "show", "--budget-name", $budget,
      "--scope", $scope, "-o", "none"))) {
  Write-Error "Budget $budget was not found; no chargeable resources will be created."
  exit 1
}

if (-not (Test-AzResource @("acr", "show", "-n", $acr, "-g", $rg, "-o", "none"))) {
  Invoke-Az @("acr", "create", "-n", $acr, "-g", $rg, "--sku", "Basic",
    "--admin-enabled", "false", "--tags", $tags, "-o", "none")
}
Invoke-Az @("acr", "build", "-r", $acr, "-t", "vcf:$Tag", "-f", "deploy/azure/Dockerfile", ".")

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

if (-not (Test-AzResource @("containerapp", "env", "show", "-n", "cae-vcuboidfit", "-g", $rg, "-o", "none"))) {
  Invoke-Az @("containerapp", "env", "create", "-n", "cae-vcuboidfit", "-g", $rg,
    "--location", $Location, "--logs-destination", "none", "--tags", $tags, "-o", "none")
}
Invoke-Az @("containerapp", "env", "storage", "set", "-n", "cae-vcuboidfit", "-g", $rg,
  "--storage-name", "vcfws", "--azure-file-account-name", $st,
  "--azure-file-account-key", $storageKey, "--azure-file-share-name", "workspace",
  "--access-mode", "ReadWrite", "-o", "none")

@{ resourceGroup = $rg; acr = $acr; storage = $st; tag = $Tag } |
  ConvertTo-Json | Set-Content -Encoding utf8 $namesPath
$acrServer = (& az acr show -n $acr -g $rg --query loginServer -o tsv).Trim()
$acrId = (& az acr show -n $acr -g $rg --query id -o tsv).Trim()
$envId = (& az containerapp env show -n "cae-vcuboidfit" -g $rg --query id -o tsv).Trim()
$image = "$acrServer/vcf:$Tag"

if (-not (Test-AzResource @("containerapp", "show", "-n", "ca-vcuboidfit", "-g", $rg, "-o", "none"))) {
  $demoSecure = Read-Host "Demo password" -AsSecureString
  $demoPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($demoSecure)
  try { $demoPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($demoPtr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($demoPtr) }
  $remoteToken = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
  Write-Output "Copy this remote-token once for the GPU agent: $remoteToken"
  $appYaml = Join-Path $env:TEMP ("vcf-app-" + [guid]::NewGuid().ToString() + ".yaml")
  $appYamlContent = @"
location: $Location
name: ca-vcuboidfit
type: Microsoft.App/containerApps
tags:
  project: vcuboidfit
  owner: nguyendev037
  expires: 2026-11-01
identity:
  type: SystemAssigned
properties:
  managedEnvironmentId: $envId
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: true
      targetPort: 3000
      transport: auto
    registries:
      - server: $acrServer
        identity: system
    secrets:
      - name: demo-password
        value: $demoPassword
      - name: remote-token
        value: $remoteToken
  template:
    containers:
      - name: vcuboidfit
        image: $image
        resources:
          cpu: 2.0
          memory: 4Gi
        env:
          - name: VCF_DEMO_PASSWORD
            secretRef: demo-password
          - name: VCF_REMOTE_TOKEN
            secretRef: remote-token
          - name: VCF_SESSIONS
            value: "1"
          - name: NEXT_PUBLIC_VCF_SESSIONS
            value: "1"
          - name: WORKSPACE
            value: /data/workspace
          - name: MAX_UPLOAD_GB
            value: "20"
        volumeMounts:
          - volumeName: vcfws
            mountPath: /data/workspace
    scale:
      minReplicas: 0
      maxReplicas: 1
    volumes:
      - name: vcfws
        storageType: AzureFile
        storageName: vcfws
"@
Set-Content -Value $appYamlContent -Encoding utf8 $appYaml
  try { Invoke-Az @("containerapp", "create", "--yaml", $appYaml, "-o", "none") }
  finally { Remove-Item -LiteralPath $appYaml -Force -ErrorAction SilentlyContinue }
  $appPrincipal = (& az containerapp show -n "ca-vcuboidfit" -g $rg --query identity.principalId -o tsv).Trim()
  Invoke-Az @("role", "assignment", "create", "--assignee-object-id", $appPrincipal,
    "--assignee-principal-type", "ServicePrincipal", "--role", "AcrPull", "--scope", $acrId, "-o", "none")
} else {
  Invoke-Az @("containerapp", "update", "-n", "ca-vcuboidfit", "-g", $rg, "--image", $image, "-o", "none")
}

if (-not (Test-AzResource @("containerapp", "job", "show", "-n", "job-vcf-sweep", "-g", $rg, "-o", "none"))) {
  $jobYaml = Join-Path $env:TEMP ("vcf-job-" + [guid]::NewGuid().ToString() + ".yaml")
  $jobYamlContent = @"
location: $Location
name: job-vcf-sweep
type: Microsoft.App/jobs
tags:
  project: vcuboidfit
  owner: nguyendev037
  expires: 2026-11-01
identity:
  type: SystemAssigned
properties:
  environmentId: $envId
  configuration:
    triggerType: Schedule
    scheduleTriggerConfig:
      cronExpression: "0 * * * *"
      replicaCompletionCount: 1
      parallelism: 1
    replicaRetryLimit: 0
    replicaTimeout: 600
  template:
    containers:
      - name: vcf-sweep
        image: $image
        resources:
          cpu: 0.5
          memory: 1Gi
        command:
          - python
          - -m
          - service.sweep
        env:
          - name: WORKSPACE
            value: /data/workspace
          - name: VCF_SESSIONS
            value: "1"
          - name: VCF_SESSION_TTL_H
            value: "24"
        volumeMounts:
          - volumeName: vcfws
            mountPath: /data/workspace
    volumes:
      - name: vcfws
        storageType: AzureFile
        storageName: vcfws
"@
Set-Content -Value $jobYamlContent -Encoding utf8 $jobYaml
  try { Invoke-Az @("containerapp", "job", "create", "--yaml", $jobYaml, "-o", "none") }
  finally { Remove-Item -LiteralPath $jobYaml -Force -ErrorAction SilentlyContinue }
  $jobPrincipal = (& az containerapp job show -n "job-vcf-sweep" -g $rg --query identity.principalId -o tsv).Trim()
  Invoke-Az @("role", "assignment", "create", "--assignee-object-id", $jobPrincipal,
    "--assignee-principal-type", "ServicePrincipal", "--role", "AcrPull", "--scope", $acrId, "-o", "none")
} else {
  Invoke-Az @("containerapp", "job", "update", "-n", "job-vcf-sweep", "-g", $rg, "--image", $image, "-o", "none")
}

$fqdn = (& az containerapp show -n "ca-vcuboidfit" -g $rg --query properties.configuration.ingress.fqdn -o tsv).Trim()
Write-Output "Container App FQDN: $fqdn"
