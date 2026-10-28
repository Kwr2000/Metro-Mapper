"""Synthetic native-field FEMA/TIGER data: classification, coverage, paging and repair."""

import copy
import gzip
import importlib.util
import json
import math
import urllib.error
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box, mapping, shape

from mm import adapter, config, registry, runner
from mm.adapter import RawPayload, RunContext
from mm.budget import CallBudget

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("flood_under_test", ROOT / "adapters/fema_nfhl/adapter.py")
flood = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flood)
NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
X, Y = flood.TO_AREA(-97.75, 30.27)
BASE = box(X, Y, X + 1000, Y + 1000)
GEOID = "484530108041"


@pytest.fixture
def context(repo):
    return RunContext("fixture", NOW, CallBudget.for_adapter("fema_nfhl", NOW), repo / "adapters/fema_nfhl")


def geometry(geom):
    return mapping(flood.reproject(geom, flood.TO_WGS84))


def feature(geom, zone="X", subtype=None, sfha="F", version="2.0"):
    return {"type": "Feature", "properties": {"FLD_ZONE": zone, "ZONE_SUBTY": subtype,
        "SFHA_TF": sfha, "DFIRM_ID": "SYNTHETIC", "VERSION_ID": version}, "geometry": geometry(geom)}


def payload(req, features, more=False):
    return RawPayload(req, {"type": "FeatureCollection", "features": features, "exceededTransferLimit": more})


def portion(start, end):
    return box(X + start * 1000, Y, X + end * 1000, Y + 1000)


def summarize(context, features):
    ad = flood.FemaNFHL()
    tiger_req, req = ad.plan(context)
    records = list(ad.normalize(payload(tiger_req, [{"type": "Feature", "properties": {"GEOID": GEOID},
                                                   "geometry": geometry(BASE)}])))
    records.extend(ad.normalize(payload(req, features)))
    return ad.finalize(records)[0]


@pytest.mark.parametrize("zone", ["A", "AE", "AH", "AO", "AR", "A99", "V", "VE"])
def test_sfha_uses_fema_flag(zone):
    row = feature(BASE, zone=zone, sfha="T")["properties"]
    assert flood.classify(row) == {"mapped": True, "sfha": True, "annual_02": False}
    row["SFHA_TF"] = "F"
    assert flood.classify(row)["sfha"] is False  # Never infer SFHA from the zone alone.


@pytest.mark.parametrize("suffix", ["", " CONTAINED IN CHANNEL", " WITH LEVEE"])
def test_point_two_phrase_variants(suffix):
    row = feature(BASE, subtype=flood.PHRASE_02 + suffix)["properties"]
    assert flood.classify(row) == {"mapped": True, "sfha": False, "annual_02": True}


@pytest.mark.parametrize(("zone", "subtype", "flag", "mapped", "annual_02"), [
    ("X", None, "F", True, False), ("X", "AREA OF MINIMAL FLOOD HAZARD", "F", True, False),
    ("X", "0.2 PCT ANNUAL CHANCE", "F", True, False),
    ("AE", flood.PHRASE_02, "F", True, False),
    ("X", flood.PHRASE_02, "T", True, False),
    ("D", None, "F", True, False), ("AREA NOT INCLUDED", None, "F", False, False),
])
def test_mapped_and_non_hazard_classification(zone, subtype, flag, mapped, annual_02):
    result = flood.classify(feature(BASE, zone=zone, subtype=subtype, sfha=flag)["properties"])
    assert result["mapped"] is mapped and result["annual_02"] is annual_02


def test_overlap_union_and_sfha_exclusion(context):
    rec = summarize(context, [feature(BASE), feature(portion(0, .3), zone="AE", sfha="T"),
        feature(portion(.2, .45), zone="A", sfha="T"),
        feature(portion(.4, .7), subtype=flood.PHRASE_02),
        feature(portion(.65, .8), subtype=flood.PHRASE_02 + " WITH LEVEE")])
    assert rec.properties["flood_share_1pct"] == .45
    assert rec.properties["flood_share_02pct"] == .35  # .40 union minus .05 overlapping SFHA.
    assert rec.properties["mapped_share"] == 1


