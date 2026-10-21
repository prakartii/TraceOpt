"""Choose an unroll factor for a C kernel by predicted proving cost.

For each factor this generates the variant with LLVM (traceopt/toolchain.py),
predicts its user and paging cycles with a calibrated CostModel (from the
executed RISC-V instructions of its machine code when they can be mapped,
traceopt/machine.py, otherwise from its IR instruction counts), checks its
outputs against the baseline in the IR interpreter (a differential test, not
a proof of equivalence), and passes the candidates to the decision rule in
traceopt/decision.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from traceopt import toolchain
from traceopt.decision import Candidate, Decision, Policy, decide
from traceopt.footprint import PAGE_BYTES, footprint
from traceopt.frequency import UnknownTripCount, dynamic_counts
from traceopt.interp import InterpError, Interpreter
from traceopt.ir import parse_module
from traceopt.machine import MachineMapError, executed_instructions
from traceopt.model import CostModel

FUNCTION = "traceopt_kernel"
DEFAULT_FACTORS = (1, 2, 4, 8)
# Inputs for the differential test, in addition to the requested one.
DIFF_INPUTS = (0, 1, 2, 3, 5, 7, 8, 9, 16, 17)
DIFF_MAX_N = 2000   # skip larger requested inputs in the interpreter (speed)


@dataclass
class Variant:
    factor: int
    ir: Path
    obj: Path
    code_bytes: int
    data_pages: int
    predicted_kernel_cycles: float | None
    prediction_unavailable: str | None
    differential_inputs: list[int]
    differential_failure: str | None
    same_as: str | None = None    # same object code as this smaller factor
    # "machine" (executed RISC-V instructions) or "ir" (the IR model fallback)
    prediction_method: str | None = None
    executed_instructions: dict[str, float] | None = None   # by class, machine method

    @property
    def name(self) -> str:
        return f"unroll{self.factor}"


@dataclass
class Result:
    source: Path
    args: dict[str, int]
    variants: list[Variant]
    decision: Decision

    @property
    def selected(self) -> Variant:
        return next(v for v in self.variants if v.name == self.decision.selected)

    def to_dict(self) -> dict:
        return {
            "source": str(self.source),
            "args": self.args,
            "selected": self.decision.selected,
            "reason": self.decision.reason,
            "selected_object": str(self.selected.obj),
            "candidates": [asdict(r) for r in self.decision.rows],
            "variants": [{**asdict(v), "ir": str(v.ir), "obj": str(v.obj)}
                         for v in self.variants],
        }


def _differential(base: Interpreter, variant: Interpreter, inputs: list[int]) -> str | None:
    """None if the variant returns the baseline's value for every input."""
    for n in inputs:
        try:
            want, _ = base.run(FUNCTION, {"0": n})
            got, _ = variant.run(FUNCTION, {"0": n})
        except InterpError as e:
            return f"n={n}: {e}"
        if got != want:
            return f"n={n}: returned {got}, baseline {want}"
    return None


def optimize(source: Path, args: dict[str, int], model: CostModel, work: Path,
             factors: tuple[int, ...] = DEFAULT_FACTORS, policy: Policy = Policy()) -> Result:
    if 1 not in factors:
        raise ValueError("factor 1 (the baseline) must be among the candidates")
    work.mkdir(parents=True, exist_ok=True)
    base_ir = toolchain.emit_base_ir(source, work / "base.ll")
    base_interp = Interpreter(base_ir.read_text())
    n = args.get("0")
    inputs = sorted(set(DIFF_INPUTS) | ({n} if n is not None and n <= DIFF_MAX_N else set()))

    variants = []
    seen: dict[str, str] = {}
    for k in sorted(set(factors)):
        ir = toolchain.unroll(base_ir, k, work / f"u{k}.ll")
        obj = toolchain.codegen(ir, work / f"u{k}.o")
        text = ir.read_text()
        # opt reprints IR even when it changes nothing, so compare the code.
        same_as = seen.setdefault(obj.read_bytes().hex(), f"unroll{k}")
        same_as = None if same_as == f"unroll{k}" else same_as
        fn = parse_module(text).functions[FUNCTION]
        kernel, why, method, executed = None, None, None, None
        try:
            if model.machine_intercept is not None:
                try:
                    executed = executed_instructions(ir, args, FUNCTION)
                    kernel = model.machine_kernel_cycles(sum(executed.values()))
                    method = "machine"
                except MachineMapError:
                    pass
            if kernel is None:
                kernel, method = model.kernel_cycles(dynamic_counts(fn, args)), "ir"
        except UnknownTripCount as e:
            kernel, why, method = None, str(e), None
        diff = None if k == 1 else _differential(base_interp, Interpreter(text), inputs)
        variants.append(Variant(k, ir, obj, toolchain.symbol_size(obj),
                                footprint(text, FUNCTION).data_pages, kernel, why,
                                inputs, diff, same_as, method,
                                dict(executed) if executed is not None else None))

    baseline = next(v for v in variants if v.factor == 1)

    def code_pages(v: Variant) -> int:
        return -(-v.code_bytes // PAGE_BYTES)

    def candidate(v: Variant) -> Candidate:
        user = None if v.predicted_kernel_cycles is None else round(
            v.predicted_kernel_cycles + model.guest_overhead)
        # The fitted paging cost already covers the baseline's code; code
        # that needs more 1 KiB pages pays the per-page cost for each extra
        # page. (Approximate: it ignores where the code lands in a page.)
        pages = v.data_pages + max(0, code_pages(v) - code_pages(baseline))
        return Candidate(v.name, user, round(model.paging_cycles(pages)),
                         v.code_bytes, v.differential_failure is None)

    # Variants opt left unchanged are not separate candidates.
    others = [candidate(v) for v in variants if v.factor != 1 and v.same_as is None]
    decision = decide(candidate(baseline), others, policy)
    return Result(source, args, variants, decision)
