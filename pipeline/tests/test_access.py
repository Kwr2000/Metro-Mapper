"""Small synthetic networks/feeds exercise routing, weights, calendars and safe publication."""
import copy
import importlib.util
import io
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest
from pyproj import Transformer
from scipy.sparse import csr_matrix

from mm import adapter, canonical, config, privacy, publish, registry, runner
from mm.adapter import RawPayload, RunContext
from mm.budget import CallBudget

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("access_under_test", ROOT / "adapters/access/adapter.py")
access = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(access)
NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


@pytest.fixture
def context(repo):
    return RunContext("fixture", NOW, CallBudget.for_adapter("access", NOW), repo / "adapters/access")


def inputs(context):
    ad = access.Access()
    return ad, {req.key: adapter.read_fixture("access", req) for req in ad.plan(context)}


def output(context, modify=None):
    ad, raws = inputs(context)
    if modify:
        modify(raws)
    return ad.finalize([r for raw in raws.values() for r in ad.normalize(raw)])


def fake_osm(path, bbox, as_of):
    collector = access.OSMCollector(bbox)
    for element in ET.parse(path).getroot():
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}
        if element.tag == "node":
            collector.node(SimpleNamespace(id=int(element.attrib["id"]), tags=tags,
                location=SimpleNamespace(lon=float(element.attrib["lon"]), lat=float(element.attrib["lat"]))))
        else:
            collector.way(SimpleNamespace(id=int(element.attrib["id"]), tags=tags,
                nodes=[SimpleNamespace(ref=int(node.attrib["ref"])) for node in element.findall("nd")]))
    return collector.compact(as_of)


def test_four_call_plan_and_source_dates(context):
    ad, raws = inputs(context)
    assert list(raws) == ["osm", "gtfs", "blocks", "block_groups"]
    assert raws["osm"].request.params == {"url": access.OSM}
    assert raws["gtfs"].request.params == {"url": access.GTFS}
    assert raws["blocks"].request.params["url"].endswith("/10/query")
    assert raws["blocks"].request.params["query"] == {
        "where": "STATE='48' AND COUNTY IN ('453','491','209') AND POP100>0", "outFields": "GEOID,POP100,INTPTLAT,INTPTLON",
        "returnGeometry": "false", "f": "json", "resultRecordCount": 100000}
    assert raws["block_groups"].request.params["query"]["outFields"] == "GEOID"
    assert ad.bbox == pytest.approx([-98.40, 29.65, -97.05, 31.0])
    assert ad.cadence == "monthly" and not ad.retain_raw and not ad.recordable


@pytest.mark.parametrize(("tags", "walk", "bike"), [
    ({"highway": "residential"}, True, True),
    ({"highway": "motorway"}, False, False), ({"highway": "trunk_link"}, False, False),
    ({"highway": "construction"}, False, False),
    ({"highway": "residential", "foot": "no"}, False, False),
    ({"highway": "residential", "access": "private"}, False, False),
    ({"highway": "residential", "access": "no", "foot": "designated"}, True, True),
    ({"highway": "residential", "access": "private", "foot": "permissive"}, True, True),
    ({"highway": "steps"}, True, False), ({"highway": "footway"}, True, False),
    ({"highway": "pedestrian", "bicycle": "designated"}, True, True),
    ({"highway": "footway", "bicycle": "yes"}, True, True),
    ({"highway": "residential", "bicycle": "no"}, True, False),
    ({}, False, False),
])
def test_mode_access_rules(tags, walk, bike):
    assert access.allowed(tags, "walk") == walk
    assert access.allowed(tags, "bike") == bike


