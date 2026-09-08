"""vbridge sch — schematic operations via the bridge daemon."""

from __future__ import annotations

import json
import sys
from typing import Any

from virtuoso_bridge.virtuoso.schematic.ops import (
    schematic_create_inst_by_master_name,
    schematic_create_wire_between_instance_terms,
    schematic_label_instance_term,
    schematic_create_pin,
    schematic_create_wire,
    schematic_create_wire_label,
)
_REQUIRED = {
    "add-inst": ["lib", "cell"],
    "wire": ["from_inst", "from_term", "to_inst", "to_term"],
    "label-term": ["inst", "term", "net"],
    "label-mos": ["inst"],
    "add-pin": ["name"],
    "add-wire": ["points"],
    "add-label": ["text"],
    "set-param": ["inst", "params"],
}


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
            op["lib"], op["cell"], "schematic",
            op.get("name", ""),
            op.get("x", 0), op.get("y", 0),
            op.get("orientation", "R0"),
        ))
    elif kind == "wire":
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
            op.get("orientation", "R0"),
            direction=op.get("dir", "inputOutput"),
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
    elif kind == "set-param":
        pass


def run_batch(lib: str, cell: str, ops_json: str, *,
              view: str = "schematic", timeout: int = 120,
              profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    try:
        ops = json.loads(ops_json)
    except json.JSONDecodeError as e:
        print(f"[sch] error: invalid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(ops, list):
        print("[sch] error: JSON must be an array of operations", file=sys.stderr)
        return 1

    edit_ops = [op for op in ops if op.get("op") != "set-param"]
    param_ops = [op for op in ops if op.get("op") == "set-param"]

    client = get_client(profile=profile, timeout=timeout)
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
        return 0
    except Exception as e:
        print(f"[sch] error: {e}", file=sys.stderr)
        return 1


def run_create(lib: str, cell: str, *, view: str = "schematic",
               timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    client = get_client(profile=profile, timeout=timeout)
    client.schematic.open(lib, cell, view=view, mode="w", timeout=timeout)
    print(f"[sch] opened {lib}/{cell}/{view}")
    return 0


def run_save(*, timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    client = get_client(profile=profile, timeout=timeout)
    client.schematic.check(timeout=timeout)
    client.schematic.save(timeout=timeout)
    print("[sch] saved")
    return 0


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
            param_str = " ".join(f"{k}={v}" for k, v in params.items()) if params else ""
            print(f"  {inst.get('name','?'):<10s} {inst.get('cell','?'):<15s} {param_str}")
        print(f"\nPins ({len(pins)}):")
        for name, info in pins.items():
            print(f"  {name:<15s} {info.get('direction','?')}")
        print(f"\nNets: {len(nets)}")
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
