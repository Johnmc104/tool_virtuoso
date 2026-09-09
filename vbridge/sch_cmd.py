"""vbridge sch — schematic operations via the bridge daemon."""

from __future__ import annotations

import json
import sys
from typing import Any

from virtuoso_bridge.virtuoso.ops import escape_skill_string
from virtuoso_bridge.virtuoso.schematic.ops import (
    schematic_create_inst_by_master_name,
    schematic_create_wire_between_instance_terms,
    schematic_label_instance_term,
    schematic_create_pin,
    schematic_create_wire,
    schematic_create_wire_label,
)
_BRIEF_PARAMS_MOS = ["w", "l", "wf", "nf", "fingers", "m", "simM"]
_BRIEF_PARAMS_SRC = ["vdc", "idc", "srcType", "freq", "va", "ia", "v1", "v2", "ampl"]
_BRIEF_PARAMS_PASSIVE = ["r", "c", "l", "model", "m"]
_BRIEF_PARAMS_ALL = set(_BRIEF_PARAMS_MOS + _BRIEF_PARAMS_SRC + _BRIEF_PARAMS_PASSIVE)


def _format_params_brief(params: dict) -> str:
    """Format instance params for text output: show only key params."""
    if not params:
        return ""
    brief = {k: v for k, v in params.items() if k in _BRIEF_PARAMS_ALL}
    if brief:
        return " ".join(f"{k}={v}" for k, v in brief.items())
    if len(params) <= 3:
        return " ".join(f"{k}={v}" for k, v in params.items())
    keys = list(params.keys())[:3]
    return " ".join(f"{k}={params[k]}" for k in keys) + f" (+{len(params)-3} more)"


def _snapshot_connections(client, lib: str, cell: str, timeout: int) -> dict:
    """Capture instance connections via sch read for diff."""
    try:
        data = client.schematic.read(lib, cell, include_positions=False, timeout=timeout)
        snapshot = {}
        for inst in data.get("instances", []):
            snapshot[inst["name"]] = {"cell": inst.get("cell", "?"), "terms": {}}
        for net_name, info in data.get("nets", {}).items():
            for conn in info.get("connections", []):
                parts = conn.split(".")
                if len(parts) == 2:
                    inst_name, term = parts
                    if inst_name in snapshot:
                        snapshot[inst_name]["terms"][term] = net_name
        return snapshot
    except Exception:
        return {}


def _report_diff(before: dict, after: dict):
    """Print connection changes between snapshots."""
    if not before or not after:
        return
    changes = []
    for name in sorted(set(list(before.keys()) + list(after.keys()))):
        if name not in before:
            changes.append(f"  + {name} (added)")
        elif name not in after:
            changes.append(f"  - {name} (removed)")
        else:
            bt, at = before[name]["terms"], after[name]["terms"]
            for term in sorted(set(list(bt.keys()) + list(at.keys()))):
                bv, av = bt.get(term, "?"), at.get(term, "?")
                if bv != av:
                    changes.append(f"  ~ {name}.{term}: {bv} → {av}")
    if changes:
        print(f"[sch] changes detected ({len(changes)}):")
        for c in changes[:20]:
            print(c)
        if len(changes) > 20:
            print(f"  ... and {len(changes)-20} more")


_REQUIRED = {
    "add-inst": ["lib", "cell"],
    "delete-inst": ["inst"],
    "move-inst": ["inst"],
    "copy-inst": ["inst", "name"],
    "connect": ["from_inst", "from_term", "to_inst", "to_term"],
    "label-term": ["inst", "term", "net"],
    "label-mos": ["inst"],
    "set-param": ["inst", "params"],
    "add-pin": ["name"],
    "add-wire": ["points"],
    "add-label": ["text"],
}


def _get_orientation(op: dict) -> str | None:
    """Get orientation from op."""
    return op.get("orientation")


