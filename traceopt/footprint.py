"""Static memory-footprint features for the paging model.

RISC Zero pages memory in 1 KiB pages; within a segment each touched page is
paged in once and, if written, paged out once (docs/feasibility.md §4.5).
Paging cost therefore follows the number of distinct pages touched, not the
number of accesses.

This module estimates the data footprint from the module globals a function
references, assuming every referenced global is touched in full. That is an
upper bound for kernels that touch only part of an array. Stack usage is not
modeled (the kernels use only registers).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from traceopt.interp import InterpError, Layout, global_definitions

PAGE_BYTES = 1024


def _global_sizes(source: str) -> dict[str, int]:
    """Size in bytes of each global whose type has a known layout."""
    layout = Layout(source)
    sizes = {}
    for name, ty, _ in global_definitions(source):
        try:
            sizes[name] = layout.size(ty)
        except InterpError:
            continue
    return sizes


@dataclass(frozen=True)
class Footprint:
    globals: dict[str, int]     # referenced global -> size in bytes
    written: set[str]           # globals stored to in the function

    @property
    def data_bytes(self) -> int:
        return sum(self.globals.values())

    @property
    def data_pages(self) -> int:
        return sum(-(-size // PAGE_BYTES) for size in self.globals.values())

    @property
    def dirty_pages(self) -> int:
        return sum(-(-size // PAGE_BYTES) for g, size in self.globals.items()
                   if g in self.written)


def footprint(source: str, function: str) -> Footprint:
    """Globals referenced by `function` in the module text, with their sizes."""
    sizes = _global_sizes(source)
    m = re.search(rf"^define\b[^\n]*@{re.escape(function)}\(.*?^\}}", source, re.M | re.S)
    if not m:
        raise KeyError(f"function {function!r} not found")
    body = m.group(0)
    used = {g for g in re.findall(r"@([\w.$]+)", body) if g in sizes}
    written = set()
    for line in body.splitlines():
        sm = re.match(r"\s*store\b.*,\s*ptr\s+(\S+)", line)
        if sm:
            target = sm.group(1).rstrip(",")
            if target.startswith("@"):
                written.add(target[1:])
            else:
                # store through a GEP: find the global it was computed from
                gm = re.search(rf"^\s*{re.escape(target)}\s*=\s*getelementptr\b.*?ptr\s+@([\w.$]+)",
                               body, re.M)
                if gm:
                    written.add(gm.group(1))
    return Footprint({g: sizes[g] for g in sorted(used)}, written & used)
