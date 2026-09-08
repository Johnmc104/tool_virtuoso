"""vbridge exec — execute a SKILL expression via the bridge daemon."""

from __future__ import annotations

import json
import sys


def run(expression: str, *, timeout: int = 30, json_output: bool = False,
        profile: str | None = None) -> int:
    from vbridge.auto_start import wait_bridge_ready
    from vbridge.env_helpers import get_client

    wait_bridge_ready(timeout=30)
    client = get_client(profile=profile, timeout=timeout)

    if expression == "-":
        expression = sys.stdin.read().strip()
    if not expression:
        print("[exec] error: empty expression", file=sys.stderr)
        return 1

    wrapped = f"progn(\n{expression}\n)"
    result = client.execute_skill(wrapped, timeout=timeout)

    if json_output:
        print(json.dumps({
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "output": result.output,
            "errors": list(result.errors) if result.errors else [],
            "time": result.execution_time,
        }, ensure_ascii=False))
    else:
        if result.output:
            print(result.output)
        if result.errors:
            for e in result.errors:
                print(f"[error] {e}", file=sys.stderr)

    return 0 if result.ok else 1