@pytest.mark.parametrize(("coverage", "available", "rounded"), [
    (.98, False, .98), (.98949, False, .989), (.9896, False, .99),
    (.989999, False, .99), (.99, True, .99), (.990001, True, .99), (1, True, 1),
])
def test_coverage_gate_before_rounding(context, coverage, available, rounded):
    rec = summarize(context, [feature(portion(0, coverage)),
        feature(portion(coverage, 1), zone="AREA NOT INCLUDED") if coverage < 1 else feature(BASE),
        feature(portion(0, .1), zone="AE", sfha="T")])
    props = rec.properties
    assert props["mapped_share"] == rounded
    if available:
        assert props["flood_share_1pct"] == .1 and props["flood_share_02pct"] == 0
    else:
        assert props["flood_share_1pct"] is None and props["flood_share_02pct"] is None
        assert props["flood_note"] == flood.MISSING_COVERAGE


def test_fully_mapped_zero_is_distinct_from_missing_coverage(context):
    zero = summarize(context, [feature(BASE, zone="D")]).properties
    missing = summarize(context, []).properties
    assert zero["mapped_share"] == 1 and zero["flood_share_1pct"] == zero["flood_share_02pct"] == 0
    assert missing["mapped_share"] == 0 and missing["flood_share_1pct"] is None
    assert missing["flood_share_02pct"] is None and missing["flood_note"] == flood.MISSING_COVERAGE


def test_rounding_and_whole_polygon_denominator(context):
    props = summarize(context, [feature(BASE), feature(portion(0, .12349), zone="AE", sfha="T"),
        feature(portion(.5, .73456), subtype=flood.PHRASE_02)]).properties
    assert props["flood_share_1pct"] == .123 and props["flood_share_02pct"] == .235


def test_polygon_holes_reduce_coverage(context):
    ring = BASE.difference(box(X + 200, Y + 200, X + 800, Y + 800))
    props = summarize(context, [feature(ring)]).properties
    assert props["mapped_share"] == .64 and props["flood_share_1pct"] is None


def test_versions_are_distinct_sorted_and_only_touching(context):
    rec = summarize(context, [feature(BASE, version="3.0"), feature(BASE, version="1.0"),
        feature(portion(.2, .4), version="3.0"),
        feature(box(X + 1000, Y, X + 2000, Y + 1000), zone="AREA NOT INCLUDED", version="2.0"),
        feature(box(X + 3000, Y, X + 4000, Y + 1000), version="not-touching")])
    assert rec.properties["effective_versions"] == "1.0,2.0,3.0"
    assert rec.properties["fema_map_link"] == "https://msc.fema.gov/portal/search"
    assert rec.source_as_of is None and flood.FemaNFHL().source_as_of([]) is None
    assert rec.dataset == "block_group" and rec.feature_id == rec.properties["geoid"] == GEOID
    assert set(rec.properties) == {"geoid", "flood_share_1pct", "flood_share_02pct", "mapped_share",
                                   "flood_note", "effective_versions", "fema_map_link"}
    assert shape(rec.geometry).is_valid
    assert all(value == round(value, 6) for ring in rec.geometry["coordinates"] for point in ring for value in point)


def test_invalid_fema_polygon_is_repaired():
    bow = Polygon([(-97, 30), (-96, 31), (-96, 30), (-97, 31), (-97, 30)])
    assert not bow.is_valid
    repaired = flood.fema_polygon(mapping(bow))
    assert repaired.is_valid and repaired.area == pytest.approx(.5)
    assert len(flood.polygon_parts(repaired)) == 2


