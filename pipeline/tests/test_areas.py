"""Naming, source validation and fixture publication; all polygons are synthetic."""

import copy
import importlib.util
import json
import urllib.error
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import MultiPolygon, box, mapping, shape

from mm import adapter, config, registry, runner
from mm.adapter import RawPayload, Request, RunContext
from mm.budget import CallBudget

MODULE_PATH = Path(__file__).resolve().parents[2] / "adapters/areas/adapter.py"
spec = importlib.util.spec_from_file_location("test_areas_adapter", MODULE_PATH)
areas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(areas)
NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
X, Y = Transformer.from_crs(4326, 5070, always_xy=True).transform(-97.78, 30.27)
BASE = box(X, Y, X + 1000, Y + 1000)


def geometry(geom):
    return mapping(areas.reproject(geom, areas.TO_WGS84))


def feature(kind, geom=BASE, county="491", name="Synthetic Name", suffix="1"):
    if kind in {"block_group", "tract"}:
        row = dict(GEOID="48" + county + "010804" + (suffix if kind == "block_group" else ""),
                   STATE="48", COUNTY=county, TRACT="010804", AREALAND=0, AREAWATER=0)
        if kind == "block_group":
            row["BLKGRP"] = suffix
    elif kind == "austin":
        row = {"PLANNING_AREA_NAME": name}
    elif kind == "wcad":
        row = dict(name=name, scode="TEST001", type="SUB", filedate="2020-01-01T00:00:00")
    else:
        row = dict(GEOID="4800001", NAME=name, BASENAME=name, LSADC="25")
    return {"type": "Feature", "properties": row,
            "geometry": geometry(MultiPolygon([geom]) if kind == "wcad" else geom)}


def payload(kind, features):
    return RawPayload(Request(kind, {"kind": kind}), {"type": "FeatureCollection", "features": features})


def portion(share):
    return box(X, Y, X + 1000 * share, Y + 1000)


def named(ad, county="491", austin=None, wcad=None, place=None):
    inputs = list(ad.normalize(payload("block_group", [feature("block_group", county=county)])))
    for kind, share in (("austin", austin), ("wcad", wcad), ("place", place)):
        rows = [] if share is None else [feature(kind, portion(share) if share else box(X - 2000, Y, X - 1000, Y + 1000), name={
            "austin": "Test Austin Plan", "wcad": "TEST CREEK SEC 3", "place": "Testville"
        }[kind])]
        inputs.extend(ad.normalize(payload(kind, rows)))
    return ad.finalize(inputs)[0]


@pytest.fixture
def ad(repo):
    result = areas.Areas()
    result.names_as_of = NOW.date()
    return result


def context():
    return RunContext("fixture", NOW, CallBudget.for_adapter("areas"), MODULE_PATH.parent)


@pytest.mark.parametrize(("original", "expected"), [
    ("AVERY RANCH SEC 3", "Avery Ranch"),
    ("AVERY RANCH SECTION 3B", "Avery Ranch"),
    ("TERAVISTA PH 2", "Teravista"),
    ("TERAVISTA PHASE II", "Teravista"),
    ("SONOMA UNIT 4", "Sonoma"),
    ("BRUSHY CREEK AMENDED", "Brushy Creek"),
    ("FOREST CREEK REPLAT", "Forest Creek"),
    ("PALOMA LAKE REVISED", "Paloma Lake"),
    ("VISTA OAKS RESUB", "Vista Oaks"),
    ("  RANCHO   SIENNA SEC 3 PHASE II REPLAT ", "Rancho Sienna"),
    ("BLOCK HOUSE CREEK, SECTION 3B", "Block House Creek"),
    ("SANTA RITA RANCH SEC. 5", "Santa Rita Ranch"),
    ("SECTION HOUSE", "Section House"),
    ("PHASE TWO RANCH", "Phase Two Ranch"),
])
def test_clean_subdivision_names(original, expected):
    assert areas.clean_subdivision_name(original) == expected


@pytest.mark.parametrize(("share", "expected"), [(.49999, "Test Creek"), (.5, "Test Austin Plan"),
                                                       (.50001, "Test Austin Plan"), (.6, "Test Austin Plan")])
def test_austin_precedence_and_half_edge(ad, share, expected):
    record = named(ad, austin=share, wcad=.8, place=1)
    assert record.properties["name"] == expected
    assert record.properties["name_source"] == ("WCAD subdivision" if share < .5 else
                                                 "City of Austin neighborhood planning area")


