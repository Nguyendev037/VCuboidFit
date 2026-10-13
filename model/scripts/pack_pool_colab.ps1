[CmdletBinding()]
param(
    [string]$DataRoot = 'E:/nuscenes_trainval',
    [string]$OutDir = 'F:/vcf_pack/pool_v24',
    [string]$Python = '',
    [long]$PartBytes = 2000000000
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
if (-not $Python) { $Python = Join-Path $repo 'model/worker/.venv/Scripts/python.exe' }
if ($PartBytes -gt 2000000000 -or $PartBytes -lt 1000000) { throw 'PartBytes must be between 1 MB and 2 GB' }
$resolvedOut = [IO.Path]::GetFullPath($OutDir)
$resolvedSource = (Resolve-Path -LiteralPath $DataRoot).Path
if ($resolvedOut.StartsWith($repo, [StringComparison]::OrdinalIgnoreCase) -or $resolvedOut.StartsWith($resolvedSource, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must be outside repo and source' }
New-Item -ItemType Directory -Force -Path $resolvedOut | Out-Null
$sha = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read HEAD' }
$codeZip = Join-Path $resolvedOut ('code_' + $sha.Substring(0,7) + '.zip')
if (Test-Path -LiteralPath $codeZip) { throw "Output already exists: $codeZip; use a new output directory" }
& git -C $repo archive --format=zip -o $codeZip HEAD
if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
$env:PYTHONIOENCODING = 'utf-8'
$packer = @'
import hashlib, json, sys, time, zipfile
from pathlib import Path
import pandas as pd
root, out, repo = map(Path, sys.argv[1:4])
limit, sha = int(sys.argv[4]), sys.argv[5]
start = time.perf_counter()
job = repo / 'model/workspace/jobs/pool_v24'
lid = pd.read_parquet(job/'lidar/index.parquet')
frames = pd.read_parquet(job/'index/frames.parquet')
keys = set(lid['sample_token'])
frames = frames[frames['sample_token'].isin(keys)]
assert len(lid) == len(keys) == 6753
assert len(frames) == 6*len(keys)
assert frames.groupby('sample_token')['cam'].nunique().eq(6).all()
paths = set(lid['lidar_path']) | set(frames['img_path'])
assert all(p.startswith('samples/LIDAR_TOP/') or p.startswith('samples/CAM_') for p in paths)
paths |= {p.relative_to(root).as_posix() for d in ['v1.0-trainval', 'maps'] for p in (root/d).rglob('*') if p.is_file()}
assert (root/'v1.0-trainval/scene.json').is_file() and (root/'maps').is_dir()
files = []
for rel in sorted(paths, key=lambda p: (0 if p.startswith('v1.0-trainval/') else 1, p)):
    p = root/rel
    assert p.resolve().is_relative_to(root.resolve()) and p.is_file(), rel
    files.append((rel, p.stat().st_size))
assert not any('sweeps/' in rel for rel, _ in files)
parts, archive, count, raw = [], None, 0, 0
part_path = None
def finish():
    global archive, count, raw
    if archive is None: return
    archive.close()
    size = part_path.stat().st_size
    assert size <= limit, (part_path, size)
    with part_path.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
    with zipfile.ZipFile(part_path) as z:
        assert len(z.infolist()) == count
        assert z.testzip() is None
    item = dict(name=part_path.name, size_bytes=size, sha256=digest, file_count=count, source_bytes=raw)
    parts.append(item)
    print(json.dumps(item), flush=True)
    archive, count, raw = None, 0, 0
for rel, size in files:
    name = 'data/'+rel
    overhead = 256 + 2*len(name.encode('utf-8'))
    if archive is not None and archive.fp.tell() + size + overhead + count*512 + 4096 > limit:
        finish()
    if archive is None:
        part_path = out/f'vcf_part_{len(parts)+1:03d}.zip'
        archive = zipfile.ZipFile(part_path, 'x', compression=zipfile.ZIP_STORED, allowZip64=True)
        count, raw = 0, 0
    assert size+overhead+4096 < limit, rel
    archive.write(root/rel, name)
    count += 1
    raw += size
finish()
spec = repo.parents[1]/'planning/11_2026-10-13_clip-context-fleet/specs/SPEC-P04-BENCHMARK-PITCH.md'
prereg = spec.read_text(encoding='utf-8').split('```prereg\n',1)[1].split('```',1)[0]
ph = hashlib.sha256(prereg.encode()).hexdigest()
assert ph == '590a7a6a17fd55b63f778dbd79c4b01ed6f33add705d84225d7db7b890a0a75d', ph
code = out/f'code_{sha[:7]}.zip'
with zipfile.ZipFile(code) as z:
    assert z.testzip() is None
    assert z.comment.decode().strip() == sha
with code.open('rb') as f: code_digest = hashlib.file_digest(f,'sha256').hexdigest()
manifest = dict(format='vcf-pool-colab-v1', archive_mode='independent_zip_parts', repo_sha=sha,
                code=dict(name=code.name,size_bytes=code.stat().st_size,sha256=code_digest),
                version='v1.0-trainval', model_mode='cluster_only', keyframes=len(keys), camera_files=len(frames),
                file_count=len(files), source_bytes=sum(s for _,s in files), parts=parts,
                prereg=prereg, prereg_sha256=ph)
with (out/'manifest.json').open('x', encoding='utf-8') as f: json.dump(manifest,f,indent=2)
print(json.dumps(dict(output=str(out),repo_sha=sha,file_count=len(files),source_bytes=manifest['source_bytes'],
                     zip_bytes=sum(p['size_bytes'] for p in parts),parts=len(parts),elapsed_s=round(time.perf_counter()-start,3),
                     code=manifest['code'],prereg_sha256=ph,crc_verified=True,sweeps=0)),flush=True)
'@
$packer | & $Python - $resolvedSource $resolvedOut $repo $PartBytes $sha
if ($LASTEXITCODE -ne 0) { throw "Packing failed: exit $LASTEXITCODE" }
