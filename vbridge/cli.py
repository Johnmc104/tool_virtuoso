"""vbridge CLI — upstream virtuoso-bridge commands + exec/sch/daemon/auto-start."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from virtuoso_bridge.cli import (
    build_parser as upstream_build_parser,
    _CLI_PROFILE,
    _SCREENSHOT_TARGET,
    _SCREENSHOT_OUTPUT,
    _SNAPSHOT_OPTS,
    _EXPORT_VISIO_OPTS,
    _make_stdio_safe,
    cli_init,
    cli_start as _orig_cli_start,
    cli_stop,
    cli_restart,
    cli_status,
    cli_license,
    cli_load,
    cli_eval,
    cli_dismiss_dialog,
    cli_dismiss_window,
    cli_list_windows,
    cli_screenshot,
    cli_windows,
    cli_snapshot,
    cli_export_visio,
    cli_bootstrap,
    cli_profile,
    cli_find,
    cli_skill_info,
    cli_doc_search,
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
    sp_auto.add_argument("--wait", action="store_true",
                         help="Block until daemon is fully ready")
    sp_auto.add_argument("--json", action="store_true", dest="json_output",
                         help="Output machine-readable JSON status")
    sp_auto.add_argument("-p", "--profile", default=None)
    sp_auto.add_argument("--env", default=None)

    # -- exec (vbridge-specific alias, kept for backward compat) ---
    sp_exec = subparsers.add_parser("exec", help="Execute SKILL expression (vbridge alias)")
    sp_exec.add_argument("expression", nargs="?", default="-",
                         help="SKILL code (use '-' or omit for stdin)")
    sp_exec.add_argument("--timeout", type=int, default=30)
    sp_exec.add_argument("--json", action="store_true", dest="json_output")
    sp_exec.add_argument("-p", "--profile", default=None)
    sp_exec.add_argument("--env", default=None)

    # -- sch ---
    sp_sch = subparsers.add_parser("sch", help="Schematic operations")
    sch_sub = sp_sch.add_subparsers(dest="sch_command")

    sp_batch = sch_sub.add_parser("batch", help="Batch ops from JSON stdin")
    sp_batch.add_argument("lib"); sp_batch.add_argument("cell")
    sp_batch.add_argument("--view", default="schematic")
    sp_batch.add_argument("--timeout", type=int, default=120)
    sp_batch.add_argument("-p", "--profile", default=None)
    sp_batch.add_argument("--env", default=None)

    sp_create = sch_sub.add_parser("create", help="Create/open cellview")
    sp_create.add_argument("lib"); sp_create.add_argument("cell")
    sp_create.add_argument("--view", default="schematic")
    sp_create.add_argument("--timeout", type=int, default=30)
    sp_create.add_argument("-p", "--profile", default=None)
    sp_create.add_argument("--env", default=None)

    sp_save = sch_sub.add_parser("save", help="Save + check cellview")
    sp_save.add_argument("--timeout", type=int, default=30)
    sp_save.add_argument("-p", "--profile", default=None)
    sp_save.add_argument("--env", default=None)

    sp_list = sch_sub.add_parser("list", help="List instances")
    sp_list.add_argument("lib"); sp_list.add_argument("cell")
    sp_list.add_argument("--view", default="schematic")
    sp_list.add_argument("--timeout", type=int, default=30)
    sp_list.add_argument("-p", "--profile", default=None)
    sp_list.add_argument("--env", default=None)

    sp_read = sch_sub.add_parser("read", help="Read schematic structure")
    sp_read.add_argument("lib"); sp_read.add_argument("cell")
    sp_read.add_argument("--json", action="store_true", dest="json_output")
    sp_read.add_argument("--timeout", type=int, default=30)
    sp_read.add_argument("-p", "--profile", default=None)
    sp_read.add_argument("--env", default=None)

    sp_param = sch_sub.add_parser("param", help="Set instance parameter")
    sp_param.add_argument("lib"); sp_param.add_argument("cell")
    sp_param.add_argument("inst", help="Instance name")
    sp_param.add_argument("param", help="Parameter name (e.g. w, l, nf)")
    sp_param.add_argument("value", help="Parameter value")
    sp_param.add_argument("--view", default="schematic")
    sp_param.add_argument("--timeout", type=int, default=30)
    sp_param.add_argument("-p", "--profile", default=None)
    sp_param.add_argument("--env", default=None)

    # -- sim ---
    sp_sim = subparsers.add_parser("sim", help="Spectre simulation")
    sim_sub = sp_sim.add_subparsers(dest="sim_command")

    sp_sim_run = sim_sub.add_parser("run", help="Run Spectre simulation")
    sp_sim_run.add_argument("netlist", help="Path to .scs netlist")
    sp_sim_run.add_argument("-o", "--output", default=None, help="Output directory")
    sp_sim_run.add_argument("--mode", default="default",
                            choices=["default", "aps", "ax", "cx", "mx", "lx"],
                            help="Spectre execution mode")
    sp_sim_run.add_argument("--timeout", type=int, default=600)
    sp_sim_run.add_argument("-p", "--profile", default=None)
    sp_sim_run.add_argument("--env", default=None)

    sp_sim_result = sim_sub.add_parser("result", help="Parse simulation results")
    sp_sim_result.add_argument("dir", help="Raw PSF output directory")
    sp_sim_result.add_argument("--signal", default=None, help="Query specific signal")
    sp_sim_result.add_argument("--json", action="store_true", dest="json_output")
    sp_sim_result.add_argument("--csv", action="store_true", dest="export_csv",
                               help="Export data as CSV")

    sp_sim_lic = sim_sub.add_parser("license", help="Check Spectre license")
    sp_sim_lic.add_argument("-p", "--profile", default=None)
    sp_sim_lic.add_argument("--env", default=None)

    # -- lib ---
    sp_lib = subparsers.add_parser("lib", help="Library management")
    lib_sub = sp_lib.add_subparsers(dest="lib_command")

    sp_lib_list = lib_sub.add_parser("list", help="List libraries")
    sp_lib_list.add_argument("--json", action="store_true", dest="json_output")
    sp_lib_list.add_argument("--timeout", type=int, default=30)
    sp_lib_list.add_argument("-p", "--profile", default=None)
    sp_lib_list.add_argument("--env", default=None)

    sp_lib_create = lib_sub.add_parser("create", help="Create library")
    sp_lib_create.add_argument("name", help="Library name")
    sp_lib_create.add_argument("--path", required=True, help="Library path")
    sp_lib_create.add_argument("--tech-lib", default=None, help="Technology library")
    sp_lib_create.add_argument("--timeout", type=int, default=60)
    sp_lib_create.add_argument("-p", "--profile", default=None)
    sp_lib_create.add_argument("--env", default=None)

    # -- symbol ---
    sp_sym = subparsers.add_parser("symbol", help="Symbol operations")
    sym_sub = sp_sym.add_subparsers(dest="symbol_command")

    sp_sym_gen = sym_sub.add_parser("generate", help="Generate symbol from schematic")
    sp_sym_gen.add_argument("lib"); sp_sym_gen.add_argument("cell")
    sp_sym_gen.add_argument("--overwrite", action="store_true")
    sp_sym_gen.add_argument("--timeout", type=int, default=60)
    sp_sym_gen.add_argument("-p", "--profile", default=None)
    sp_sym_gen.add_argument("--env", default=None)

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
        print("usage: vbridge sch {batch,create,save,list,read,param} ...")
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
    if sub == "read":
        from vbridge.sch_cmd import run_read
        return run_read(args.lib, args.cell,
                        json_output=args.json_output,
                        timeout=args.timeout, profile=profile)
    if sub == "param":
        from vbridge.sch_cmd import run_param
        return run_param(args.lib, args.cell, args.inst, args.param, args.value,
                         view=args.view, timeout=args.timeout, profile=profile)
    print(f"unknown sch subcommand: {sub}")
    return 1


def _handle_sim(args, profile: str | None) -> int:
    sub = getattr(args, "sim_command", None)
    if not sub:
        print("usage: vbridge sim {run,result,license} ...")
        return 1

    if sub == "run":
        from vbridge.sim_cmd import run_sim
        return run_sim(args.netlist, output_dir=args.output,
                       mode=args.mode, timeout=args.timeout,
                       profile=profile)
    if sub == "result":
        from vbridge.sim_cmd import run_result
        return run_result(args.dir, signal=args.signal,
                          json_output=args.json_output,
                          export_csv=getattr(args, "export_csv", False))
    if sub == "license":
        from vbridge.sim_cmd import run_license
        return run_license(profile=profile)
    print(f"unknown sim subcommand: {sub}")
    return 1


def _handle_lib(args, profile: str | None) -> int:
    sub = getattr(args, "lib_command", None)
    if not sub:
        print("usage: vbridge lib {list,create} ...")
        return 1

    if sub == "list":
        from vbridge.lib_cmd import run_list
        return run_list(json_output=args.json_output,
                        timeout=args.timeout, profile=profile)
    if sub == "create":
        from vbridge.lib_cmd import run_create
        return run_create(args.name, args.path, tech_lib=args.tech_lib,
                          timeout=args.timeout, profile=profile)
    print(f"unknown lib subcommand: {sub}")
    return 1


def _handle_symbol(args, profile: str | None) -> int:
    sub = getattr(args, "symbol_command", None)
    if not sub:
        print("usage: vbridge symbol {generate} ...")
        return 1

    if sub == "generate":
        from vbridge.symbol_cmd import run_generate
        return run_generate(args.lib, args.cell, overwrite=args.overwrite,
                            timeout=args.timeout, profile=profile)
    print(f"unknown symbol subcommand: {sub}")
    return 1


def _is_local_mode() -> bool:
    """Check if bridge is configured for local mode (no SSH needed).

    Reads env vars already loaded by main() — does not re-load .env.
    """
    import os
    from virtuoso_bridge.transport.tunnel import _is_localhost
    profile = _CLI_PROFILE[0]
    suffix = f"_{profile}" if profile else ""
    host = os.getenv(f"VB_REMOTE_HOST{suffix}", "").strip()
    if not host:
        host = os.getenv(f"VB_DAEMON_HOST{suffix}", "").strip()
    return _is_localhost(host) if host else False


def _load_local(file: str, timeout: int, quiet: bool) -> int:
    """Load .il via SKILL load() — no SSH upload needed."""
    import json
    from pathlib import Path
    p = Path(file)
    if not p.is_file():
        print(f"ERROR: file not found: {p}", file=sys.stderr)
        return 2
    from vbridge.env_helpers import get_client
    from virtuoso_bridge.virtuoso.ops import escape_skill_string
    client = get_client(profile=_CLI_PROFILE[0], timeout=timeout)
    abs_path = str(p.resolve())
    result = client.execute_skill(
        f'load("{escape_skill_string(abs_path)}")', timeout=timeout,
    )
    if not quiet:
        print(json.dumps({
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "output": result.output or "",
            "errors": list(result.errors) if result.errors else [],
        }, indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


def _load_with_local_fallback(*, file: str, timeout: int = 60,
                              quiet: bool = False) -> int:
    """Use direct SKILL load() in local mode; upstream cli_load otherwise."""
    if _is_local_mode():
        return _load_local(file, timeout, quiet)
    return cli_load(file=file, timeout=timeout, quiet=quiet)


def main(argv: list[str] | None = None) -> int:
    _make_stdio_safe()
    parser = build_parser()
    args = parser.parse_args(argv)

    _CLI_PROFILE[0] = None
    set_runtime_env_file(getattr(args, "env", None))

    if getattr(args, "bind_venv", False):
        profile_arg = getattr(args, "profile", None)
        if not profile_arg:
            parser.error("--bind-venv requires -p/--profile")
        from virtuoso_bridge.profile import bind_venv_profile
        try:
            bind_venv_profile(profile_arg)
        except Exception as exc:
            parser.error(str(exc))

    from virtuoso_bridge.profile import resolve_profile
    profile = resolve_profile(getattr(args, "profile", None))
    if profile is not None:
        _CLI_PROFILE[0] = profile

    upstream_dispatch = {
        "init": lambda: cli_init(
            remote=getattr(args, "remote", None),
            jump=getattr(args, "jump", None),
            force=getattr(args, "force", False),
        ),
        "profile": lambda: cli_profile(
            action=getattr(args, "profile_action"),
            profile=getattr(args, "profile", None),
        ),
        "start": _patched_cli_start,
        "stop": cli_stop,
        "restart": cli_restart,
        "status": cli_status,
        "license": cli_license,
        "load": lambda: _load_with_local_fallback(
            file=getattr(args, "file"),
            timeout=getattr(args, "timeout", 60),
            quiet=getattr(args, "quiet", False),
        ),
        "eval": lambda: cli_eval(
            skill=getattr(args, "skill", None),
            stdin=getattr(args, "stdin", False),
            timeout=getattr(args, "timeout", 60),
            quiet=getattr(args, "quiet", False),
        ),
        "dismiss-dialog": cli_dismiss_dialog,
        "list-windows": lambda: cli_list_windows(
            json_output=getattr(args, "json", False),
            top_level=getattr(args, "top_level", False),
        ),
        "dismiss-window": lambda: cli_dismiss_window(
            window_id=getattr(args, "window_id"),
            action=getattr(args, "action", "enter"),
        ),
        "bootstrap": lambda: cli_bootstrap(
            window_id=getattr(args, "window"),
            timeout=getattr(args, "timeout", 12),
        ),
        "screenshot": cli_screenshot,
        "windows": cli_windows,
        "snapshot": cli_snapshot,
        "export-visio": cli_export_visio,
        "skill-find": lambda: cli_find(
            query=getattr(args, "query", None),
            mode=getattr(args, "mode", "fuzzy"),
            limit=getattr(args, "limit", 50),
            include_desc=getattr(args, "include_desc", False),
            json_output=getattr(args, "json", False),
        ),
        "skill-info": lambda: cli_skill_info(
            func_name=getattr(args, "func_name", None) or "",
            json_output=getattr(args, "json", False),
        ),
        "doc-search": lambda: cli_doc_search(
            query=getattr(args, "query", None),
            doc_roots=getattr(args, "doc_root", []),
            limit=getattr(args, "limit", 10),
            list_roots=getattr(args, "list_roots", False),
            json_output=getattr(args, "json", False),
            rebuild_index=getattr(args, "rebuild_index", False),
        ),
    }

    screenshot_target = getattr(args, "target", None)
    if screenshot_target is not None:
        _SCREENSHOT_TARGET[0] = screenshot_target
    screenshot_output = getattr(args, "output", None)
    if screenshot_output is not None:
        _SCREENSHOT_OUTPUT[0] = screenshot_output
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
        return startup_sequence(
            timeout=args.timeout,
            wait=getattr(args, "wait", False),
            json_output=getattr(args, "json_output", False),
        )

    if command == "exec":
        from vbridge.exec_cmd import run
        return run(args.expression, timeout=args.timeout,
                   json_output=args.json_output, profile=profile)

    if command == "sch":
        return _handle_sch(args, profile)

    if command == "sim":
        return _handle_sim(args, profile)

    if command == "lib":
        return _handle_lib(args, profile)

    if command == "symbol":
        return _handle_symbol(args, profile)

    if command == "daemon":
        return _run_daemon(args.host, args.port)

    parser.print_help()
    return 1
