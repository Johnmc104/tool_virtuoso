"""vbridge sim plot — waveform visualization."""

from __future__ import annotations

import sys
from pathlib import Path


def run_plot(raw_dir: str, signals_str: str, output: str, *,
             from_time: float | None = None, to_time: float | None = None,
             fmt: str = "html") -> int:
    from virtuoso_bridge.spectre.psf import read_psf_ascii

    d = Path(raw_dir)
    if not d.is_dir():
        print(f"[plot] error: directory not found: {raw_dir}", file=sys.stderr)
        return 1

    signal_names = [s.strip() for s in signals_str.split(",")]
    from vbridge.sim_cmd import _find_analysis_files
    analysis_files = _find_analysis_files(d)

    traces: list[tuple[str, list, list]] = []
    x_label = "time (s)"

    for af in analysis_files:
        try:
            data = read_psf_ascii(af)
        except Exception:
            continue
        x_vals_raw = data.get("time") or data.get("freq")
        if not x_vals_raw or not isinstance(x_vals_raw, list):
            continue
        x_vals = [x.real if isinstance(x, complex) else x for x in x_vals_raw]
        x_label = "freq (Hz)" if "freq" in data and "time" not in data else "time (s)"

        for sig in signal_names:
            if sig in data and isinstance(data[sig], list):
                raw = data[sig]
                vals = [abs(v) if isinstance(v, complex) else v for v in raw]
                if from_time is not None or to_time is not None:
                    t0 = from_time if from_time is not None else x_vals[0]
                    t1 = to_time if to_time is not None else x_vals[-1]
                    filtered = [(t, v) for t, v in zip(x_vals, vals) if t0 <= t <= t1]
                    if filtered:
                        tx, tv = zip(*filtered)
                        traces.append((sig, list(tx), list(tv)))
                else:
                    traces.append((sig, x_vals, vals))
        if traces:
            break

    if not traces:
        print(f"[plot] error: no signals found: {signals_str}", file=sys.stderr)
        return 1

    out_path = Path(output)
    if fmt == "png":
        return _plot_png(traces, x_label, out_path)
    else:
        return _plot_html(traces, x_label, out_path)


_COLORS = ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c', '#0891b2']


def _plot_html(traces: list, x_label: str, out_path: Path) -> int:
    max_pts = 2000
    all_y = []
    trace_data = []
    for name, xv, yv in traces:
        if len(yv) > max_pts:
            step = len(yv) // max_pts
            xv, yv = xv[::step], yv[::step]
        all_y.extend(yv)
        trace_data.append((name, xv, yv))

    y_min, y_max = min(all_y), max(all_y)
    margin = (y_max - y_min) * 0.1 or 0.1
    x_all = trace_data[0][1]
    title = ", ".join(t[0] for t in trace_data)
    total_pts = sum(len(t[2]) for t in trace_data)

    trace_js = ""
    legend_js = ""
    for i, (name, xv, yv) in enumerate(trace_data):
        color = _COLORS[i % len(_COLORS)]
        xj = ",".join(f"{v:.6g}" for v in xv)
        yj = ",".join(f"{v:.6g}" for v in yv)
        trace_js += f"drawTrace([{xj}],[{yj}],'{color}');\n"
        legend_js += f"ctx.fillStyle='{color}';ctx.fillText('{name}',W-140,20+{i}*18);\n"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{margin:20px;font:14px monospace}}canvas{{border:1px solid #ccc}}</style>
</head><body>
<h3>{title} ({total_pts} pts)</h3>
<canvas id="c" width="1200" height="400"></canvas>
<script>
const c=document.getElementById('c'),ctx=c.getContext('2d');
const W=c.width,H=c.height,P=50;
const xMin={x_all[0]:.6g},xMax={x_all[-1]:.6g},yMin={y_min-margin:.6g},yMax={y_max+margin:.6g};
function tx(x){{return P+(x-xMin)/(xMax-xMin)*(W-P*2)}}
function ty(y){{return H-P-(y-yMin)/(yMax-yMin)*(H-P*2)}}
ctx.strokeStyle='#ddd';ctx.lineWidth=0.5;
for(let i=0;i<5;i++){{let y=yMin+(yMax-yMin)*i/4;ctx.beginPath();ctx.moveTo(P,ty(y));ctx.lineTo(W-P,ty(y));ctx.stroke();ctx.fillStyle='#666';ctx.fillText(y.toPrecision(4),2,ty(y)+4)}}
function drawTrace(X,Y,color){{ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.beginPath();for(let i=0;i<X.length;i++){{i===0?ctx.moveTo(tx(X[i]),ty(Y[i])):ctx.lineTo(tx(X[i]),ty(Y[i]))}}ctx.stroke()}}
{trace_js}{legend_js}ctx.fillStyle='#333';ctx.fillText('{x_label}',W/2,H-5);
</script></body></html>"""

    out_path.write_text(html)
    print(f"[plot] {out_path} ({total_pts} pts, {len(trace_data)} traces)")
    return 0


def _plot_png(traces: list, x_label: str, out_path: Path) -> int:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("[plot] error: matplotlib not available, use HTML format", file=sys.stderr)
        return 1

    fig, ax = plt.subplots(figsize=(12, 4))
    total_pts = 0
    for name, xv, yv in traces:
        ax.plot(xv, yv, linewidth=0.8, label=name)
        total_pts += len(yv)
    ax.set_xlabel(x_label)
    ax.set_title(f"{', '.join(t[0] for t in traces)} ({total_pts} pts)")
    if len(traces) > 1:
        ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(str(out_path), dpi=150)
    plt.close(fig)
    print(f"[plot] {out_path} ({total_pts} pts, {len(traces)} traces)")
    return 0
