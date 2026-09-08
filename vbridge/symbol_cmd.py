"""vbridge symbol — symbol generation CLI commands."""

from __future__ import annotations

import sys


def run_generate(lib: str, cell: str, *, overwrite: bool = False,
                 timeout: int = 60, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    client = get_client(profile=profile, timeout=timeout)
    try:
        result = client.symbol.generate_from_schematic(
            lib, cell, overwrite=overwrite, timeout=timeout,
        )
        print(f"[symbol] {result.action.value}: {lib}/{cell}/{result.symbol_view}")
        print(f"  terminals: {', '.join(result.terminal_names)}")
        return 0
    except Exception as e:
        print(f"[symbol] error: {e}", file=sys.stderr)
        return 1