def test_shortest_path_duplicate_edges_and_multi_source_choice(context, monkeypatch):
    _, raws = inputs(context)
    osm = copy.deepcopy(raws["osm"].body)
    osm["ways"].append(copy.deepcopy(osm["ways"][0]))
    network = access.Network(osm, "walk")
    assert network.graph.nnz // 2 == 6  # duplicate ways do not double the weights
    original = access.dijkstra
    calls = []
    def spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(access, "dijkstra", spy)
    times = network.nearest([osm["nodes"]["3"], osm["nodes"]["5"]], "walk")
    assert times[0] == pytest.approx(2.8, abs=.00001)
    assert times[3] == pytest.approx(1.4, abs=.00001)
    assert math.isinf(times[6])
    assert calls[0]["min_only"] is True and calls[0]["limit"] == 4800
    assert network.nearest([osm["nodes"]["3"]], "bike")[0] == pytest.approx(.84, abs=.00001)
    assert calls[1]["limit"] == pytest.approx(16000)


def test_snap_limit_and_empty_mode(context):
    _, raws = inputs(context)
    osm = raws["osm"].body
    network = access.Network(osm, "walk")
    first, second = network.tree.data[:2]
    direction = (first - second) / np.linalg.norm(first - second)
    undo = Transformer.from_crs(5070, 4326, always_xy=True)
    points = [undo.transform(*(first + direction * distance)) for distance in (299, 301)]
    assert list(network.snap(points)) == [0, -1]
    empty = access.Network({"nodes": osm["nodes"], "ways": []}, "bike")
    assert list(empty.snap([osm["nodes"]["1"]])) == [-1]
    assert len(empty.nearest([], "bike")) == 0


@pytest.mark.parametrize(("values", "weights", "expected"), [
    ([1, 5, 9], [1, 1, 1], 5), ([1, 5], [1, 1], 1),
    ([9, 1, 5], [1, 3, 2], 1), ([5, 5, 9], [1, 1, 1], 5),
    ([61, 3], [51, 49], 61), ([3, 61], [51, 49], 3),
])
def test_population_weighted_median_odd_even_and_ties(values, weights, expected):
    assert access.weighted_median(values, weights) == expected


def test_cap_missing_basket_and_no_residents(context):
    assert access.capped_minutes(60) == 60 and access.capped_minutes(60.01) == 61
    assert access.capped_minutes(math.inf) == 61
    records = {r.feature_id: r.properties for r in output(context) if r.dataset == "block_group"}
    first = records["484530001001"]
    assert first["walk_grocery"] == 3 and first["bike_grocery"] == 1
    assert first["walk_basket"] == 6 and first["bike_basket"] == 2
    assert first["transit_departures_7_9"] == 3 and first["transit_per_hour"] == 1.5
    assert first["service_date"] == "2026-11-04" and first["osm_as_of"] == "2026-10-21"
    assert access.TRANSIT_SCOPE in first["transit_note"]
    remote = records["484530001002"]
    assert all(remote[m] is None and remote[m + "_note"] == access.OVER_60 for m in access.MEASURES)
    assert remote["transit_per_hour"] == 0 and access.NO_TRANSIT in remote["transit_note"]
    empty = records["484530001003"]
    assert all(empty[m] is None for m in access.MEASURES)
    assert empty["access_note"] == access.NO_RESIDENTS and empty["transit_per_hour"] is None
    def no_library(raws):
        raws["osm"].body["destinations"][:] = [r for r in raws["osm"].body["destinations"] if r["kind"] != "library"]
    changed = next(r.properties for r in output(context, no_library) if r.feature_id == "484530001001")
    assert changed["walk_basket"] is None and changed["walk_basket_note"] == access.OVER_60
    assert changed["walk_grocery"] == 3


