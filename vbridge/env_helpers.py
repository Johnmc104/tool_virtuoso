"""VirtuosoClient factory for vbridge commands."""

from __future__ import annotations

import os

from virtuoso_bridge.env import load_vb_env


def get_client(profile: str | None = None, timeout: int = 30):
    """Create a VirtuosoClient that works in all deployment modes."""
    load_vb_env()

    from virtuoso_bridge.transport.tunnel import SSHClient, _is_localhost
    from virtuoso_bridge.virtuoso.basic.bridge import VirtuosoClient

    state = SSHClient.read_state(profile)
    suffix = f"_{profile}" if profile else ""
    host = os.getenv(f"VB_REMOTE_HOST{suffix}", "localhost").strip()
    is_local = _is_localhost(host)

    if state:
        port = state["port"]
        if is_local:
            return VirtuosoClient(host="127.0.0.1", port=port, timeout=timeout)
        ssh = SSHClient.from_env(keep_remote_files=True, profile=profile)
        return VirtuosoClient(host="127.0.0.1", port=port, timeout=timeout, tunnel=ssh)

    if is_local:
        port = int(os.getenv(f"VB_REMOTE_PORT{suffix}", "65432"))
        return VirtuosoClient.local(port=port)

    return VirtuosoClient.from_env(profile=profile, timeout=timeout)
