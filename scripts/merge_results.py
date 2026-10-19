#!/usr/bin/env python3
"""Replace records in a variants results file with re-measured ones.

    python3 scripts/merge_results.py BASE.json NEW.json --out MERGED.json

Every (benchmark, unroll_factor) present in NEW replaces all of BASE's
records for that pair. The merged file keeps BASE's metadata and lists the
replacement in `merged_from`, so the provenance of each record stays visible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def merge(base: dict, new: dict, new_name: str) -> dict:
    replaced = {(r["benchmark"], r["unroll_factor"]) for r in new["records"]}
    kept = [r for r in base["records"]
            if (r["benchmark"], r["unroll_factor"]) not in replaced]
    order = {(r["benchmark"], r["unroll_factor"]): i for i, r in enumerate(base["records"])}
    records = sorted(kept + new["records"],
                     key=lambda r: (order.get((r["benchmark"], r["unroll_factor"]), len(order)),
                                    r["n"]))
    return {
        **base,
        "records": records,
        "errors": base.get("errors", []) + new.get("errors", []),
        "merged_from": base.get("merged_from", []) + [{
            "file": new_name,
            "created": new.get("created"),
            "replaced": sorted([b, k] for b, k in replaced),
        }],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    merged = merge(json.loads(args.base.read_text()), json.loads(args.new.read_text()),
                   args.new.name)
    args.out.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"{len(merged['records'])} records; replaced "
          f"{merged['merged_from'][-1]['replaced']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
