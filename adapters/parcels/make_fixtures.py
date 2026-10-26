"""Regenerate a few synthetic compact county responses and native TIGER polygons."""
import json
from pathlib import Path

from adapter import COUNTIES, COUNTERS
from shapely.geometry import box, mapping

ROOT = Path(__file__).parent / "fixtures"


def main():
    for i, fips in enumerate(COUNTIES):
        west = -97.8 + i * .1
        identifiers = ["R070302", "R000123"] if fips == "48491" else ["00123", "456"]
        points = [[identity, f"TEST-GEO-{i}-{j}", round(west + .01 + .01 * j, 6), 30.31]
                  for j, identity in enumerate(identifiers)]
        stats = {**dict.fromkeys(COUNTERS, 0), "records_read": 5, "blank_ids": 1,
                 "zero_ids": 1, "repeated_ids_merged": 1, "repeated_records_merged": 1}
        body = {"parcels": points, "skipped": stats, "date_acq": "2026-02-01" if fips == "48209" else "2026-07-01", "tax_year": "2026"}
        (ROOT / f"stratmap_{fips}.json").write_text(json.dumps({"status": 200, "body": body}, indent=2) + "\n")
    features = [{"type": "Feature", "properties": {"GEOID": fips + "0001001"},
                 "geometry": mapping(box(-97.8 + i * .1, 30.3, -97.75 + i * .1, 30.35))}
                for i, fips in enumerate(COUNTIES)]
    (ROOT / "block_groups.json").write_text(json.dumps({"status": 200, "body": {
        "type": "FeatureCollection", "features": features}}, indent=2) + "\n")


if __name__ == "__main__":
    main()
