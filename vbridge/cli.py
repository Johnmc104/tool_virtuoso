"""vbridge CLI — upstream virtuoso-bridge commands + exec/load/sch/daemon/auto-start."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from virtuoso_bridge.cli import (
    build_parser as upstream_build_parser,
    main as upstream_main,
    _CLI_PROFILE,
    _SCREENSHOT_TARGET,
    _SNAPSHOT_OPTS,
    _EXPORT_VISIO_OPTS,
    _make_stdio_safe,
    cli_init,
    cli_start as _orig_cli_start,
    cli_stop,
    cli_restart,
    cli_status,
    cli_license,
    cli_dismiss_dialog,
    cli_screenshot,
    cli_windows,
    cli_snapshot,
    cli_export_visio,
)
from virtuoso_bridge.env import set_runtime_env_file


def _patched_cli_start() -> int:
    """Wrap upstream cli_start to patch setup.il for frozen mode."""
    rc = _orig_cli_start()
    if rc == 0 and getattr(sys, "frozen", False):
        from vbridge._frozen_patches import patch_setup_for_frozen
        try:
            from virtuoso_bridge.transport.tunnel import SSHClient
            state = SSHClient.read_state()
            if state and state.get("setup_path"):
                patch_setup_for_frozen(state["setup_path"])
        except Exception:
            pass
    return rc


def build_parser():
    """Build upstream parser then add extension subcommands."""
    parser = upstream_build_parser()

    # Accept -u (Python unbuffered flag) silently — ramic_bridge.il hardcodes it
    parser.add_argument("-u", action="store_true", default=False,
                        help=argparse.SUPPRESS)

    for action in parser._subparsers._actions:
        if hasattr(action, "_parser_class"):
            subparsers = action
            break
    else:
        raise RuntimeError("cannot find subparsers in upstream parser")

    # -- auto-start ---
    sp_auto = subparsers.add_parser(
        "auto-start", help="One-click: start bridge + launch Virtuoso + wait")
    sp_auto.add_argument("--timeout", type=float, default=60,
                         help="Max seconds to wait for daemon")
    sp_auto.add_argument("-p", "--profile", default=None)
    sp_auto.add_argument("--env", default=None)

    # -- exec ---
    sp_exec = subparsers.add_parser("exec", help="Execute SKILL expression")
    sp_exec.add_argument("expression", nargs="?", default="-",
                         help="SKILL code (use '-' or omit for stdin)")
    sp_exec.add_argument("--timeout", type=int, default=30)
    sp_exec.add_argument("--json", action="store_true", dest="json_output")
    sp_exec.add_argument("-p", "--profile", default=None)
    sp_exec.add_argument("--env", default=None)

    # -- load ---
    sp_load = subparsers.add_parser("load", help="Load .il file in Virtuoso")
    sp_load.add_argument("path", help="Path to .il file")
    sp_load.add_argument("--verbose", action="store_true")
    sp_load.add_argument("--timeout", type=int, default=60)
    sp_load.add_argument("-p", "--profile", default=None)
    sp_load.add_argument("--env", default=None)

    # -- sch ---
    sp_sch = subparsers.add_parser("sch", help="Schematic operations")
    sch_sub = sp_sch.add_subparsers(dest="sch_command")

    sp_batch = sch_sub.add_parser("batch", help="Batch ops from JSON stdin")
    sp_batch.add_argument("lib"); sp_batch.add_argument("cell")
    sp_batch.add_argument("--view", default="schematic")
    sp_batch.add_argument("--timeout", type=int, default=120)
    sp_batch.add_argument("-p", "--profile", default=None)

    sp_create = sch_sub.add_parser("create", help="Create/open cellview")
    sp_create.add_argument("lib"); sp_create.add_argument("cell")
    sp_create.add_argument("--view", default="schematic")
    sp_create.add_argument("--timeout", type=int, default=30)
    sp_create.add_argument("-p", "--profile", default=None)

    sp_save = sch_sub.add_parser("save", help="Save + check cellview")
    sp_save.add_argument("--timeout", type=int, default=30)
    sp_save.add_argument("-p", "--profile", default=None)

    sp_list = sch_sub.add_parser("list", help="List instances")
    sp_list.add_argument("lib"); sp_list.add_argument("cell")
    sp_list.add_argument("--view", default="schematic")
    sp_list.add_argument("--timeout", type=int, default=30)
    sp_list.add_argument("-p", "--profile", default=None)

    # -- daemon (internal, called by Virtuoso IPC) ---
    sp_daemon = subparsers.add_parser("daemon", help="Run RAMIC bridge daemon")
    sp_daemon.add_argument("host"); sp_daemon.add_argument("port", type=int)

    return parser


def _run_daemon(host: str, port: int) -> int:
    """Run RAMIC bridge daemon inline (no external Python needed)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        script = (
            Path(meipass) / "virtuoso_bridge" / "virtuoso" / "basic"
            / "resources" / "ramic_bridge_daemon_3.py"
        )
    else:
        try:
            from virtuoso_bridge.transport.tunnel import _find_ramic_bridge_daemon
            script = _find_ramic_bridge_daemon(3)
        except Exception:
            from importlib.resources import files
            script = Path(
                str(files("virtuoso_bridge.virtuoso.basic.resources")
                    .joinpath("ramic_bridge_daemon_3.py"))
            )

    sys.argv = [str(script), host, str(port)]
    code = Path(script).read_text(encoding="utf-8")
    exec(compile(code, str(script), "exec"), {
        "__name__": "__main__",
        "__file__": str(script),
    })
    return 0