def test_calendar_holiday_additions_and_time_boundaries(context):
    _, raws = inputs(context)
    files = raws["gtfs"].body["files"]
    day, services = access.service_day(files, date(2026, 10, 24))
    assert day == date(2026, 11, 4) and services == {"weekday", "extra"}
    assert access.service_day(files, date(2026, 11, 4))[0] == date(2026, 11, 4)
    assert access.service_day(files, date(2026, 11, 5))[0] == date(2026, 11, 11)
    _, _, active, departures = access.transit_schedule(files, NOW.date())
    assert active == {"t1", "t2", "t3", "late", "nine"}
    assert departures["s1"] == {"t1", "t3"} and departures["s2"] == {"t1", "t2"}
    assert access.departure_seconds("25:00:00") == 90000
    assert access.departure_seconds("08:59:59") == 32399
    with pytest.raises(ValueError):
        access.departure_seconds("07:60:00")
    expired = {**files, "calendar_dates.txt": "service_id,date,exception_type\n", "calendar.txt": files["calendar.txt"].replace("20991231", "20200102")}
    with pytest.raises(ValueError, match="Wednesday"):
        access.service_day(expired, NOW.date())


def test_transit_counts_each_trip_once_and_uses_network_800_metres(context):
    _, raws = inputs(context)
    osm = raws["osm"].body
    network = access.Network(osm, "walk")
    day, stops, _, departures = access.transit_schedule(raws["gtfs"].body["files"], NOW.date())
    assert day == date(2026, 11, 4)
    counts = access.transit_counts(network, network.snap([osm["nodes"]["1"], osm["nodes"]["7"]]), stops, departures)
    assert counts == [3, 0]  # t1 serves two nearby stops, still counted once
    network.graph = csr_matrix(([800., 800.], ([0, 3], [3, 0])), shape=(8, 8))
    assert access.transit_counts(network, [0], {"s2": stops["s2"]}, {"s2": {"t1"}}) == [1]
    network.graph = csr_matrix(([801., 801.], ([0, 3], [3, 0])), shape=(8, 8))
    assert access.transit_counts(network, [0], {"s2": stops["s2"]}, {"s2": {"t1"}}) == [0]


def test_osm_collector_clips_without_shortcuts_and_filters_small_parks(context):
    ad, _ = inputs(context)
    doc = fake_osm(context.adapter_dir / "fixtures/tiny.osm", ad.bbox, "2026-10-21")
    assert "9" not in doc["nodes"] and "10" not in doc["nodes"]
    assert [w["nodes"] for w in doc["ways"] if w["id"] == 104] == [["2", "3"]]
    assert all(set(w["tags"]) <= set(access.WAY_TAGS) for w in doc["ways"])
    parks = [d for d in doc["destinations"] if d["kind"] == "park"]
    assert len(parks) == 5 and {d["osm_id"] for d in parks} == {"w101"}
    assert {d["osm_id"] for d in doc["destinations"] if d["kind"] == "grocery"} == {"n1", "w103"}


def test_real_pyosmium_reads_tiny_native_osm_when_installed(context):
    osmium = pytest.importorskip("osmium", reason="Live-file parser dependency; CI installs it, fixture development is offline")
    ad, _ = inputs(context)
    path = context.adapter_dir / "fixtures/tiny.osm"
    expected = fake_osm(path, ad.bbox, "2026-10-21")
    assert access.parse_osm(path, ad.bbox, "2026-10-21") == expected
    pbf = context.adapter_dir / "tiny-generated.osm.pbf"
    writer = osmium.SimpleWriter(str(pbf))
    class ToPBF(osmium.SimpleHandler):
        def node(self, node):
            writer.add_node(node)
        def way(self, way):
            writer.add_way(way)
    try:
        ToPBF().apply_file(str(path))
    finally:
        writer.close()
    assert access.parse_osm(pbf, ad.bbox, "2026-10-21") == expected


def test_gtfs_zip_selects_only_required_columns(context):
    _, raws = inputs(context)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in raws["gtfs"].body["files"].items():
            if name == "stop_times.txt":
                lines = text.splitlines()
                text = lines[0] + ",phone\n" + "\n".join(line + ",SYNTHETIC PRIVATE" for line in lines[1:])
            archive.writestr(name, text)
        archive.writestr("feed_info.txt", "feed_version\nsynthetic-native\n")
    result = access.read_gtfs_zip(buffer.getvalue())
    assert result["gtfs_feed_version"] == "synthetic-native"
    assert "phone" not in result["files"]["stop_times.txt"] and "PRIVATE" not in str(result)



