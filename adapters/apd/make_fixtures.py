"""Deterministic synthetic aggregate responses; never downloads source reports."""
import json
from pathlib import Path

from pyproj import Transformer
from shapely import transform, union_all
from shapely.geometry import box, mapping

ROOT = Path(__file__).parent / "fixtures"
TO_WGS = Transformer.from_crs(5070, 4326, always_xy=True).transform
X, Y = Transformer.from_crs(4326, 5070, always_xy=True).transform(-97.8, 30.2)


def geometry(geom):
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = TO_WGS(xy[:, 0], xy[:, 1])
        return result
    return mapping(transform(geom, coordinates))


def write(name, body):
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / (name + ".json")).write_text(json.dumps({"status": 200, "body": body}, separators=(",", ":")) + "\n")


def main():
    features, counts, city = [], [], []
    violent = ["Murder", "Rape", "Robbery", "Aggravated Assault"]
    property_categories = ["Burglary", "Theft", "Auto Theft"]
    for i in range(100):
        left, bottom = X + (i % 10) * 2000, Y + (i // 10) * 2000
        geom = box(left, bottom, left + 1000, bottom + 1000)
        code = "453" + f"{100 + i:06d}" + "1"
        features.append({"type": "Feature", "properties": {"GEOID": "48" + code, "POP100": 50 if i == 2 else 1000 + i * 10},
                         "geometry": geometry(geom)})
        if i == 1:
            city.append(box(left + 500, bottom, left + 1000, bottom + 1000))
        elif i > 1:
            city.append(geom)
        if i != 3:  # An inside-city block group with a real observed zero.
            for category, n in [(violent[i % 4], i % 5 + 1), (property_categories[i % 3], i % 7 + 2), (None, i % 3 + 1)]:
                counts.append({"census_block_group": code, "category_description": category, "n": str(n)})
    counts += [{"census_block_group": None, "category_description": None, "n": "7"},
               {"census_block_group": None, "category_description": "Theft", "n": "3"},
               {"census_block_group": "9990001001", "category_description": "Theft", "n": "2"}]
    write("counts", counts)
    write("counts_unknown_category", [{**counts[0], "category_description": "Unknown offense"}, *counts[1:]])
    write("total", [{"n": str(sum(int(row["n"]) for row in counts))}])
    write("block_groups", {"type": "FeatureCollection", "features": features})
    write("city", {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"GEOID": "4805000"},
                                                              "geometry": geometry(union_all(city))}]})


if __name__ == "__main__":
    main()
