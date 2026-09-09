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


def _to_real(v):
    """Convert complex to float if imaginary part is zero."""
    if isinstance(v, complex):
        return v.real if v.imag == 0 else [v.real, v.imag]
    return v


def _find_analysis_files(d: Path) -> list[Path]:
    """Find PSF ASCII analysis result files in a directory."""
    analysis_exts = {".ac", ".tran", ".dc", ".noise", ".stb", ".pss"}
    results = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        if f.suffix in analysis_exts:
            results.append(f)
        elif any(ext in f.name for ext in analysis_exts):
            results.append(f)
    return results


def _summarize_signal(vals):
    """One-line summary for a signal value."""
    if not isinstance(vals, list):
        return str(vals)
    reals = [v.real if isinstance(v, complex) else v for v in vals
             if isinstance(v, (int, float, complex))]
    if not reals:
        return f"[{len(vals)} points]"
    return f"[{len(reals)} pts] min={min(reals):.4g}  max={max(reals):.4g}"


def run_result(raw_dir: str, *, signal: str | None = None,
               json_output: bool = False,
               export_csv: bool = False) -> int:
    from virtuoso_bridge.spectre.psf import read_psf_ascii

    d = Path(raw_dir)
    if not d.is_dir():
        print(f"[sim] error: directory not found: {raw_dir}", file=sys.stderr)
        return 1

    analysis_files = _find_analysis_files(d)
    if not analysis_files:
        print(f"[sim] error: no analysis files found in {raw_dir}", file=sys.stderr)
        return 1

    all_data: dict[str, dict] = {}
    for af in analysis_files:
        try:
            data = read_psf_ascii(af)
            all_data[af.name] = data
        except Exception as e:
            print(f"[sim] warning: cannot parse {af.name}: {e}", file=sys.stderr)

    if not all_data:
        print("[sim] error: no parseable results found", file=sys.stderr)
        return 1

    if export_csv:
        return _export_csv(all_data, signal)

    if signal:
        for fname, data in all_data.items():
            if signal in data:
                vals = data[signal]
                if json_output:
                    if isinstance(vals, list):
                        print(json.dumps({signal: [_to_real(v) for v in vals]},
                                         ensure_ascii=False))
                    else:
                        print(json.dumps({signal: _to_real(vals)},
                                         ensure_ascii=False))
                else:
                    print(f"{fname}: {signal} = {_summarize_signal(vals)}")
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
            summary[fname] = {}
            for k, v in data.items():
                if isinstance(v, list):
                    reals = [x.real if isinstance(x, complex) else x for x in v
                             if isinstance(x, (int, float, complex))]
                    summary[fname][k] = {
                        "points": len(v),
                        "min": min(reals) if reals else None,
                        "max": max(reals) if reals else None,
                    }
                else:
                    summary[fname][k] = _to_real(v)
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    else:
        for fname, data in all_data.items():
            print(f"\n{fname}:")
            for k, v in data.items():
                print(f"  {k}: {_summarize_signal(v)}")
    return 0


def _export_csv(all_data: dict[str, dict], signal_filter: str | None) -> int:
    """Export parsed data as CSV to stdout."""
    for fname, data in all_data.items():
        sweep_keys = [k for k, v in data.items() if isinstance(v, list)]
        scalar_keys = [k for k, v in data.items() if not isinstance(v, list)]
        if scalar_keys and not sweep_keys:
            print(f"# {fname} (scalar)")
            print("signal,value")
            for k in sorted(scalar_keys):
                if signal_filter and k != signal_filter:
                    continue
                print(f"{k},{_to_real(data[k])}")
        elif sweep_keys:
            cols = [k for k in sweep_keys
                    if not signal_filter or k == signal_filter or k == "time" or k == "freq"]
            if not cols:
                continue
            print(f"# {fname} (sweep, {len(data[cols[0]])} points)")
            print(",".join(cols))
            n = len(data[cols[0]])
            for i in range(n):
                row = [str(_to_real(data[c][i])) for c in cols]
                print(",".join(row))
    return 0