def test_geometry_collections_keep_nested_polygonal_parts():
    geom = GeometryCollection([LineString([(-97, 30), (-96, 31)]), GeometryCollection([
        box(-97, 30, -96.9, 30.1), MultiPolygon([box(-96.8, 30, -96.7, 30.1)])])])
    result = flood.fema_polygon(mapping(geom))
    assert result.is_valid and result.area == pytest.approx(.02)


@pytest.mark.parametrize("doc", [None, {}, {"type": "Point", "coordinates": [-97, 30]},
    {"type": "LineString", "coordinates": [[-97, 30], [-97, 31]]},
    {"type": "Polygon", "coordinates": []}, mapping(box(200, 30, 201, 31))])
def test_unusable_fema_geometry_is_skipped(doc):
    assert flood.fema_polygon(doc) is None


def test_skips_are_counted_without_dumping_source_rows(context, capsys):
    req = flood.FemaNFHL().page_request(0)
    good = feature(BASE)
    bad = copy.deepcopy(good)
    bad["geometry"] = None
    records = list(flood.FemaNFHL().normalize(payload(req, [good, bad, bad])))
    assert len(records) == 1
    error = capsys.readouterr().err
    assert "skipped 2 rows without usable polygon geometry" in error
    assert "DFIRM_ID" not in error and "SYNTHETIC" not in error


def test_plan_and_two_page_follow_up(context):
    ad = flood.FemaNFHL()
    requests = ad.plan(context)
    assert [req.key for req in requests] == ["block_groups", "nfhl_0"]
    assert requests[0].params["url"] == flood.TIGER
    assert requests[0].params["query"] == {"where": "STATE='48' AND COUNTY IN ('453','491','209')",
        "outFields": "GEOID", "outSR": 4326, "f": "geojson", "returnGeometry": "true"}
    query = requests[1].params["query"]
    assert requests[1].params["url"] == flood.FEMA
    assert query == {"where": "1=1", "geometry": ",".join(map(str, config.app_config().study_bbox)),
        "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,DFIRM_ID,VERSION_ID", "outSR": 4326, "f": "geojson",
        "returnGeometry": "true", "maxAllowableOffset": .00005, "orderByFields": "OBJECTID",
        "resultOffset": 0, "resultRecordCount": 1000}
    first = adapter.read_fixture("fema_nfhl", requests[1])
    assert len(first.body["features"]) < 1000  # The flag, not the row count, controls paging.
    extra = ad.follow_up(first, context)
    assert [req.key for req in extra] == ["nfhl_1000"]
    assert extra[0].params["query"]["resultOffset"] == 1000
    assert ad.follow_up(adapter.read_fixture("fema_nfhl", extra[0]), context) == []


def test_nested_transfer_flag_and_full_final_page(context):
    ad = flood.FemaNFHL()
    req = ad.page_request(0)
    raw = payload(req, [feature(BASE)])
    del raw.body["exceededTransferLimit"]
    raw.body["properties"] = {"exceededTransferLimit": True}
    assert ad.follow_up(raw, context)[0].key == "nfhl_1000"
    assert ad.follow_up(payload(req, [feature(BASE)] * 1000), context) == []


@pytest.mark.parametrize(("offset", "more"), [(0, True), (1000, False), (1000, True)])
def test_empty_promised_page_fails(context, offset, more):
    ad = flood.FemaNFHL()
    with pytest.raises(ValueError, match="more features were promised"):
        ad.follow_up(payload(ad.page_request(offset), [], more), context)


@pytest.mark.parametrize("issue", ["status", "not_geojson", "missing_features", "missing_fields", "not_feature",
                                   "bad_flag", "too_many", "bad_classification"])
