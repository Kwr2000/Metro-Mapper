"""Regenerate native-field synthetic FEMA/TIGER GeoJSON; never calls a source."""

import json
from pathlib import Path

from adapter import TO_AREA, TO_WGS84, reproject
from shapely.geometry import Polygon, box, mapping

OUT = Path(__file__).parent / "fixtures"


def square(lon, lat):
    x, y = TO_AREA(lon, lat)
    return box(x, y, x + 1000, y + 1000)


def portion(geom, start, end):
    x, y, right, top = geom.bounds
    return box(x + (right - x) * start, y, x + (right - x) * end, top)


def feature(geom, **properties):
    return {"type": "Feature", "properties": properties,
            "geometry": mapping(reproject(geom, TO_WGS84)) if geom is not None else None}


def hazard(geom, zone="X", subtype=None, sfha="F", version="2.0"):
    return feature(geom, FLD_ZONE=zone, ZONE_SUBTY=subtype, SFHA_TF=sfha,
                   DFIRM_ID="SYNTHETIC", VERSION_ID=version)


def write(key, features, more=False):
    doc = {"status": 200, "body": {"type": "FeatureCollection", "features": features,
                                   "exceededTransferLimit": more}}
    (OUT / f"{key}.json").write_text(json.dumps(doc, indent=2) + "\n")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    travis, williamson, hays = square(-97.75, 30.27), square(-97.69, 30.51), square(-97.94, 29.89)
    write("block_groups", [feature(geom, GEOID=geoid) for geom, geoid in
        ((travis, "484530108041"), (williamson, "484910108041"), (hays, "482090108041"))])
    write("nfhl_0", [hazard(travis), hazard(portion(travis, 0, .3), zone="AE", sfha="T", version="3.0"),
        hazard(williamson, zone="D", version="1.0"), hazard(portion(hays, 0, .95), version="5.0"),
        hazard(portion(hays, .95, 1), zone="AREA NOT INCLUDED", version="6.0"),
        hazard(portion(hays, 0, .25), zone="A", sfha="T", version="5.0")], more=True)
    page2 = [hazard(portion(travis, .2, .45), zone="A", sfha="T"),
        hazard(portion(travis, .4, .7), subtype="0.2 PCT ANNUAL CHANCE FLOOD HAZARD CONTAINED IN CHANNEL", version="4.0"),
        hazard(portion(travis, .65, .8), subtype="0.2 PCT ANNUAL CHANCE FLOOD HAZARD WITH LEVEE", version="4.0"),
        hazard(None)]
    # A bow tie outside the fixture block groups exercises native-geometry repair too.
    page2.append({"type": "Feature", "properties": {"FLD_ZONE": "X", "ZONE_SUBTY": None,
        "SFHA_TF": "F", "DFIRM_ID": "SYNTHETIC", "VERSION_ID": "7.0"},
        "geometry": mapping(Polygon([(-98.2, 30.7), (-98.19, 30.71), (-98.19, 30.7),
                                     (-98.2, 30.71), (-98.2, 30.7)]))})
    write("nfhl_1000", page2)
