# Azure Lite deploy runbook

One Azure Container App (Consumption, 2 vCPU / 4 GiB, min 0 / max 1 replica) running web + worker,
an SMB Azure Files share `workspace` mounted at `/data/workspace`, an hourly Container Apps Job
`job-vcf-sweep` that deletes expired sessions, and the CPU `azure-lite` worker profile.
Planning record: BuildLab `planning/20_2026-10-15_azure-deploy-lite/`. No credentials live in this repo.

## Current deployment (2026-10-15)

| Item | Value |
|---|---|
| Subscription | Azure for Students (policy allows only `japaneast`, `malaysiawest`, `indonesiacentral`, `uaenorth`, `indiasouthcentral`) |
| Region | `japaneast` for every resource (RG metadata also `japaneast`) |
| Resource group | `rg-vcuboidfit-demo`, tags `project=vcuboidfit owner=nguyendev037 expires=2026-11-01` |
| Budget | `budget-vcuboidfit-demo`, subscription scope, 100 USD/month, alerts Actual 25/50/75 + Forecast 100 |
| Pull identity | user-assigned `id-vcuboidfit` with `AcrPull` (shared by app and job) |
| Names | `deploy/azure/.names.json` (git-ignored): ACR `acrvcf…`, storage `stvcf…` |

## Prerequisites (operator machine)

1. **Azure CLI** in a venv on a data drive, e.g. `F:\tools\azure-cli` (`az` 2.91). If IPv6 on the
   machine is broken (browser works, `curl -6` times out), `az login` hangs silently: the venv ships a
   `Lib\site-packages\sitecustomize.py` that forces IPv4 — keep it.
2. `az login --use-device-code` (Azure for Students account).
3. **Docker Desktop running.** Azure for Students rejects ACR Tasks (`TasksOperationsNotAllowed`),
   so `az acr build` cannot be used; the image is built locally and pushed.
4. Budget exists before any billable resource (the script refuses to continue otherwise).

## Deploy / update

Run from the repo root in **Windows PowerShell**:

```powershell
$env:PATH = "F:\tools\azure-cli\Scripts;$env:PATH"
powershell -ExecutionPolicy Bypass -File deploy\azure\deploy.ps1 -Location japaneast
```

What the script does (idempotent; reruns reuse `.names.json`):

1. Reuse/create RG; verify the budget.
2. ACR Basic (admin disabled) in `-AcrLocation` (default `japaneast`); identity + `AcrPull`.
3. Stage a minimal build context (~6 MB: `web` without `node_modules/.next/mock-media/.env*.local`,
   `model/worker/{pyproject.toml,c4,service,configs}`, `deploy/azure`) on `E:\` (else `%TEMP%`),
   `docker build`, `az acr login`, `docker push <acr>.azurecr.io/vcf:<git short sha>`, delete the stage.
4. Storage account + share `workspace` (100 GiB); environment `cae-vcuboidfit` with storage `vcfws`.
5. First run only: prompts **Demo password** (hidden) and prints the **remote-token once** — copy it
   somewhere outside the repo. Creates `ca-vcuboidfit` and `job-vcf-sweep` from temporary YAML.
   Later runs: `containerapp update --image` for app and job.
6. Prints the FQDN.

Flags: `-Tag <sha>` (default HEAD), `-AcrLocation <region>`, `-SkipBuild` (image `vcf:<Tag>` already
pushed — e.g. the build ran unattended and only the password step is left).

Commit before deploying so the image tag matches the code.

## Checks after deploy

```powershell
$fqdn = az containerapp show -n ca-vcuboidfit -g rg-vcuboidfit-demo --query properties.configuration.ingress.fqdn -o tsv
curl.exe -s -o NUL -w "%{http_code}`n" https://$fqdn/          # 401 without password
curl.exe -s -u demo:<password> https://$fqdn/api/health          # ok:true, sets vcf_sid
az containerapp revision list -n ca-vcuboidfit -g rg-vcuboidfit-demo -o table
az containerapp logs show -n ca-vcuboidfit -g rg-vcuboidfit-demo --tail 100
```

## Demo hours

```powershell
az containerapp update -n ca-vcuboidfit -g rg-vcuboidfit-demo --min-replicas 1   # 15 min before
az containerapp update -n ca-vcuboidfit -g rg-vcuboidfit-demo --min-replicas 0   # after
```

## GPU agent (operator-run, outside the Azure work package)

```powershell
docker run --rm --gpus all -e VCF_REMOTE_TOKEN=<token> -v E:\vcf_agent:/work `
  -v ${PWD}\model:/repo/model vcuboidfit_pointpillars:0.1 `
  python /repo/model/scripts/colab_agent.py --server https://<fqdn>/api --work /work --purge
```

`E:\vcf_agent` is temporary. Never commit the token.

## Known pitfalls (all hit on 2026-10-15)

| Symptom | Cause | Fix in script |
|---|---|---|
| Script stops on `WARNING: Command group 'consumption' is in preview` | PS 5.1 + `$ErrorActionPreference='Stop'` turns redirected stderr into a fatal error | `AZURE_CORE_ONLY_SHOW_ERRORS=true`; az judged by exit code |
| `-o was unexpected at this time` | `az.bat` runs through cmd.exe, which mis-parses `--query "length(@)"` | no parentheses in `--query` |
| A second ACR appears after a failed run | random names were saved only at the end | `.names.json` written as soon as names are minted |
| `az acr build` silent for minutes | it walks/filters the whole repo (~21 GB of `model/workspace` + `.venv`) | staged ~6 MB context |
| `NoRegisteredProviderFound … registries/runs` | ACR Tasks not offered in `malaysiawest` | moot now: local docker build |
| `TasksOperationsNotAllowed` | ACR Tasks blocked on Azure for Students | local `docker build` + `docker push` |
| `next build` downloads SWC and fails `ENOTFOUND` | flaky IPv6 made `npm ci` silently drop optional Linux binaries | `NODE_OPTIONS=--dns-result-order=ipv4first`, `--fetch-retries=5`, fail fast if a Linux native is missing |
| `Environments: .env.local` in build log | local config copied into the image | excluded in stage, `.dockerignore`, and `rm` in Dockerfile |
| `InvalidResourceGroupLocation` | `az group create` with another region on an existing RG | create RG only if missing |
| First revision cannot pull (401) | system identity exists only after create | user-assigned identity granted `AcrPull` before create |

## Teardown

`powershell -ExecutionPolicy Bypass -File deploy\azure\teardown.ps1` on 2026-11-01, or earlier if
Actual cost reaches 75 USD. Deleting the RG deletes the share and every session's data. The budget is
subscription-scoped and survives; delete it in Cost Management if no longer wanted. Afterwards prune
the local image: `docker image rm <acr>.azurecr.io/vcf:<tag>`; `docker builder prune` (Docker data on D:).
