"""Static estimate of block execution frequencies and dynamic counts.

Method (documented in docs/architecture.md §4):

- Each loop is collapsed into one node of its parent region, so every region
  is acyclic. Probability flows forward from the region's header (or the
  function entry) and is split at conditional branches.
- A block's frequency is its reach probability within its innermost region,
  multiplied by the trip counts of all enclosing loops (from `trip_count`).
- Branch heuristic: a branch whose one side enters a loop with a known trip
  count >= 1 (a loop guard), directly or through a preheader that only
  jumps to the loop, always enters the loop. All other conditional branches
  are split evenly. This is a heuristic, not a profile.

If any loop's trip count is unknown, UnknownTripCount is raised.
"""

from __future__ import annotations

from collections import Counter

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
    trips: dict[str, int] = {}
    for loop in loops:
        t = trip_count(fn, loop, args)
        if t is None:
            raise UnknownTripCount(f"trip count of loop at {loop.header!r} is unknown")
        trips[loop.header] = t

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
                return trips[t] >= 1
            if t is None or t not in nodes or len(succ[t]) != 1:
                return False
            nxt = succ[t][0]
            return (
                nxt in child_by_header
                and trips[nxt] >= 1
                and fn.block(t).terminator.text.split()[1] == "label"
            )

        indegree = Counter(m for n in nodes for m in succ[n] if m is not None)
        reach = Counter({entry: 1.0})
        ready = [n for n in nodes if indegree[n] == 0]
        while ready:
            n = ready.pop()
            targets = succ[n]
            weights = [1.0 / len(targets)] * len(targets) if targets else []
            if len(targets) == 2:
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
                solve(child, child.header, child.children, scale * reach[n] * trips[n])
            else:
                freq[n] = scale * reach[n]

    solve(None, fn.entry.label, top_children, 1.0)
    return freq


def dynamic_counts(fn: Function, args: dict[str, int] | None = None) -> Counter:
    """Estimated dynamic instruction-class counts for one call."""
    freq = block_frequencies(fn, args)
    per_block = block_counts(fn)
    total: Counter = Counter()
    for label, f in freq.items():
        for cls, count in per_block[label].items():
            total[cls] += f * count
    return total
