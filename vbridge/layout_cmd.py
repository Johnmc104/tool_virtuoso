"""vbridge layout — layout operations."""

from __future__ import annotations

import json
import sys

from virtuoso_bridge.virtuoso.ops import escape_skill_string


def run_read(lib: str, cell: str, *, json_output: bool = False,
             timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    client = get_client(profile=profile, timeout=timeout)
    elib = escape_skill_string(lib)
    ecell = escape_skill_string(cell)

    skill = (
        f'let((cv insts shapes bbox area) '
        f'cv = dbOpenCellViewByType("{elib}" "{ecell}" "layout" "" "r") '
        f'unless(cv error("layout view not found")) '
        f'insts = length(cv~>instances) '
        f'shapes = length(cv~>shapes) '
        f'bbox = cv~>bBox '
        f'list(insts shapes bbox))'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[layout] error: {r.errors[0]}", file=sys.stderr)
        return 1

    from virtuoso_bridge import decode_skill_output
    raw = decode_skill_output(r.output)

    if json_output:
        print(raw)
    else:
        print(f"{lib}/{cell}/layout")
        print(f"  {raw}")
    return 0


def run_export_gds(lib: str, cell: str, output: str, *,
                   timeout: int = 120, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from pathlib import Path

    client = get_client(profile=profile, timeout=timeout)
    try:
        result = client.layout.export_gds(
            lib, cell, output_path=Path(output), timeout=timeout,
        )
        if result.ok:
            print(f"[layout] GDS exported: {output}")
            return 0
        else:
            print(f"[layout] error: {result.reason}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"[layout] error: {e}", file=sys.stderr)
        return 1


def run_batch(lib: str, cell: str, ops_json: str, *,
              dry_run: bool = False,
              timeout: int = 120, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge.virtuoso.layout.ops import (
        layout_create_rect,
        layout_create_path,
        layout_create_label,
        layout_create_via_by_name,
        layout_create_polygon,
        layout_fit_view,
    )

    try:
        ops = json.loads(ops_json)
    except json.JSONDecodeError as e:
        print(f"[layout] error: invalid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(ops, list):
        print("[layout] error: JSON must be an array", file=sys.stderr)
        return 1

    if dry_run:
        for i, op in enumerate(ops):
            kind = op.get("op", "?")
            layer = op.get("layer", "")
            print(f"  #{i}: {kind} {layer} {op.get('text', op.get('via', ''))}")
        print(f"[layout] dry-run: {len(ops)} ops would be applied")
        return 0

    client = get_client(profile=profile, timeout=timeout)
    try:
        with client.layout.modify(lib, cell, timeout=timeout) as lay:
            for i, op in enumerate(ops):
                kind = op.get("op", "")
                try:
                    if kind == "add-rect":
                        lay.add(layout_create_rect(
                            op["layer"], op.get("purpose", "drawing"),
                            op["x1"], op["y1"], op["x2"], op["y2"]))
                    elif kind == "add-path":
                        points = [(p[0], p[1]) for p in op["points"]]
                        lay.add(layout_create_path(
                            op["layer"], op.get("purpose", "drawing"),
                            points, op["width"]))
                    elif kind == "add-label":
                        lay.add(layout_create_label(
                            op["layer"], op.get("purpose", "drawing"),
                            op.get("x", 0), op.get("y", 0), op["text"],
                            op.get("justification", "centerCenter"),
                            op.get("rotation", "R0"),
                            op.get("font", "roman"),
                            op.get("height", 0.1)))
                    elif kind == "add-via":
                        lay.add(layout_create_via_by_name(
                            op["via"], op.get("x", 0), op.get("y", 0)))
                    elif kind == "add-polygon":
                        points = [(p[0], p[1]) for p in op["points"]]
                        lay.add(layout_create_polygon(
                            op["layer"], op.get("purpose", "drawing"), points))
                    elif kind == "fit-view":
                        lay.add(layout_fit_view())
                    else:
                        print(f"[layout] error in op #{i}: unknown op '{kind}'", file=sys.stderr)
                        return 1
                except (KeyError, TypeError) as e:
                    print(f"[layout] error in op #{i}: {e}", file=sys.stderr)
                    return 1

        print(f"[layout] OK: {len(ops)} ops applied to {lib}/{cell}/layout")
        return 0
    except Exception as e:
        print(f"[layout] error: {e}", file=sys.stderr)
        return 1


def run_layers(lib: str, cell: str, *,
               timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output

    client = get_client(profile=profile, timeout=timeout)
    elib = escape_skill_string(lib)
    ecell = escape_skill_string(cell)

    skill = (
        f'let((cv result) '
        f'cv = dbOpenCellViewByType("{elib}" "{ecell}" "layout" "" "r") '
        f'unless(cv error("layout view not found")) '
        f'result = nil '
        f'foreach(shape cv~>shapes '
        f'  let((lpp) lpp = list(shape~>layerName shape~>purpose) '
        f'    unless(member(lpp result) result = cons(lpp result)))) '
        f'result)'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[layout] error: {r.errors[0]}", file=sys.stderr)
        return 1

    raw = decode_skill_output(r.output)
    import re
    layers = re.findall(r'\("(\w+)"\s+"(\w+)"\)', raw)
    for layer, purpose in layers:
        print(f"  {layer}:{purpose}")
    print(f"Total: {len(layers)} layer/purpose pairs")
    return 0
