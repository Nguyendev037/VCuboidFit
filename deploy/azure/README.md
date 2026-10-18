# Azure Lite deploy runbook

One Azure Container App (Consumption, 2 vCPU / 4 GiB, min 0 / max 1 replica) running web + worker,
an SMB Azure Files share `workspace` mounted at `/data/workspace`, an hourly Container Apps Job
`job-vcf-sweep` that deletes expired sessions, and the CPU `azure-lite` worker profile.
Planning record: BuildLab `planning/20_2026-10-15_azure-deploy-lite/`. No credentials live in this repo.

## Current deployment (2026-10-16)

| Item | Value |
|---|---|
| Subscription | Azure for Students (policy allows only `japaneast`, `malaysiawest`, `indonesiacentral`, `uaenorth`, `indiasouthcentral`) |
| Region | `japaneast` for every resource (RG metadata also `japaneast`) |
| Resource group | `rg-vcuboidfit-demo`, tags `project=vcuboidfit owner=nguyendev037 expires=2026-11-01` |
| Budget | `budget-vcuboidfit-demo`, subscription scope, 100 USD/month, alerts Actual 25/50/75 + Forecast 100 |
| Pull identity | user-assigned `id-vcuboidfit` with `AcrPull` (shared by app and job) |
| Names | `deploy/azure/.names.json` (git-ignored): ACR `acrvcf…`, storage `stvcf…` |
| Environment | `cae-vcuboidfit`, `environmentMode: WorkloadProfiles` (Consumption profile), storage `vcfws` |
| App | `ca-vcuboidfit`, ingress external :3000, min 0 / max 1, FQDN `ca-vcuboidfit.graymeadow-7a5b88aa.japaneast.azurecontainerapps.io` |
| Image | `vcf:8f0c52c` (revision `ca-vcuboidfit--0000020`, 2026-10-18; overlay on `vcf:c74a859`, see pitfalls) |
| Access | **Public, no demo password** (owner decision 2026-10-17, BuildLab plan 20 D29). `VCF_DEMO_PASSWORD` is not set, so `web/proxy.ts` skips Basic Auth; per-visitor sessions (`vcf_sid`) stay on |
| Job | `job-vcf-sweep`, cron `0 * * * *`, 0.5 vCPU / 1 GiB |

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
4. Storage account + share `workspace` (100 GiB); environment `cae-vcuboidfit` created by ARM PUT
   (api `2026-07-01`) with `environmentMode: WorkloadProfiles` — the script refuses to continue on an
   `Express` environment — then storage `vcfws`.
5. First run only: prompts **Demo password** (hidden; the live app runs without one, see *Access*) and prints the **remote-token once** — copy it
   somewhere outside the repo. Creates `ca-vcuboidfit` and `job-vcf-sweep` by ARM PUT (body in a temp
   file, deleted). Later runs: `containerapp update --image` for app and job.
6. Prints the FQDN.

Flags: `-Tag <sha>` (default HEAD), `-AcrLocation <region>`, `-SkipBuild` (image `vcf:<Tag>` already
pushed), `-DeferDemoPassword` (unattended first create: the app is locked with a random password nobody
sees and the remote-token is written to `%USERPROFILE%\.vcuboidfit\remote-token.txt`, outside the repo).

The live app is public on purpose. The password gate is optional: to turn it back on (or rotate it), run
(hidden prompt, restarts the revision):

```powershell
powershell -ExecutionPolicy Bypass -File deploy\azure\set-demo-password.ps1
```

Avoid spaces and `" & | < > ^ % !` in the password (`az.cmd` passes it through cmd.exe).

Public access has a cost path: opening `/dashboard` asks the server to rent a vast.ai GPU. What bounds it is
`VCF_VAST_MAX_DPH` (price cap), at most one machine, the agent deleting the machine after 15 idle minutes,
and the 100 USD budget alerts.

Commit before deploying so the image tag matches the code.

## Checks after deploy

```powershell
$fqdn = az containerapp show -n ca-vcuboidfit -g rg-vcuboidfit-demo --query properties.configuration.ingress.fqdn -o tsv
curl.exe -s -o NUL -w "%{http_code}`n" https://$fqdn/          # 200 (public; 401 only if a demo password is set)
curl.exe -s https://$fqdn/api/health                            # ok:true, sets vcf_sid
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

