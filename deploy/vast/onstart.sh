#!/usr/bin/env bash
# Vast.ai on-start: cai moi truong Tang 1 (colab_setup.sh) roi chay GPU agent keo viec tu web.
# Can bien moi truong cua instance: VCF_SERVER (https://<fqdn>/api), VCF_REMOTE_TOKEN.
# Tuy chon: VCF_REF (nhanh/commit, mac dinh main). Log: /root/vcf/agent.log
set -euo pipefail
: "${VCF_SERVER:?dat VCF_SERVER=https://<fqdn>/api}"
: "${VCF_REMOTE_TOKEN:?dat VCF_REMOTE_TOKEN}"
REF=${VCF_VAST_REF:-${VCF_REF:-main}}
export VCF_HOME=/root/vcf
REPO=$VCF_HOME/VCuboidFit
mkdir -p "$VCF_HOME"
exec > >(tee -a "$VCF_HOME/agent.log") 2>&1

# Lay ma nguon qua HTTPS tarball (image khong chac co git); khong keo LFS.
# So COMMIT, khong so ten nhanh: REF=main khong doi ten nen ban cu tung bi giu mai, ban sua
# (vd d26bd2f, pip --no-deps) khong bao gio toi may da cai (do 2026-10-17). API loi => tai lai.
SHA=$(python3 - "$REF" <<'PYEOF' || true
import sys, urllib.request
req = urllib.request.Request("https://api.github.com/repos/Nguyendev037/VCuboidFit/commits/" + sys.argv[1],
                             headers={"Accept": "application/vnd.github.sha"})
print(urllib.request.urlopen(req, timeout=30).read().decode().strip())
PYEOF
)
echo "ma nguon: ref=$REF commit=${SHA:-khong-ro} (tren may: $(cat "$REPO/.sha" 2>/dev/null || echo chua-co))"
if [ -z "$SHA" ] || [ ! -f "$REPO/.sha" ] || [ "$(cat "$REPO/.sha")" != "$SHA" ]; then
  rm -rf "$REPO" && mkdir -p "$REPO"
  python3 - "${SHA:-$REF}" "$REPO" <<'PYEOF'
import io, sys, tarfile, urllib.request
ref, dst = sys.argv[1], sys.argv[2]
data = urllib.request.urlopen(f"https://codeload.github.com/Nguyendev037/VCuboidFit/tar.gz/{ref}").read()
with tarfile.open(fileobj=io.BytesIO(data)) as t:
    for m in t.getmembers():
        parts = m.name.split("/", 1)
        if len(parts) == 2 and parts[1].startswith("model/") and not parts[1].startswith("model/workspace/"):
            m.name = parts[1]
            t.extract(m, dst)
PYEOF
  echo "$REF" > "$REPO/.ref"
  if [ -n "$SHA" ]; then echo "$SHA" > "$REPO/.sha"; fi
fi

bash "$REPO/model/scripts/colab_setup.sh"
export PCDET_ROOT=$VCF_HOME/OpenPCDet
export PYTHONPATH=$REPO/model/worker:$PCDET_ROOT

# Agent tu retry mang; neu thoat vi loi khac thi khoi dong lai sau 30 s.
while true; do
  code=0
  python3 -u "$REPO/model/scripts/colab_agent.py" --server "$VCF_SERVER" --work "$VCF_HOME/work" --idle-exit-min "${VCF_IDLE_MIN:-15}" || code=$?
  if [ "$code" -eq 0 ]; then
    # Official credentials: https://github.com/vast-ai/docs/blob/main/guides/instances/docker-environment.mdx
    # Verified 2026-10-16. Never use the account-wide VAST_API_KEY here.
    if [ -z "${CONTAINER_ID:-}" ] || [ -z "${CONTAINER_API_KEY:-}" ]; then
      echo "WARNING: missing CONTAINER_ID/CONTAINER_API_KEY; idle agent will not restart; stop manually"
      break
    fi
    # Stop, not destroy: the web resumes this machine next time (environment kept).
    python3 - <<'PYEOF'
import json, os, urllib.request
request = urllib.request.Request(
    "https://console.vast.ai/api/v0/instances/" + str(int(os.environ["CONTAINER_ID"])) + "/",
    data=json.dumps({"state": "stopped"}).encode(), method="PUT",
    headers={"Authorization": "Bearer " + os.environ["CONTAINER_API_KEY"],
             "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print("idle instance stop requested")
except Exception:
    print("WARNING: instance stop failed; stop manually")
PYEOF
    break
  fi
  echo "agent thoat $(date -u) - khoi dong lai sau 30 s"
  sleep 30
done
