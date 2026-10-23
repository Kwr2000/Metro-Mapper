"""Regenerate synthetic native-field GeoJSON; never contacts any source.

Run with the pipeline dependencies installed: python adapters/areas/make_fixtures.py.
Square shapes and naming coverage are constructed in EPSG:5070 then stored in WGS84.
"""

import json
from pathlib import Path

from shapely.geometry import MultiPolygon, box, mapping
from adapter import TO_AREA, TO_WGS84, reproject

OUT = Path(__file__).parent / "fixtures"


def square(lon, lat):
    x, y = TO_AREA(lon, lat)
    return box(x, y, x + 1000, y + 1000)


def portion(geom, start, end):
    x, y, right, top = geom.bounds
    return box(x + (right - x) * start, y, x + (right - x) * end, top)


def feature(geom, **properties):
    if "scode" in properties:
        geom = MultiPolygon([geom])
    return {"type": "Feature", "properties": properties,
            "geometry": mapping(reproject(geom, TO_WGS84))}


def write(key, features):
    # One feature per line keeps the full 2,000-row page inspectable in a diff.
    rows = ",\n".join(json.dumps(row, separators=(",", ":")) for row in features)
    (OUT / f"{key}.json").write_text('{"status":200,"body":{"type":"FeatureCollection","features":[\n'
                                  + rows + '\n]}}\n')


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    austin = square(-97.75, 30.27)
    wcad45 = square(-97.69, 30.51)
    wcad35 = square(-97.67, 30.54)
    near = square(-97.94, 29.89)
    fallback = square(-98.05, 30.02)
    for county, geometries in (("453", [austin]), ("491", [wcad45, wcad35]), ("209", [near, fallback])):
        write(f"block_group_{county}", [feature(geom, GEOID=f"48{county}010804{i}", STATE="48",
            COUNTY=county, TRACT="010804", BLKGRP=str(i), AREALAND=900000, AREAWATER=100000)
            for i, geom in enumerate(geometries, 1)])
        tracts = [] if county == "209" else [feature(box(*geometries[0].bounds),
            GEOID=f"48{county}010804", STATE="48", COUNTY=county, TRACT="010804",
            AREALAND=900000, AREAWATER=100000)]
        write(f"tract_{county}", tracts)
    # One synthetic incorporated place (multipart), one synthetic CDP.
    place_parts = [portion(austin, 0, .8), portion(wcad45, 0, .7), portion(wcad35, 0, .7)]
    write("place_26", [feature(MultiPolygon(place_parts), GEOID="4800001", NAME="Testville",
                                BASENAME="Testville", LSADC="25")])
    write("place_28", [feature(portion(near, 0, .25), GEOID="4800002", NAME="Test CDP",
                                BASENAME="Test", LSADC="57")])
    write("austin", [feature(portion(austin, 0, .6), PLANNING_AREA_NAME="Test Austin Plan")])
    wcad = [feature(portion(wcad45, 0, .25), name="TEST CREEK SEC 3", scode="0000",
                    type="SUB", filedate="2020-01-01T00:00:00"),
            feature(portion(wcad35, 0, .35), name="TEST OAKS PHASE II", scode="0001",
                    type="SUB", filedate="2020-01-01T00:00:00")]
    # Fill a genuine 2,000-row page with synthetic copies outside the study area.
    # No smaller test-only page size: fixture and live use the same follow_up path.
    filler = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]]}
    wcad.extend({"type": "Feature", "properties": {"name": "TEST FILLER", "scode": f"{i:04d}",
        "type": "SUB", "filedate": "2020-01-01T00:00:00"}, "geometry": filler} for i in range(2, 2000))
    write("wcad_0", wcad)
    write("wcad_2000", [feature(portion(wcad45, .25, .45), name="TEST CREEK REPLAT", scode="2000",
                                type="SUB", filedate="2020-01-01T00:00:00")])