def test_gtfs_with_calendar_dates_only(context):
    # CapMetro's feed has no calendar.txt (live run 40054053666); service days come only
    # from calendar_dates.txt, which GTFS allows.
    _, raws = inputs(context)
    files = dict(raws["gtfs"].body["files"])
    wed = access.service_day(files, date(2026, 10, 24))[0].strftime("%Y%m%d")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            if name == "calendar.txt":
                continue
            if name == "calendar_dates.txt":
                service = next(iter(access.service_day(files, date(2026, 10, 24))[1]))
                text = f"service_id,date,exception_type\n{service},{wed},1\n"
            archive.writestr(name, text)
    result = access.read_gtfs_zip(buffer.getvalue())
    day, services = access.service_day(result["files"], date(2026, 10, 24))
    assert day.strftime("%Y%m%d") == wed and services
    with zipfile.ZipFile(buffer := io.BytesIO(), "w") as archive:
        archive.writestr("stops.txt", "stop_id\n")
    with pytest.raises(ValueError, match="neither calendar"):
        access.read_gtfs_zip(buffer.getvalue())

@pytest.mark.parametrize("failure", [False, True])
def test_streamed_pbf_is_deleted_before_return_or_exception(context, monkeypatch, failure):
    ad, raws = inputs(context)
    class Response(io.BytesIO):
        status = 200
        headers = {"Last-Modified": "Wed, 21 Oct 2026 00:00:00 GMT"}
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(b"synthetic binary placeholder"))
    saved = []
    def parser(path, bbox, as_of, check_time):
        check_time()
        assert path.exists() and path.read_bytes() == b"synthetic binary placeholder"
        assert as_of == "2026-10-21" and bbox == ad.bbox
        saved.append(path)
        if failure:
            raise ValueError("synthetic parser failure")
        return raws["osm"].body
    monkeypatch.setattr(access, "parse_osm", parser)
    if failure:
        raw = ad.fetch(raws["osm"].request, context)
        assert raw.status == 502
        with pytest.raises(ValueError, match="OSM parse failed"):
            ad.follow_up(raw, context)
    else:
        assert ad.fetch(raws["osm"].request, context).body == raws["osm"].body
    assert saved and not saved[0].exists() and not list((context.adapter_dir.parents[1] / "data/raw").rglob("*.pbf"))


@pytest.mark.parametrize("key", ["walk_nodes", "grocery_in_study", "stops", "active_trips", "blocks"])
def test_production_size_checks_are_not_relaxed(key):
    stats = {"walk_nodes": 100000, "grocery_in_study": 50, "stops": 1000, "active_trips": 1000, "blocks": 20000}
    access.volume_checks(stats)
    stats[key] -= 1
    with pytest.raises(ValueError, match=key):
        access.volume_checks(stats)


@pytest.mark.parametrize(("count", "success"), [(20, True), (19, False)])
def test_95_percent_snap_guard_even_on_tiny_fixtures(context, count, success):
    def modify(raws):
        first = raws["blocks"].body["features"][0]
        rows = [copy.deepcopy(first) for _ in range(count)]
        for i, row in enumerate(rows, 10):
            row["attributes"]["GEOID"] = "484530001001" + f"{i:03d}"
        rows[-1]["attributes"].update(INTPTLON="-098.2000000", INTPTLAT="+30.0000000")
        raws["blocks"].body["features"][:] = rows
    if success:
        assert output(context, modify)
    else:
        with pytest.raises(ValueError, match="95%"):
            output(context, modify)


