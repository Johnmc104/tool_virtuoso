"""X11 display detection for Virtuoso GUI startup."""

from __future__ import annotations

import logging
import os
import subprocess

_log = logging.getLogger(__name__)


def ensure_display() -> bool:
    """Ensure DISPLAY is set for X11 GUI applications."""
    if os.environ.get("DISPLAY"):
        return True

    try:
        import getpass
        username = getpass.getuser()
        result = subprocess.run(
            ["pgrep", "-a", "-f", f"vncsession.*{username}"],
            capture_output=True, timeout=3, text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                for part in parts:
                    if part.startswith(":") and part[1:].isdigit():
                        os.environ["DISPLAY"] = part
                        _log.debug("Detected VNC DISPLAY=%s", part)
                        return True
    except Exception:
        pass

    from pathlib import Path
    x11_dir = Path("/tmp/.X11-unix")
    if x11_dir.is_dir():
        for sock in sorted(x11_dir.iterdir()):
            name = sock.name
            if name.startswith("X"):
                display = f":{name[1:]}"
                try:
                    result = subprocess.run(
                        ["xdpyinfo", "-display", display],
                        capture_output=True, timeout=3,
                    )
                    if result.returncode == 0:
                        os.environ["DISPLAY"] = display
                        _log.debug("Auto-detected DISPLAY=%s", display)
                        return True
                except Exception:
                    continue

    _log.debug("No X11 display found")
    return False
