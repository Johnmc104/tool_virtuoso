"""vbridge cleanup — kill stale Cadence processes and remove OA lock files."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_cleanup(*, search_dir: str | None = None, dry_run: bool = False) -> int:
    user = os.getenv("USER", "")
    actions = 0

    procs = _find_stale_processes(user)
    if procs:
        print(f"[cleanup] Found {len(procs)} stale Cadence process(es):")
        for pid, cmd in procs:
            print(f"  PID {pid}: {cmd}")
        if not dry_run:
            for pid, cmd in procs:
                try:
                    os.kill(pid, 15)
                    print(f"  Killed {pid}")
                    actions += 1
                except OSError as e:
                    print(f"  Failed to kill {pid}: {e}", file=sys.stderr)
    else:
        print("[cleanup] No stale Cadence processes found.")

    locks = _find_lock_files(search_dir)
    if locks:
        print(f"\n[cleanup] Found {len(locks)} OA lock file(s):")
        for lf in locks:
            print(f"  {lf}")
        if not dry_run:
            for lf in locks:
                try:
                    lf.unlink()
                    actions += 1
                except OSError as e:
                    print(f"  Failed to remove {lf}: {e}", file=sys.stderr)
    else:
        print("[cleanup] No OA lock files found.")

    if dry_run:
        print(f"\n[cleanup] Dry run — no action taken. Would clean {len(procs)} processes + {len(locks)} locks.")
    elif actions:
        print(f"\n[cleanup] Cleaned {actions} item(s).")
    return 0


def _find_stale_processes(user: str) -> list[tuple[int, str]]:
    patterns = ["virtuoso", "cdsServIpc", "spectre"]
    results = []
    for pat in patterns:
        try:
            r = subprocess.run(
                ["pgrep", "-u", user, "-a", "-f", pat],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                for line in r.stdout.strip().splitlines():
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        pid = int(parts[0])
                        cmd = parts[1][:80]
                        if "vbridge" not in cmd and "claude" not in cmd:
                            results.append((pid, cmd))
        except Exception:
            pass
    seen = set()
    deduped = []
    for pid, cmd in results:
        if pid not in seen:
            seen.add(pid)
            deduped.append((pid, cmd))
    return deduped


def _find_lock_files(search_dir: str | None) -> list[Path]:
    root = Path(search_dir) if search_dir else Path.cwd()
    locks = []
    try:
        for lf in root.rglob("*.cdslck*"):
            if lf.is_file():
                locks.append(lf)
    except PermissionError:
        pass
    return locks