@pytest.mark.parametrize("key", ["osm", "gtfs", "blocks", "block_groups"])
@pytest.mark.parametrize("issue", ["http", "non_json", "missing_field"])
def test_bad_inputs_fail_closed(context, key, issue):
    ad, raws = inputs(context)
    raw = raws[key]
    if issue == "http":
        raw = RawPayload(raw.request, raw.body, status=503)
    elif issue == "non_json":
        raw = RawPayload(raw.request, "<html>unavailable</html>")
    elif key == "osm":
        del raw.body["nodes"]
    elif key == "gtfs":
        raw.body["files"]["trips.txt"] = "wrong\nvalue\n"
    else:
        del raw.body["features"][0]["attributes" if key == "blocks" else "properties"]["GEOID"]
    with pytest.raises((ValueError, KeyError)):
        list(ad.normalize(raw))


def test_transfer_limit_and_runtime_fail_closed(context, monkeypatch):
    ad, raws = inputs(context)
    for key in ["blocks", "block_groups"]:
        raws[key].body["exceededTransferLimit"] = True
        with pytest.raises(ValueError, match="exceededTransferLimit"):
            ad.follow_up(raws[key], context)
    monkeypatch.setattr(access.time, "monotonic", lambda: ad.started + 1501)
    with pytest.raises(ValueError, match="runtime"):
        ad.check_time()


def test_manifests_share_one_bundle_and_fixture_labels(context):
    run = runner.run("access", now=NOW)
    assert run.status == "success", run.errors
    assert run.calls_made == 0 and run.planned_calls == 4 and run.rows_out == 14
    layers = [l for l in registry.compile_registry().layers if l.source == "access"]
    assert len(layers) == 9 and len({l.data_url for l in layers}) == 1
    assert {l.data_bundle for l in layers} == {"access_block_group"}
    for layer in layers:
        assert layer.group == "Access" and layer.refresh == "monthly" and not layer.default_visible
        assert layer.freshness == "fixture_only" and layer.as_of == "2026-10-21"
        assert layer.license == "ODbL 1.0 (derived from OpenStreetMap); CMTA Open Data License"
        assert layer.attribution == "© OpenStreetMap contributors; Capital Metro (CMTA) GTFS; U.S. Census Bureau"
        assert {f.field for f in layer.popup} >= set(access.MEASURES) | {"access_note", "transit_note", "osm_as_of", "service_date", "gtfs_feed_version", "geoid"}
        assert layer.legend[-1].color == "#bdbdbd"
        assert layer.legend[0].color == ("#edf8e9" if layer.id == "access_transit" else "#006d2c")
        if layer.variant:
            assert layer.variant.key in {"walk", "bike"} and layer.variant.label in {"Walk", "Bike"}
            assert layer.popup[0].field.startswith(layer.variant.key + "_")
        doc = json.loads(publish.published_path(layer).read_text())
        assert doc["test_data"] is True and len(doc["features"]) == 4
        assert all(not privacy.personal_keys(f["properties"]) for f in doc["features"])


def test_failure_preserves_last_publication(context):
    assert runner.run("access", now=NOW).status == "success"
    folder = context.adapter_dir.parents[1] / "web/public/data/layers"
    previous = {path: path.read_bytes() for path in folder.glob("access_*.geojson")}
    path = context.adapter_dir / "fixtures/blocks.json"
    path.write_text('{"body":{"features":[],"exceededTransferLimit":true}}')
    assert runner.run("access", now=NOW).status == "failed"
    assert previous and {path: path.read_bytes() for path in previous} == previous


