#!/usr/bin/env python3
"""Draw the proving-cost staircase from scripts/prove_staircase.py results.

    python3 scripts/plot_staircase.py results/proving/staircase-fib.json --highlight 20000

Writes one SVG per metric next to the JSON file (…-time.svg, …-memory.svg),
with no plotting library needed. Everything drawn is measured:

- each dot is one (n, version): x = cycles the program runs, y = the median
  of its proofs; the bar through it spans the fastest and slowest proof;
- each flat line is one proved size (bucket): it spans the cycles of the
  runs that landed in it, at the median of those runs;
- the arrow joins the original and the unrolled version at the same n
  (--highlight), with the measured change.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from traceopt.present import factor_label, fmt  # noqa: E402

WIDTH, HEIGHT = 900, 520
LEFT, RIGHT, TOP, BOTTOM = 80, 30, 60, 70
COLORS = {"unroll1": "#d9622b", "unroll2": "#8a5cc2", "unroll4": "#2a9d8f",
          "unroll8": "#2563c9"}
LEVEL, GRID, TEXT, MUTED = "#9aa0a6", "#e3e5e8", "#1f2328", "#5f6670"
# A white outline keeps labels readable where they cross dots or lines.
HALO = 'stroke="#ffffff" stroke-width="4" paint-order="stroke"'

METRICS = {
    "time": {"title": "Proving time", "unit": "s", "value": lambda p: p["median_prove_seconds"],
             "low": lambda p: min(p["prove_seconds"]), "high": lambda p: max(p["prove_seconds"]),
             "label": lambda v: f"{v:.0f} s"},
    "memory": {"title": "Peak prover memory", "unit": "MiB",
               "value": lambda p: p["peak_memory_kib"] / 1024,
               "low": None, "high": None, "label": lambda v: f"{v:,.0f} MiB"},
}


def nice_step(span: float, ticks: int = 6) -> float:
    """A round tick spacing (1, 2 or 5 times a power of ten) for this span."""
    raw = span / ticks
    power = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
    for m in (1, 2, 5, 10):
        if m * power >= raw:
            return m * power
    return 10 * power


def levels(points: list[dict], value) -> list[dict]:
    """One flat line per proved size: its measured cycle range and median."""
    out = []
    for size in sorted({p["total_cycles"] for p in points}):
        inside = [p for p in points if p["total_cycles"] == size]
        out.append({"total_cycles": size,
                    "x0": min(p["user_cycles"] for p in inside),
                    "x1": max(p["user_cycles"] for p in inside),
                    "y": statistics.median(value(p) for p in inside)})
    return out


def svg(data: dict, metric: str, highlight: int | None) -> str:
    m = METRICS[metric]
    points = [p for p in data["points"] if "median_prove_seconds" in p]
    if not points:
        raise ValueError("no proved points in this file")
    xmax = max(p["user_cycles"] for p in points) * 1.05
    ytop = max((m["high"] or m["value"])(p) for p in points) * 1.12
    xstep, ystep = nice_step(xmax), nice_step(ytop)
    pw, ph = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM

    def x(v):
        return LEFT + v / xmax * pw

    def y(v):
        return TOP + ph - v / ytop * ph

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
           f'width="{WIDTH}" height="{HEIGHT}" font-family="system-ui, sans-serif" '
           f'font-size="12" role="img">',
           f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>',
           f'<text x="{LEFT}" y="26" font-size="17" font-weight="600" fill="{TEXT}">'
           f'{escape(m["title"])} moves in steps: {escape(data["program"])}, '
           f'real RISC Zero proofs</text>',
           f'<text x="{LEFT}" y="45" fill="{MUTED}">Each flat line is one proved size '
           f'(power-of-two bucket); dots are measured runs '
           f'({data["repeat"]} proofs each{", bar = fastest to slowest" if m["low"] else ""}).'
           f'</text>']
    v = 0.0
    while v <= ytop:
        out.append(f'<line x1="{LEFT}" x2="{LEFT + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
                   f'stroke="{GRID}"/>')
        out.append(f'<text x="{LEFT - 8}" y="{y(v) + 4:.1f}" text-anchor="end" '
                   f'fill="{MUTED}">{m["label"](v)}</text>')
        v += ystep
    v = 0.0
    while v <= xmax:
        out.append(f'<text x="{x(v):.1f}" y="{TOP + ph + 18}" text-anchor="middle" '
                   f'fill="{MUTED}">{fmt(int(v))}</text>')
        v += xstep
    out.append(f'<line x1="{LEFT}" x2="{LEFT + pw}" y1="{TOP + ph}" y2="{TOP + ph}" '
               f'stroke="{MUTED}"/>')
    out.append(f'<text x="{LEFT + pw / 2}" y="{HEIGHT - 22}" text-anchor="middle" '
               f'fill="{TEXT}">Cycles the program runs (user cycles, measured)</text>')

    for lv in levels(points, m["value"]):
        x0, x1 = x(lv["x0"]) - 8, x(lv["x1"]) + 8
        out.append(f'<line x1="{x0:.1f}" x2="{x1:.1f}" y1="{y(lv["y"]):.1f}" '
                   f'y2="{y(lv["y"]):.1f}" stroke="{LEVEL}" stroke-width="3" '
                   f'stroke-linecap="round" opacity="0.55"/>')
        right = x1 + 140 < WIDTH   # room for the label after the line?
        out.append(f'<text x="{x1 + 6 if right else x0 - 6:.1f}" y="{y(lv["y"]) + 4:.1f}" '
                   f'text-anchor="{"start" if right else "end"}" fill="{MUTED}" {HALO}>'
                   f'proved size {fmt(lv["total_cycles"])}</text>')

    for p in points:
        cx, cy = x(p["user_cycles"]), y(m["value"](p))
        color = COLORS.get(p["version"], TEXT)
        if m["low"]:
            out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(m["low"](p)):.1f}" '
                       f'y2="{y(m["high"](p)):.1f}" stroke="{color}" stroke-width="2"/>')
        shape = (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5"' if p["version"] == "unroll1"
                 else f'<rect x="{cx - 5:.1f}" y="{cy - 5:.1f}" width="10" height="10"')
        out.append(f'{shape} fill="{color}"><title>n = {p["n"]:,}, '
                   f'{escape(factor_label(p["version"]))}: {fmt(p["user_cycles"])} cycles, '
                   f'proved size {fmt(p["total_cycles"])}, {m["label"](m["value"](p))}'
                   f'</title></{"circle" if p["version"] == "unroll1" else "rect"}>')

    if highlight is not None:
        pair = [p for p in points if p["n"] == highlight]
        base = next((p for p in pair if p["version"] == "unroll1"), None)
        other = next((p for p in pair if p["version"] != "unroll1"), None)
        if base and other:
            bx, by = x(base["user_cycles"]), y(m["value"](base))
            ox, oy = x(other["user_cycles"]), y(m["value"](other))
            change = (m["value"](other) - m["value"](base)) / m["value"](base) * 100
            out.append('<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" '
                       'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                       f'<path d="M0,0 L10,5 L0,10 z" fill="{TEXT}"/></marker></defs>')
            out.append(f'<path d="M{bx:.1f},{by + 9:.1f} Q{bx:.1f},{oy:.1f} '
                       f'{ox + 12:.1f},{oy:.1f}" fill="none" stroke="{TEXT}" '
                       f'stroke-width="1.5" marker-end="url(#head)"/>')
            for i, line in enumerate((
                    f"n = {highlight:,}: TraceOpt's {factor_label(other['version'])}",
                    f"proved size {fmt(base['total_cycles'])} → {fmt(other['total_cycles'])}",
                    f"{m['label'](m['value'](base))} → {m['label'](m['value'](other))} "
                    f"({change:+.0f}%)")):
                out.append(f'<text x="{bx - 12:.1f}" y="{by + 4 + i * 16:.1f}" '
                           f'text-anchor="end" font-weight="{600 if i == 2 else 400}" '
                           f'fill="{TEXT}" {HALO}>{escape(line)}</text>')

    lx = LEFT + 12
    for i, version in enumerate(dict.fromkeys(p["version"] for p in points)):
        ly = TOP + 14 + i * 20
        color = COLORS.get(version, TEXT)
        mark = (f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>'
                if version == "unroll1" else
                f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" fill="{color}"/>')
        out.append(mark + f'<text x="{lx + 18}" y="{ly}" fill="{TEXT}">'
                   f'{escape(factor_label(version))}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path, help="a staircase-*.json file")
    parser.add_argument("--highlight", type=int, help="draw the arrow at this n")
    args = parser.parse_args()
    data = json.loads(args.results.read_text())
    for metric in METRICS:
        path = args.results.with_name(f"{args.results.stem}-{metric}.svg")
        path.write_text(svg(data, metric, args.highlight), encoding="utf-8")
        print(f"written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
