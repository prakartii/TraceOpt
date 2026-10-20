"""Self-contained HTML report of a demo run and the evaluation.

`render` takes the JSON written by `scripts/demo.py --json`, the evaluation
report from scripts/evaluate.py, and optionally the fit report from
scripts/fit_model.py, and returns one HTML page with no external
dependencies (charts are inline SVG), so it can be opened from disk.
"""

from __future__ import annotations

from html import escape

from traceopt.present import (explain_note, factor_label, fmt, outcome,
                              power_of_two_ladder, unpadded)

CSS = """
:root {
  --bg: #fbfaf7; --panel: #ffffff; --text: #1f2328; --muted: #5d6670;
  --line: #d9dde3; --accent: #2f5d9e; --used: #2f5d9e; --pad: #e7c9a0;
  --good: #1f7a3f; --bad: #b42318; --soft: #f1f3f6; --code: #f5f5f2;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #15181c; --panel: #1d2126; --text: #e6e8eb; --muted: #9aa4ae;
    --line: #333a42; --accent: #7aa7e6; --used: #6e9de0; --pad: #8a6a43;
    --good: #5cc283; --bad: #f07a6c; --soft: #252a30; --code: #1a1e22;
  }
}
:root[data-theme="dark"] {
  --bg: #15181c; --panel: #1d2126; --text: #e6e8eb; --muted: #9aa4ae;
  --line: #333a42; --accent: #7aa7e6; --used: #6e9de0; --pad: #8a6a43;
  --good: #5cc283; --bad: #f07a6c; --soft: #252a30; --code: #1a1e22;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 1.9rem; line-height: 1.2; margin: 0 0 8px; }
h2 { font-size: 1.35rem; margin: 48px 0 12px; padding-top: 16px;
  border-top: 1px solid var(--line); }
h3 { font-size: 1.05rem; margin: 28px 0 8px; }
p { margin: 8px 0; }
.lead { color: var(--muted); font-size: 1.05rem; }
.muted { color: var(--muted); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px; margin: 20px 0; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 14px; }
.card b { display: block; font-size: 1.6rem; line-height: 1.2; }
.card span { color: var(--muted); font-size: .9rem; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 16px; margin: 12px 0; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .93rem; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line);
  vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
pre { background: var(--code); border: 1px solid var(--line); border-radius: 8px;
  padding: 12px; overflow-x: auto; font-size: .85rem; line-height: 1.45; margin: 8px 0; }
code { font-family: ui-monospace, "Cascadia Code", Consolas, monospace; }
.flow { display: flex; flex-wrap: wrap; align-items: stretch; gap: 8px; margin: 12px 0; }
.flow div { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 10px 12px; flex: 1 1 150px; }
.flow div b { display: block; }
.flow div span { color: var(--muted); font-size: .85rem; }
.flow i { align-self: center; color: var(--muted); font-style: normal; }
.yes { color: var(--good); font-weight: 600; }
.no { color: var(--bad); font-weight: 600; }
.chosen td { background: var(--soft); }
.badge { display: inline-block; padding: 1px 8px; border-radius: 99px; font-size: .82rem;
  border: 1px solid var(--line); white-space: nowrap; }
.badge.won { color: var(--good); border-color: var(--good); }
.badge.worse { color: var(--bad); border-color: var(--bad); }
.badge.missed { color: var(--accent); border-color: var(--accent); }
.badge.kept { color: var(--muted); }
.nw { white-space: nowrap; }
.io { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 8px 0; }
.io dt { color: var(--muted); }
.io dd { margin: 0; }
svg text { fill: var(--text); font: 12px system-ui, sans-serif; }
svg .tick { stroke: var(--muted); stroke-dasharray: 3 3; }
svg .tick-label { fill: var(--muted); }
svg .used { fill: var(--used); }
svg .pad { fill: var(--pad); }
.legend { display: flex; gap: 16px; font-size: .85rem; color: var(--muted); margin: 4px 0; }
.legend i { display: inline-block; width: 12px; height: 12px; border-radius: 2px;
  vertical-align: -1px; margin-right: 4px; }
"""