def test_bad_fema_responses_fail(context, issue):
    ad = flood.FemaNFHL()
    raw = payload(ad.page_request(0), [feature(BASE)])
    status = 200
    if issue == "status":
        status = 503
    elif issue == "not_geojson":
        raw.body["type"] = "not geojson"
    elif issue == "missing_features":
        del raw.body["features"]
    elif issue == "missing_fields":
        del raw.body["features"][0]["properties"]["SFHA_TF"]
    elif issue == "not_feature":
        raw.body["features"][0]["type"] = "Polygon"
    elif issue == "bad_flag":
        raw.body["exceededTransferLimit"] = "true"
    elif issue == "too_many":
        raw.body["features"] *= 1001
    else:
        raw.body["features"][0]["properties"]["SFHA_TF"] = "unknown"
    with pytest.raises(ValueError):
        list(ad.normalize(RawPayload(raw.request, raw.body, status)))


def test_extra_source_fields_never_reach_canonical_or_published_properties(context):
    ad = flood.FemaNFHL()
    req = ad.page_request(0)
    row = feature(BASE)
    row["properties"].update(OBJECTID=1, OWNER_NAME="Never publish")
    records = list(ad.normalize(payload(req, [row])))
    assert all("OWNER_NAME" not in rec.model_dump_json() and "DFIRM_ID" not in rec.model_dump_json() for rec in records)


@pytest.mark.parametrize("issue", ["missing", "null_geometry", "invalid_geometry", "wrong_geoid", "transfer", "duplicate"])
def test_missing_or_invalid_tiger_boundary_fails(context, issue):
    ad = flood.FemaNFHL()
    req = ad.plan(context)[0]
    rows = [{"type": "Feature", "properties": {"GEOID": GEOID}, "geometry": geometry(BASE)}]
    more = False
    if issue == "missing":
        rows = []
    elif issue == "null_geometry":
        rows[0]["geometry"] = None
    elif issue == "invalid_geometry":
        rows[0]["geometry"] = {"type": "Polygon", "coordinates": [
            [[-97, 30], [-96, 31], [-96, 30], [-97, 31], [-97, 30]]]}
    elif issue == "wrong_geoid":
        rows[0]["properties"]["GEOID"] = "48453010804"
    elif issue == "transfer":
        more = True
    else:
        rows *= 2
    with pytest.raises(ValueError):
        ad.finalize(list(ad.normalize(payload(req, rows, more))))
    with pytest.raises(ValueError, match="no TIGER"):
        ad.finalize([])


