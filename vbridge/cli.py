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


def _ensure_cadence_in_path():
    """Auto-detect Cadence install path via daemon and add to PATH for SKILL Finder."""
    import os, shutil, re
    from pathlib import Path
    if shutil.which("virtuoso"):
        return
    try:
        from vbridge.env_helpers import get_client
        from virtuoso_bridge import decode_skill_output
        client = get_client(timeout=5)
        r = client.execute_skill('getInstallPath()', timeout=5)
        if r.output:
            import re
            raw = decode_skill_output(r.output).strip()
            m = re.search(r'(/[^")\s]+)', raw)
            install = m.group(1) if m else ""
            bin_dir = Path(install) / "bin" / "64bit" if install else None
            if bin_dir and bin_dir.is_dir():
                os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
    except Exception:
        pass


def _set_prog_recursive(parser, prog: str):
    """Replace prog name in parser and all subparsers."""
    parser.prog = prog
    for action in parser._actions:
        if hasattr(action, '_parser_class') and hasattr(action, 'choices'):
            for name, subparser in (action.choices or {}).items():
                _set_prog_recursive(subparser, f"{prog} {name}")


def _add_common_opts(sp, *, timeout: int = 30):
    """Add common options (-p, --env, --timeout) with help text."""
    sp.add_argument("--timeout", type=int, default=timeout, help=f"Timeout in seconds (default: {timeout})")
    sp.add_argument("-p", "--profile", default=None, help="Connection profile name")
    sp.add_argument("--env", default=None, help="Explicit .env file path")


def _add_lib_cell_args(sp):
    """Add lib + cell positional args with help text."""
    sp.add_argument("lib", help="Library name (e.g. my_osc, CRN65LP_v1.7a)")
    sp.add_argument("cell", help="Cell name (e.g. osc, nch_33)")


def _get_version() -> str:
    from pathlib import Path
    for p in [Path(__file__).parent.parent / "VERSION",
              Path(__file__).parent / "VERSION"]:
        if p.is_file():
            return p.read_text().strip()
    return "dev"


class _VbridgeHelpAction(argparse._HelpAction):
    """Custom help that shows grouped command summary."""

    def __call__(self, parser, namespace, values, option_string=None):
        version = _get_version()
        print(f"vbridge v{version} — Virtuoso Bridge CLI")
        print()
        print("usage: vbridge [-h] [-V] <command> [options]")
        print()
        print("connection:")
        print("  init          Create .env config           auto-start    One-click start")
        print("  start/stop    Manage SSH tunnel             status        Check connection")
        print()
        print("schematic:")
        print("  sch read      Read topology (--json)        sch list      List instances")
        print("  sch param     Set parameter (auto w/wf)     sch batch     Batch JSON ops (--dry-run)")
        print("  sch netlist   Export netlist (--standalone)  sch create    Create cellview (--force)")
        print()
        print("simulation:")
        print("  sim run       Run Spectre simulation        sim result    View results (--csv)")
        print("  sim measure   Measure: freq/avg/gain/bw/thd sim plot     Waveform plot (HTML/PNG)")
        print()
        print("maestro:")
        print("  maestro run   Run Maestro simulation        maestro var   Design variables")
        print("  maestro signals  List signals               maestro export  Export waveform")
        print()
        print("library:")
        print("  lib list      List libraries (--detail)     lib cells     PDK devices (--filter)")
        print("  lib cell-info Device attributes             lib views     Cell views")
        print()
        print("layout:")
        print("  layout read   Layout summary                 layout layers  List used layers")
        print("  layout export-gds  Export GDS-II              layout batch   Batch layout ops")
        print()
        print("other:")
        print("  exec          Execute SKILL expression      load          Load .il script")
        print("  cleanup       Kill stale processes           symbol generate  Create symbol")
        print("  skill-find    Search SKILL API docs          screenshot   Capture window")
        print()
        print("options:")
        print("  -h, --help    Show this help                -V, --version  Show version")
        print("  -p PROFILE    Connection profile             --env FILE    Explicit .env path")
        print()
        print("Use 'vbridge <command> --help' for detailed usage of each command.")
        parser.exit()