@pytest.mark.parametrize(("share", "expected"), [(.39999, "Testville"), (.4, "Test Creek"),
                                                       (.40001, "Test Creek"), (.45, "Test Creek"),
                                                       (.35, "Testville")])
def test_wcad_forty_percent_edge(ad, share, expected):
    assert named(ad, wcad=share, place=.7).properties["name"] == expected


@pytest.mark.parametrize("county", ["453", "209"])
def test_wcad_is_only_for_williamson(ad, county):
    rec = named(ad, county=county, wcad=1, place=.25)
    assert rec.properties["name"] == "Near Testville"
    assert rec.properties["name_source"] == "Census place"


@pytest.mark.parametrize(("share", "expected"), [(0, "Williamson County area 010804.1"),
    (.0001, "Near Testville"), (.4999, "Near Testville"), (.5, "Testville"), (.50001, "Testville")])
def test_place_half_edge_uses_unrounded_share(ad, share, expected):
    rec = named(ad, place=share)
    assert rec.properties["name"] == expected
    assert rec.properties["name_share"] == (round(share, 3) if share else None)


def test_empty_naming_sources_and_fallback(ad):
    rec = named(ad, county="209")
    assert rec.properties["name"] == "Hays County area 010804.1"
    assert rec.properties["name_source"] == "Census block group"
    assert rec.properties["name_share"] is None


def test_grouped_plats_union_overlap_and_choose_largest(ad):
    records = list(ad.normalize(payload("block_group", [feature("block_group")])))
    rows = [feature("wcad", portion(.25), name="TEST CREEK SEC 1"),
            feature("wcad", box(X + 250, Y, X + 450, Y + 1000), name="TEST CREEK PH 2"),
            feature("wcad", portion(.25), name="TEST CREEK REPLAT"),
            feature("wcad", portion(.42), name="OTHER PLACE")]
    records.extend(ad.normalize(payload("wcad", rows)))
    rec = ad.finalize(records)[0]
    assert rec.properties["name"] == "Test Creek"
    assert rec.properties["name_share"] == .45
    # Repeated 25% plats must not pass 40% just because they overlap.
    records = records[:1] + list(ad.normalize(payload("wcad", [rows[0], rows[2]])))
    assert ad.finalize(records)[0].properties["name_source"] == "Census block group"


def test_largest_place_and_tie_are_deterministic(ad):
    records = list(ad.normalize(payload("block_group", [feature("block_group")])))
    records.extend(ad.normalize(payload("place", [feature("place", portion(.3), name="Z Testville"),
                                                    feature("place", portion(.7), name="A Testville")])))
    assert ad.finalize(records)[0].properties["name"] == "A Testville"
    tied = list(ad.normalize(payload("place", [feature("place", portion(.7), name="Z Testville"),
                                                 feature("place", portion(.7), name="A Testville")])))
    assert ad.finalize([records[0], *tied])[0].properties["name"] == "A Testville"


@pytest.mark.parametrize("kind", ["austin", "place"])
def test_only_wcad_names_are_grouped(ad, kind):
    records = list(ad.normalize(payload("block_group", [feature("block_group")])))
    rows = [feature(kind, portion(.3), name="Same Name"),
            feature(kind, box(X + 300, Y, X + 600, Y + 1000), name="Same Name")]
    records.extend(ad.normalize(payload(kind, rows)))
    rec = ad.finalize(records)[0]
    if kind == "austin":
        assert rec.properties["name_source"] == "Census block group"
    else:
        assert rec.properties["name"] == "Near Same Name"
        assert rec.properties["name_share"] == .3


def test_published_contract_area_precision_and_dates(ad):
    record = named(ad, austin=.6)
    props = record.properties
    assert record.dataset == "block_group" and record.feature_id == "484910108041"
    assert props["tract"] == "010804" and props["county"] == "Williamson"
    assert props["area_sq_mi"] == round(1_000_000 / 1609.344 ** 2, 3)
    assert props["name_share"] == .6
    assert props["boundary_note"] == "2020 Census boundaries; names as of 2026-10-23"
    assert record.source_as_of.isoformat() == "2020-01-01"
    assert ad.source_as_of([]).isoformat() == "2020-01-01"
    assert set(props) == {"geoid", "county", "tract", "name", "name_source", "name_share",
                          "area_sq_mi", "boundary_note"}
    assert shape(record.geometry).is_valid
    for ring in record.geometry["coordinates"]:
        for point in ring:
            assert all(v == round(v, 6) for v in point)
    tract = ad.finalize(list(ad.normalize(payload("tract", [feature("tract")]))))[0]
    assert tract.dataset == "tract" and tract.feature_id == "48491010804"
    assert set(tract.properties) == {"geoid", "county", "area_sq_mi"}