def test_fetch_mocked_transport_only(context, monkeypatch):
    class Response(BytesIO):
        status = 200
        headers: dict = {}
    def response(request, timeout):
        assert timeout == 90 and request.get_header("User-agent") == flood.FemaNFHL.user_agent
        assert request.get_header("Accept-encoding") == "gzip"
        assert request.full_url.startswith(flood.FEMA + "?") and "resultOffset=1000" in request.full_url
        return Response(b'{"type":"FeatureCollection","features":[]}')
    monkeypatch.setattr("urllib.request.urlopen", response)
    ad = flood.FemaNFHL()
    raw = ad.fetch(ad.page_request(1000), context)
    assert raw.status == 200 and raw.fetched_at is not None and raw.body["features"] == []
    def gzipped(request, timeout):
        r = Response(gzip.compress(b'{"type":"FeatureCollection","features":[]}'))
        r.headers = {"Content-Encoding": "gzip"}
        return r
    monkeypatch.setattr("urllib.request.urlopen", gzipped)
    assert ad.fetch(ad.page_request(1000), context).body["type"] == "FeatureCollection"
    def error(*args, **kwargs):
        raise urllib.error.HTTPError(flood.FEMA, 503, "Unavailable", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", error)
    raw = ad.fetch(ad.page_request(0), context)
    with pytest.raises(ValueError, match="HTTP 503"):
        ad.follow_up(raw, context)


def test_fixture_publication_is_only_block_groups_and_test_data(context):
    run = runner.run("fema_nfhl", now=NOW)
    assert run.status == "success", run.errors
    assert run.calls_made == 0 and run.planned_calls == 3 and run.rows_out == 5
    root = context.adapter_dir.parents[1]
    output = root / "web/public/data/layers/flood_share.geojson"
    doc = json.loads(output.read_text())
    assert doc["test_data"] is True and doc["source_as_of"] is None
    features = {f["id"]: f for f in doc["features"]}
    assert set(features) == {"484530108041", "484910108041", "482090108041"}
    assert features["484530108041"]["properties"]["flood_share_1pct"] == .45
    assert features["484530108041"]["properties"]["flood_share_02pct"] == .35
    assert features["484910108041"]["properties"]["flood_share_1pct"] == 0
    assert features["482090108041"]["properties"]["flood_share_1pct"] is None
    assert features["482090108041"]["properties"]["mapped_share"] == .95
    assert features["482090108041"]["properties"]["effective_versions"] == "5.0,6.0"
    assert [p.name for p in output.parent.glob("*.geojson")] == ["flood_share.geojson"]
    assert not any(field in output.read_text() for field in flood.FIELDS)
    layer = next(layer for layer in registry.compile_registry().layers if layer.source == "fema_nfhl")
    assert layer.freshness == "fixture_only" and layer.as_of == run.finished_at.date().isoformat()  # fixture run date
    assert layer.join == layer.dataset == "block_group" and layer.group == "Flood"
    assert layer.style.type == "fill" and not layer.default_visible and layer.refresh == "monthly"
    assert layer.description == ("Share of each area inside FEMA's mapped flood zones. Not a prediction of "
        "flooding at any address; local and Atlas 14 floodplains may be larger.")
    assert layer.attribution == "FEMA National Flood Hazard Layer" and layer.license == "Public domain"
    assert [entry.label for entry in layer.legend] == ["None", "Under 5%", "5–15%", "15–30%", "30% or more", "Not available"]
    assert [entry.color for entry in layer.legend] == ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c", "#bdbdbd"]
    assert [field.field for field in layer.popup] == ["flood_share_1pct", "flood_share_02pct", "mapped_share", "flood_note", "fema_map_link", "geoid"]
    assert layer.popup[4].format == "link"
    assert layer.style.paint["fill-color"][:3] == ["case", ["==", ["get", "flood_share_1pct"], None], "#bdbdbd"]


@pytest.mark.parametrize("issue", ["empty", "not_geojson"])
def test_bad_later_page_preserves_previous_published_layer(context, issue):
    assert runner.run("fema_nfhl", now=NOW).status == "success"
    root = context.adapter_dir.parents[1]
    output = root / "web/public/data/layers/flood_share.geojson"
    previous = output.read_bytes()
    body = {"type": "FeatureCollection", "features": [], "exceededTransferLimit": False} if issue == "empty" else {"error": "source down"}
    (context.adapter_dir / "fixtures/nfhl_1000.json").write_text(json.dumps({"status": 200, "body": body}))
    run = runner.run("fema_nfhl", now=NOW)
    assert run.status == "failed" and output.read_bytes() == previous


def test_budget_and_live_gate(context, monkeypatch):
    limits = config.budgets().adapters["fema_nfhl"]
    assert limits.per_day == 40 and limits.min_interval_seconds == 15 and limits.max_minutes == 20
    assert flood.FemaNFHL.retry_wait_seconds == 60
    # Ungated after Claude's first live check (run 40012121921, DECISIONS 2026-10-23).
    gates = yaml.safe_load((ROOT / "config/live_gates.yaml").read_text()).get("gated") or {}
    assert "fema_nfhl" not in gates


def test_hazard_slivers_are_repaired_or_skipped():
    # A bow-tie repairs to two triangles with area; a degenerate sliver is skipped.
    bowtie = Polygon([(-97.7, 30.3), (-97.69, 30.31), (-97.69, 30.3), (-97.7, 30.31), (-97.7, 30.3)])
    fixed = flood.hazard_area_polygon(bowtie)
    assert fixed is not None and fixed.is_valid and fixed.area > 0
    point_like = Polygon([(-97.7, 30.3), (-97.7, 30.3), (-97.7, 30.3), (-97.7, 30.3)])
    assert flood.hazard_area_polygon(point_like) is None
