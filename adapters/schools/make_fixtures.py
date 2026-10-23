"""Generate synthetic native-field fixtures at the real production guard sizes; no network."""
import json
from pathlib import Path

from pyproj import Transformer
from shapely import transform
from shapely.geometry import box, mapping

OUT = Path(__file__).parent / "fixtures"
PROJECT = Transformer.from_crs(4326, 5070, always_xy=True).transform
UNPROJECT = Transformer.from_crs(5070, 4326, always_xy=True).transform
NAMES = ["Leander Independent School District", "Pflugerville Independent School District",
         "Georgetown Independent School District", "Hays Consolidated Independent School District"]
NAMES += [f"Test District {i:02d} Independent School District" for i in range(5, 21)]


def geometry(geom):
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = UNPROJECT(xy[:, 0], xy[:, 1])
        return result
    return mapping(transform(geom, coordinates))


def feature(geom, **props):
    return {"type": "Feature", "properties": props, "geometry": geom}


def write(key, body):
    # One record per line: inspectable synthetic data without enormous pretty-printed files.
    if isinstance(body, list):
        content = '[\n' + ',\n'.join(json.dumps(row, separators=(',', ':')) for row in body) + '\n]'
    else:
        content = '{"type":"FeatureCollection","features":[\n' + ',\n'.join(
            json.dumps(row, separators=(',', ':')) for row in body['features']) + '\n],"exceededTransferLimit":false}'
    (OUT / f"{key}.json").write_text('{"status":200,"body":' + content + '}\n')


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    x, y = PROJECT(-97.8, 30.2)
    districts, bgs = [], []
    for i, name in enumerate(NAMES):
        left, bottom = x + (i % 5) * 3000, y + (i // 5) * 3000
        geom = geometry(box(left, bottom, left + 1000, bottom + 1000))
        districts.append(feature(geom, GEOID=f"48{i + 1:05d}", NAME=name, BASENAME=name,
                                 LOGRADE="PK", HIGRADE="12"))
        bgs.append(feature(geom, GEOID=f"{('48453','48491','48209')[i % 3]}{i:06d}1"))
    districts.append(feature(geometry(box(x + 999, y, x + 1500, y + 1000)), GEOID="4899999",
        NAME="Test Sliver Independent School District", BASENAME="Test Sliver", LOGRADE="PK", HIGRADE="12"))
    write("districts", {"features": districts})
    write("block_groups", {"features": bgs})
    campuses, directory, ratings = [], [], []
    for i in range(500):
        district = i % 20
        lea = f"48{district + 1:05d}"
        nces = lea + f"{i + 1:05d}"
        tea_district = f"{district + 1:03d}901"
        tea_campus = tea_district + f"{i + 1:03d}"
        point = [-97.8 + (i % 25) * .001, 30.2 + (i // 25) * .001]
        campuses.append(feature({"type": "Point", "coordinates": point}, NCESSCH=nces, LEAID=lea,
            NAME=f"Test Campus {i + 1:03d}", CITY="Test City", CNTY=("48453", "48491", "48209")[i % 3], SCHOOLYEAR="2024-2025"))
        if i >= 480:
            continue
        directory.append({"school_number": "'" + tea_campus, "nces_school_id": "'" + nces,
            "district_number": "'" + tea_district, "district_name": NAMES[district],
            "district_web_page_address": (f"district{district + 1}.example.test" if district != 19 else None)})
        if i == 0:
            directory[-1]["school_principal"] = "SYNTHETIC PRIVATE VALUE NEVER STORE"
        if i > 450 or i == 2:
            continue
        letter = ("A", "B", "C", "D", "F")[i % 5]
        row = {"campus_number": "'" + tea_campus, "campus": f"Test Campus {i + 1:03d}",
            "district_number": "'" + tea_district, "district": NAMES[district], "school_type": "Elementary",
            "grades_served": "PK-05", "charter": "Yes" if i == 0 else "No", "alternative_education": "No",
            "relative_performance_rating": letter}
        for domain in ("overall", "academic_growth", "school_progress", "student_achievement", "closing_the_gaps"):
            row[domain + "_rating"] = "Not Rated" if i == 1 else letter
            row[domain + "_score"] = None if i == 1 else str(90 - (i % 5) * 10)
        ratings.append(row)
    write("campuses", {"features": campuses})
    write("directory", directory)
    write("ratings", ratings)