def bucket_svg(rows: list[tuple[str, int, int]], width: int = 900) -> str:
    """Horizontal bars: cycles used (solid) and padding up to the power of two.

    rows: (label, cycles used, padded total). Dashed lines mark the powers of
    two between the smallest use and the largest padded total.
    """
    label_w, right = 190, 90
    bar_w = width - label_w - right
    row_h, top = 30, 24
    scale = max(p for _, _, p in rows)
    height = top + row_h * len(rows) + 8
    x = lambda v: label_w + bar_w * v / scale  # noqa: E731
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="cycles used and padding per version">']
    for p in power_of_two_ladder(min(u for _, u, _ in rows), scale):
        if p > scale:
            continue
        parts.append(f'<line class="tick" x1="{x(p):.1f}" x2="{x(p):.1f}" y1="16" '
                     f'y2="{height - 4}"/>')
        parts.append(f'<text class="tick-label" x="{x(p):.1f}" y="12" '
                     f'text-anchor="middle">{fmt(p)}</text>')
    for i, (label, used, padded) in enumerate(rows):
        y = top + i * row_h
        parts.append(f'<text x="0" y="{y + 15}">{escape(label)}</text>')
        parts.append(f'<rect class="pad" x="{label_w}" y="{y + 3}" '
                     f'width="{x(padded) - label_w:.1f}" height="18" rx="2"/>')
        parts.append(f'<rect class="used" x="{label_w}" y="{y + 3}" '
                     f'width="{x(min(used, padded)) - label_w:.1f}" height="18" rx="2"/>')
        parts.append(f'<text x="{x(padded) + 6:.1f}" y="{y + 16}">{fmt(padded)}</text>')
    parts.append("</svg>")
    return "".join(parts)


LEGEND = ('<div class="legend"><span><i style="background:var(--used)"></i>cycles the run '
          'needs</span><span><i style="background:var(--pad)"></i>padding to the power of two '
          '(proved but wasted)</span><span>dashed lines: power-of-two sizes</span></div>')


SHORT_OUTCOMES = {"kept": "no gain possible", "won": "win taken", "missed": "win missed",
                  "worse": "worse"}


def _version(name: str) -> str:
    return f'<span class="nw">{escape(factor_label(name))}</span>'


