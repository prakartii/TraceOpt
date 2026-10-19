"""The calibrated cost model used to score candidates.

    kernel cycles  = intercept + Σ_f w_f · dynamic_count_f
    user cycles    = kernel cycles + guest_overhead
    paging cycles  = paging_base + paging_per_page · data_pages

The user and paging predictions feed the segment model
(traceopt/segments.py), whose padded total is what candidates are compared
on. All coefficients come from measurements (scripts/fit_model.py); none are
taken from documentation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from traceopt.segments import padded_total_cycles


@dataclass
class CostModel:
    intercept: float
    weights: dict[str, float]
    guest_overhead: float
    paging_base: float
    paging_per_page: float
    source: dict = field(default_factory=dict)   # provenance: data file, toolchain
    # Feature name -> instruction classes summed into it; a feature missing
    # here is a single class of the same name.
    feature_definitions: dict[str, list[str]] = field(default_factory=dict)

    def feature_value(self, feature: str, dynamic_counts: dict[str, float]) -> float:
        classes = self.feature_definitions.get(feature, [feature])
        return sum(dynamic_counts.get(c, 0.0) for c in classes)

    def kernel_cycles(self, dynamic_counts: dict[str, float]) -> float:
        return self.intercept + sum(w * self.feature_value(f, dynamic_counts)
                                    for f, w in self.weights.items())

    def user_cycles(self, dynamic_counts: dict[str, float]) -> float:
        return self.kernel_cycles(dynamic_counts) + self.guest_overhead

    def paging_cycles(self, data_pages: int) -> float:
        return self.paging_base + self.paging_per_page * data_pages

    def padded_total(self, dynamic_counts: dict[str, float], data_pages: int,
                     segment_limit_po2: int = 20) -> int:
        """Predicted padded total cycles, assuming a single segment's paging."""
        return padded_total_cycles(round(self.user_cycles(dynamic_counts)),
                                   round(self.paging_cycles(data_pages)),
                                   segment_limit_po2)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> "CostModel":
        data = json.loads(Path(path).read_text())
        try:
            return cls(**data)
        except TypeError as e:
            raise ValueError(f"{path}: not a cost model file ({e})") from None
