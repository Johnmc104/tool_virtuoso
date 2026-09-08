"""vbridge sim — Spectre simulation CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def run_sim(netlist: str, *, output_dir: str | None = None,
            mode: str = "default", timeout: int = 600,
            profile: str | None = None) -> int:
    from virtuoso_bridge.env import load_vb_env
    from virtuoso_bridge.spectre.runner import SpectreSimulator, spectre_mode_args

    load_vb_env()

    p = Path(netlist)
    if not p.is_file():
        print(f"[sim] error: netlist not found: {netlist}", file=sys.stderr)
        return 1

    spectre_args = spectre_mode_args(mode) if mode != "default" else None
    work = Path(output_dir) if output_dir else None

    try:
        sim = SpectreSimulator.from_env(
            spectre_args=spectre_args,
            work_dir=work,
            timeout=timeout,
            profile=profile,
        )
    except Exception as e:
        print(f"[sim] error: cannot create simulator: {e}", file=sys.stderr)
        return 1

    print(f"[sim] Running {p.name} ...", file=sys.stderr)
    result = sim.run_simulation(p)

    out = {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "signals": sorted(result.data.keys()) if result.data else [],
        "errors": list(result.errors) if result.errors else [],
        "warnings": list(result.warnings) if result.warnings else [],
        "output_dir": str(result.metadata.get("output_dir", "")),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


def run_result(raw_dir: str, *, signal: str | None = None,
               json_output: bool = False) -> int:
    from virtuoso_bridge.spectre.psf import read_psf_ascii, result_file

    d = Path(raw_dir)
    if not d.is_dir():
        print(f"[sim] error: directory not found: {raw_dir}", file=sys.stderr)
        return 1

    analysis_exts = (".ac", ".tran", ".dc", ".noise", ".stb", ".pss")
    analysis_files = [f for f in sorted(d.iterdir())
                      if f.suffix in analysis_exts and f.is_file()]

    if not analysis_files:
        psf_candidates = [f for f in sorted(d.iterdir())
                          if f.is_file() and not f.name.startswith(".")]
        if psf_candidates:
            analysis_files = psf_candidates[:5]

    if not analysis_files:
        print(f"[sim] error: no analysis files found in {raw_dir}", file=sys.stderr)
        return 1

    all_data = {}
    for af in analysis_files:
        try:
            data = read_psf_ascii(af)
            all_data[af.name] = data
        except Exception as e:
            print(f"[sim] warning: cannot parse {af.name}: {e}", file=sys.stderr)

    if not all_data:
        print("[sim] error: no parseable results found", file=sys.stderr)
        return 1

    if signal:
        for fname, data in all_data.items():
            if signal in data:
                vals = data[signal]
                if json_output:
                    if isinstance(vals, list):
                        print(json.dumps({signal: [v.real if isinstance(v, complex) and v.imag == 0 else str(v) for v in vals]}, ensure_ascii=False))
                    else:
                        print(json.dumps({signal: vals}, ensure_ascii=False))
                else:
                    print(f"{fname}: {signal} = {vals if not isinstance(vals, list) else f'[{len(vals)} points]'}")
                return 0
        print(f"[sim] error: signal '{signal}' not found", file=sys.stderr)
        available = set()
        for data in all_data.values():
            available.update(data.keys())
        print(f"  Available: {sorted(available)}", file=sys.stderr)
        return 1

    if json_output:
        summary = {}
        for fname, data in all_data.items():
            summary[fname] = {k: f"[{len(v)} points]" if isinstance(v, list) else v
                              for k, v in data.items()}
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    else:
        for fname, data in all_data.items():
            print(f"\n{fname}:")
            for k, v in data.items():
                if isinstance(v, list):
                    print(f"  {k}: [{len(v)} points]")
                else:
                    print(f"  {k}: {v}")
    return 0


def run_license(*, profile: str | None = None) -> int:
    from virtuoso_bridge.env import load_vb_env
    from virtuoso_bridge.spectre.runner import SpectreSimulator

    load_vb_env()
    try:
        sim = SpectreSimulator.from_env(profile=profile)
        info = sim.check_license()
        ok = info.get("ok", False) if isinstance(info, dict) else bool(info)
        if isinstance(info, dict):
            print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"[sim] Spectre license: {'OK' if ok else 'NOT AVAILABLE'}")
        return 0 if ok else 1
    except Exception as e:
        print(f"[sim] error: {e}", file=sys.stderr)
        return 1
