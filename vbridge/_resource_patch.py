"""Monkey-patch resource finders for PyInstaller _MEIPASS."""

from __future__ import annotations

import logging
import sys

_log = logging.getLogger(__name__)


def patch_resource_finders() -> None:
    """Patch vbridge resource finders to use sys._MEIPASS in frozen binaries."""
    if not getattr(sys, "frozen", False):
        return

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return

    from pathlib import Path
    res_dir = Path(meipass) / "virtuoso_bridge" / "virtuoso" / "basic" / "resources"
    if not res_dir.is_dir():
        _log.debug("_MEIPASS resource dir not found: %s", res_dir)
        return

    import virtuoso_bridge.transport.tunnel as _tmod

    _orig_find_il = _tmod._find_ramic_bridge_il
    _orig_find_daemon = _tmod._find_ramic_bridge_daemon

    def _patched_find_il() -> Path:
        try:
            return _orig_find_il()
        except FileNotFoundError:
            p = res_dir / "ramic_bridge.il"
            if p.is_file():
                return p
            raise

    def _patched_find_daemon(python_major: int) -> Path:
        try:
            return _orig_find_daemon(python_major)
        except FileNotFoundError:
            fname = "ramic_bridge_daemon_3.py" if python_major >= 3 else "ramic_bridge_daemon_27.py"
            p = res_dir / fname
            if p.is_file():
                return p
            raise

    _tmod._find_ramic_bridge_il = _patched_find_il
    _tmod._find_ramic_bridge_daemon = _patched_find_daemon
    _log.debug("Patched resource finders -> _MEIPASS: %s", res_dir)
