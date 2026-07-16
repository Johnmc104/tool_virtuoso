"""vbridge load — load an IL file into Virtuoso via the bridge daemon."""

from __future__ import annotations

import sys
from pathlib import Path


def run(path: str, *, verbose: bool = False, timeout: int = 60,
        profile: str | None = None) -> int:
    from vbridge.auto_start import wait_bridge_ready
    from vbridge.env_helpers import get_client

    wait_bridge_ready(timeout=30)

    p = Path(path)
    if not p.is_file():
        print(f"[load] error: file not found: {path}", file=sys.stderr)
        return 1

    client = get_client(profile=profile, timeout=timeout)
    result = client.load_il(str(p.resolve()), timeout=timeout)

    if result.ok:
        print(f"[load] OK: {p.name}")
        if verbose and result.output:
            print(result.output)
    else:
        print(f"[load] FAILED: {p.name}", file=sys.stderr)
        if result.output:
            print(result.output, file=sys.stderr)
        if result.errors:
            for e in result.errors:
                print(f"  {e}", file=sys.stderr)
    return 0 if result.ok else 1
