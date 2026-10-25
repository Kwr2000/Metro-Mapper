"""Regenerate six entirely synthetic precincts; never calls a source."""
import json
from pathlib import Path

from adapter import COUNTIES, MEMBERS, RETURNS, VRTO, reproject, TO_WGS84
from shapely.geometry import box, mapping


def main():
    root = Path(__file__).parent / "fixtures"
    counties = [453, 453, 491, 491, 209, 209]
    votes = {2024: [(60, 30, 5, 3, 2), (20, 20, 4, 3, 2), (0, 0, 0, 0, 0),
                    (25, 25, 0, 0, 0), (2, 1, 1, 0, 0), (17, 31, 2, 0, 1)],
             2020: [(50, 40, 10, 0, 0), (30, 20, 0, 0, 0), (0, 0, 0, 0, 0),
                    (60, 30, 10, 0, 0), (60, 20, 20, 0, 0), (0, 0, 0, 0, 0)]}
    turnout = {2024: [(200, 120), (50, 49), (0, 0), (100, 75), (200, 100), (100, 60)],
               2020: [(100, 101), (80, 60), (0, 0), (120, 110), (200, 100), (0, 1)]}
    members = {}
    for filename, (year, kind) in MEMBERS.items():
        rows = [list(RETURNS if kind == "Returns" else VRTO)]
        for i, county in enumerate(counties):
            vtd, key = f"{i + 1:04d}", str(101 + i)
            if kind == "VRTO":
                rows.append([key, *map(str, turnout[year][i])])
            else:
                for party, count in zip(("D", "R", "L", "G", "W"), votes[year][i]):
                    name = f"Synthetic {year} {party} candidate"
                    rows.append([COUNTIES[county], str(county), vtd, str(county) + vtd, key,
                                 "President", name, party, "", str(count)])
                    if party == "W" and i == 0:
                        rows[-1][-1] = str(max(0, count - 1))
                        rows.append([COUNTIES[county], str(county), vtd, str(county) + vtd, key,
                                     "President", "Another synthetic write-in", party, "", str(min(count, 1))])
        members[filename] = rows
    (root / "election_data.json").write_text(json.dumps({"status": 200, "body": {"members": members}}, indent=2) + "\n")
    features = []
    for i, county in enumerate(counties):
        vtd = f"{i + 1:04d}"
        geom = reproject(box(-168000 + i * 1200, 804000, -167000 + i * 1200, 805000), TO_WGS84)
        features.append({"type": "Feature", "properties": {"CNTY": county, "VTD": vtd,
                         "VTDKEY": 101 + i, "CNTYVTD": str(county) + vtd}, "geometry": mapping(geom)})
    (root / "vtd_shapes.json").write_text(json.dumps({"status": 200, "body": {
        "type": "FeatureCollection", "features": features}}, indent=2) + "\n")


if __name__ == "__main__":
    main()
