"""Validate vbridge imports against upstream virtuoso-bridge-lite.

Run after submodule updates to catch API breakage early:
    python3.11 tests/test_imports.py
"""

from __future__ import annotations

import sys
import importlib


def _check(label: str, fn):
    try:
        fn()
        print(f"  [OK] {label}")
        return True
    except Exception as e:
        print(f"  [FAIL] {label}: {e}")
        return False


def test_upstream_cli_symbols():
    """Verify all symbols we import from upstream cli.py still exist."""
    from virtuoso_bridge import cli
    symbols = [
        "build_parser", "main",
        "_CLI_PROFILE", "_SCREENSHOT_TARGET", "_SCREENSHOT_OUTPUT",
        "_SNAPSHOT_OPTS", "_EXPORT_VISIO_OPTS", "_make_stdio_safe",
        "cli_init", "cli_start", "cli_stop", "cli_restart",
        "cli_status", "cli_license", "cli_load", "cli_eval",
        "cli_dismiss_dialog", "cli_dismiss_window", "cli_list_windows",
        "cli_screenshot", "cli_windows", "cli_snapshot", "cli_export_visio",
        "cli_bootstrap", "cli_profile", "cli_find", "cli_skill_info",
        "cli_doc_search",
    ]
    missing = [s for s in symbols if not hasattr(cli, s)]
    assert not missing, f"Missing upstream symbols: {missing}"


def test_upstream_tunnel_symbols():
    """Verify tunnel.py symbols used by auto_start and env_helpers."""
    from virtuoso_bridge.transport.tunnel import (
        SSHClient, _is_localhost, _find_ramic_bridge_daemon,
        _generate_virtuoso_setup_il,
    )
    assert callable(SSHClient.read_state)
    assert callable(SSHClient.from_env)
    assert callable(_is_localhost)
    assert callable(_find_ramic_bridge_daemon)
    assert callable(_generate_virtuoso_setup_il)


def test_upstream_env_symbols():
    """Verify env.py symbols used by auto_start and env_helpers."""
    from virtuoso_bridge.env import (
        set_runtime_env_file, load_vb_env, default_user_env_path,
    )
    assert callable(set_runtime_env_file)
    assert callable(load_vb_env)
    assert callable(default_user_env_path)


def test_upstream_schematic_ops():
    """Verify schematic ops functions used by sch_cmd."""
    from virtuoso_bridge.virtuoso.schematic.ops import (
        schematic_create_inst_by_master_name,
        schematic_create_wire_between_instance_terms,
        schematic_label_instance_term,
        schematic_create_pin,
        schematic_create_wire,
        schematic_create_wire_label,
    )
    for fn in [schematic_create_inst_by_master_name,
               schematic_create_wire_between_instance_terms,
               schematic_label_instance_term,
               schematic_create_pin,
               schematic_create_wire,
               schematic_create_wire_label]:
        assert callable(fn), f"{fn.__name__} not callable"


def test_upstream_spectre_apis():
    """Verify Spectre APIs used by sim_cmd."""
    from virtuoso_bridge.spectre.runner import SpectreSimulator, spectre_mode_args
    from virtuoso_bridge.spectre.psf import read_psf_ascii
    assert callable(SpectreSimulator.from_env)
    assert callable(SpectreSimulator.run_simulation)
    assert callable(spectre_mode_args)
    assert callable(read_psf_ascii)


def test_upstream_domain_ops():
    """Verify domain Ops classes used by lib_cmd and symbol_cmd."""
    from virtuoso_bridge.virtuoso.library import LibraryOps
    from virtuoso_bridge.virtuoso.symbol import SymbolOps
    assert callable(LibraryOps.list)
    assert callable(LibraryOps.create)
    assert callable(SymbolOps.generate_from_schematic)


def test_upstream_runtime_paths():
    """Verify runtime_paths used by auto_start."""
    from virtuoso_bridge.runtime_paths import log_dir
    assert callable(log_dir)


def test_upstream_profile():
    """Verify profile module used by cli.py."""
    from virtuoso_bridge.profile import resolve_profile
    assert callable(resolve_profile)


def test_vbridge_parser_builds():
    """Verify the full vbridge parser builds without conflicts."""
    from vbridge.cli import build_parser
    parser = build_parser()
    for action in parser._subparsers._actions:
        if hasattr(action, "_name_parser_map"):
            cmds = sorted(action._name_parser_map.keys())
            assert len(cmds) >= 27, f"Expected 27+ commands, got {len(cmds)}: {cmds}"
            for expected in ["auto-start", "exec", "sim", "lib", "symbol",
                             "sch", "eval", "load", "status"]:
                assert expected in cmds, f"Missing command: {expected}"
            return
    raise AssertionError("No subparsers found in parser")


def test_vbridge_all_modules_import():
    """Verify all vbridge modules import cleanly."""
    modules = [
        "vbridge.cli", "vbridge.auto_start", "vbridge.exec_cmd",
        "vbridge.sch_cmd", "vbridge.sim_cmd", "vbridge.lib_cmd",
        "vbridge.symbol_cmd", "vbridge.env_helpers",
        "vbridge._frozen_patches", "vbridge._display",
    ]
    for mod in modules:
        importlib.import_module(mod)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    print(f"Running {len(tests)} validation tests...\n")
    for test in tests:
        ok = _check(test.__name__, test)
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"\n{'=' * 40}")
    print(f"Passed: {passed}, Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