def _dispatch_op(sch: Any, op: dict) -> None:
    kind = op.get("op", "")
    required = _REQUIRED.get(kind)
    if required is None:
        raise ValueError(f"unknown op: {kind!r}")
    missing = [k for k in required if k not in op]
    if missing:
        raise ValueError(f"op {kind!r} missing required fields: {missing}")

    if kind == "add-inst":
        sch.add(schematic_create_inst_by_master_name(
            op["lib"], op["cell"], op.get("view", "symbol"),
            op.get("name", ""),
            op.get("x", 0), op.get("y", 0),
            _get_orientation(op) or "R0",
        ))
    elif kind == "connect":
        sch.add(schematic_create_wire_between_instance_terms(
            op["from_inst"], op["from_term"],
            op["to_inst"], op["to_term"],
        ))
    elif kind == "label-term":
        sch.add(schematic_label_instance_term(
            op["inst"], op["term"], op["net"],
        ))
    elif kind == "label-mos":
        sch.add_net_label_to_transistor(
            op["inst"],
            op.get("drain"), op.get("gate"),
            op.get("source"), op.get("body"),
        )
    elif kind == "add-pin":
        sch.add(schematic_create_pin(
            op["name"],
            op.get("x", 0), op.get("y", 0),
            _get_orientation(op) or "R0",
            direction=op.get("direction", "inputOutput"),
        ))
    elif kind == "add-wire":
        points = [(p[0], p[1]) for p in op["points"]]
        sch.add(schematic_create_wire(points))
    elif kind == "add-label":
        sch.add(schematic_create_wire_label(
            op.get("x", 0), op.get("y", 0),
            op["text"],
            justification="lowerLeft",
            rotation="R0",
        ))
    elif kind == "delete-inst":
        einst = escape_skill_string(op["inst"])
        sch.add(
            f'let((rbInst) rbInst = car(setof(i cv~>instances i~>name == "{einst}")) '
            f'unless(rbInst error("instance not found: {einst}")) '
            f'dbDeleteObject(rbInst))'
        )
    elif kind == "move-inst":
        einst = escape_skill_string(op["inst"])
        x = float(op.get("x", 0))
        y = float(op.get("y", 0))
        orient = _get_orientation(op)
        orient_skill = f' rbInst~>orient = "{escape_skill_string(orient)}"' if orient else ""
        sch.add(
            f'let((rbInst) rbInst = car(setof(i cv~>instances i~>name == "{einst}")) '
            f'unless(rbInst error("instance not found: {einst}")) '
            f'rbInst~>xy = list({x:g} {y:g}){orient_skill})'
        )
    elif kind == "copy-inst":
        esrc = escape_skill_string(op["inst"])
        ename = escape_skill_string(op["name"])
        x = float(op.get("x", 0))
        y = float(op.get("y", 0))
        orient = _get_orientation(op) or "R0"
        sch.add(
            f'let((rbSrc rbDst) rbSrc = car(setof(i cv~>instances i~>name == "{esrc}")) '
            f'unless(rbSrc error("instance not found: {esrc}")) '
            f'rbDst = dbCreateInst(cv dbOpenCellView(rbSrc~>libName rbSrc~>cellName "symbol") '
            f'"{ename}" list({x:g} {y:g}) "{escape_skill_string(orient)}") '
            f'let((srcCdf dstCdf) srcCdf = cdfGetInstCDF(rbSrc) dstCdf = cdfGetInstCDF(rbDst) '
            f'when(srcCdf && dstCdf foreach(p srcCdf~>parameters '
            f'let((dp) dp = cdfFindParamByName(dstCdf p~>name) when(dp dp~>value = p~>value))))))'
        )
    elif kind == "set-param":
        pass


