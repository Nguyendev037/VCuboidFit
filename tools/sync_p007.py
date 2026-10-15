"""Push VCuboidFit to its own remote, then replay new commits into P-007/source-tool/ and push that too.

P-007 (team repo) holds this whole repository under ``source-tool/`` with the full history
(rewritten paths, so SHAs differ). The last synced commit is found by matching the newest
non-merge commit touching ``source-tool/`` in P-007 with a commit here (author, author date,
subject). New commits are replayed one by one with ``git format-patch | git am --directory``,
keeping author, date and message.

    python tools/sync_p007.py              # push both
    python tools/sync_p007.py --dry-run    # list what would be replayed, change nothing
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
DEFAULT_DST = Path("F:/BuildPhase/P-007")
PREFIX = "source-tool"
BRANCH = "main"
SEP = "\x1f"


def git(repo: Path, *args: str, input: bytes | None = None) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], input=input, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} (in {repo}) failed with exit {proc.returncode}:\n"
                         f"{proc.stderr.decode(errors='replace')}")
    return proc.stdout.decode(errors="replace").strip()


def require_clean_main(repo: Path) -> None:
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
        raise SystemExit(f"{repo}: not on {BRANCH}")
    if git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit(f"{repo}: tracked changes not committed")


def find_last_synced(dst: Path) -> str:
    fmt = SEP.join(["%an", "%aI", "%s"])
    key = git(dst, "log", "-1", "--no-merges", f"--format={fmt}", BRANCH, "--", PREFIX)
    for line in git(SRC, "log", f"--format=%H{SEP}{fmt}", BRANCH).splitlines():
        sha, rest = line.split(SEP, 1)
        if rest == key:
            return sha
    raise SystemExit(f"P-007 last {PREFIX}/ commit has no match here ({key!r}); "
                     f"someone edited {PREFIX}/ directly in P-007 - resolve by hand")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dst", type=Path, default=DEFAULT_DST)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dst: Path = args.dst

    require_clean_main(SRC)
    require_clean_main(dst)
    git(dst, "pull", "--ff-only", "-q", "origin", BRANCH)

    base = find_last_synced(dst)
    commits = git(SRC, "rev-list", "--reverse", f"{base}..{BRANCH}").splitlines()
    if git(SRC, "rev-list", "--merges", f"{base}..{BRANCH}"):
        raise SystemExit(f"merge commits in {base[:7]}..{BRANCH}; replay by hand")
    print(f"last synced {base[:7]}; {len(commits)} new commit(s)")
    for sha in commits:
        print("  " + git(SRC, "log", "-1", "--format=%h %s", sha))
    if args.dry_run:
        return 0

    git(SRC, "push", "origin", BRANCH)
    if commits:
        lfs_src, lfs_dst = SRC / ".git/lfs/objects", dst / ".git/lfs/objects"
        if lfs_src.is_dir():
            shutil.copytree(lfs_src, lfs_dst, dirs_exist_ok=True,
                            copy_function=lambda s, d: Path(d).exists() or shutil.copy2(s, d))
        patches = subprocess.run(
            ["git", "-C", str(SRC), "format-patch", "--stdout", "--binary", "-k", f"{base}..{BRANCH}"],
            capture_output=True, check=True).stdout
        try:
            git(dst, "am", "-k", "--3way", f"--directory={PREFIX}", input=patches)
        except SystemExit:
            git(dst, "am", "--abort")
            raise
        git(dst, "push", "origin", BRANCH)
    print(f"pushed: VCuboidFit {git(SRC, 'rev-parse', '--short', BRANCH)}, "
          f"P-007 {git(dst, 'rev-parse', '--short', BRANCH)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
