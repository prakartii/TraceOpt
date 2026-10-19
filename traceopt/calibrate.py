"""Fit the linear cost model and measure its held-out error.

    cycles ≈ intercept + Σ_f w_f · x_f

Standard library only (decision D3). Weights are fitted by ordinary least
squares on the normal equations; with `nonnegative=True`, features whose
weight comes out negative are fixed at zero one at a time and the model is
refitted (a simple active-set heuristic, not an exact NNLS solver). The
intercept is unconstrained: it absorbs fixed overhead such as the call into
the kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Row = dict[str, float]


@dataclass
class LinearModel:
    intercept: float
    weights: dict[str, float]
    unidentified: list[str] = field(default_factory=list)

    def predict(self, row: Row) -> float:
        return self.intercept + sum(w * row.get(f, 0.0) for f, w in self.weights.items())


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gauss-Jordan elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [rhs] for row, rhs in zip(a, b)]
    scale = max((abs(x) for row in a for x in row), default=1.0) or 1.0
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) <= 1e-9 * scale:
            raise ValueError("features are linearly dependent; drop or combine some")
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col:
                factor = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= factor * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def _ols(rows: list[Row], y: list[float], features: list[str]) -> tuple[float, list[float]]:
    xs = [[1.0] + [r.get(f, 0.0) for f in features] for r in rows]
    k = len(features) + 1
    xtx = [[sum(x[i] * x[j] for x in xs) for j in range(k)] for i in range(k)]
    xty = [sum(x[i] * t for x, t in zip(xs, y)) for i in range(k)]
    sol = _solve(xtx, xty)
    return sol[0], sol[1:]


def fit(rows: list[Row], y: list[float], features: list[str],
        nonnegative: bool = True) -> LinearModel:
    if len(rows) != len(y) or not rows:
        raise ValueError("need the same, non-zero number of rows and targets")
    unidentified = [f for f in features if len({r.get(f, 0.0) for r in rows}) == 1]
    active = [f for f in features if f not in unidentified]
    if len(rows) < len(active) + 1:
        raise ValueError(f"{len(rows)} observations cannot fit {len(active) + 1} parameters")

    while True:
        intercept, w = _ols(rows, y, active)
        negative = [(wi, f) for wi, f in zip(w, active) if wi < 0]
        if not nonnegative or not negative:
            break
        active.remove(min(negative)[1])

    weights = {f: 0.0 for f in features}
    weights.update(zip(active, w))
    return LinearModel(intercept, weights, unidentified)


def independent_features(rows: list[Row], features: list[str],
                         tol: float = 1e-9) -> tuple[list[str], list[str]]:
    """Split `features` into a linearly independent subset and the rest.

    Features are taken in the given order (so list the preferred ones first);
    one is kept if it is not a linear combination of the intercept and the
    features kept before it. Uses Gram-Schmidt on the columns.
    """
    basis: list[list[float]] = []
    n = len(rows)

    def residual(col: list[float]) -> list[float]:
        for b in basis:
            dot = sum(x * y for x, y in zip(col, b))
            col = [x - dot * y for x, y in zip(col, b)]
        return col

    one = [1.0] * n
    norm = sum(x * x for x in one) ** 0.5
    if norm:
        basis.append([x / norm for x in one])
    kept, dropped = [], []
    for f in features:
        col = [float(r.get(f, 0.0)) for r in rows]
        scale = max((abs(x) for x in col), default=0.0)
        res = residual(col)
        size = sum(x * x for x in res) ** 0.5
        if scale and size > tol * scale * max(1.0, n ** 0.5):
            basis.append([x / size for x in res])
            kept.append(f)
        else:
            dropped.append(f)
    return kept, dropped


def relative_errors(model: LinearModel, rows: list[Row], y: list[float]) -> list[float]:
    """(predicted - measured) / measured for each observation."""
    return [(model.predict(r) - t) / t for r, t in zip(rows, y)]


def leave_one_group_out(rows: list[Row], y: list[float], groups: list[str],
                        features: list[str], nonnegative: bool = True) -> dict[str, list[float]]:
    """Relative errors on each group (e.g. benchmark) when fitted without it."""
    errors: dict[str, list[float]] = {}
    for g in sorted(set(groups)):
        train = [i for i, gi in enumerate(groups) if gi != g]
        test = [i for i, gi in enumerate(groups) if gi == g]
        model = fit([rows[i] for i in train], [y[i] for i in train], features, nonnegative)
        errors[g] = relative_errors(model, [rows[i] for i in test], [y[i] for i in test])
    return errors