def _handle_sch(args, profile: str | None) -> int:
    sub = getattr(args, "sch_command", None)
    if not sub:
        print("usage: vbridge sch {batch,create,save,list} ...")
        return 1

    if sub == "batch":
        from vbridge.sch_cmd import run_batch
        return run_batch(args.lib, args.cell, sys.stdin.read(),
                         view=args.view, timeout=args.timeout, profile=profile)
    if sub == "create":
        from vbridge.sch_cmd import run_create
        return run_create(args.lib, args.cell, view=args.view,
                          timeout=args.timeout, profile=profile)
    if sub == "save":
        from vbridge.sch_cmd import run_save
        return run_save(timeout=args.timeout, profile=profile)
    if sub == "list":
        from vbridge.sch_cmd import run_list_instances
        return run_list_instances(args.lib, args.cell, view=args.view,
                                  timeout=args.timeout, profile=profile)
    print(f"unknown sch subcommand: {sub}")
    return 1


def main(argv: list[str] | None = None) -> int:
    _make_stdio_safe()
    parser = build_parser()
    args = parser.parse_args(argv)

    upstream_dispatch = {
        "init": lambda: cli_init(
            remote=getattr(args, "remote", None),
            jump=getattr(args, "jump", None),
            force=getattr(args, "force", False),
        ),
        "start": _patched_cli_start,
        "stop": cli_stop,
        "restart": cli_restart,
        "status": cli_status,
        "license": cli_license,
        "dismiss-dialog": cli_dismiss_dialog,
        "screenshot": cli_screenshot,
        "windows": cli_windows,
        "snapshot": cli_snapshot,
        "export-visio": cli_export_visio,
    }

    profile = getattr(args, "profile", None)
    if profile is not None:
        _CLI_PROFILE[0] = profile
    set_runtime_env_file(getattr(args, "env", None))

    screenshot_target = getattr(args, "target", None)
    if screenshot_target is not None:
        _SCREENSHOT_TARGET[0] = screenshot_target
    if args.command == "snapshot":
        for k in _SNAPSHOT_OPTS:
            v = getattr(args, k, None)
            if v is not None:
                _SNAPSHOT_OPTS[k] = v
    if args.command == "export-visio":
        for k in _EXPORT_VISIO_OPTS:
            v = getattr(args, k, None)
            if v is not None:
                _EXPORT_VISIO_OPTS[k] = v

    command = args.command

    if command in upstream_dispatch:
        return upstream_dispatch[command]()

    if command == "auto-start":
        from vbridge.auto_start import startup_sequence
        return startup_sequence(timeout=args.timeout)

    if command == "exec":
        from vbridge.exec_cmd import run
        return run(args.expression, timeout=args.timeout,
                   json_output=args.json_output, profile=profile)

    if command == "load":
        from vbridge.load_cmd import run
        return run(args.path, verbose=args.verbose,
                   timeout=args.timeout, profile=profile)

    if command == "sch":
        return _handle_sch(args, profile)

    if command == "daemon":
        return _run_daemon(args.host, args.port)

    parser.print_help()
    return 1