def run_measure(raw_dir: str, measure: str, signal: str, *,
                from_time: float | None = None,
                to_time: float | None = None) -> int:
    from virtuoso_bridge.spectre.psf import read_psf_ascii

    d = Path(raw_dir)
    if not d.is_dir():
        print(f"[sim] error: directory not found: {raw_dir}", file=sys.stderr)
        return 1

    analysis_files = _find_analysis_files(d)
    vals = None
    raw_vals = None
    time_vals = None
    for af in analysis_files:
        try:
            data = read_psf_ascii(af)
        except Exception:
            continue
        if signal in data and isinstance(data[signal], list):
            raw_vals = data[signal]
            vals = [abs(x) if isinstance(x, complex) else x for x in raw_vals]
            time_vals = data.get("time") or data.get("freq")
            if time_vals and isinstance(time_vals, list):
                time_vals = [x.real if isinstance(x, complex) else x for x in time_vals]
            break

    if vals is None:
        print(f"[sim] error: signal '{signal}' not found as sweep data", file=sys.stderr)
        return 1

    if time_vals and (from_time is not None or to_time is not None):
        t0 = from_time if from_time is not None else time_vals[0]
        t1 = to_time if to_time is not None else time_vals[-1]
        filtered = [(t, v, r) for t, v, r in zip(time_vals, vals, raw_vals) if t0 <= t <= t1]
        if not filtered:
            print(f"[sim] error: no data in range [{t0}, {t1}]", file=sys.stderr)
            return 1
        time_vals = [f[0] for f in filtered]
        vals = [f[1] for f in filtered]
        raw_vals = [f[2] for f in filtered]

    if measure == "avg":
        print(f"{sum(vals) / len(vals):.6g}")
    elif measure == "rms":
        rms = (sum(v * v for v in vals) / len(vals)) ** 0.5
        print(f"{rms:.6g}")
    elif measure == "minmax":
        print(f"min={min(vals):.6g}  max={max(vals):.6g}")
    elif measure == "freq":
        if not time_vals:
            print("[sim] error: no time axis for frequency measurement", file=sys.stderr)
            return 1
        mid = (max(vals) + min(vals)) / 2
        crossings = []
        for i in range(1, len(vals)):
            if vals[i - 1] < mid <= vals[i]:
                frac = (mid - vals[i - 1]) / (vals[i] - vals[i - 1])
                crossings.append(time_vals[i - 1] + frac * (time_vals[i] - time_vals[i - 1]))
        if len(crossings) < 2:
            print("[sim] error: not enough zero crossings for frequency", file=sys.stderr)
            return 1
        periods = [crossings[j + 1] - crossings[j] for j in range(len(crossings) - 1)]
        freq = 1 / (sum(periods) / len(periods))
        print(f"{freq:.6g}")
    elif measure == "gain":
        mag_db = [20 * _log10(abs(v)) if abs(v) > 0 else -999 for v in raw_vals]
        print(f"{max(mag_db):.4g} dB")
    elif measure == "bw":
        if not time_vals:
            print("[sim] error: no freq axis for bandwidth", file=sys.stderr)
            return 1
        mag_db = [20 * _log10(abs(v)) if abs(v) > 0 else -999 for v in raw_vals]
        peak = max(mag_db)
        target = peak - 3.0
        for i in range(1, len(mag_db)):
            if mag_db[i - 1] >= target > mag_db[i]:
                frac = (target - mag_db[i - 1]) / (mag_db[i] - mag_db[i - 1])
                f3db = time_vals[i - 1] * (time_vals[i] / time_vals[i - 1]) ** frac
                print(f"{f3db:.6g}")
                return 0
        print("[sim] error: -3dB point not found", file=sys.stderr)
        return 1
    elif measure == "ugf":
        if not time_vals:
            print("[sim] error: no freq axis for UGF", file=sys.stderr)
            return 1
        mag_db = [20 * _log10(abs(v)) if abs(v) > 0 else -999 for v in raw_vals]
        for i in range(1, len(mag_db)):
            if mag_db[i - 1] >= 0 > mag_db[i]:
                frac = (0 - mag_db[i - 1]) / (mag_db[i] - mag_db[i - 1])
                fugf = time_vals[i - 1] * (time_vals[i] / time_vals[i - 1]) ** frac
                print(f"{fugf:.6g}")
                return 0
        print("[sim] error: unity-gain crossing not found", file=sys.stderr)
        return 1
    elif measure == "pm":
        if not time_vals:
            print("[sim] error: no freq axis for phase margin", file=sys.stderr)
            return 1
        mag_db = [20 * _log10(abs(v)) if abs(v) > 0 else -999 for v in raw_vals]
        fugf = None
        for i in range(1, len(mag_db)):
            if mag_db[i - 1] >= 0 > mag_db[i]:
                frac = (0 - mag_db[i - 1]) / (mag_db[i] - mag_db[i - 1])
                fugf = time_vals[i - 1] * (time_vals[i] / time_vals[i - 1]) ** frac
                phase_at_ugf = _interp_phase(raw_vals, time_vals, fugf, i)
                pm = 180 + phase_at_ugf
                print(f"{pm:.4g} deg (UGF={fugf:.6g} Hz)")
                return 0
        print("[sim] error: unity-gain crossing not found", file=sys.stderr)
        return 1
    elif measure == "thd":
        mags = [abs(v) for v in raw_vals]
        if len(mags) < 3:
            print("[sim] error: need at least 3 harmonics for THD", file=sys.stderr)
            return 1
        h1 = mags[1] if mags[0] < mags[1] * 0.01 else mags[0]
        h1_idx = 1 if mags[0] < mags[1] * 0.01 else 0
        if h1 == 0:
            print("[sim] error: fundamental is zero", file=sys.stderr)
            return 1
        harm_sum = sum(m * m for i, m in enumerate(mags) if i != h1_idx and i > 0)
        thd = (harm_sum ** 0.5) / h1 * 100
        print(f"{thd:.4g}%")
    else:
        print(f"[sim] error: unknown measure '{measure}'",
              file=sys.stderr)
        return 1
    return 0


def _log10(x: float) -> float:
    import math
    return math.log10(x) if x > 0 else -999


def _interp_phase(raw_vals: list, freqs: list, target_freq: float, idx: int) -> float:
    """Interpolate phase at target frequency between idx-1 and idx."""
    import cmath
    p0 = cmath.phase(raw_vals[idx - 1]) * 180 / cmath.pi
    p1 = cmath.phase(raw_vals[idx]) * 180 / cmath.pi
    if abs(p1 - p0) > 180:
        if p1 > p0:
            p1 -= 360
        else:
            p0 -= 360
    import math
    frac = math.log(target_freq / freqs[idx - 1]) / math.log(freqs[idx] / freqs[idx - 1])
    return p0 + frac * (p1 - p0)


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