## Known pitfalls (hit on 2026-10-15/16)

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
| `ExpressEnvironmentResourceNotSupported` on `env storage set` | `az containerapp env create` (CLI 2.91, no mode flag) produced an **Express** environment: no Azure Files, no jobs. Visible only with api `>= 2026-07-01` (older APIs return `environmentMode: null`) | ARM PUT with `environmentMode: WorkloadProfiles`; `Standard` is rejected (valid: `WorkloadProfiles`, `ConsumptionOnly`, `Reserved`, `Express`) |
| `Object of type date is not JSON serializable` | bare YAML `expires: 2026-11-01` parsed as a date | moot: app/job created by ARM PUT with JSON |
| 400 `could not be converted to System.Boolean. Path: $` on `containerapp create --yaml` | CLI (api 2025-07-01) sends an envelope full of nulls | ARM PUT, api `2026-07-01`, minimal body |
| Revision stuck `Activating`, console `set: pipefail\r: invalid option` | `start.sh` checked out with CRLF before the `*.sh eol=lf` rule | Dockerfile strips `\r` from `start.sh` |
| `AADSTS530035 … blocked by security defaults` | cached token expired; tenant requires interactive MFA | `az login --tenant <tenant-id>` (browser) |
| Push of `vcf:<sha>` crawls for an hour after a version bump | `COPY model/worker/pyproject.toml` precedes `pip install`, so changing only `version` rebuilds the ~580 MB dependency layer and re-pushes it (130 KB/s uplink on 2026-10-18) | if dependencies are unchanged, build a one-off overlay `FROM <acr>/vcf:<previous sha>` that re-copies `model/worker/{pyproject.toml,c4,service,configs}` + web standalone, push, then `deploy.ps1 -SkipBuild -Tag <sha>` (done for `8f0c52c`, ~60 MB pushed) |

## API, sessions and the GPU agent: incidents on 2026-10-17

With `VCF_SESSIONS=1` every worker call must carry the caller's session. The browser holds the
cookie `vcf_sid` (32 hex chars, set by `web/proxy.ts`); **every Next server route that calls the
worker must copy it into the `x-vcf-session` header**. Without it the worker answers
`404 not_found` ("Không tìm thấy tài nguyên") even though the resource exists. Routes that call
the worker: `app/api/[...path]` (catch-all proxy), `app/api/media/[jobId]/[...path]` (ownership
check), `app/api/uploads/[id]/finalize` (`POST /datasets`). Local mode has sessions off, so a
missing header only fails on Azure. Add a test for the header with every new server route.

| Symptom | Cause | Fix |
|---|---|---|
| Upload reaches "100% đã tải" and nothing happens; worker log `POST /datasets 404` | `finalize` route called the worker without `x-vcf-session` | `f97bcf8` forwards the cookie; test in `web/app/api/uploads/uploads.test.ts` |
| Vast machine running, `/api/health` → `remoteAgent.lastSeen: null`, `gpu/status` stays `starting` | `deploy/vast/onstart.sh` cached the code by ref **name** (`main`), so the machine kept its first copy; its `colab_setup.sh` step 4/5 still resolved `worker[service,dev]` and died with pip `ResolutionTooDeep`, so the agent never started | `86f78f3` compares the commit SHA; see [deploy/vast/README.md](../vast/README.md#agent-never-connects) |
| `deploy_run21` failed in `docker build`: pip `Read timed out` | PyPI network timeout (transient) | rerun `deploy.ps1` (run22 passed) |
| `docker build` cannot reach `dockerDesktopLinuxEngine` | Docker Desktop not running | start Docker Desktop, wait for `docker info` |
| Every LiDAR job fails at step 1 "Chỉ mục LiDAR" (`failed · lidar_index · 0/1`), console log shows nothing | image sets `C4_PROFILE=azure-lite` but the stage CLI hard-coded `--profile` choices `[local-4060, cloud]`; argparse exits 2 | `c74a859` takes choices from `configs/profiles/*.yaml`. Stage errors live only in `jobs/<id>/logs/<stage>.log` on the share: `az storage file download-batch -s workspace --pattern "jobs/<id>/*"` |

Diagnose an API 404 or a stuck step in this order (read-only):

```powershell
az containerapp logs show -n ca-vcuboidfit -g rg-vcuboidfit-demo --type console --tail 120   # worker access log: method, path, status
curl.exe -s https://$fqdn/api/health                                                          # remoteAgent.lastSeen = GPU agent heartbeat
$key = az storage account keys list -g rg-vcuboidfit-demo -n <stvcf…> --query "[0].value" -o tsv
az storage file list --account-name <stvcf…> --account-key $key -s workspace -p uploads -o table   # uploads/<id>/session.json = owner
```

Reproduce with one session: `GET /dashboard` (cookie jar) → `POST /api/uploads` → `POST /api/uploads/<id>/finalize`.
An empty upload must answer `409 no_files`, never `404`.

## Teardown

`powershell -ExecutionPolicy Bypass -File deploy\azure\teardown.ps1` on 2026-11-01, or earlier if
Actual cost reaches 75 USD. Deleting the RG deletes the share and every session's data. The budget is
subscription-scoped and survives; delete it in Cost Management if no longer wanted. Afterwards prune
the local image: `docker image rm <acr>.azurecr.io/vcf:<tag>`; `docker builder prune` (Docker data on D:).