def test_plan_exact_endpoints_fields_and_paging(ad):
    requests = ad.plan(context())
    assert len(requests) == 10
    for kind, layer in (("block_group", 8), ("tract", 6)):
        for county in ("453", "491", "209"):
            req = next(req for req in requests if req.key == f"{kind}_{county}")
            assert req.params["url"] == f"{areas.TIGER}/{layer}/query"
            assert req.params["query"] == {
                "where": f"STATE='48' AND COUNTY='{county}'", "outFields": areas.FIELDS[kind],
                "outSR": 4326, "f": "geojson", "returnGeometry": "true"}
    for layer in (26, 28):
        req = next(req for req in requests if req.key == f"place_{layer}")
        assert req.params["url"] == f"{areas.TIGER}/{layer}/query"
        assert req.params["query"]["geometry"] == ",".join(map(str, config.app_config().study_bbox))
        assert req.params["query"]["outFields"] == "GEOID,NAME,BASENAME,LSADC"
        assert req.params["query"]["geometryType"] == "esriGeometryEnvelope"
    assert next(req for req in requests if req.key == "austin").params["url"] == areas.AUSTIN
    first = requests[-1]
    assert first.params["url"] == areas.WCAD
    assert first.params["query"] == {"$select": "name,scode,type,filedate,geometry",
        "$order": "scode", "$limit": 2000, "$offset": 0}
    raw = adapter.read_fixture("areas", first)
    assert len(raw.body["features"]) == 2000
    extra = ad.follow_up(raw, context())
    assert [req.key for req in extra] == ["wcad_2000"]
    assert extra[0].params["query"]["$offset"] == 2000
    second = adapter.read_fixture("areas", extra[0])
    assert 0 < len(second.body["features"]) < 2000
    assert ad.follow_up(second, context()) == []


@pytest.mark.parametrize("failure", ["status", "not_geojson", "missing_features", "transfer",
    "nested_transfer", "missing_field", "point", "null_geometry", "invalid_polygon"])
def test_bad_responses_fail_closed(ad, failure):
    """Census boundaries are strict: any bad response or geometry fails the run."""
    raw = payload("block_group", [feature("block_group")])
    body = copy.deepcopy(raw.body)
    status = 200
    if failure == "status":
        status = 503
    elif failure == "not_geojson":
        body = {"error": {"message": "service unavailable"}}
    elif failure == "missing_features":
        del body["features"]
    elif failure == "transfer":
        body["exceededTransferLimit"] = True
    elif failure == "nested_transfer":
        body["properties"] = {"exceededTransferLimit": True}
    elif failure == "missing_field":
        body["features"][0]["properties"] = {}
    elif failure == "extra_field":
        body["features"][0]["properties"]["OWNER_NAME"] = "Never publish"
    elif failure == "point":
        body["features"][0]["geometry"] = {"type": "Point", "coordinates": [-97, 30]}
    elif failure == "null_geometry":
        body["features"][0]["geometry"] = None
    else:
        body["features"][0]["geometry"] = {"type": "Polygon", "coordinates": [
            [[-97, 30], [-96, 31], [-96, 30], [-97, 31], [-97, 30]]]}
    with pytest.raises((ValueError, AttributeError)):
        list(ad.normalize(RawPayload(raw.request, body, status)))


def test_duplicate_boundaries_rejected(ad):
    rows = list(ad.normalize(payload("block_group", [feature("block_group"), feature("block_group")])))
    with pytest.raises(ValueError, match="duplicate boundary"):
        ad.finalize(rows)


