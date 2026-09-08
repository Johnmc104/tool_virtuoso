"""vbridge auto-start — upper-layer orchestrator.

Two-part design:
  - Upper layer (this file): state detection, duplicate prevention, scheduling
  - Lower layer: `virtuoso-bridge start` (handles actual bridge setup)
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from vbridge._display import ensure_display


def _read_state() -> dict | None:
    """Read state.json written by virtuoso-bridge start."""
    from virtuoso_bridge.transport.tunnel import SSHClient
    return SSHClient.read_state()


def _get_setup_path() -> str | None:
    """Get setup_path from state."""
    state = _read_state()
    if state:
        p = state.get("setup_path")
        if p and Path(p).is_file():
            return p
    return None


def _get_port() -> int:
    """Get bridge port from state or env."""
    state = _read_state()
    if state and state.get("port"):
        return int(state["port"])
    return int(os.environ.get("VB_LOCAL_PORT",
               os.environ.get("VB_REMOTE_PORT", "65432")))


def is_daemon_responding(port: int | None = None) -> bool:
    """Check if RAMIC daemon responds on port."""
    if port is None:
        port = _get_port()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
            s.sendall(b'1+1\n')
            s.settimeout(2)
            return len(s.recv(64)) > 0
    except Exception:
        return False


def _is_virtuoso_running() -> bool:
    """Check if a virtuoso -replay process is already running."""
    try:
        r = subprocess.run(["pgrep", "-f", "virtuoso.*-replay"],
                           capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def _ensure_setup_il() -> str | None:
    """If virtuoso_setup.il is missing, generate it from state info."""
    state = _read_state()
    if not state:
        return None
    setup_path = state.get("setup_path")
    if not setup_path:
        return None
    if Path(setup_path).is_file():
        return setup_path

    work_dir = Path(setup_path).parent
    work_dir.mkdir(parents=True, exist_ok=True)

    daemon_file = work_dir / "ramic_bridge_daemon_3.py"
    il_file = work_dir / "ramic_bridge.il"
    if not daemon_file.is_file() or not il_file.is_file():
        return None

    port = state.get("port", 65432)
    identity_path = state.get("identity_path")
    if getattr(sys, "frozen", False):
        vbridge_bin = str(Path(sys.executable).parent / "vbridge")
        python_cmd = vbridge_bin
        daemon_ref = "daemon"
    else:
        python_cmd = sys.executable
        daemon_ref = str(daemon_file)

    from virtuoso_bridge.transport.tunnel import _generate_virtuoso_setup_il
    content = _generate_virtuoso_setup_il(
        daemon_path=daemon_ref,
        il_path=str(il_file),
        python_cmd=python_cmd,
        port=port,
        identity_path=identity_path,
    )
    Path(setup_path).write_text(content, encoding="utf-8")
    print(f"[auto-start] Generated {setup_path}")
    return setup_path


def _run_bridge_start() -> int:
    """Ensure .env is valid, then run bridge start directly."""
    from virtuoso_bridge.env import default_user_env_path, load_vb_env
    from virtuoso_bridge.cli import cli_init

    env_path = default_user_env_path()
    need_init = True
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("VB_REMOTE_HOST=") and s.split("=", 1)[1].strip():
                need_init = False
                break

    if need_init:
        print("[auto-start] VB_REMOTE_HOST is empty, re-initializing...")
        cli_init(remote="localhost", force=True)

    load_vb_env()

    state = _read_state()
    if state and not is_daemon_responding():
        from virtuoso_bridge.cli import cli_stop
        cli_stop()

    from vbridge.cli import _patched_cli_start
    return _patched_cli_start()


def _wait_for_daemon(port: int, timeout: float = 60) -> bool:
    """Poll until daemon responds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_daemon_responding(port):
            return True
        time.sleep(1)
    return False


def _launch_virtuoso(setup_path: str) -> subprocess.Popen | None:
    """Launch virtuoso -replay in background, detached."""
    from virtuoso_bridge.runtime_paths import log_dir as _log_dir
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        vlog = open(log_dir / "virtuoso_autostart.log", "w")
        proc = subprocess.Popen(
            ["virtuoso", "-replay", setup_path],
            stdout=vlog, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return proc
    except Exception as e:
        print(f"[auto-start] Failed to launch Virtuoso: {e}")
        return None


def startup_sequence(timeout: float = 60) -> int:
    """One-click startup. No prior init required.

    Flow:
      1. Check state: if daemon responding, done (no duplicate)
      2. Check setup files: if missing, call `virtuoso-bridge start`
      3. If virtuoso on PATH + X11 available: launch GUI
      4. Wait for daemon
    """
    port = _get_port()

    # --- State check: prevent duplicate ---
    if is_daemon_responding(port):
        print(f"[auto-start] Daemon already responding on port {port}.")
        return 0

    # --- Ensure setup files exist (call lower layer) ---
    setup_path = _get_setup_path()
    if not setup_path:
        print("[auto-start] Setup files missing, running bridge start...")
        rc = _run_bridge_start()
        if rc != 0:
            print("[auto-start] bridge start failed")
            return 1
        setup_path = _get_setup_path()
        if not setup_path:
            setup_path = _ensure_setup_il()
    else:
        print(f"[auto-start] Setup: {setup_path}")

    # Re-read port after start (may have changed)
    port = _get_port()

    if not setup_path:
        print("[auto-start] Bridge started but setup file not generated")
        return 0

    # Check again after start
    if is_daemon_responding(port):
        print(f"[auto-start] Daemon responding on port {port}.")
        return 0

    # --- Patch for frozen binary ---
    if getattr(sys, "frozen", False):
        from vbridge._frozen_patches import patch_setup_for_frozen
        patch_setup_for_frozen(setup_path)

    # --- Try to launch Virtuoso ---
    vbin = shutil.which("virtuoso")
    if not vbin:
        print(f"[auto-start] 'virtuoso' not on PATH")
        print(f"  Load in CIW: load(\"{setup_path}\")")
        return 0

    if not ensure_display():
        print(f"[auto-start] No X11 display available")
        print(f"  Load in CIW: load(\"{setup_path}\")")
        return 0

    if _is_virtuoso_running():
        print("[auto-start] Virtuoso already running.")
        if is_daemon_responding(port):
            print("[auto-start] Ready!")
            return 0
        print(f"  Waiting for CIW to load setup script...")
        print(f"  Or manually: load(\"{setup_path}\")")
        print(f"  Check: vbridge status")
        return 0

    print("[auto-start] Launching Virtuoso...")
    proc = _launch_virtuoso(setup_path)
    if not proc:
        return 1

    # Verify process is alive after brief settle
    time.sleep(2)
    if proc.poll() is not None:
        print(f"[auto-start] Virtuoso exited immediately (code={proc.returncode})")
        return 1

    print(f"[auto-start] Virtuoso PID {proc.pid} started.")

    # Quick check — Virtuoso cold start is slow, don't block forever
    if _wait_for_daemon(port, timeout=min(timeout, 15)):
        print("[auto-start] Ready!")
        return 0

    print(f"[auto-start] Virtuoso is starting (may take 1-2 minutes).")
    print(f"  Check: vbridge status")
    return 0


def wait_bridge_ready(timeout: float = 30) -> bool:
    """Block until bridge daemon is ready (for exec/load commands)."""
    if is_daemon_responding():
        return True
    return _wait_for_daemon(_get_port(), timeout=timeout)
