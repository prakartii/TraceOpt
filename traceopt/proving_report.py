"""Self-contained HTML page of the real-proof results in results/proving/.

`render` takes the reports written by scripts/prove_compare.py (and
optionally scripts/prove_staircase.py) and returns one HTML page with
inline SVG charts and no external dependencies. Every number shown is read
from those files.
"""

from __future__ import annotations

from html import escape

from traceopt.html_report import CSS, _table
from traceopt.present import factor_label, fmt

EXTRA_CSS = """
svg .bar-base { fill: var(--muted); }
svg .bar-chosen { fill: var(--good); }
svg .bar-clang { fill: var(--accent); }
svg .bar-other { fill: var(--pad); }
svg .whisker { stroke: var(--text); stroke-width: 1.5; }
svg .value { fill: var(--muted); }
.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 12px; }
.panel img { width: 100%; height: auto; display: block; border-radius: 6px; }
"""


def title(report: dict) -> str:
    inputs = " ".join(str(v) for v in report["inputs"])
    return f'{report["program"]} {inputs}'.strip()


def label(name: str, report: dict) -> str:
    text = factor_label(name)
    if name == report["selected"] and name != "unroll1":
        text += " (TraceOpt)"
    return text


def _bar_class(name: str, report: dict) -> str:
    if name == "unroll1":
        return "bar-base"
    if name == report["selected"]:
        return "bar-chosen"
    return "bar-clang" if name.startswith("clang-") else "bar-other"


def change(before: float, after: float) -> str:
    if not before:
        return ""
    pct = round((after - before) / before * 100)
    return f"{pct:+d}%" if pct else "0%"   # never "-0%"