def test_fetch_http_error_becomes_failed_response(ad, monkeypatch):
    def error(*args, **kwargs):
        raise urllib.error.HTTPError(areas.AUSTIN, 503, "Unavailable", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", error)
    req = next(req for req in ad.plan(context()) if req.key == "austin")
    raw = ad.fetch(req, context())
    assert raw.status == 503
    with pytest.raises(ValueError, match="HTTP 503"):
        ad.follow_up(raw, context())


def test_fetch_uses_request_query_and_user_agent(ad, monkeypatch):
    class Response(BytesIO):
        status = 200
    def response(request, timeout):
        assert request.full_url.startswith(areas.WCAD + "?")
        assert "%24offset=2000" in request.full_url and "%24order=scode" in request.full_url
        assert request.get_header("User-agent") == ad.user_agent
        assert timeout == 90
        return Response(b'{"type":"FeatureCollection","features":[]}')
    monkeypatch.setattr("urllib.request.urlopen", response)
    raw = ad.fetch(ad.wcad_request(2000), context())
    assert raw.status == 200 and raw.fetched_at is not None
    assert ad.follow_up(raw, context()) == []


def test_fixtures_publish_only_boundaries_and_show_test_data(repo):
    run = runner.run("areas", now=NOW)
    assert run.status == "success", run.errors
    assert run.calls_made == 0 and run.planned_calls == 11 and run.rows_out == 7
    reg = registry.compile_registry()
    layers = {layer.id: layer for layer in reg.layers if layer.source == "areas"}
    assert set(layers) == {"block_groups", "tracts"}
    block = layers["block_groups"]
    assert block.group == "Areas" and block.join == "block_group" and block.order == 10
    assert block.default_visible and block.refresh == "annual" and block.style.type == "line"
    assert "City of Austin" in block.attribution and "Williamson Central Appraisal District" in block.attribution
    assert block.disclaimer == ("This product is for informational purposes and may not have been "
                                "prepared for or be suitable for legal, engineering, or surveying purposes.")
    assert not layers["tracts"].default_visible and layers["tracts"].order == 11
    assert layers["tracts"].refresh == "annual"
    documents = {}
    for key, layer in layers.items():
        assert layer.freshness == "fixture_only" and layer.as_of == "2020-01-01"
        doc = json.loads((repo / "web/public" / layer.data_url).read_text())
        assert doc["test_data"] is True and doc["source_as_of"] == "2020-01-01"
        assert all(f["geometry"]["type"] in {"Polygon", "MultiPolygon"} for f in doc["features"])
        documents[key] = doc
    props = [feature["properties"] for feature in documents["block_groups"]["features"]]
    assert {row["county"] for row in props} == {"Travis", "Williamson", "Hays"}
    assert {row["name_source"] for row in props} == {"City of Austin neighborhood planning area",
        "WCAD subdivision", "Census place", "Census block group"}
    assert any(row["name_share"] == .45 and row["name_source"] == "WCAD subdivision" for row in props)
    assert any(row["name"] == "Near Test CDP" for row in props)
    assert any(row["name"] == "Testville" and row["name_source"] == "Census place" for row in props)


def test_bad_later_page_preserves_last_published_layers(repo):
    assert runner.run("areas", now=NOW).status == "success"
    files = list((repo / "web/public/data/layers").glob("*.geojson"))
    before = {p: p.read_bytes() for p in files}
    path = repo / "adapters/areas/fixtures/wcad_2000.json"
    path.write_text('{"status":200,"body":{"type":"FeatureCollection","features":[],"exceededTransferLimit":true}}')
    run = runner.run("areas", now=NOW)
    assert run.status == "failed" and "exceededTransferLimit" in " ".join(run.errors)
    assert {p: p.read_bytes() for p in files} == before


def test_budget_and_repo_live_gate(repo):
    b = config.budgets().adapters["areas"]
    assert b.per_day == 20 and b.min_interval_seconds == 1
    # Core fixture clears gates; restore the actual repository gate for this check.
    gate_path = MODULE_PATH.parents[2] / "config/live_gates.yaml"
    (repo / "config/live_gates.yaml").write_text(gate_path.read_text())
    config.clear_cache()
    run = runner.run("areas", mode="live", now=NOW)
    assert run.status == "skipped" and run.calls_made == 0
    assert "awaiting Claude's first live check" in " ".join(run.notes)


def test_extra_fields_are_ignored_and_never_published(ad):
    raw = payload("austin", [feature("austin")])
    raw.body["features"][0]["properties"]["OBJECTID"] = 7
    raw.body["features"][0]["properties"]["OWNER_NAME"] = "Never publish"
    [rec] = list(ad.normalize(raw))
    assert set(rec.properties) == {"kind", "name"}


def test_naming_polygons_are_repaired_or_skipped(ad):
    bowtie = {"type": "Polygon", "coordinates": [[[-97, 30], [-96, 31], [-96, 30], [-97, 31], [-97, 30]]]}
    good, bad, null, point = (feature("austin") for _ in range(4))
    bad["geometry"], null["geometry"] = bowtie, None
    point["geometry"] = {"type": "Point", "coordinates": [-97, 30]}
    rows = list(ad.normalize(payload("austin", [good, bad, null, point])))
    assert len(rows) == 2  # the good one and the repaired bow-tie
    from shapely.geometry import shape
    assert all(shape(r.geometry).is_valid and shape(r.geometry).area > 0 for r in rows)
