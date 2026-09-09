"""vbridge maestro — Maestro simulation and waveform export."""

from __future__ import annotations

import json
import sys

from virtuoso_bridge.virtuoso.ops import escape_skill_string


def run_sim(lib: str, cell: str, *, view: str = "maestro",
            timeout: int = 600, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    client = get_client(profile=profile, timeout=timeout)
    skill = (
        f'let((s) '
        f's = maeOpenSetup("{escape_skill_string(lib)}" "{escape_skill_string(cell)}" '
        f'"{escape_skill_string(view)}" ?application "Assembler" ?mode "a") '
        f'maeRunSimulation() '
        f'let((rd) rd = asiGetResultsDir(asiGetCurrentSession()) '
        f'list(s rd)))'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[maestro] error: {r.errors[0]}", file=sys.stderr)
        return 1
    from virtuoso_bridge import decode_skill_output
    raw = decode_skill_output(r.output)
    print(f"[maestro] Simulation complete: {raw}")
    return 0


def run_signals(lib: str, cell: str, *, history: str | None = None,
                analysis: str = "tran", timeout: int = 60,
                profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output

    client = get_client(profile=profile, timeout=timeout)

    psf_dir = _resolve_psf_dir(client, lib, cell, history=history, timeout=timeout)
    if not psf_dir:
        print("[maestro] error: cannot find PSF results directory", file=sys.stderr)
        return 1

    skill = (
        f'progn('
        f'openResults("{escape_skill_string(psf_dir)}") '
        f'selectResults("{escape_skill_string(analysis)}") '
        f'outputs())'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[maestro] error: {r.errors[0]}", file=sys.stderr)
        return 1

    raw = decode_skill_output(r.output)
    signals = _parse_skill_list(raw)
    for s in signals:
        print(f"  {s}")
    print(f"Total: {len(signals)} signals")
    return 0


def run_export(lib: str, cell: str, signal: str, output: str, *,
               history: str | None = None, analysis: str = "tran",
               timeout: int = 120, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output
    from pathlib import Path

    client = get_client(profile=profile, timeout=timeout)

    psf_dir = _resolve_psf_dir(client, lib, cell, history=history, timeout=timeout)
    if not psf_dir:
        print("[maestro] error: cannot find PSF results directory", file=sys.stderr)
        return 1

    out_path = str(Path(output).resolve())
    esig = escape_skill_string(signal)
    if not signal.startswith("/"):
        esig = "/" + esig

    skill = (
        f'progn('
        f'openResults("{escape_skill_string(psf_dir)}") '
        f'selectResults("{escape_skill_string(analysis)}") '
        f'let((w) '
        f'w = v("{esig}") '
        f'if(w progn('
        f'ocnPrint(w ?output "{escape_skill_string(out_path)}" '
        f'?numberNotation (quote none) ?numSpaces 1) '
        f'"exported") '
        f'"signal not found")))'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[maestro] error: {r.errors[0]}", file=sys.stderr)
        return 1

    from virtuoso_bridge import decode_skill_output
    result = decode_skill_output(r.output).strip().strip('"')
    if result == "exported":
        lines = 0
        try:
            with open(out_path) as f:
                lines = sum(1 for _ in f)
        except OSError:
            pass
        print(f"[maestro] Exported {signal} → {out_path} ({lines} lines)")
        return 0
    else:
        print(f"[maestro] error: signal '{signal}' not found in {analysis} results", file=sys.stderr)
        return 1


def _resolve_psf_dir(client, lib: str, cell: str, *,
                     history: str | None = None, timeout: int = 30) -> str | None:
    """Find the PSF results directory for a Maestro history.

    Maestro stores results in a nested structure:
      ~/simulation/<lib>/<cell>/maestro/results/maestro/<history>/
        1/<test>/psf/          ← actual PSF data (tran.tran.tran etc.)
        psf/<test>/psf/        ← symlinks or copies
        psf/<test>/netlist/    ← generated netlists
    """
    import os

    base = os.path.expanduser(f"~/simulation/{lib}/{cell}/maestro/results/maestro")
    if not os.path.isdir(base):
        return None

    if history:
        candidates = [history]
    else:
        entries = sorted(os.listdir(base), reverse=True)
        candidates = [e for e in entries
                      if os.path.isdir(os.path.join(base, e))
                      and not e.endswith(".zip")
                      and not e.startswith(".")]

    for h in candidates:
        hist_dir = os.path.join(base, h)
        if not os.path.isdir(hist_dir):
            continue
        for root, dirs, files in os.walk(hist_dir):
            if root.endswith("/psf") and any(f.startswith("tran.") or f.startswith("dc") for f in files):
                return root
    return None


def run_var(lib: str, cell: str, name: str | None = None, value: str | None = None, *,
            timeout: int = 30, profile: str | None = None) -> int:
    """Get or set Maestro design variables."""
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output

    client = get_client(profile=profile, timeout=timeout)

    elib = escape_skill_string(lib)
    ecell = escape_skill_string(cell)

    setup_skill = (
        f'maeOpenSetup("{elib}" "{ecell}" "maestro" '
        f'?application "Assembler" ?mode "{"a" if value else "r"}")'
    )
    client.execute_skill(setup_skill, timeout=timeout)

    if name and value:
        skill = f'maeSetVar("{escape_skill_string(name)}" "{escape_skill_string(value)}") "{name}={value}"'
        r = client.execute_skill(skill, timeout=timeout)
        if r.errors:
            print(f"[maestro] error: {r.errors[0]}", file=sys.stderr)
            return 1
        print(f"[maestro] Set {name} = {value}")
        return 0
    elif name:
        skill = f'maeGetVarValue("{escape_skill_string(name)}")'
        r = client.execute_skill(skill, timeout=timeout)
        if r.errors:
            print(f"[maestro] error: {r.errors[0]}", file=sys.stderr)
            return 1
        val = decode_skill_output(r.output).strip().strip('"')
        print(f"{name} = {val}")
        return 0
    else:
        skill = 'let((vars result) vars = maeGetDesignVarList() result = nil foreach(v vars result = cons(list(v maeGetVarValue(v)) result)) reverse(result))'
        r = client.execute_skill(skill, timeout=timeout)
        raw = decode_skill_output(r.output)
        if raw.strip() == "nil" or not raw.strip():
            print("(no design variables)")
        else:
            pairs = _parse_skill_pairs(raw)
            for n, v in pairs:
                print(f"  {n:<20s} {v}")
            if not pairs:
                print(f"  {raw}")
        return 0


def _parse_skill_list(raw: str) -> list[str]:
    raw = raw.strip()
    if raw == "nil":
        return []
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    return [s.strip().strip('"') for s in raw.split() if s.strip().strip('"')]


def _parse_skill_pairs(raw: str) -> list[tuple[str, str]]:
    import re
    return re.findall(r'\("([^"]*?)"\s+"([^"]*?)"\)', raw)
