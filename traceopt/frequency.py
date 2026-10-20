"""Static estimate of block execution frequencies and dynamic counts.

Method (documented in docs/architecture.md §4):

- Each loop is collapsed into one node of its parent region, so every region
  is acyclic. Probability flows forward from the region's header (or the
  function entry) and is split at conditional branches.
- A block's frequency is its reach probability within its innermost region,
  multiplied by the trip counts of all enclosing loops (from `trip_count`).
- Branches and switches whose condition can be computed from constants and
  the given arguments (traceopt/evaluate.py) are taken exactly. This covers
  the guards and remainder checks of runtime-unrolled loops.
- Otherwise, a branch heuristic: a branch whose one side enters a loop with a
  known trip count >= 1 (a loop guard), directly or through a preheader that
  only jumps to the loop, always enters the loop. All other conditional
  branches and switches are split evenly among their successors. This is a
  heuristic, not a profile.

If a loop that may execute has an unknown trip count, UnknownTripCount is
raised. Loops that are never reached need no trip count.
"""

from __future__ import annotations

import re
from collections import Counter

from traceopt.evaluate import Evaluator
from traceopt.features import block_counts
from traceopt.ir import Function
from traceopt.loops import Loop, find_loops, trip_count


class UnknownTripCount(ValueError):
    pass


def _innermost(loops: list[Loop]) -> dict[str, Loop | None]:
    owner: dict[str, Loop | None] = {}
    for loop in sorted(loops, key=lambda lp: lp.depth):
        for label in loop.body:
            owner[label] = loop
    return owner


def block_frequencies(fn: Function, args: dict[str, int] | None = None) -> dict[str, float]:
    """Estimated executions of each reachable block for one call."""
    loops = find_loops(fn)
    by_header = {loop.header: loop for loop in loops}
    trips: dict[str, int] = {}
    evaluator = Evaluator(fn, args)

    def trips_of(header: str) -> int:
        if header not in trips:
            t = trip_count(fn, by_header[header], args)
            if t is None:
                raise UnknownTripCount(f"trip count of loop at {header!r} is unknown")
            trips[header] = t
        return trips[header]

    def known_target(label: str) -> int | None:
        """Index of the successor the block's terminator takes, if it can be computed."""
        words = fn.block(label).terminator.text.split()
        if len(words) >= 3 and words[:2] == ["br", "i1"]:
            v = evaluator.value(words[2].rstrip(","), 1)
            return None if v is None else (0 if v else 1)
        if len(words) >= 3 and words[0] == "switch":
            width = int(words[1][1:])
            v = evaluator.value(words[2].rstrip(","), width)
            if v is None:
                return None
            cases = re.findall(r"i\d+\s+(-?\d+),\s*label", fn.block(label).terminator.text)
            mask = (1 << width) - 1
            for i, c in enumerate(cases):
                if int(c) & mask == v:
                    return i + 1  # successors are the default, then the cases in order
            return 0
        return None

    owner = _innermost(loops)
    top_children = [lp for lp in loops if lp.parent is None]
    freq: dict[str, float] = {}

    def node_of(label: str, region: Loop | None) -> str | None:
        """Node representing `label` inside `region`, or None if outside it."""
        if region is not None and label not in region.body:
            return None
        loop = owner.get(label)
        while loop is not None and loop.parent is not region:
            loop = loop.parent
        return label if loop is None or loop is region else loop.header

    def solve(region: Loop | None, entry: str, children: list[Loop], scale: float) -> None:
        child_by_header = {c.header: c for c in children}
        succ: dict[str, list[str | None]] = {}
        nodes = {entry}
        stack = [entry]
        while stack:
            n = stack.pop()
            if n in child_by_header:
                targets = [t for _, t in child_by_header[n].exits(fn)]
            else:
                targets = fn.block(n).successors
            mapped: list[str | None] = []
            for t in targets:
                m = node_of(t, region)
                if region is not None and m == region.header:
                    m = None  # back edge: ends this iteration
                mapped.append(m)
                if m is not None and m not in nodes:
                    nodes.add(m)
                    stack.append(m)
            succ[n] = mapped

        def enters_loop(t: str | None) -> bool:
            if t in child_by_header:
                return trips_of(t) >= 1
            if t is None or t not in nodes or len(succ[t]) != 1:
                return False
            nxt = succ[t][0]
            return (
                nxt in child_by_header
                and trips_of(nxt) >= 1
                and fn.block(t).terminator.text.split()[1] == "label"
            )

        indegree = Counter(m for n in nodes for m in succ[n] if m is not None)
        reach = Counter({entry: 1.0})
        ready = [n for n in nodes if indegree[n] == 0]
        while ready:
            n = ready.pop()
            targets = succ[n]
            weights = [1.0 / len(targets)] * len(targets) if targets else []
            known = known_target(n) if len(targets) >= 2 and n not in child_by_header else None
            if known is not None:
                weights = [0.0] * len(targets)
                weights[known] = 1.0
            elif len(targets) == 2:
                for i, t in enumerate(targets):
                    if enters_loop(t) and not enters_loop(targets[1 - i]):
                        weights = [0.0, 0.0]
                        weights[i] = 1.0
            for t, w in zip(targets, weights):
                if t is None:
                    continue
                reach[t] += reach[n] * w
                indegree[t] -= 1
                if indegree[t] == 0:
                    ready.append(t)

        for n in nodes:
            if n in child_by_header:
                child = child_by_header[n]
                if reach[n] == 0:
                    freq.update((label, 0.0) for label in child.body)
                    continue
                solve(child, child.header, child.children, scale * reach[n] * trips_of(n))
            else:
                freq[n] = scale * reach[n]

    solve(None, fn.entry.label, top_children, 1.0)
    return freq


def counts_from_frequencies(fn: Function, freq: dict[str, float]) -> Counter:
    """Instruction-class counts given how often each block executes."""
    per_block = block_counts(fn)
    total: Counter = Counter()
    for label, f in freq.items():
        for cls, count in per_block[label].items():
            total[cls] += f * count
    return total


def dynamic_counts(fn: Function, args: dict[str, int] | None = None) -> Counter:
    """Estimated dynamic instruction-class counts for one call."""
    return counts_from_frequencies(fn, block_frequencies(fn, args))