def bars_svg(report: dict, metric: str, width: int = 380) -> str:
    """One horizontal bar per version: median proving time (with the range of
    the proofs as a whisker) or peak memory, with the change to the original."""
    versions = report["versions"]
    names = list(versions)
    if metric == "time":
        value = lambda v: v["median_prove_seconds"]  # noqa: E731
        show = lambda x: f"{x:.1f} s"  # noqa: E731
        span = lambda v: (min(v["prove_seconds"]), max(v["prove_seconds"]))  # noqa: E731
    else:
        value = lambda v: v["peak_memory_kib"] / 1024  # noqa: E731
        show = lambda x: f"{x:,.0f} MiB"  # noqa: E731
        span = None
    label_w, right, row_h, top = 165, 95, 28, 6
    bar_w = width - label_w - right
    top_value = max((span(v)[1] if span else value(v)) for v in versions.values())
    x = lambda v: label_w + bar_w * v / top_value  # noqa: E731
    height = top + row_h * len(names) + 4
    base = value(versions["unroll1"])
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="{escape(metric)} per version">']
    for i, name in enumerate(names):
        v = versions[name]
        y = top + i * row_h
        parts.append(f'<text x="0" y="{y + 15}">{escape(label(name, report))}</text>')
        parts.append(f'<rect class="{_bar_class(name, report)}" x="{label_w}" y="{y + 3}" '
                     f'width="{x(value(v)) - label_w:.1f}" height="16" rx="2">'
                     f'<title>{escape(show(value(v)))}</title></rect>')
        end = x(value(v))
        if span:
            lo, hi = span(v)
            parts.append(f'<line class="whisker" x1="{x(lo):.1f}" x2="{x(hi):.1f}" '
                         f'y1="{y + 11}" y2="{y + 11}"/>')
            end = max(end, x(hi))
        text = show(value(v)) + ("" if name == "unroll1" else f"  {change(base, value(v))}")
        parts.append(f'<text class="value" x="{end + 6:.1f}" y="{y + 15}">'
                     f'{escape(text)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _results_table(reports: list[dict]) -> str:
    rows = []
    for r in reports:
        base = r["versions"]["unroll1"]
        for name, v in r["versions"].items():
            rows.append([
                f"<code>{escape(title(r))}</code>" if name == "unroll1" else "",
                escape(label(name, r)), fmt(v["total_cycles"]),
                "" if name == "unroll1" else change(base["total_cycles"], v["total_cycles"]),
                str(v["segments"]), f'{v["median_prove_seconds"]:.1f} s',
                "" if name == "unroll1" else change(base["median_prove_seconds"],
                                                    v["median_prove_seconds"]),
                f'{v["peak_memory_kib"] / 1024:,.0f} MiB',
                f'{fmt(v["seal_bytes"])} B',
                '<span class="yes">yes</span>' if v["correct"] else '<span class="no">NO</span>'])
    # A proving network charges per proved cycle, so the bill changes like the
    # proved size; the time column is what this laptop measured.
    return _table(["Program", "Version", "Proved size", "Prover's bill", "Segments",
                   "Proving time", "Change", "Peak memory", "Proof size", "Correct?"], rows,
                  numeric={2, 3, 4, 5, 6, 7, 8})


def _chain_section(i: int, chain: list[dict]) -> str:
    rows = []
    for r in chain:
        for name, v in r["versions"].items():
            rows.append([f"<code>{escape(title(r))}</code>" if name == "unroll1" else "",
                         escape(label(name, r)), fmt(v["total_cycles"]),
                         f'{v["prove_seconds"]:.1f} s', f'{v["verify_seconds"] * 1000:.0f} ms',
                         f'{fmt(v["receipt_file_bytes"])} B',
                         '<span class="yes">yes</span>' if v["valid"]
                         and v["answer"] == r["expected"] else '<span class="no">NO</span>'])
    attacks = [a for r in chain for a in r["attacks"]]
    rejected = sum(not a["valid"] for a in attacks)
    return (f'<h2>{i}. The blockchain view: prover and verifier</h2>'
            '<p>On a blockchain, one party proves the computation and the chain only verifies '
            'the proof. Here the prover saves each receipt to a file, and a separate '
            '<code>verify</code> step checks it against the program\'s image ID (a fingerprint '
            'of its machine code) and reads the answer from it, without running the '
            'program.</p>'
            + _table(["Program", "Version", "Proved size", "Proving", "Verifying",
                      "Receipt file", "Verified answer correct?"], rows, numeric={2, 3, 4, 5})
            + f'<p><b>{rejected} of {len(attacks)} forged receipts were rejected</b>: one bit '
            'changed in the proof, the original\'s receipt presented as TraceOpt\'s version, '
            'and a receipt presented as an unknown program.</p>'
            '<p class="muted">Verifying here uses the RISC Zero library on the same laptop. '
            'A chain such as Ethereum verifies a compressed Groth16 proof in a smart '
            'contract; that step needs Docker and more memory and is not shown.</p>')


def span(values: list[float]) -> str:
    """'39%–72%', or '50%' when every value rounds the same."""
    lo, hi = f"{min(values):.0%}", f"{max(values):.0%}"
    return lo if lo == hi else f"{lo}–{hi}"


def render(reports: list[dict], succinct: list[dict], staircase: dict | None,
           staircase_images: list[str], chain: list[dict] | None = None) -> str:
    """reports: composite-receipt comparisons; succinct: succinct-receipt ones;
    staircase_images: paths of the staircase SVGs, relative to the page;
    chain: scripts/chain_demo.py reports."""
    chain = chain or []
    chosen = [r for r in reports if r["selected"] != "unroll1"]
    time_cuts = [1 - r["versions"][r["selected"]]["median_prove_seconds"]
                 / r["versions"]["unroll1"]["median_prove_seconds"] for r in chosen]
    mem_cuts = [1 - r["versions"][r["selected"]]["peak_memory_kib"]
                / r["versions"]["unroll1"]["peak_memory_kib"] for r in chosen]
    proofs = sum(len(v["prove_seconds"]) for r in reports + succinct
                 for v in r["versions"].values())
    if staircase:
        proofs += sum(len(p.get("prove_seconds", [])) for p in staircase["points"])
    cards = [(str(proofs), "real proofs generated and verified")]
    if time_cuts:
        cards += [(span(time_cuts), "less proving time where TraceOpt unrolled"),
                  (span(mem_cuts), "less prover memory where TraceOpt unrolled")]
    cards.append(("all" if all(v["correct"] for r in reports + succinct
                               for v in r["versions"].values()) else "NOT all",
                  "answers matched the native program"))

    body = ['<main><h1>TraceOpt: real proofs</h1><p class="lead">What proving actually '
            'costs with the RISC Zero prover, for the original program, the version TraceOpt '
            'chooses, and plain Clang builds.</p>',
            '<div class="cards">' + "".join(
                f'<div class="card"><b>{escape(v)}</b><span>{escape(t)}</span></div>'
                for v, t in cards) + "</div>"]
    section = 1
    if staircase_images:
        body.append(f'<h2>{section}. Proving cost moves in steps</h2>'
                    '<p>Each dot is a real proof. Proving time and memory stay flat inside one '
                    'proved size (a power of two) and jump at its edge. TraceOpt predicts which '
                    'step a version lands on before running anything.</p>')
        body += [f'<div class="panel"><img src="{escape(p)}" alt="staircase chart"></div>'
                 for p in staircase_images]
        section += 1
    body.append(f'<h2>{section}. Original vs TraceOpt vs Clang, per program</h2>'
                '<p>Bars: median proving time (the line spans the fastest and slowest proof) '
                'and peak memory. Grey is the original, green TraceOpt\'s choice, blue plain '
                'Clang. Percentages are against the original.</p>')
    for r in reports:
        seg = (f", segments capped at 2^{r['segment_po2']}" if r.get("segment_po2") else "")
        body.append(f'<h3><code>{escape(title(r))}</code> <span class="muted">'
                    f'({r["repeat"]} proofs per version{escape(seg)})</span></h3>'
                    '<div class="charts">'
                    f'<div class="panel"><b>Proving time</b>{bars_svg(r, "time")}</div>'
                    f'<div class="panel"><b>Peak memory</b>{bars_svg(r, "memory")}</div>'
                    '</div>')
    section += 1
    body.append(f'<h2>{section}. All measurements</h2>' + _results_table(reports))
    section += 1
    if chain:
        body.append(_chain_section(section, chain))
        section += 1
    if succinct:
        body.append(f'<h2>{section}. The compressed proof has a fixed size</h2>'
                    '<p>A succinct receipt compresses all segment proofs into one. Its size is '
                    'the same for every program, so no compiler can shrink it; TraceOpt still '
                    'makes it cheaper to generate.</p>' + _results_table(succinct))
        section += 1
    body.append(f'<h2>{section}. Limits</h2><ul>'
                '<li>Runs with segments of at most 2^18 cycles only: larger ones did not fit '
                'in the development machine\'s memory (about 7.6 GB in WSL).</li>'
                '<li>Proving times vary by up to about 75% between runs on this laptop; '
                'versions are proved alternately and the median is shown. Memory does not '
                'vary.</li>'
                '<li>One machine, the CPU prover, a few small programs.</li>'
                '<li>These programs are cases where TraceOpt chose to unroll. In the executor '
                'evaluation (<code>results/evaluation-clang21.json</code>) plain '
                '<code>clang -O2</code> did better than TraceOpt in 1 of 16 cases '
                '(<code>nested_fnv</code>, n = 3000: 262,144 against 524,288 cycles); that '
                'case is not proved here.</li></ul>'
                '<h3>Reproduce</h3><pre><code>scripts/prove_compare.sh demos/fib.c 20000 '
                '--conventional O2 O3\nscripts/prove_staircase.sh demos/fib.c --n 1000 8000 '
                '18000\npython3 scripts/make_proving_report.py</code></pre></main>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>TraceOpt Real Proofs</title><style>{CSS}{EXTRA_CSS}</style></head><body>"
            + "".join(body) + "</body></html>\n")
