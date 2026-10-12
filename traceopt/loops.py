"""Control-flow analysis: predecessors, dominators, and natural loops."""

from __future__ import annotations

from dataclasses import dataclass, field

from traceopt.ir import Function


def predecessors(fn: Function) -> dict[str, list[str]]:
    preds: dict[str, list[str]] = {b.label: [] for b in fn.blocks}
    for b in fn.blocks:
        for s in b.successors:
            preds[s].append(b.label)
    return preds


def reachable(fn: Function) -> list[str]:
    """Labels reachable from the entry block, in reverse postorder."""
    seen: set[str] = set()
    order: list[str] = []

    def visit(label: str) -> None:
        seen.add(label)
        for s in fn.block(label).successors:
            if s not in seen:
                visit(s)
        order.append(label)

    visit(fn.entry.label)
    return order[::-1]


def dominators(fn: Function) -> dict[str, set[str]]:
    """Iterative dominator sets over reachable blocks."""
    order = reachable(fn)
    preds = predecessors(fn)
    live = set(order)
    entry = fn.entry.label
    dom = {label: set(order) for label in order}
    dom[entry] = {entry}

    changed = True
    while changed:
        changed = False
        for label in order[1:]:
            incoming = [dom[p] for p in preds[label] if p in live]
            new = set.intersection(*incoming) | {label} if incoming else {label}
            if new != dom[label]:
                dom[label] = new
                changed = True
    return dom


@dataclass
class Loop:
    header: str
    latches: list[str]
    body: set[str]
    parent: Loop | None = None
    children: list[Loop] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return 1 if self.parent is None else self.parent.depth + 1

    def exits(self, fn: Function) -> list[tuple[str, str]]:
        """(from, to) edges leaving the loop."""
        return [
            (label, s)
            for label in sorted(self.body)
            for s in fn.block(label).successors
            if s not in self.body
        ]


def find_loops(fn: Function) -> list[Loop]:
    """Natural loops, one per header, outermost first, with nesting links."""
    dom = dominators(fn)
    preds = predecessors(fn)
    by_header: dict[str, Loop] = {}

    for label in dom:
        for s in fn.block(label).successors:
            if s in dom[label]:  # back edge label -> s
                loop = by_header.setdefault(s, Loop(header=s, latches=[], body={s}))
                loop.latches.append(label)
                stack = [label]
                while stack:
                    node = stack.pop()
                    if node not in loop.body:
                        loop.body.add(node)
                        stack.extend(p for p in preds[node] if p in dom)

    loops = sorted(by_header.values(), key=lambda lp: -len(lp.body))
    for i, inner in enumerate(loops):
        candidates = [o for o in loops[:i] if inner.header in o.body]
        if candidates:
            inner.parent = min(candidates, key=lambda o: len(o.body))
            inner.parent.children.append(inner)
    return sorted(loops, key=lambda lp: (lp.depth, lp.header))
