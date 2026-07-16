"""vbridge sch — schematic operations via the bridge daemon."""

from __future__ import annotations

import json
import sys
from typing import Any


def _dispatch_op(sch: Any, op: dict) -> None:
    kind = op.get("op", "")
    if kind == "add-inst":
        sch.add_instance(
            op["lib"], op["cell"],
            (op.get("x", 0), op.get("y", 0)),
            orientation=op.get("orientation", "R0"),
            name=op.get("name", ""),
        )
    elif kind == "wire":
        sch.add_wire_between_instance_terms(
            op["from_inst"], op["from_term"],
            op["to_inst"], op["to_term"],
        )
    elif kind == "label-term":
        sch.add_net_label_to_instance_term(
            op["inst"], op["term"], op["net"],
        )
    elif kind == "label-mos":
        sch.add_net_label_to_transistor(
            op["inst"],
            op.get("drain"), op.get("gate"),
            op.get("source"), op.get("body"),
        )
    elif kind == "add-pin":
        sch.add_pin(
            op["name"],
            (op.get("x", 0), op.get("y", 0)),
            orientation=op.get("orientation", "R0"),
            direction=op.get("dir", "inputOutput"),
        )
    elif kind == "add-wire":
        points = [(p[0], p[1]) for p in op["points"]]
        sch.add_wire(points)
    elif kind == "add-label":
        sch.add_label(
            (op.get("x", 0), op.get("y", 0)),
            op["text"],
        )
    else:
        raise ValueError(f"unknown op: {kind!r}")


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

    client = get_client(profile=profile, timeout=timeout)
    try:
        with client.schematic.edit(lib, cell, view=view, timeout=timeout) as sch:
            for i, op in enumerate(ops):
                try:
                    _dispatch_op(sch, op)
                except (KeyError, TypeError, ValueError) as e:
                    print(f"[sch] error in op #{i}: {e}", file=sys.stderr)
                    return 1
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
    client = get_client(profile=profile, timeout=timeout)
    skill = (
        'let((cv insts buf)\n'
        f'cv = dbOpenCellViewByType("{lib}" "{cell}" "{view}")\n'
        'insts = cv~>instances\n'
        'buf = ""\n'
        'foreach(inst insts\n'
        '  buf = strcat(buf sprintf(nil "  %-8s  %-15s  (%.2f, %.2f)\\n"\n'
        '    inst~>name inst~>cellName xCoord(inst~>xy) yCoord(inst~>xy))))\n'
        'buf = strcat(buf sprintf(nil "Total: %d instances\\n" length(insts)))\n'
        'dbClose(cv)\n'
        'buf)'
    )
    result = client.execute_skill(skill, timeout=timeout)
    if result.output:
        out = result.output
        if out.startswith('"') and out.endswith('"'):
            out = out[1:-1]
        out = out.replace("\\n", "\n")
        print(out, end="")
    return 0 if result.ok else 1
