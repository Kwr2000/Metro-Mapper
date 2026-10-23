"""Regenerate synthetic ACS native-field fixtures; no network and no credentials."""

import json
from datetime import datetime, timezone
from pathlib import Path

from adapter import ACS, metrics
from mm.adapter import RunContext
from mm.budget import CallBudget

OUT = Path(__file__).parent / "fixtures"


def cell_value(base, suffix, variant):
    denominator = {item[3] for item in metrics.METRICS.values() if item[3]}
    if base.startswith("B01001_"):
        estimate = 920 if base.endswith("_001") else (460 if base.endswith(("_002", "_026")) else 20)
    else:
        estimate = 1000 if base in denominator else 100
    estimate = {"B01003_001": 920, "B19013_001": 100000, "B25077_001": 250000,
                "B25064_001": 1500, "B25035_001": 1990, "B01002_001": 35,
                "B25003_002": 400}.get(base, estimate)
    value = {"E": str(estimate), "M": "10", "EA": None, "MA": None}[suffix]
    special = {
        0: {"B19013_001M": "30000", "B25077_001M": "75000.1", "B01002_001M": None,
            "B25003_001M": "200", "B25003_002M": "10"},
        1: {"B19013_001E": "-666666666", "B19013_001EA": "250,000+", "B19013_001MA": "**",
            "B25003_001E": "0", "B01003_001E": "0", "B01003_001M": "1",
            "B11003_010E": "-222222222"},
        2: {"B19013_001M": "-222222222", "B25064_001E": "not numeric", "B01003_001E": "NaN",
            "B25077_001M": "(X)", "B25077_001MA": "not available"},
    }
    return special[variant].get(base + suffix, value)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    ctx = RunContext("fixture", datetime(2026, 10, 23, tzinfo=timezone.utc),
                     CallBudget.for_adapter("acs"), OUT.parent)
    rows = {}
    for scale in metrics.SCALES:
        rows[scale] = []
        for county_index, county in enumerate(metrics.COUNTIES):
            for index in range(3 if scale == "block_group" else 1):
                variant = index if scale == "block_group" else county_index
                geoid = "48" + county + "010804" + (str(index + 1) if scale == "block_group" else "")
                rows[scale].append((county, geoid, variant, county_index, index))
    for req in ACS().plan(ctx):
        scale = req.params["scale"]
        if req.params["kind"] == "polygons":
            features = []
            for county, geoid, variant, ci, index in rows[scale]:
                x, y = -97.8 + ci * .1 + index * .015, 30.25 + ci * .1
                ring = [[round(x + dx, 6), round(y + dy, 6)] for dx, dy in
                        ((0, 0), (.01, 0), (.01, .01), (0, .01), (0, 0))]
                features.append({"type": "Feature", "properties": {"GEOID": geoid},
                                 "geometry": {"type": "Polygon", "coordinates": [ring]}})
            body = {"type": "FeatureCollection", "features": features}
        else:
            bases = metrics.PARTS[req.params["part"]]
            geography = ["state", "county", "tract"] + (["block group"] if scale == "block_group" else [])
            header = metrics.variables(bases) + geography
            body = [header]
            for county, geoid, variant, ci, index in rows[scale]:
                if county != req.params["county"]:
                    continue
                values = [cell_value(base, suffix, variant) for base in bases for suffix in ("E", "M", "EA", "MA")]
                body.append(values + ["48", county, "010804"] + ([geoid[-1]] if scale == "block_group" else []))
        (OUT / f"{req.key}.json").write_text(json.dumps({"status": 200, "body": body}, indent=2) + "\n")
