"""Robust .env loading and VirtuosoClient factory."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env_robust() -> None:
    """Load .env without requiring upstream _repo_root().

    Search: CWD/.env -> ~/.virtuoso-bridge/.env -> VB_REMOTE_HOST already set.
    """
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        load_dotenv(cwd_env, override=True)
        return

    user_env = Path.home() / ".virtuoso-bridge" / ".env"
    if user_env.is_file():
        load_dotenv(user_env, override=True)
        return

    vb_root = os.environ.get("VIRTUOSO_BRIDGE_ROOT", "")
    if vb_root:
        root_env = Path(vb_root) / ".env"
        if root_env.is_file():
            load_dotenv(root_env, override=True)
            return


def get_client(profile: str | None = None, timeout: int = 30):
    """Create a VirtuosoClient that works in all deployment modes."""
    load_env_robust()

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
