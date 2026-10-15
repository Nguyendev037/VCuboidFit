$ErrorActionPreference = "Stop"
$name = Read-Host "Type rg-vcuboidfit-demo to confirm deletion"
if ($name -cne "rg-vcuboidfit-demo") { throw "Confirmation did not match." }
az group delete -n rg-vcuboidfit-demo --yes --no-wait
if ($LASTEXITCODE) { throw "az group delete failed" }
Write-Output "Deletion submitted. Verify the resource group after at least 60 seconds."
