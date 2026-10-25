"""Regenerate tiny synthetic native DPS tables and TIGER geometries; no network."""
import json
from pathlib import Path

from adapter import CITIES, SHERIFFS
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely import transform

ROOT = Path(__file__).parent / "fixtures"
UNDO = Transformer.from_crs(5070, 4326, always_xy=True).transform
BASE_X, BASE_Y = -350000, 820000


def polygon(x, y, width=1000, height=1000):
    return mapping(transform(box(BASE_X + x, BASE_Y + y, BASE_X + x + width, BASE_Y + y + height), UNDO, interleaved=False))


def write(key, body):
    (ROOT / (key + ".json")).write_text(json.dumps({"status": 200, "body": body}, indent=2) + "\n")


def main():
    reports = {k: [] for k in (615, 613, 652)}
    headers = ["ORI", "Agency", "Population", "Murder", "Rape", "Robbery", "Aggravated Assault",
               "Burglary", "Larceny", "AutoTheft", "Human Trafficking\nCommercial Sex Acts",
               "Human Trafficking\nInvoluntary Servitude", "Arson", "Total", "%Change"]
    for i, (ori, (_, name)) in enumerate(CITIES.items()):
        report = 615 if i < 3 else 613 if i < 9 else 652
        reports[report].append((ori, name.upper() + " PD", 20000 if i < 9 else 4000, i))
    for i, (county, ori) in enumerate(SHERIFFS.items()):
        name = {"453": "TRAVIS", "491": "WILLIAMSON", "209": "HAYS"}[county] + " CO SO"
        reports[652].append((ori, name, 100000, 30 + i))
    reports[615].append(("TXDPD0000", "DALLAS PD", 150000, 50))
    reports[652] += [("TX2272500", "UNIV OF TX AUSTIN PD", 0, 40), ("TX0010100", "ELSEWHERE PD", 10000, 41)]
    for report, agencies in reports.items():
        h = headers.copy()
        if report != 615:
            h[6], h[9], h[14] = "Assault", "Auto Theft", "% Change"
        rows = [["Texas Cities - 2025 vs 2024"], h]
        for ori, name, pop, i in agencies:
            rows.append([ori, name, str(pop)])
            if ori not in {"TX2460500", "TXDPD0000"}:  # One agency lacks the prior year, as the live format permits.
                rows.append(["", "Number of Offenses - 2024", "", "1", "1", "1", "1", "2", "2", "2", "0", "0", "0", "10", ""])
            # Part I = 25 for Austin; excluded categories make the portal Total = 33.
            counts = [10] * 10 + [100] if ori == "TXDPD0000" else [1, 2, 3, 4, 5, 6, 4 + i, 2, 3, 3, 33 + i]
            rows.append(["", "Number of Offenses - 2025", "", *map(str, counts), ""])
        write(f"dps_{report}", {"sheets": {"Index Crime": rows, "Legend Info": [
            ["Printed On: 10/24/2026"], ["Beginning Date: 01/01/2025"], ["Ending Date: 12/31/2025"],
            ["Offenses: 09A, 09B, 11A, 11B, 11C, 120, 13A, 200, 220, 23A-23H, 240, 64A, 64B"], ["Data Type: NIBRS"]]}})
    names = ["Murder and Nonnegligent Manslaughter", "Rape", "Robbery", "Aggravated Assault",
             "Burglary/Breaking and Entering", "Larceny", "Motor Vehicle Theft"]
    write("dps_633", {"sheets": {"Rates": [["Crime rates - 2025"], ["Offense", "2024", "2025", "% Change"],
          *[[name, "100", str(100 * (i + 1)), "0"] for i, name in enumerate(names)]]}})
    places = []
    for i, (ori, (geoid, name)) in enumerate(CITIES.items()):
        # Austin spans BGs with different county prefixes. Three neighboring cities form split/tie cases.
        x = {0: 0, 1: 4000, 2: 4400}.get(i, 10000 + i * 2000)
        width = {0: 1000, 1: 400, 2: 300}.get(i, 1000)
        places.append({"type": "Feature", "properties": {"GEOID": geoid, "BASENAME": name},
                       "geometry": polygon(x, 0, width)})
    write("places", {"type": "FeatureCollection", "features": places})
    # A no-PD city is simply outside the 25 mapped places and uses its county sheriff.
    specs = [("484530001001", 0, 0, 1000), ("484910001001", 0, 0, 1000),
             ("482090001001", 2000, 0, 1000), ("484910001002", 3000, 0, 1000),
             ("484530001002", 4000, 0, 1000), ("484530001003", 500, 0, 1000),
             ("484910001003", 8000, 0, 1000)]
    write("block_groups", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"GEOID": g}, "geometry": polygon(x, y, w)} for g, x, y, w in specs]})


if __name__ == "__main__":
    main()
