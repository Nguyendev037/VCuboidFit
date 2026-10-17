# GPU agent on Vast.ai

The web on Azure only queues Tier 1 jobs (`/api/remote/*`). A rented Vast.ai GPU runs
[`onstart.sh`](onstart.sh): it builds the Tier 1 environment with `model/scripts/colab_setup.sh`
(same as Colab), then loops `model/scripts/colab_agent.py`, which pulls a job, runs PointPillars
(default seed weights from Git LFS, no training) and posts `signals.parquet` back.

## Needs

- Vast.ai account with credit, API key from <https://cloud.vast.ai/manage-keys/>.
- `pip install vastai` then `vastai set api-key <key>` (stored in `~/.config/vastai`, never in the repo).
- Remote token of the Azure app (never commit it):

```powershell
$env:PATH = "F:\tools\azure-cli\Scripts;$env:PATH"
$token = az containerapp secret show -n ca-vcuboidfit -g rg-vcuboidfit-demo --secret-name remote-token --query value -o tsv
```

## Launch

```powershell
vastai search offers "gpu_name in [RTX_3060,RTX_3090,RTX_4090,RTX_A5000] num_gpus=1 cuda_vers>=11.8 disk_space>=40 reliability>0.98 inet_down>200" -o dph
vastai create instance <offer_id> --image pytorch/pytorch:2.1.2-cuda11.8-cudnn8-devel --disk 40 --ssh --direct `
  --env "-e VCF_SERVER=https://<fqdn>/api -e VCF_REMOTE_TOKEN=$token" --onstart deploy/vast/onstart.sh
```

First boot installs and builds OpenPCDet (~10–15 min). Then on the web: run Tier 1 remotely.

## Watch and stop

```powershell
vastai show instances
vastai logs <instance_id> --tail 50      # or ssh in: tail -f /root/vcf/agent.log
vastai destroy instance <instance_id>   # billing stops only on destroy (stop still bills disk)
```

Log lines: `khong co viec` = idle · `nhan viec` = started · `da gui ket qua` = done.

## Dashboard autostart (H04 / SPEC-P05)

The online dashboard sends one warm request on mount; its 4-second overlay only sends the
request. First GPU boot is estimated at 10–15 minutes and has not been measured live.
Tier 0 remains usable while the GPU starts. Local mode does not request a machine.

The worker requires `VAST_API_KEY`, `VCF_GPU_AUTOSTART=1`, `VCF_SERVER` (the public web
URL ending in `/api`), and `VCF_REMOTE_TOKEN`. `VCF_VAST_MAX_DPH` defaults to `0.6`;
`VCF_VAST_REF` defaults to `main`. It uses label `vcuboidfit-agent`, a 40 GB disk and
the PyTorch 2.1.2 / CUDA 11.8 image. Keep `VAST_API_KEY` only in the Container App
secret `vast-api-key`; never expose it with a `NEXT_PUBLIC_` variable.

An operator can run `deploy/azure/set-vast-key.ps1` to enter the key without writing it
to a file. A later `deploy.ps1 -SkipBuild` references that secret and sets autostart and
the price ceiling only when the secret exists. `VCF_GPU_AUTOSTART=0` disables autostart.
`deploy.ps1` sets `VCF_SERVER=https://<app-fqdn>/api` in an env update after the app
FQDN is available, including on first creation (D29). Without `VCF_SERVER`, warm and
status return `disabled` / `no-server-url` without constructing a network client.
The first real Azure/Vast A17 measurement remains pending.

Create PUT requests are never retried. If a timeout or 5xx leaves the result unknown,
the worker persists the attempt and reports `starting` for up to 20 minutes. Listing
an instance with label `vcuboidfit-agent` resumes normal startup tracking. If none
appears after 20 minutes, it reports `error` / `create-unknown` and continues blocking
new rentals, even after restart. Check Vast instances manually before reconciling the
attempt; do not retry a rental or clear `warm.json` while its outcome is unknown.

`colab_agent.py --idle-exit-min N` exits successfully with `het viec - tu tat` after N
minutes without receiving a task. The environment default is `VCF_IDLE_MIN` (0 disables
idle exit); `onstart.sh` passes 15 by default. A running task resets the idle timer when
it ends. A normal idle exit sends one PUT `{"state": "stopped"}` for this instance (stop,
not destroy: disk billing continues, the installed environment is kept) and does not
restart the agent. On the next dashboard visit the worker resumes a stopped
`vcuboidfit-agent` instance (PUT `{"state": "running"}`, re-sent at most every 10
minutes) instead of renting a new one; it rents only when no labelled instance exists,
only on verified hosts, and only when the owner opts in with `VCF_VAST_ALLOW_RENT=1`
(default off: renting a new machine needs the owner's approval; otherwise warm reports
`idle` / `rent-needs-approval`). Other exit codes retain the existing restart loop.

Vast injects **`CONTAINER_ID`** and **`CONTAINER_API_KEY`** for instance-scoped control,
confirmed on 2026-10-16 in its [official Docker environment documentation](https://github.com/vast-ai/docs/blob/main/guides/instances/docker-environment.mdx).
Self-stop uses these values, not the account key, with the
[manage-instance REST endpoint](https://vast.ai/developers/api).
If either variable is absent, or the stop fails, the script prints a warning and
stops the loop. **The instance may still be billed for GPU time: stop it manually.**
The script never logs credentials.
