"""Synthetic native ACS ucgid comparison responses; no source calls."""
import json
from pathlib import Path
from adapter import BENCHMARK_GEOS, PEER_IDS, metrics

root = Path(__file__).parent / "fixtures"
for part, bases in metrics.PARTS.items():
    header = metrics.variables(bases) + ["ucgid"]
    rows = [header]
    for index, geoid in enumerate([*BENCHMARK_GEOS, *PEER_IDS]):
        cells = {}
        for base in bases:
            estimate = 1000 if base.endswith("_001") else 10
            if base == "B01003_001": estimate = 900000 + index * 1000
            if base == "B19013_001": estimate = 90000 + index * 1000
            if base == "B25077_001": estimate = 350000
            if base == "B25064_001": estimate = 1500
            if base == "B25035_001": estimate = 1985
            if base == "B01002_001": estimate = 35
            for suffix, value in (("E", str(estimate)), ("M", "5"), ("EA", None), ("MA", None)):
                cells[base + suffix] = value
        rows.append([cells.get(col, geoid) for col in header])
    # One native row per line keeps a complete 19-geography response easy to review.
    body = ",\n".join("    " + json.dumps(row) for row in rows)
    (root / f"benchmarks_{part}.json").write_text('{\n  "status": 200,\n  "body": [\n' + body + '\n  ]\n}\n')
