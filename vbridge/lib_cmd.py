"""vbridge lib — library management CLI commands."""

from __future__ import annotations

import json
import sys

from virtuoso_bridge.virtuoso.ops import escape_skill_string


def run_list(*, json_output: bool = False, detail: bool = False,
             timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output

    client = get_client(profile=profile, timeout=timeout)

    if detail or json_output:
        skill = (
            'let((result) result = nil '
            'foreach(lib ddGetLibList() '
            '  result = cons(list(lib~>name lib~>readPath) result)) '
            'reverse(result))'
        )
        r = client.execute_skill(skill, timeout=timeout)
        raw = decode_skill_output(r.output)
        pairs = _parse_skill_pairs(raw)

        if json_output:
            print(json.dumps([{"name": n, "path": p} for n, p in pairs],
                             ensure_ascii=False, indent=2))
        else:
            for name, path in pairs:
                print(f"  {name:<25s} {path}")
            print(f"Total: {len(pairs)} libraries")
    else:
        libs = client.library.list(timeout=timeout)
        for lib in libs:
            print(f"  {lib}")
        print(f"Total: {len(libs)} libraries")
    return 0


def run_create(name: str, path: str, *, tech_lib: str | None = None,
               timeout: int = 60, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client

    client = get_client(profile=profile, timeout=timeout)
    try:
        info = client.library.create(name, path, technology_library=tech_lib,
                                     timeout=timeout)
        print(f"[lib] Created: {info.name} at {info.path}")
        if info.technology_library:
            print(f"  tech: {info.technology_library}")
        return 0
    except Exception as e:
        print(f"[lib] error: {e}", file=sys.stderr)
        return 1


def run_cells(lib: str, *, filter_pattern: str | None = None,
              json_output: bool = False, timeout: int = 30,
              profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output

    client = get_client(profile=profile, timeout=timeout)
    elib = escape_skill_string(lib)
    skill = (
        f'let((lib result) lib = ddGetObj("{elib}") '
        f'unless(lib error("library not found: {elib}")) '
        f'result = sort(lib~>cells~>name nil) result)'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[lib] error: {r.errors[0]}", file=sys.stderr)
        return 1

    raw = decode_skill_output(r.output)
    cells = _parse_skill_list(raw)

    if filter_pattern:
        import fnmatch
        cells = [c for c in cells if fnmatch.fnmatch(c, filter_pattern)]

    if json_output:
        print(json.dumps(cells, ensure_ascii=False))
    else:
        for c in cells:
            print(f"  {c}")
        print(f"Total: {len(cells)} cells")
    return 0


def run_cell_info(lib: str, cell: str, *, json_output: bool = False,
                  timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output

    client = get_client(profile=profile, timeout=timeout)
    elib = escape_skill_string(lib)
    ecell = escape_skill_string(cell)

    skill = (
        f'let((obj cdf result views desc) '
        f'obj = ddGetObj("{elib}" "{ecell}") '
        f'unless(obj error("cell not found")) '
        f'views = obj~>views~>name '
        f'cdf = cdfGetCellCDF(obj) '
        f'desc = "" '
        f'result = nil '
        f'when(cdf '
        f'  let((dp) dp = cdfFindParamByName(cdf "description") when(dp desc = dp~>defValue)) '
        f'  foreach(p cdf~>parameters '
        f'    when(member(p~>name list("model" "w" "wf" "l" "fingers" "nf" "m" "simM" '
        f'         "r" "c" "vdc" "idc" "freq" "ad" "as" "pd" "ps" "nrd" "nrs")) '
        f'      result = cons(list(p~>name p~>defValue) result)))) '
        f'list(desc views reverse(result)))'
    )
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[lib] error: {r.errors[0]}", file=sys.stderr)
        return 1

    raw = decode_skill_output(r.output)

    if json_output:
        desc, views, params = _parse_cell_info(raw)
        print(json.dumps({"lib": lib, "cell": cell, "description": desc,
                          "views": views, "params": {k: v for k, v in params}},
                         ensure_ascii=False, indent=2))
    else:
        desc, views, params = _parse_cell_info(raw)
        print(f"{cell}", end="")
        if desc and desc.strip():
            print(f" — {desc.strip()}")
        else:
            print()
        if views:
            print(f"  Views:    {', '.join(views)}")
        if params:
            print(f"  Defaults: {' '.join(f'{k}={v}' for k, v in params if v)}")
    return 0


def run_views(lib: str, cell: str, *, json_output: bool = False,
              timeout: int = 30, profile: str | None = None) -> int:
    from vbridge.env_helpers import get_client
    from virtuoso_bridge import decode_skill_output

    client = get_client(profile=profile, timeout=timeout)
    elib = escape_skill_string(lib)
    ecell = escape_skill_string(cell)
    skill = f'ddGetObj("{elib}" "{ecell}")~>views~>name'
    r = client.execute_skill(skill, timeout=timeout)
    if r.errors:
        print(f"[lib] error: {r.errors[0]}", file=sys.stderr)
        return 1

    raw = decode_skill_output(r.output)
    views = _parse_skill_list(raw)

    if json_output:
        print(json.dumps(views, ensure_ascii=False))
    else:
        for v in views:
            print(f"  {v}")
        print(f"Total: {len(views)} views")
    return 0


def _parse_skill_list(raw: str) -> list[str]:
    raw = raw.strip()
    if raw == "nil":
        return []
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    return [s.strip().strip('"') for s in raw.split() if s.strip().strip('"')]


def _parse_skill_pairs(raw: str) -> list[tuple[str, str]]:
    """Parse nested SKILL list like ((\"a\" \"b\") (\"c\" \"d\"))."""
    import re
    pairs = re.findall(r'\("([^"]*?)"\s+"([^"]*?)"\)', raw)
    return pairs


def _parse_cell_info(raw: str) -> tuple[str, list[str], list[tuple[str, str]]]:
    """Parse cell-info SKILL output: (desc (views...) ((k v)...))."""
    import re
    desc_match = re.search(r'^\("(.*?)"', raw)
    desc = desc_match.group(1) if desc_match else ""

    views_match = re.search(r'\(("[\w]+"(?:\s+"[\w]+")*)\)', raw[raw.find(desc) + len(desc):] if desc else raw)
    views = []
    if views_match:
        views = [v.strip('"') for v in views_match.group(1).split() if v.strip('"')]

    params = re.findall(r'\("(\w+)"\s+"([^"]*)"\)', raw)
    return desc, views, params
