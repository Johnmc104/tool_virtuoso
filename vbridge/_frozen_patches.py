"""PyInstaller frozen-binary patches for virtuoso-bridge resources."""

from __future__ import annotations

import logging
import os
import re

_log = logging.getLogger(__name__)


def patch_setup_for_frozen(setup_path: str) -> None:
    """Rewrite virtuoso_setup.il to call `vbridge daemon` instead of python."""
    import sys as _sys
    if not getattr(_sys, "frozen", False):
        return

    from pathlib import Path
    p = Path(setup_path)
    if not p.is_file():
        return

    vbridge_bin = str(Path(_sys.executable).parent / "vbridge")
    content = p.read_text(encoding="utf-8")

    content = re.sub(
        r'setShellEnvVar\("RB_PYTHON_PATH"\s+"[^"]+"\)',
        f'setShellEnvVar("RB_PYTHON_PATH" "{vbridge_bin}")',
        content,
    )
    content = re.sub(
        r'setShellEnvVar\("RB_DAEMON_PATH"\s+"[^"]+"\)',
        'setShellEnvVar("RB_DAEMON_PATH" "daemon")',
        content,
    )
    p.write_text(content, encoding="utf-8")
    _log.debug("Patched setup IL -> %s daemon", vbridge_bin)