def test_mocked_live_storage_and_count_only_summary(context, monkeypatch, capsys):
    ad = access.Access()
    original = adapter.load
    monkeypatch.setattr(adapter, "load", lambda name: ad if name == "access" else original(name))
    monkeypatch.setattr(ad, "fetch", lambda req, ctx: adapter.read_fixture("access", req))
    monkeypatch.setattr(access, "volume_checks", lambda stats: None)  # Small fixtures only; production bounds tested above.
    monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    run = runner.run("access", mode="live", now=NOW)
    assert run.status == "success" and run.calls_made == 4, run.errors
    records = canonical.read("area_feature", "access")
    assert {r.dataset for r in records} == {"block_group", "run_summary", "benchmark"}
    assert all(not privacy.personal_keys(r.properties) for r in records)
    assert not (context.adapter_dir.parents[1] / "data/raw").exists()
    spec = importlib.util.spec_from_file_location("access_live_summary", ROOT / "tools/live_summary.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.main("access") == 0
    report = capsys.readouterr().out
    assert "walk_nodes=8" in report and "snapped_share=1.0" in report and "service_date=2026-11-04" in report
    assert "runtime_seconds=" in report and "peak_memory_mb=" in report


def test_budget_and_live_gate(context, monkeypatch):
    b = config.budgets().adapters["access"]
    assert b.per_day == 6 and b.min_interval_seconds == 5 and b.max_minutes == 25
    # Ungated after Claude's first live check (run 40146625568, DECISIONS 2026-10-25).
    import yaml
    gates = yaml.safe_load((ROOT / "config/live_gates.yaml").read_text()).get("gated") or {}
    assert "access" not in gates


def test_failed_osm_download_is_not_retried_by_runner(context, monkeypatch):
    ad = access.Access()
    original = adapter.load
    monkeypatch.setattr(adapter, "load", lambda name: ad if name == "access" else original(name))
    calls = []
    def error(*args, **kwargs):
        calls.append(1)
        raise OSError("synthetic unavailable")
    monkeypatch.setattr("urllib.request.urlopen", error)
    monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    run = runner.run("access", mode="live", now=NOW)
    assert run.status == "failed" and run.calls_made == 1 and len(calls) == 1
    assert "OSM download failed" in " ".join(run.errors)


@pytest.mark.parametrize("blocked", [{"highway": "motorway"}, {"highway": "residential", "foot": "no"}])
def test_forbidden_shortcut_never_enters_the_graph(context, blocked):
    _, raws = inputs(context)
    osm = copy.deepcopy(raws["osm"].body)
    osm["ways"] = [{"id": 1, "nodes": ["1", "6", "3"], "tags": {"highway": "residential"}},
                   {"id": 2, "nodes": ["1", "3"], "tags": blocked}]
    network = access.Network(osm, "walk")
    times = network.nearest([osm["nodes"]["3"]], "walk")
    assert network.graph.nnz // 2 == 2
    assert times[0] > access.great_circle(osm["nodes"]["1"], osm["nodes"]["3"]) / 80


def test_compact_osm_extra_properties_never_enter_canonical_inputs(context):
    ad, raws = inputs(context)
    osm = raws["osm"].body
    osm["ways"][0]["tags"]["phone"] = "SYNTHETIC PRIVATE"
    osm["destinations"][0]["owner_name"] = "SYNTHETIC PRIVATE"
    [record] = list(ad.normalize(raws["osm"]))
    assert "phone" not in record.model_dump_json() and "owner_name" not in record.model_dump_json()
    assert "SYNTHETIC PRIVATE" not in record.model_dump_json()


def test_live_mode_enforces_size_guards_and_keeps_previous_layers(context, monkeypatch):
    assert runner.run("access", now=NOW).status == "success"
    ad = access.Access()
    original = adapter.load
    monkeypatch.setattr(adapter, "load", lambda name: ad if name == "access" else original(name))
    monkeypatch.setattr(ad, "fetch", lambda req, ctx: adapter.read_fixture("access", req))
    monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    path = context.adapter_dir.parents[1] / "web/public/data/layers/access_block_group.geojson"
    before = path.read_bytes()
    run = runner.run("access", mode="live", now=NOW)
    assert run.status == "failed" and "walk_nodes below production minimum" in " ".join(run.errors)
    assert path.read_bytes() == before
