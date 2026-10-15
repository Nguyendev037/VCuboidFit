# Azure Lite deploy runbook

This profile uses one Azure Container App (Consumption, max one replica), an SMB Azure Files `workspace` share, and the CPU `azure-lite` worker profile. Budget creation and the final Container Apps commands are intentionally operator-gated; this repository does not contain credentials or tokens.

## Prerequisites

1. Create the 100 USD budget and alerts before any billable resource.
2. Confirm an allowed region, then run `pwsh deploy/azure/deploy.ps1 -Location <region>`.
3. Complete the Container Apps environment/app/job configuration from SPEC-P03 using the generated `.names.json`.

## GPU agent (operator-run, outside this work package)

```powershell
docker run --rm --gpus all -e VCF_REMOTE_TOKEN=<token> -v E:\vcf_agent:/work `
  -v ${PWD}\model:/repo/model vcuboidfit_pointpillars:0.1 `
  python /repo/model/scripts/colab_agent.py --server https://<fqdn>/api --work /work --purge
```

`E:\vcf_agent` is temporary. Do not commit the token or upload credentials. The GPU model agent is WP5 and is not implemented in this commit.

## Teardown

Run `pwsh deploy/azure/teardown.ps1` on 2026-11-01 or earlier if the budget threshold is reached. Verify deletion in Portal after the command has settled.