def run_batch(lib: str, cell: str, ops_json: str, *,
              view: str = "schematic", dry_run: bool = False,
              timeout: int = 120, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    try:
        ops = json.loads(ops_json)
    except json.JSONDecodeError as e:
        print(f"[sch] error: invalid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(ops, list):
        print("[sch] error: JSON must be an array of operations", file=sys.stderr)
        return 1

    if dry_run:
        for i, op in enumerate(ops):
            kind = op.get("op", "?")
            inst = op.get("inst", op.get("name", ""))
            detail = ""
            if kind == "set-param":
                detail = f" params={op.get('params', {})}"
            elif kind == "add-inst":
                detail = f" {op.get('lib','')}/{op.get('cell','')}"
            elif kind in ("label-mos", "label-term"):
                detail = f" {', '.join(f'{k}={v}' for k, v in op.items() if k not in ('op', 'inst'))}"
            print(f"  #{i}: {kind} {inst}{detail}")
        print(f"[sch] dry-run: {len(ops)} ops would be applied to {lib}/{cell}/{view}")
        return 0

    edit_ops = [op for op in ops if op.get("op") != "set-param"]
    param_ops = [op for op in ops if op.get("op") == "set-param"]

    client = get_client(profile=profile, timeout=timeout)

    before = _snapshot_connections(client, lib, cell, timeout)

    try:
        if edit_ops:
            with client.schematic.edit(lib, cell, view=view, timeout=timeout) as sch:
                for i, op in enumerate(edit_ops):
                    try:
                        _dispatch_op(sch, op)
                    except (KeyError, TypeError, ValueError) as e:
                        print(f"[sch] error in op #{i}: {e}", file=sys.stderr)
                        return 1

        if param_ops:
            from virtuoso_bridge.virtuoso.schematic.params import _run_batched_param_update
            for op in param_ops:
                params = op.get("params", {})
                if not isinstance(params, dict) or not params:
                    print(f"[sch] error: set-param 'params' must be a non-empty dict",
                          file=sys.stderr)
                    return 1
                _run_batched_param_update(client, lib, cell, op["inst"], params)

        print(f"[sch] OK: {len(ops)} ops applied to {lib}/{cell}/{view}")

        after = _snapshot_connections(client, lib, cell, timeout)
        _report_diff(before, after)

        return 0
    except Exception as e:
        print(f"[sch] error: {e}", file=sys.stderr)
        return 1


def run_create(lib: str, cell: str, *, view: str = "schematic", view_type: str = "",
               force: bool = False,
               timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output
    client = get_client(profile=profile, timeout=timeout)
    if not force:
        check = client.execute_skill(
            f'ddGetObj("{escape_skill_string(lib)}" "{escape_skill_string(cell)}" '
            f'"{escape_skill_string(view)}")', timeout=timeout)
        exists = decode_skill_output(check.output).strip() not in ("nil", "")
        if exists:
            print(f"[sch] error: {lib}/{cell}/{view} already exists. Use --force to overwrite.",
                  file=sys.stderr)
            return 1
    vt = view_type or {"schematic": "schematic", "layout": "maskLayout"}.get(view, "schematic")
    skill = (
        f'let((cv) '
        f'cv = dbOpenCellViewByType("{escape_skill_string(lib)}" '
        f'"{escape_skill_string(cell)}" "{escape_skill_string(view)}" '
        f'"{escape_skill_string(vt)}" "w") '
        f'when(cv dbSave(cv)) '
        f'if(cv "created" "failed"))'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[sch] error: {r.errors[0]}", file=sys.stderr)
        return 1
    print(f"[sch] Created {lib}/{cell}/{view}")
    return 0


def run_save(*, timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    client = get_client(profile=profile, timeout=timeout)
    skill = (
        'let((cv ok) '
        'cv = geGetEditCellView() '
        'if(cv '
        'then progn(schCheck(cv) dbSave(cv) ok = t) '
        'else ok = nil) '
        'if(ok "saved" "no cellview open"))'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[sch] error: {r.errors[0]}", file=sys.stderr)
        return 1
    from virtuoso_bridge import decode_skill_output
    result = decode_skill_output(r.output).strip().strip('"')
    print(f"[sch] {result}")
    return 0 if result == "saved" else 1


def run_list_instances(lib: str, cell: str, *, view: str = "schematic",
                       timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge.virtuoso.schematic.reader import read_schematic

    client = get_client(profile=profile, timeout=timeout)
    data = read_schematic(client, lib, cell, include_positions=True, timeout=timeout)
    instances = data.get("instances", [])
    for inst in instances:
        name = inst.get("name", "?")
        cell_name = inst.get("cell", "?")
        xy = inst.get("xy", [0, 0])
        print(f"  {name:<8s}  {cell_name:<15s}  ({xy[0]:.2f}, {xy[1]:.2f})")
    print(f"Total: {len(instances)} instances")
    return 0


def run_read(lib: str, cell: str, *, json_output: bool = False,
             timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    client = get_client(profile=profile, timeout=timeout)
    data = client.schematic.read(lib, cell, include_positions=True, timeout=timeout)

    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        instances = data.get("instances", [])
        pins = data.get("pins", {})
        nets = data.get("nets", {})
        print(f"Schematic: {lib}/{cell}")
        print(f"\nInstances ({len(instances)}):")
        for inst in instances:
            params = inst.get("params", {})
            param_str = _format_params_brief(params) if params else ""
            print(f"  {inst.get('name','?'):<10s} {inst.get('cell','?'):<15s} {param_str}")
        print(f"\nPins ({len(pins)}):")
        for name, info in pins.items():
            print(f"  {name:<15s} {info.get('direction','?')}")
        if nets:
            print(f"\nNets ({len(nets)}):")
            for net_name, net_info in sorted(nets.items()):
                conns = net_info.get("connections", [])
                conns_str = ", ".join(conns[:5])
                if len(conns) > 5:
                    conns_str += f", ... ({len(conns)} total)"
                print(f"  {net_name:<12s} {conns_str}")
        else:
            print(f"\nNets: 0")
    return 0


def run_param(lib: str, cell: str, inst: str, param: str, value: str, *,
              view: str = "schematic", timeout: int = 30,
              profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge.virtuoso.schematic.params import _run_batched_param_update

    client = get_client(profile=profile, timeout=timeout)
    try:
        applied = _run_batched_param_update(client, lib, cell, inst, {param: value})
        print(f"[sch] Set {inst}.{param} = {value} (with CDF callbacks)")
        return 0
    except Exception as e:
        print(f"[sch] error: {e}", file=sys.stderr)
        return 1


def run_netlist(lib: str, cell: str, output_dir: str, *,
                view: str = "schematic", simulator: str = "spectre",
                standalone: bool = False, section: str = "tt_lib",
                timeout: int = 120, profile: str | None = None) -> int:
    from pathlib import Path
    from vbridge.env_helpers import get_client

    client = get_client(profile=profile, timeout=timeout)
    out = Path(output_dir)
    try:
        result = client.schematic.export_netlist(
            lib, cell, out, view=view, simulator=simulator, timeout=timeout,
        )
        input_file = getattr(result, "input_file", None) or (out / "input.scs")
        print(f"[sch] Netlist exported: {input_file}")

        if standalone:
            model_path = _detect_pdk_model(client, lib, cell, timeout=timeout)
            if model_path:
                _make_standalone(Path(input_file), model_path, section)
                print(f"[sch] Standalone: {model_path} section={section}")
            else:
                print("[sch] warning: could not auto-detect PDK model path", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"[sch] error: {e}", file=sys.stderr)
        return 1


def _detect_pdk_model(client, lib: str, cell: str, *, timeout: int = 30) -> str | None:
    """Auto-detect PDK model file from device instances → cds.lib path."""
    from virtuoso_bridge import decode_skill_output
    from pathlib import Path
    import re

    skill = (
        f'let((cv inst) '
        f'cv = dbOpenCellViewByType("{escape_skill_string(lib)}" '
        f'"{escape_skill_string(cell)}" "schematic" "" "r") '
        f'inst = car(setof(i cv~>instances '
        f'rexMatchp("nch_" i~>cellName) || rexMatchp("pch_" i~>cellName) || rexMatchp("g45" i~>cellName))) '
        f'when(inst inst~>libName))'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors or not r.output or r.output.strip('"') == "nil":
        return None

    pdk_lib = decode_skill_output(r.output).strip().strip('"')
    cds_name = re.sub(r'\.', '#2e', pdk_lib)

    for cds_lib_path in _find_cds_lib_files():
        try:
            with open(cds_lib_path, 'r') as f:
                for line in f:
                    if line.strip().startswith(f'DEFINE {cds_name} '):
                        lib_path = line.strip().split(None, 2)[2]
                        parent = str(Path(lib_path).parent)
                        model = f"{parent}/models/spectre/toplevel.scs"
                        if Path(model).is_file():
                            return model
        except (OSError, IndexError):
            continue
    return None


def _find_cds_lib_files() -> list[str]:
    """Search for cds.lib from cwd upward."""
    from pathlib import Path
    import os
    result = []
    p = Path(os.getcwd())
    while p != p.parent:
        f = p / "cds.lib"
        if f.is_file():
            result.append(str(f))
        p = p.parent
    return result


def _make_standalone(netlist: 'Path', model_path: str, section: str) -> None:
    """Replace ade_e.scs with PDK model include and add default analysis."""
    text = netlist.read_text()
    text = text.replace(
        'include "ade_e.scs"',
        f'include "{model_path}" section={section}'
    )
    if 'tran ' not in text and 'dc ' not in text and 'ac ' not in text:
        text += "\ntran tran stop=2u errpreset=moderate\ndcOp dc\n"
    netlist.write_text(text)