def _table(head: list[str], rows: list[list[str]], numeric: set[int] = frozenset(),
           row_class: list[str] | None = None) -> str:
    def cell(tag: str, i: int, v: str) -> str:
        cls = ' class="num"' if i in numeric else ""
        return f"<{tag}{cls}>{v}</{tag}>"
    out = ['<div class="scroll"><table><thead><tr>']
    out += [cell("th", i, h) for i, h in enumerate(head)]
    out.append("</tr></thead><tbody>")
    for j, r in enumerate(rows):
        cls = f' class="{row_class[j]}"' if row_class and row_class[j] else ""
        out.append(f"<tr{cls}>" + "".join(cell("td", i, v) for i, v in enumerate(r)) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _intro() -> str:
    return """
<h2>1. The idea in plain words</h2>
<p>A <b>zero-knowledge virtual machine</b> (zkVM) such as RISC Zero runs a program and
produces a <b>proof</b> that it ran correctly. Anyone can check the proof quickly without
re-running the program. Producing the proof is the expensive part, and its cost grows
with the number of execution steps (<b>cycles</b>).</p>
<p>RISC Zero proves cycles in blocks whose size is a <b>power of two</b>: a run that needs
140,000 cycles is proved as 262,144. Saving cycles therefore only lowers the proving cost
when the run drops into a smaller power-of-two size. Ordinary compilers optimize for CPU
speed and know nothing about this.</p>
<p><b>TraceOpt</b> generates several versions of a program (here: loop unrolling),
predicts the proving size of each one <i>without running the zkVM</i>, and chooses the
cheapest version it can trust. The zkVM then runs the chosen version so the prediction
can be checked against the real numbers.</p>
<h3>Pipeline</h3>
<div class="flow">
  <div><b>C program</b><span>a small kernel with an input <code>n</code></span></div><i>→</i>
  <div><b>LLVM</b><span>clang + opt build versions unrolled 1×, 2×, 4×, 8×</span></div><i>→</i>
  <div><b>Predict</b><span>count executed operations, apply the fitted cost model,
    round up to a power of two</span></div><i>→</i>
  <div><b>Decide</b><span>cheapest version that is a safe saving and passes answer
    checks</span></div><i>→</i>
  <div><b>RISC Zero</b><span>runs the version; real answer and cycle counts are compared
    with the prediction</span></div>
</div>
"""


def _case(i: int, c: dict, policy: dict) -> str:
    n, rows = c["n"], {r["name"]: r for r in c["candidates"]}
    out = [f'<h2>{i}. Example: <code>{escape(c["benchmark"])}</code> with n = {n}</h2>',
           f'<p class="lead">{escape(c["why"]).capitalize()}.</p>',
           f'<h3>The program (<code>{escape(c["source"])}</code>)</h3>',
           f'<pre><code>{escape(c["source_code"])}</code></pre>',
           '<dl class="io">',
           f'<dt>Input</dt><dd>{escape(c["input"])}</dd>',
           f'<dt>Output</dt><dd>{escape(c["output"])}</dd>',
           f'<dt>Expected answer</dt><dd><b>{c["expected"]}</b> <span class="muted">(computed '
           'independently by the Python reference in tests/reference.py)</span></dd></dl>']

    out.append("<h3>Versions TraceOpt considers</h3><p>Unrolling copies the loop body so each "
               "round of the loop does several iterations' work: fewer compare-and-jump steps "
               "run, but the code gets bigger. Each version is run in TraceOpt's IR "
               "interpreter on several inputs and must return the same answer as the original "
               "(a test on those inputs, not a proof of equivalence).</p>")
    vrows = []
    for v in c["variants"]:
        if v["factor"] == 1:
            check = "reference"
        elif v["differential_failure"]:
            check = f'<span class="no">no: {escape(v["differential_failure"])}</span>'
        else:
            check = f'<span class="yes">yes</span>, on {len(v["differential_inputs"])} inputs'
        vrows.append([_version(v["name"]), f'{fmt(v["code_bytes"])} B',
                      str(v["ir_instructions"])]
                     + [fmt(v["executed"][f]) for f in v["executed"]] + [check])
    feats = list(c["variants"][0]["executed"])
    out.append(_table(["version", "code size", "IR instructions"]
                      + [f"{f} ops executed" for f in feats] + ["same answer?"],
                      vrows, numeric=set(range(1, 3 + len(feats)))))

    out.append("<h3>Predicted cost</h3><p><i>needed</i> = program cycles (from the model) + "
               "paging cycles (loading and saving the 1 KiB memory pages the program touches) "
               "+ 4,113 reserved cycles. The prover charges the next power of two.</p>")
    cands = [r for r in c["candidates"] if r["padded_total"] is not None]
    prow = []
    for r in cands:
        used = unpadded(r["predicted_user_cycles"], r["paging_per_segment"])
        prow.append([_version(r["name"]), fmt(r["predicted_user_cycles"]),
                     fmt(r["paging_per_segment"]), fmt(used), f'<b>{fmt(r["padded_total"])}</b>'])
    out.append(_table(["version", "program", "paging", "needed", "proved as"], prow,
                      numeric={1, 2, 3, 4}))
    out.append('<div class="panel">' + LEGEND + bucket_svg(
        [(factor_label(r["name"]), unpadded(r["predicted_user_cycles"], r["paging_per_segment"]),
          r["padded_total"]) for r in cands]) + "</div>")

    out.append(f'<h3>Decision</h3><p>A version is chosen only if it lowers the proved size by '
               f'at least {policy["min_improvement"]:.0%}, still does so when its prediction is '
               f'{policy["uncertainty"]:.0%} too optimistic, passed the answer checks, and grows '
               f'the code by at most {policy["max_code_growth"]:g}×.</p>')
    drows, dcls = [], []
    for r in c["candidates"]:
        chosen = r["name"] == c["selected"]
        mark = ('<span class="yes nw">✔ chosen</span>' if chosen
                else "–" if r["note"] == "baseline" else "✘")
        drows.append([mark, _version(r["name"]),
                      escape(explain_note(r["note"], policy["min_improvement"],
                                          policy["max_code_growth"]))])
        dcls.append("chosen" if chosen else "")
    for v in c["variants"]:
        if v["same_as"]:
            drows.append(["✘", _version(v["name"]),
                          f"LLVM produced the same code as {factor_label(v['same_as'])}"])
            dcls.append("")
    out.append(_table(["", "version", "why"], drows, row_class=dcls))
    sel, base = rows[c["selected"]], rows["unroll1"]
    if c["selected"] == "unroll1":
        out.append("<p><b>TraceOpt keeps the original program</b>: no version is a safe "
                   "saving.</p>")
    else:
        out.append(f'<p><b>TraceOpt chooses {factor_label(sel["name"])}</b>: predicted proved '
                   f'size {fmt(sel["padded_total"])} instead of {fmt(base["padded_total"])} '
                   f'({1 - sel["padded_total"] / base["padded_total"]:.0%} less proving '
                   'work).</p>')

    if c["measured"]:
        out.append("<h3>Checked in the real RISC Zero zkVM</h3><p>Each listed version was "
                   "linked into the RISC Zero guest and executed with the same input. Measured "
                   "are the original, the chosen version, and the rejected version with the "
                   "best prediction (the one a greedy optimizer would have picked).</p>")
        mrows, mcls = [], []
        for name, m in c["measured"].items():
            r = rows[name]
            ok = m["output"] == c["expected"]
            mrows.append([_version(name) + (" <b>(chosen)</b>" if name == c["selected"] else ""),
                          str(m["output"]),
                          '<span class="yes">yes</span>' if ok else '<span class="no">NO</span>',
                          fmt(r["predicted_user_cycles"]), fmt(m["user_cycles"]),
                          fmt(r["padded_total"]), f'<b>{fmt(m["total_cycles"])}</b>'])
            mcls.append("chosen" if name == c["selected"] else "")
        out.append(_table(["version", "zkVM answer", "correct?", "program cycles predicted",
                           "measured", "proved as predicted", "measured"], mrows,
                          numeric={1, 3, 4, 5, 6}, row_class=mcls))
        out.append('<div class="panel">' + LEGEND + bucket_svg(
            [(factor_label(name), unpadded(m["user_cycles"], m["paging_cycles"]),
              m["total_cycles"]) for name, m in c["measured"].items()]) + "</div>")
        chosen_m, orig = c["measured"][c["selected"]], c["measured"]["unroll1"]
        notes = []
        if c["selected"] != "unroll1":
            change = 1 - chosen_m["total_cycles"] / orig["total_cycles"]
            notes.append(f'Measured proved size: {fmt(orig["total_cycles"])} → '
                         f'{fmt(chosen_m["total_cycles"])} ({change:.0%} less proving work).')
        for name, m in c["measured"].items():
            if name in ("unroll1", c["selected"]):
                continue
            predicted = rows[name]["padded_total"]
            if m["total_cycles"] < chosen_m["total_cycles"]:
                notes.append(f"{factor_label(name)} (rejected) measured smaller, "
                             f"{fmt(m['total_cycles'])}: the safety margin cost a win here.")
            elif predicted < m["total_cycles"]:
                notes.append(f"{factor_label(name)} (rejected) was predicted to need "
                             f"{fmt(predicted)} but really needed {fmt(m['total_cycles'])}: "
                             "the promised saving did not happen, so rejecting it was right.")
            else:
                notes.append(f"{factor_label(name)} (rejected) measured "
                             f"{fmt(m['total_cycles'])}: no better than the choice.")
        out += [f"<p><b>{escape(t)}</b></p>" for t in notes]
    return "".join(out)


def _evaluation(i: int, ev: dict, fit: dict | None) -> str:
    recs = ev["records"]
    keys = [outcome(r) for r in recs]
    counts = {k: keys.count(k) for k in SHORT_OUTCOMES}
    right = sum(r["predicted"]["traceopt"]["padded_total"]
                == r["measured"]["traceopt"]["total_cycles"] for r in recs)
    ns = sorted({r["n"] for r in recs})
    out = [f'<h2>{i}. Full evaluation</h2>',
           f'<p>{len({r["benchmark"] for r in recs})} kernels × {len(ns)} inputs '
           f'(n = {", ".join(map(str, ns))}), none of them used to fit the model. Each build was '
           'executed in RISC Zero and its output checked against the reference. Values are the '
           'measured proved size (padded cycles); lower is better. "Best possible" is the '
           'lowest any unroll version reached.</p>']
    rows = []
    for r, k in zip(recs, keys):
        m = r["measured"]
        rows.append([f'<code>{escape(r["benchmark"])}</code>', str(r["n"]),
                     fmt(m["baseline"]["total_cycles"]), fmt(m["conventional"]["total_cycles"]),
                     f'{fmt(m["traceopt"]["total_cycles"])} <span class="muted nw">'
                     f'({"original" if r["selected"] == "unroll1" else factor_label(r["selected"])})'
                     '</span>',
                     fmt(r["best_variant_total"]),
                     f'<span class="badge {k}">{SHORT_OUTCOMES[k]}</span>'])
    out.append(_table(["kernel", "n", "original (-O1, no unroll)", "clang -O2", "TraceOpt",
                       "best possible", "outcome"], rows, numeric={1, 2, 3, 4, 5}))
    out.append(_table(["outcome", "cases"], [
        ["No version could lower the proved size; original kept", str(counts["kept"])],
        ["A saving was available and TraceOpt took it", str(counts["won"])],
        ["A saving was available and TraceOpt missed it", str(counts["missed"])],
        ["TraceOpt's choice was worse than the original", str(counts["worse"])],
        ["Predicted proved size of TraceOpt's choice was exactly right", f"{right} of {len(recs)}"],
    ], numeric={1}))
    if fit and "leave_one_benchmark_out" in fit:
        lobo = fit["leave_one_benchmark_out"]
        out.append("<h3>How accurate is the cycle model?</h3><p>Leave-one-kernel-out test: the "
                   "model is fitted without a kernel, then predicts that kernel. Mean and "
                   "worst relative error of predicted program cycles:</p>")
        out.append(_table(["kernel left out", "mean error", "worst error"],
                          [[f"<code>{escape(k)}</code>", f'{v["mean_abs"]:.1%}',
                            f'{v["max_abs"]:.1%}'] for k, v in sorted(lobo.items())],
                          numeric={1, 2}))
    return "".join(out)


def _closing(i: int) -> str:
    return f"""
<h2>{i}. What this shows, and its limits</h2>
<ul>
<li>Proving cost moves in power-of-two steps, so most cycle savings do not change it. An
optimizer needs to know where the steps are.</li>
<li>TraceOpt predicts cycles from LLVM IR without running the zkVM and uses the prediction
to decide; when it changed the code, the predicted saving was real.</li>
<li>It is deliberately cautious near the step edges: that avoided false wins and also missed
some real ones.</li>
</ul>
<p class="muted">Limits: four small kernels; one optimization (loop unrolling); cycle counts
from RISC Zero's executor (full proofs did not fit in the development machine's memory);
answers checked on test inputs, which is not a formal proof of equivalence.</p>
<h3>Reproduce</h3>
<pre><code>wsl -d Ubuntu
cd /mnt/c/.../TraceOpt
scripts/build_backend.sh          # once, about 4 minutes
scripts/demo.sh                   # narrated terminal demo
scripts/demo.sh --no-pause --json results/demo-run.json
python3 scripts/make_report.py    # rebuilds this page</code></pre>
"""


def render(demo: dict, evaluation: dict, fit: dict | None = None) -> str:
    recs = evaluation["records"]
    keys = [outcome(r) for r in recs]
    right = sum(r["predicted"]["traceopt"]["padded_total"]
                == r["measured"]["traceopt"]["total_cycles"] for r in recs)
    won = [r for r, k in zip(recs, keys) if k == "won"]
    best = max((1 - r["measured"]["traceopt"]["total_cycles"]
                / r["measured"]["baseline"]["total_cycles"] for r in won), default=0.0)
    cards = [
        (str(len(recs)), "evaluation cases (4 kernels × 4 inputs)"),
        (str(keys.count("won")), f"proving-cost savings taken (up to {best:.0%})"),
        (str(keys.count("worse")), "cases where TraceOpt made proving worse"),
        (f"{right}/{len(recs)}", "proved sizes predicted exactly"),
    ]
    body = ['<main><h1>TraceOpt</h1><p class="lead">Choosing compiler optimizations by '
            'zero-knowledge proving cost: a demo report with real RISC Zero measurements.</p>',
            '<div class="cards">'
            + "".join(f"<div class=\"card\"><b>{v}</b><span>{escape(t)}</span></div>"
                      for v, t in cards) + "</div>",
            _intro()]
    section = 2
    for c in demo["cases"]:
        body.append(_case(section, c, demo["policy"]))
        section += 1
    body.append(_evaluation(section, evaluation, fit))
    body.append(_closing(section + 1))
    p = demo["model_parameters"]
    terms = " + ".join(f"{w:.3f} × {escape(f)}" for f, w in p["weights"].items())
    body.append(f'<p class="muted">Model: <code>{escape(demo["model"])}</code>. Program cycles ≈ '
                f'{p["intercept"]:.0f} + {terms} + {p["guest_overhead"]:.0f}; paging ≈ '
                f'{p["paging_base"]:.0f} + {p["paging_per_page"]:.0f} × pages touched.</p></main>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>TraceOpt Demo Report</title><style>{CSS}</style></head><body>"
            + "".join(body) + "</body></html>\n")
