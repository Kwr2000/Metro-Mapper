"""Tiny synthetic compact OSM, GTFS and native TIGER inputs; no downloads."""
import csv
import io
import json
import math
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"


def write(name, body):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps({"status": 200, "body": body}, indent=2) + "\n")


def csv_text(fields, rows):
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(fields); writer.writerows(rows)
    return text.getvalue()


def main():
    lon, lat = -97.78, 30.27
    dx = math.degrees(112 / (6371008.8 * math.cos(math.radians(lat))))
    dy = math.degrees(112 / 6371008.8)
    nodes = {str(i): [lon + (i - 1) * dx, lat] for i in range(1, 6)}
    nodes.update({"6": [lon, lat + dy], "7": [lon + 60 * dx, lat], "8": [lon + 61 * dx, lat]})
    kinds = {"grocery": "3", "park": "5", "school": "6", "pharmacy": "1", "food": "2", "hardware": "3", "bank": "4", "library": "5"}
    write("osm", {"nodes": nodes, "ways": [
        {"id": 100, "nodes": ["1", "2", "3", "4", "5"], "tags": {"highway": "residential"}},
        {"id": 101, "nodes": ["1", "6"], "tags": {"highway": "footway", "bicycle": "yes"}},
        {"id": 102, "nodes": ["7", "8"], "tags": {"highway": "residential"}}],
        "destinations": [{"kind": kind, "lon": nodes[node][0], "lat": nodes[node][1], "osm_id": "n" + node} for kind, node in kinds.items()],
        "osm_as_of": "2026-10-21"})
    files = {
        "calendar.txt": csv_text(["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"],
            [["weekday", 1, 1, 1, 1, 1, 0, 0, "20200101", "20991231"], ["weekend", 0, 0, 0, 0, 0, 1, 1, "20200101", "20991231"]]),
        "calendar_dates.txt": csv_text(["service_id", "date", "exception_type"], [["weekday", "20261028", 2], ["extra", "20261104", 1]]),
        "trips.txt": csv_text(["route_id", "service_id", "trip_id"], [["bus", "weekday", "t1"], ["rail", "weekday", "t2"], ["bus", "extra", "t3"],
            ["bus", "weekday", "late"], ["bus", "weekday", "nine"], ["bus", "weekend", "inactive"]]),
        "routes.txt": csv_text(["route_id", "route_type"], [["bus", 3], ["rail", 2]]),
        "stops.txt": csv_text(["stop_id", "stop_lat", "stop_lon"], [["s1", nodes["1"][1], nodes["1"][0]], ["s2", nodes["4"][1], nodes["4"][0]], ["remote", nodes["7"][1], nodes["7"][0]]]),
        "stop_times.txt": csv_text(["trip_id", "stop_id", "departure_time"], [["t1", "s1", "07:00:00"], ["t1", "s2", "07:10:00"], ["t2", "s2", "08:59:59"],
            ["t3", "s1", "08:00:00"], ["late", "s1", "25:00:00"], ["nine", "s1", "09:00:00"], ["inactive", "s1", "08:00:00"]]),
    }
    write("gtfs", {"files": files, "gtfs_feed_version": "synthetic-2026"})
    groups = ["48453000100" + str(i) for i in range(1, 5)]
    blocks = []
    for i, (group, node, population) in enumerate([(groups[0], "1", 70), (groups[0], "4", 30), (groups[1], "7", 50), (groups[3], "5", 100)], 1):
        point = nodes[node]
        blocks.append({"attributes": {"GEOID": group + f"{i:03d}", "POP100": population, "INTPTLON": f"{point[0]:+012.7f}", "INTPTLAT": f"{point[1]:+.7f}"}})
    write("blocks", {"features": blocks, "exceededTransferLimit": False})
    polygons = []
    for group, point in zip(groups, [nodes["2"], nodes["7"], [lon, lat + 10 * dy], nodes["5"]]):
        x, y = point
        polygons.append({"type": "Feature", "properties": {"GEOID": group}, "geometry": {"type": "Polygon", "coordinates": [
            [[x - dx, y - dy], [x + dx, y - dy], [x + dx, y + dy], [x - dx, y + dy], [x - dx, y - dy]]]}})
    write("block_groups", {"type": "FeatureCollection", "features": polygons, "exceededTransferLimit": False})


if __name__ == "__main__":
    main()
