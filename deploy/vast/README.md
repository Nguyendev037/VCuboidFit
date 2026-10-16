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
vastai search offers "gpu_name in [RTX_3090,RTX_4090,RTX_A5000] num_gpus=1 cuda_vers>=11.8 disk_space>=40 reliability>0.98 inet_down>200" -o dph
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
H04 does not authorize adding `VCF_SERVER` in deploy.ps1: that configuration remains an
open deployment gate, along with the first real Azure/Vast A17 measurement.

`colab_agent.py --idle-exit-min N` exits successfully with `het viec - tu tat` after N
minutes without receiving a task. The environment default is `VCF_IDLE_MIN` (0 disables
idle exit); `onstart.sh` passes 15 by default. A running task resets the idle timer when
it ends. A normal idle exit triggers one DELETE request for this instance and does not
restart the agent. Other exit codes retain the existing restart loop.

Vast injects **`CONTAINER_ID`** and **`CONTAINER_API_KEY`** for instance-scoped control,
confirmed on 2026-10-16 in its [official Docker environment documentation](https://github.com/vast-ai/docs/blob/main/guides/instances/docker-environment.mdx).
Self-destruction uses these values, not the account key, with the
[destroy-instance REST endpoint](https://vast.ai/developers/api).
If either variable is absent, or destruction fails, the script prints a warning and
stops the loop. **The instance may still be billed: the operator must destroy it manually.**
The script never logs credentials.