def build_parser():
    """Build upstream parser then add extension subcommands."""
    parser = upstream_build_parser()
    parser.add_argument("-V", "--version", action="version",
                        version=f"vbridge {_get_version()}")

    # Replace default help with grouped version
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            action.__class__ = _VbridgeHelpAction
            break

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
    sp_exec.add_argument("--timeout", type=int, default=30, help="Timeout in seconds (default: 30)")
    sp_exec.add_argument("--json", action="store_true", dest="json_output",
                         help="JSON output with status/errors/time")
    sp_exec.add_argument("-p", "--profile", default=None, help="Connection profile name")
    sp_exec.add_argument("--env", default=None, help="Explicit .env file path")

    # -- sch ---
    sp_sch = subparsers.add_parser("sch", help="Schematic operations")
    sch_sub = sp_sch.add_subparsers(dest="sch_command")

    sp_batch = sch_sub.add_parser("batch", help="Batch JSON operations from stdin",
        epilog="op types:\n"
               "  Instance:  add-inst, delete-inst, move-inst, copy-inst\n"
               "  Connect:   connect, label-mos, label-term\n"
               "  Params:    set-param\n"
               "  Other:     add-pin, add-wire, add-label\n"
               "\n"
               "common fields: inst (instance name), x/y (position), orientation (R0/MX/MY/R180)\n"
               "example: echo '[{\"op\":\"add-inst\",\"lib\":\"myPDK\",\"cell\":\"nch\",\"name\":\"M1\",\"x\":0,\"y\":0}]' | vbridge sch batch LIB CELL",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_lib_cell_args(sp_batch)
    sp_batch.add_argument("--view", default="schematic", help="View name (default: schematic)")
    sp_batch.add_argument("--dry-run", action="store_true", help="Show what would be done without executing")
    _add_common_opts(sp_batch, timeout=120)

    sp_create = sch_sub.add_parser("create", help="Create new cellview (requires --force if exists)")
    _add_lib_cell_args(sp_create)
    sp_create.add_argument("--view", default="schematic", help="View name (default: schematic)")
    sp_create.add_argument("--force", action="store_true", help="Overwrite existing cellview")
    _add_common_opts(sp_create)

    sp_save = sch_sub.add_parser("save", help="Check and save current cellview")
    _add_common_opts(sp_save)

    sp_list = sch_sub.add_parser("list", help="List instances (name + cell + position)")
    _add_lib_cell_args(sp_list)
    sp_list.add_argument("--view", default="schematic", help="View name (default: schematic)")
    _add_common_opts(sp_list)

    sp_read = sch_sub.add_parser("read", help="Read schematic structure (instances, nets, pins)")
    _add_lib_cell_args(sp_read)
    sp_read.add_argument("--json", action="store_true", dest="json_output",
                         help="Structured JSON output (recommended for programmatic use)")
    _add_common_opts(sp_read)

    sp_param = sch_sub.add_parser("param", help="Set instance parameter (auto-syncs w/wf)")
    _add_lib_cell_args(sp_param)
    sp_param.add_argument("inst", help="Instance name (e.g. M0, I10)")
    sp_param.add_argument("param", help="Parameter name (e.g. w, l, nf, vdc)")
    sp_param.add_argument("value", help="Parameter value (e.g. 2u, 180n, 4)")
    sp_param.add_argument("--view", default="schematic", help="View name (default: schematic)")
    _add_common_opts(sp_param)

    sp_netlist = sch_sub.add_parser("netlist", help="Export Spectre netlist from schematic")
    _add_lib_cell_args(sp_netlist)
    sp_netlist.add_argument("-o", "--output", required=True, help="Output directory")
    sp_netlist.add_argument("--simulator", default="spectre", help="Simulator type (default: spectre)")
    sp_netlist.add_argument("--standalone", action="store_true",
                            help="Auto-inject PDK model include + default analysis (tran+dc)")
    sp_netlist.add_argument("--section", default="tt_lib", help="Model section (default: tt_lib)")
    _add_common_opts(sp_netlist, timeout=120)

    # -- sim ---
    sp_sim = subparsers.add_parser("sim", help="Spectre simulation")
    sim_sub = sp_sim.add_subparsers(dest="sim_command")

    sp_sim_run = sim_sub.add_parser("run", help="Run Spectre simulation")
    sp_sim_run.add_argument("netlist", help="Netlist file (.scs)")
    sp_sim_run.add_argument("-o", "--output", default=None, help="Output directory for raw PSF results")
    sp_sim_run.add_argument("--mode", default="default",
                            choices=["default", "aps", "ax", "cx", "mx", "lx"],
                            help="Spectre execution mode (default: default)")
    _add_common_opts(sp_sim_run, timeout=600)

    sp_sim_result = sim_sub.add_parser("result", help="View simulation results (overview, CSV, or JSON)")
    sp_sim_result.add_argument("dir", help="Raw PSF directory")
    sp_sim_result.add_argument("--signal", default=None, help="Filter to one signal (optional)")
    sp_sim_result.add_argument("--json", action="store_true", dest="json_output",
                               help="JSON output")
    sp_sim_result.add_argument("--csv", action="store_true", dest="export_csv",
                               help="Export waveform data as CSV")

    sp_sim_meas = sim_sub.add_parser("measure",
                                     help="One-line measurement from results",
                                     epilog="tran: freq, avg, rms, minmax\n"
                                            "AC:   gain (dB), bw (-3dB Hz), ugf (0dB Hz), pm (deg)\n"
                                            "PSS:  thd (%)",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sp_sim_meas.add_argument("dir", help="Raw PSF directory")
    sp_sim_meas.add_argument("type",
                             choices=["freq", "avg", "rms", "minmax", "gain", "bw", "ugf", "pm", "thd"],
                             help="Measurement type")
    sp_sim_meas.add_argument("signal", help="Signal name (e.g. ON, out, V0:p)")
    sp_sim_meas.add_argument("--from", type=float, default=None, dest="from_time",
                             help="Start time/freq (e.g. 1e-6)")
    sp_sim_meas.add_argument("--to", type=float, default=None, dest="to_time",
                             help="End time/freq")

    sp_sim_plot = sim_sub.add_parser("plot", help="Plot waveform to HTML or PNG")
    sp_sim_plot.add_argument("dir", help="Raw PSF directory")
    sp_sim_plot.add_argument("signal", help="Signal(s), comma-separated (e.g. ON or ON,OP)")
    sp_sim_plot.add_argument("-o", "--output", required=True, help="Output file (.html or .png)")
    sp_sim_plot.add_argument("--from", type=float, default=None, dest="from_time",
                             help="Start time/freq (e.g. 1e-6)")
    sp_sim_plot.add_argument("--to", type=float, default=None, dest="to_time",
                             help="End time/freq")

    sp_sim_lic = sim_sub.add_parser("license", help="Check Spectre license availability")
    _add_common_opts(sp_sim_lic)

    # -- cleanup ---
    sp_cleanup = subparsers.add_parser("cleanup", help="Kill stale Cadence processes + remove OA locks")
    sp_cleanup.add_argument("--dir", default=None, help="Directory to search for lock files")
    sp_cleanup.add_argument("--dry-run", action="store_true", help="Show what would be done")

    # -- lib ---
    sp_lib = subparsers.add_parser("lib", help="Library management")
    lib_sub = sp_lib.add_subparsers(dest="lib_command")

    sp_lib_list = lib_sub.add_parser("list", help="List all libraries")
    sp_lib_list.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    sp_lib_list.add_argument("--detail", action="store_true", help="Show library paths")
    _add_common_opts(sp_lib_list)

    sp_lib_create = lib_sub.add_parser("create", help="Create a new library")
    sp_lib_create.add_argument("name", help="Library name")
    sp_lib_create.add_argument("--path", required=True, help="Filesystem path for the library")
    sp_lib_create.add_argument("--tech-lib", default=None, help="Technology library (e.g. gpdk045)")
    _add_common_opts(sp_lib_create, timeout=60)

    sp_lib_cells = lib_sub.add_parser("cells", help="List cells in a library")
    sp_lib_cells.add_argument("lib", help="Library name (e.g. CRN65LP_v1.7a)")
    sp_lib_cells.add_argument("--filter", default=None, help="Glob pattern (e.g. nch_*, pch_33*)")
    sp_lib_cells.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    _add_common_opts(sp_lib_cells)

    sp_lib_cellinfo = lib_sub.add_parser("cell-info", help="Show cell CDF defaults and views")
    _add_lib_cell_args(sp_lib_cellinfo)
    sp_lib_cellinfo.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    _add_common_opts(sp_lib_cellinfo)

    sp_lib_views = lib_sub.add_parser("views", help="List views of a cell")
    _add_lib_cell_args(sp_lib_views)
    sp_lib_views.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    _add_common_opts(sp_lib_views)

    # -- symbol ---
    sp_sym = subparsers.add_parser("symbol", help="Symbol operations")
    sym_sub = sp_sym.add_subparsers(dest="symbol_command")

    sp_sym_gen = sym_sub.add_parser("generate", help="Auto-generate symbol from schematic pins")
    _add_lib_cell_args(sp_sym_gen)
    sp_sym_gen.add_argument("--overwrite", action="store_true", help="Overwrite existing symbol")
    _add_common_opts(sp_sym_gen, timeout=60)

    # -- maestro ---
    sp_mae = subparsers.add_parser("maestro", help="Maestro simulation and waveform export")
    mae_sub = sp_mae.add_subparsers(dest="maestro_command")

    sp_mae_run = mae_sub.add_parser("run", help="Run Maestro simulation")
    _add_lib_cell_args(sp_mae_run)
    _add_common_opts(sp_mae_run, timeout=600)

    sp_mae_signals = mae_sub.add_parser("signals", help="List available signals in results")
    _add_lib_cell_args(sp_mae_signals)
    sp_mae_signals.add_argument("--history", default=None, help="History name (e.g. Interactive.2, auto-detect if omitted)")
    sp_mae_signals.add_argument("--analysis", default="tran", help="Analysis type (default: tran)")
    _add_common_opts(sp_mae_signals, timeout=60)

    sp_mae_var = mae_sub.add_parser("var", help="Get/set design variables")
    _add_lib_cell_args(sp_mae_var)
    sp_mae_var.add_argument("name", nargs="?", default=None, help="Variable name (omit to list all)")
    sp_mae_var.add_argument("value", nargs="?", default=None, help="Value to set (omit to read)")
    _add_common_opts(sp_mae_var)

    sp_mae_export = mae_sub.add_parser("export", help="Export waveform to text file")
    _add_lib_cell_args(sp_mae_export)
    sp_mae_export.add_argument("signal", help="Signal name (e.g. ON, /ON, V0:p)")
    sp_mae_export.add_argument("-o", "--output", required=True, help="Output file path")
    sp_mae_export.add_argument("--history", default=None, help="History name (auto-detect if omitted)")
    sp_mae_export.add_argument("--analysis", default="tran", help="Analysis type (default: tran)")
    _add_common_opts(sp_mae_export, timeout=120)

    # -- layout ---
    sp_lay = subparsers.add_parser("layout", help="Layout operations")
    lay_sub = sp_lay.add_subparsers(dest="layout_command")

    sp_lay_read = lay_sub.add_parser("read", help="Read layout summary (instances, shapes, bbox)")
    _add_lib_cell_args(sp_lay_read)
    sp_lay_read.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    _add_common_opts(sp_lay_read)

    sp_lay_gds = lay_sub.add_parser("export-gds", help="Export layout to GDS-II file")
    _add_lib_cell_args(sp_lay_gds)
    sp_lay_gds.add_argument("-o", "--output", required=True, help="Output GDS file path")
    _add_common_opts(sp_lay_gds, timeout=120)

    sp_lay_batch = lay_sub.add_parser("batch", help="Batch layout ops from JSON stdin",
        epilog="op types: add-rect, add-path, add-label, add-via, add-polygon, fit-view",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_lib_cell_args(sp_lay_batch)
    sp_lay_batch.add_argument("--dry-run", action="store_true", help="Preview without executing")
    _add_common_opts(sp_lay_batch, timeout=120)

    sp_lay_layers = lay_sub.add_parser("layers", help="List used layer/purpose pairs")
    _add_lib_cell_args(sp_lay_layers)
    _add_common_opts(sp_lay_layers)

    # -- daemon (internal, hidden from help) ---
    sp_daemon = subparsers.add_parser("daemon", help=argparse.SUPPRESS)
    sp_daemon.add_argument("host"); sp_daemon.add_argument("port", type=int)

    _set_prog_recursive(parser, "vbridge")
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
        print("usage: vbridge sch {read,list,param,batch,netlist,create,save} ...")
        print("\nread:")
        print("  read        Read schematic (instances + nets + pins, --json for structured data)")
        print("  list        List instances (name + cell + position)")
        print("\nedit:")
        print("  param       Set one instance parameter: vbridge sch param LIB CELL INST PARAM VALUE")
        print("  batch       Batch JSON ops from stdin (add/delete/move/copy-inst, connect, set-param, label-mos, ...)")
        print("  create      Create new cellview (WARNING: overwrites if exists)")
        print("  save        Check + save current cellview")
        print("\nexport:")
        print("  netlist     Export Spectre netlist (--standalone for auto PDK model injection)")
        return 1

    if sub == "batch":
        from vbridge.sch_cmd import run_batch
        return run_batch(args.lib, args.cell, sys.stdin.read(),
                         view=args.view, dry_run=getattr(args, "dry_run", False),
                         timeout=args.timeout, profile=profile)
    if sub == "create":
        from vbridge.sch_cmd import run_create
        return run_create(args.lib, args.cell, view=args.view,
                          force=getattr(args, "force", False),
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
    if sub == "netlist":
        from vbridge.sch_cmd import run_netlist
        return run_netlist(args.lib, args.cell, args.output,
                           simulator=args.simulator,
                           standalone=getattr(args, "standalone", False),
                           section=getattr(args, "section", "tt_lib"),
                           timeout=args.timeout, profile=profile)
    print(f"unknown sch subcommand: {sub}")
    return 1


def _handle_sim(args, profile: str | None) -> int:
    sub = getattr(args, "sim_command", None)
    if not sub:
        print("usage: vbridge sim {run,result,measure,plot,license} ...")
        print("\nrun:")
        print("  run         Run Spectre: vbridge sim run NETLIST -o DIR [--mode aps]")
        print("\nresults:")
        print("  result      View results overview, or export --csv / --json")
        print("  measure     One-line measurement: vbridge sim measure DIR TYPE SIGNAL")
        print("              types: freq avg rms minmax (tran) | gain bw ugf pm (AC) | thd (PSS)")
        print("  plot        Waveform plot: vbridge sim plot DIR SIGNAL -o wave.html")
        print("\nother:")
        print("  license     Check Spectre license")
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
    if sub == "plot":
        from vbridge.plot_cmd import run_plot
        out = args.output
        fmt = "png" if out.endswith(".png") else "html"
        return run_plot(args.dir, args.signal, out,
                        from_time=args.from_time, to_time=args.to_time, fmt=fmt)
    if sub == "measure":
        from vbridge.sim_cmd import run_measure
        return run_measure(args.dir, args.type, args.signal,
                           from_time=args.from_time, to_time=args.to_time)
    if sub == "license":
        from vbridge.sim_cmd import run_license
        return run_license(profile=profile)
    print(f"unknown sim subcommand: {sub}")
    return 1


def _handle_lib(args, profile: str | None) -> int:
    sub = getattr(args, "lib_command", None)
    if not sub:
        print("usage: vbridge lib {list,create,cells,cell-info,views} ...")
        print("\nsubcommands:")
        print("  list        List libraries (--detail for paths)")
        print("  create      Create library (--path, --tech-lib)")
        print("  cells       List cells in a library (--filter, --json)")
        print("  cell-info   Show cell CDF attributes (--json)")
        print("  views       List views of a cell")
        return 1

    if sub == "list":
        from vbridge.lib_cmd import run_list
        return run_list(json_output=args.json_output,
                        detail=getattr(args, "detail", False),
                        timeout=args.timeout, profile=profile)
    if sub == "create":
        from vbridge.lib_cmd import run_create
        return run_create(args.name, args.path, tech_lib=args.tech_lib,
                          timeout=args.timeout, profile=profile)
    if sub == "cells":
        from vbridge.lib_cmd import run_cells
        return run_cells(args.lib, filter_pattern=args.filter,
                         json_output=args.json_output,
                         timeout=args.timeout, profile=profile)
    if sub == "cell-info":
        from vbridge.lib_cmd import run_cell_info
        return run_cell_info(args.lib, args.cell,
                             json_output=args.json_output,
                             timeout=args.timeout, profile=profile)
    if sub == "views":
        from vbridge.lib_cmd import run_views
        return run_views(args.lib, args.cell,
                         json_output=args.json_output,
                         timeout=args.timeout, profile=profile)
    print(f"unknown lib subcommand: {sub}")
    return 1


def _handle_maestro(args, profile: str | None) -> int:
    sub = getattr(args, "maestro_command", None)
    if not sub:
        print("usage: vbridge maestro {run,signals,export,var} ...")
        print("\nsubcommands:")
        print("  run         Run Maestro simulation")
        print("  signals     List available signals (--history H, --analysis A)")
        print("  export      Export waveform to file (-o FILE, --history H)")
        print("  var         Get/set design variables (NAME [VALUE])")
        return 1

    if sub == "run":
        from vbridge.maestro_cmd import run_sim
        return run_sim(args.lib, args.cell,
                       timeout=args.timeout, profile=profile)
    if sub == "signals":
        from vbridge.maestro_cmd import run_signals
        return run_signals(args.lib, args.cell,
                           history=args.history, analysis=args.analysis,
                           timeout=args.timeout, profile=profile)
    if sub == "export":
        from vbridge.maestro_cmd import run_export
        return run_export(args.lib, args.cell, args.signal, args.output,
                          history=args.history, analysis=args.analysis,
                          timeout=args.timeout, profile=profile)
    if sub == "var":
        from vbridge.maestro_cmd import run_var
        return run_var(args.lib, args.cell,
                       name=args.name, value=args.value,
                       timeout=args.timeout, profile=profile)
    print(f"unknown maestro subcommand: {sub}")
    return 1


def _handle_layout(args, profile: str | None) -> int:
    sub = getattr(args, "layout_command", None)
    if not sub:
        print("usage: vbridge layout {read,export-gds,batch,layers} ...")
        print("\nsubcommands:")
        print("  read        Read layout summary (instances, shapes, bbox)")
        print("  export-gds  Export to GDS-II file (-o FILE)")
        print("  batch       Batch layout ops from JSON stdin (--dry-run)")
        print("  layers      List used layer/purpose pairs")
        return 1

    if sub == "read":
        from vbridge.layout_cmd import run_read
        return run_read(args.lib, args.cell,
                        json_output=args.json_output,
                        timeout=args.timeout, profile=profile)
    if sub == "export-gds":
        from vbridge.layout_cmd import run_export_gds
        return run_export_gds(args.lib, args.cell, args.output,
                              timeout=args.timeout, profile=profile)
    if sub == "batch":
        from vbridge.layout_cmd import run_batch
        return run_batch(args.lib, args.cell, sys.stdin.read(),
                         dry_run=getattr(args, "dry_run", False),
                         timeout=args.timeout, profile=profile)
    if sub == "layers":
        from vbridge.layout_cmd import run_layers
        return run_layers(args.lib, args.cell,
                          timeout=args.timeout, profile=profile)
    print(f"unknown layout subcommand: {sub}")
    return 1


def _handle_symbol(args, profile: str | None) -> int:
    sub = getattr(args, "symbol_command", None)
    if not sub:
        print("usage: vbridge symbol {generate} ...")
        print("\nsubcommands:")
        print("  generate    Auto-generate symbol from schematic pins (--overwrite)")
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

    if command in ("skill-find", "skill-info", "doc-search"):
        _ensure_cadence_in_path()

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

    if command == "maestro":
        return _handle_maestro(args, profile)

    if command == "layout":
        return _handle_layout(args, profile)

    if command == "cleanup":
        from vbridge.cleanup_cmd import run_cleanup
        return run_cleanup(search_dir=getattr(args, "dir", None),
                           dry_run=getattr(args, "dry_run", False))

    if command == "daemon":
        return _run_daemon(args.host, args.port)

    parser.print_help()
    return 1
