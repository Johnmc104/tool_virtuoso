"""vbridge lib — library management CLI commands."""

from __future__ import annotations

import json
import sys


def run_list(*, json_output: bool = False, timeout: int = 30,
             profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    client = get_client(profile=profile, timeout=timeout)
    libs = client.library.list(timeout=timeout)

    if json_output:
        print(json.dumps(libs, ensure_ascii=False))
    else:
        for lib in libs:
            print(f"  {lib}")
        print(f"Total: {len(libs)} libraries")
    return 0


def run_create(name: str, path: str, *, tech_lib: str | None = None,
               timeout: int = 60, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    client = get_client(profile=profile, timeout=timeout)
    try:
        info = client.library.create(name, path, technology_library=tech_lib,
                                     timeout=timeout)
        print(f"[lib] Created: {info.name} at {info.path}")
        if info.technology_library:
            print(f"  tech: {info.technology_library}")
        return 0
    except Exception as e:
        print(f"[lib] error: {e}", file=sys.stderr)
        return 1
