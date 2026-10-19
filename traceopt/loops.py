"""Control-flow analysis: predecessors, dominators, natural loops, trip counts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from traceopt.evaluate import evaluate
from traceopt.ir import Function, Instruction


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


# --- Trip counts -------------------------------------------------------------

_BR_COND_RE = re.compile(r"^br\s+i1\s+(%\S+),\s*label\s+%(\S+),\s*label\s+%([^,\s]+)")
# `samesign` (LLVM 20+) asserts both operands have the same sign, which makes
# the signed and unsigned predicates agree; it does not change the result.
_ICMP_RE = re.compile(r"^icmp\s+(?:samesign\s+)?(\w+)\s+i\d+\s+([^,]+),\s*(\S+)")
_PHI_INCOMING_RE = re.compile(r"\[\s*([^,\]]+),\s*%([^\s\]]+)\s*\]")
_ADD_RE = re.compile(r"^add\s+(?:(?:nuw|nsw)\s+)*i\d+\s+([^,]+),\s*(\S+)")

_NEGATE = {
    "eq": "ne", "ne": "eq",
    "ult": "uge", "uge": "ult", "ule": "ugt", "ugt": "ule",
    "slt": "sge", "sge": "slt", "sle": "sgt", "sgt": "sle",
}
_SWAP = {
    "eq": "eq", "ne": "ne",
    "ult": "ugt", "ugt": "ult", "ule": "uge", "uge": "ule",
    "slt": "sgt", "sgt": "slt", "sle": "sge", "sge": "sle",
}


def _body(inst: Instruction) -> str:
    """Instruction text without the `%x =` assignment."""
    return inst.text.split("=", 1)[1].strip() if inst.result else inst.text


def _definitions(fn: Function) -> dict[str, Instruction]:
    return {i.result: i for b in fn.blocks for i in b.instructions if i.result}


def _resolve(token: str, fn: Function, args: dict[str, int]) -> int | None:
    token = token.strip()
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if token.startswith("%") and token[1:] in fn.params:
        return args.get(token[1:])
    # A value computed from constants and arguments, e.g. the runtime
    # unroller's `%unroll_iter = sub i32 %n, %xtraiter` (unsigned result).
    return evaluate(fn, token, args)


def trip_count(fn: Function, loop: Loop, args: dict[str, int] | None = None) -> int | None:
    """Number of times the loop body runs per entry, or None if unknown.

    Supports rotated loops (as produced by Clang -O1): a single latch ending
    in a conditional branch to the header or out of the loop, controlled by
    `icmp` on an induction variable `phi [init, outside], [iv + step, latch]`
    with constant positive step. The initial value and bound may be
    constants or function parameters given in `args`. Loop guards outside
    the loop are not modeled: the result assumes the loop is entered.
    """
    args = args or {}
    if len(loop.latches) != 1:
        return None
    latch = fn.block(loop.latches[0])
    m = _BR_COND_RE.match(latch.terminator.text)
    if not m:
        return None
    cond, on_true, on_false = m.group(1)[1:], m.group(2), m.group(3)
    if loop.header == on_true and on_false not in loop.body:
        exit_on_true = False
    elif loop.header == on_false and on_true not in loop.body:
        exit_on_true = True
    else:
        return None

    defs = _definitions(fn)
    cmp_inst = defs.get(cond)
    if cmp_inst is None or cmp_inst.opcode != "icmp":
        return None
    m = _ICMP_RE.match(_body(cmp_inst))
    if not m:
        return None
    pred, lhs, rhs = m.group(1), m.group(2).strip(), m.group(3).strip()

    for phi in fn.block(loop.header).instructions:
        if phi.opcode != "phi":
            break
        incoming = {blk: val.strip() for val, blk in _PHI_INCOMING_RE.findall(phi.text)}
        if len(incoming) != 2 or latch.label not in incoming:
            continue
        nxt = incoming[latch.label]
        init_tok = next(v for b, v in incoming.items() if b != latch.label)
        add = defs.get(nxt[1:]) if nxt.startswith("%") else None
        if add is None or add.opcode != "add":
            continue
        am = _ADD_RE.match(_body(add))
        if not am:
            continue
        ops = [am.group(1).strip(), am.group(2).strip()]
        iv = f"%{phi.result}"
        if iv not in ops:
            continue
        step = _resolve(ops[1] if ops[0] == iv else ops[0], fn, {})
        start = _resolve(init_tok, fn, args)
        if step is None or step <= 0 or start is None:
            continue

        tested = {iv: start - step, nxt: start}  # value of `a` in v_k = a + k*step
        if lhs in tested:
            a, bound_tok, p = tested[lhs], rhs, pred
        elif rhs in tested:
            a, bound_tok, p = tested[rhs], lhs, _SWAP[pred]
        else:
            continue
        bound = _resolve(bound_tok, fn, args)
        if bound is None or pred not in _NEGATE:
            return None
        if p.startswith("u") and (start < 0 or bound < 0):
            return None
        exit_pred = p if exit_on_true else _NEGATE[p]
        return _solve(exit_pred, a, step, bound)
    return None


def _solve(exit_pred: str, a: int, step: int, bound: int) -> int | None:
    """Smallest k >= 1 with `a + k*step <exit_pred> bound`, for step > 0."""
    diff = bound - a
    if exit_pred == "eq":
        if diff % step == 0 and diff // step >= 1:
            return diff // step
        return None
    if exit_pred in ("uge", "sge"):
        return max(1, -(-diff // step))
    if exit_pred in ("ugt", "sgt"):
        return max(1, diff // step + 1)
    return None
