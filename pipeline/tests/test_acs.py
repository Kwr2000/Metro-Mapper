"""ACS math, strict joins, credential hygiene and generated manifests; no live sources."""

import copy
import importlib.util
import json
import math
import re
import subprocess
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest

from mm import adapter, config, inputs, registry, runner
from mm.adapter import RawPayload, RunContext
from mm.budget import CallBudget
from mm.manifests import load_layers

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("acs_under_test", ROOT / "adapters/acs/adapter.py")
acs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(acs)
NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
# Deliberately fake, supplied only by tests at the transport boundary.
TOKEN = "synthetic-test-credential"


@pytest.fixture
def context(repo):
    return RunContext("fixture", NOW, CallBudget.for_adapter("acs", NOW), repo / "adapters/acs")


def fixtures(context):
    return [adapter.read_fixture("acs", req) for req in acs.ACS().plan(context)]


def normalized(context):
    ad = acs.ACS()
    return [rec for raw in fixtures(context) for rec in ad.normalize(raw)]


def cells(**overrides):
    source = {
        "B25003_002": {"estimate": 40, "moe": 5, "estimate_annotation": None, "moe_annotation": None},
        "B25003_001": {"estimate": 100, "moe": 3, "estimate_annotation": None, "moe_annotation": None},
        "B11003_003": {"estimate": 10, "moe": 3, "estimate_annotation": None, "moe_annotation": None},
        "B11003_010": {"estimate": 20, "moe": 4, "estimate_annotation": None, "moe_annotation": None},
        "B11003_016": {"estimate": 30, "moe": 12, "estimate_annotation": None, "moe_annotation": None},
        "B11003_001": {"estimate": 200, "moe": 10, "estimate_annotation": None, "moe_annotation": None},
    }
    for key, values in overrides.items():
        source.setdefault(key, {"estimate": None, "moe": None, "estimate_annotation": None,
                                "moe_annotation": None}).update(values)
    return {acs.CELL_IDS[base]: value for base, value in source.items()}


@pytest.mark.parametrize("value", [None, "", " ", "(X)", "bad", "250,000+", "NaN", "inf", float("nan"),
    "-666666666", "-222222222", "-1", -5, True, [], {}])
def test_sentinels_and_non_numeric_are_null(value):
    assert acs.number(value) is None


@pytest.mark.parametrize(("value", "expected"), [("0", 0), ("12.5", 12.5), (" 42 ", 42), (2, 2)])
def test_numeric_cells_preserve_zero_and_fraction(value, expected):
    assert acs.number(value) == expected


@pytest.mark.parametrize(("estimate", "moe", "flag"), [
    (100, 30, "MOE ≤30% of estimate"), (100, 30.0001, "low reliability"),
    (100, 29.9999, "MOE ≤30% of estimate"), (0, 1, "low reliability"),
    (0, 0, "MOE ≤30% of estimate"), (0, None, "reliability unknown"),
    (100, None, "reliability unknown"), (None, 10, "estimate unavailable"),
    (None, None, "estimate unavailable"),
])
def test_reliability_exact_edges(estimate, moe, flag):
    assert acs.reliability(estimate, moe) == flag


def test_share_moe_subtraction_formula():
    result = acs.measure(cells(), ("B25003_002",), "B25003_001")
    assert result[0] == .4
    assert result[1] == pytest.approx(math.sqrt(5 ** 2 - .4 ** 2 * 3 ** 2) / 100)
    assert result[2] == "MOE ≤30% of estimate"


def test_share_moe_negative_radicand_uses_addition():
    values = cells(B25003_002={"moe": 1}, B25003_001={"moe": 10})
    result = acs.measure(values, ("B25003_002",), "B25003_001")
    assert result[1] == pytest.approx(math.sqrt(1 + .4 ** 2 * 100) / 100)


def test_summed_numerator_moe_is_root_sum_squares():
    result = acs.measure(cells(), ("B11003_003", "B11003_010", "B11003_016"), "B11003_001")
    assert result[0] == .3
    assert result[1] == pytest.approx(math.sqrt(3 ** 2 + 4 ** 2 + 12 ** 2 - .3 ** 2 * 10 ** 2) / 200)


@pytest.mark.parametrize("d", [0, None])
def test_zero_or_missing_denominator_is_unavailable(d):
    result = acs.measure(cells(B25003_001={"estimate": d}), ("B25003_002",), "B25003_001")
    assert result[:3] == (None, None, "estimate unavailable")


@pytest.mark.parametrize("base", ["B25003_002", "B25003_001"])
def test_missing_moe_preserves_estimate_and_unknown_reliability(base):
    values = cells(**{base: {"moe": None}})
    result = acs.measure(values, ("B25003_002",), "B25003_001")
    assert result[:3] == (.4, None, "reliability unknown")


def test_missing_numerator_is_not_partially_summed():
    values = cells(B11003_010={"estimate": None})
    result = acs.measure(values, ("B11003_003", "B11003_010", "B11003_016"), "B11003_001")
    assert result[:3] == (None, None, "estimate unavailable")


def test_share_above_one_fails_instead_of_clamping():
    with pytest.raises(ValueError, match="outside"):
        acs.measure(cells(B25003_002={"estimate": 101}), ("B25003_002",), "B25003_001")


def test_native_annotations_survive_derived_shares():
    values = cells(B25003_002={"estimate_annotation": "(X)", "moe_annotation": "***"},
                   B25003_001={"estimate_annotation": "250,000+", "moe_annotation": "**"})
    result = acs.measure(values, ("B25003_002",), "B25003_001")
    assert result[3] == ("Numerator: Census: not applicable; "
                         "Numerator: Census: no margin of error for an open-ended range; "
                         "Denominator: Census reports a range: 250,000 or more; "
                         "Denominator: Census: margin of error not computed (too few responses)")
    assert result[4] is None  # only a direct median shows a range in place of its value


@pytest.mark.parametrize("ea, ma, fmt, display, note", [
    ("250,000+", "***", "currency", "$250,000 or more", None),
    ("10,000-", "***", "currency", "$10,000 or less", None),
    ("3,500+", "***", "currency", "$3,500 or more", None),
    ("2020+", "***", "number", "2020 or later", None),
    ("1939-", "***", "number", "1939 or earlier", None),
    ("-", "**", "currency", None, "Census: too few survey responses to estimate"),
    ("N", None, "number", None, "Census: not shown (too few cases)"),
    (None, "*****", "number", None, "Census: controlled estimate, no sampling margin of error"),
    ("odd", None, "number", None, "Census note: odd"),
])
def test_census_codes_in_plain_words(ea, ma, fmt, display, note):
    values = cells(B19013_001={"estimate": 250001, "moe": None, "estimate_annotation": ea, "moe_annotation": ma})
    result = acs.measure(values, ("B19013_001",), None, fmt)
    assert result[4] == display and result[3] == note


def test_plan_has_26_calls_and_complete_quartets_without_key(context, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", TOKEN)
    requests = acs.ACS().plan(context)
    assert len(requests) == 26 and len({req.key for req in requests}) == 26
    assert len(acs.metrics.NON_AGE_BASES) == 28
    assert sum(req.params["kind"] == "acs" for req in requests) == 24
    assert TOKEN not in repr(requests) and '"key"' not in json.dumps([req.params for req in requests])
    for req in requests:
        assert (context.adapter_dir / "fixtures" / (req.key + ".json")).is_file()
        query = req.params["query"]
        if req.params["kind"] == "polygons":
            layer = 8 if req.params["scale"] == "block_group" else 6
            assert req.params["url"] == f"{acs.TIGER}/{layer}/query"
            assert query == {"where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID",
                             "outSR": 4326, "f": "geojson", "returnGeometry": "true"}
        else:
            assert req.params["url"] == acs.API
            assert query["for"] == ("block group:*" if req.params["scale"] == "block_group" else "tract:*")
            assert query["in"] == f"state:48 county:{req.params['county']}" + (
                " tract:*" if req.params["scale"] == "block_group" else "")
            if req.params["part"] == "age":
                assert query["get"] == "group(B01001)"
            else:
                variables = query["get"].split(",")
                assert len(variables) <= 50 and len(variables) % 4 == 0
                for i in range(0, len(variables), 4):
                    base = variables[i][:-1]
                    assert variables[i:i + 4] == [base + suffix for suffix in ("E", "M", "EA", "MA")]
    for path in (context.adapter_dir / "fixtures").glob("*.json"):
        text = path.read_text()
        assert TOKEN not in text and "CENSUS_API_KEY" not in text and '"key"' not in text
        if not path.name.startswith("polygons"):
            assert any(re.fullmatch(r"B\d+_\d+EA", field) for field in json.loads(text)["body"][0])


def test_every_metric_uses_the_spec_cells():
    specs = acs.metrics.METRICS
    for metric, ranges in (("under_18_share", (range(3, 7), range(27, 31))),
                           ("age_18_34_share", (range(7, 13), range(31, 37))),
                           ("age_65_plus_share", (range(20, 26), range(44, 50)))):
        assert specs[metric][2] == tuple(f"B01001_{i:03d}" for r in ranges for i in r)
        assert specs[metric][3] == "B01001_001"
    assert specs["family_children_share"][2] == ("B11003_003", "B11003_010", "B11003_016")
    assert specs["bachelors_plus_share"][2] == tuple(f"B15003_{i:03d}" for i in range(22, 26))
    for i, metric in enumerate(("nh_white_share", "nh_black_share", "nh_aian_share", "nh_asian_share",
                               "nh_nhpi_share", "nh_some_other_share", "nh_two_or_more_share"), 3):
        assert specs[metric][2:4] == ((f"B03002_{i:03d}",), "B03002_001")


def test_fixture_values_and_native_annotations(context):
    records = acs.ACS().finalize(normalized(context))
    assert len(records) == 12
    first = next(rec for rec in records if rec.feature_id == "484530108041")
    p = first.properties
    assert p["median_household_income"] == 100000 and p["median_household_income_moe"] == 30000
    assert p["median_household_income_reliability"] == "MOE ≤30% of estimate"
    assert p["median_home_value_reliability"] == "low reliability"
    assert p["median_age_reliability"] == "reliability unknown"
    assert p["owner_occupied_share_moe"] == pytest.approx(math.sqrt(10 ** 2 + .4 ** 2 * 200 ** 2) / 1000)
    second = next(rec for rec in records if rec.feature_id == "484530108042").properties
    assert second["owner_occupied_share"] is None and second["family_children_share"] is None
    assert second["population"] == 0 and second["population_reliability"] == "low reliability"
    assert second["median_household_income"] is None
    assert second["median_household_income_annotation"] == (
        "Census reports a range: 250,000 or more; "
        "Census: margin of error not computed (too few responses)")
    assert second["median_household_income_reliability"] == "estimate unavailable"
    third = next(rec for rec in records if rec.feature_id == "484530108043").properties
    assert third["median_gross_rent"] is None and third["population"] is None
    assert third["median_household_income_moe"] is None
    for rec in records:
        assert rec.source_as_of.isoformat() == "2024-12-31"
        assert rec.dataset in {"block_group", "tract"}
        assert rec.properties["geography"] == acs.metrics.SCALES[rec.dataset]
        assert rec.properties["vintage"] == "ACS 2020–2024 5-year estimates"
        assert not re.search(r"B\d{5}_\d{3}", rec.model_dump_json())


@pytest.mark.parametrize("kind", ["missing_row", "extra_row", "duplicate_row", "duplicate_polygon", "missing_polygon"])
def test_polygon_row_mismatch_and_duplicates_fail(context, kind):
    records = normalized(context)
    row = next(rec for rec in records if rec.dataset == "acs_values")
    polygon = next(rec for rec in records if rec.dataset == "acs_polygons")
    if kind == "missing_row":
        records.remove(row)
    elif kind == "extra_row":
        records.append(row.model_copy(update={"feature_id": "484530108049",
                                              "properties": {**row.properties, "geoid": "484530108049"}}))
    elif kind == "duplicate_row":
        records.append(row)
    elif kind == "duplicate_polygon":
        records.append(polygon)
    else:
        records.remove(polygon)
    with pytest.raises(ValueError, match="mismatch|duplicate"):
        acs.ACS().finalize(records)


@pytest.mark.parametrize("issue", ["html", "missing_header", "duplicate_header", "short_row", "wrong_county", "numeric_geoid"])
def test_bad_acs_response_fails(context, issue):
    raw = next(raw for raw in fixtures(context) if raw.request.params["kind"] == "acs")
    body = copy.deepcopy(raw.body)
    if issue == "html":
        body = "<html>missing_key</html>"
    elif issue == "missing_header":
        body[0][0] = "unknown_variable"
    elif issue == "duplicate_header":
        body[0][0] = body[0][1]
    elif issue == "short_row":
        body[1].pop()
    elif issue == "wrong_county":
        body[1][body[0].index("county")] = "491"
    else:
        body[1][body[0].index("tract")] = 10804
    with pytest.raises(ValueError):
        list(acs.ACS().normalize(RawPayload(raw.request, body)))


@pytest.mark.parametrize("issue", ["not_geojson", "transfer", "invalid", "wrong_geoid"])
def test_bad_polygon_response_fails(context, issue):
    raw = fixtures(context)[0]
    body = copy.deepcopy(raw.body)
    if issue == "not_geojson":
        body = {"error": "unavailable"}
    elif issue == "transfer":
        body["exceededTransferLimit"] = True
    elif issue == "invalid":
        body["features"][0]["geometry"] = {"type": "Point", "coordinates": [-97, 30]}
    else:
        body["features"][0]["properties"]["GEOID"] = "bad"
    with pytest.raises(ValueError):
        list(acs.ACS().normalize(RawPayload(raw.request, body)))


class Response(BytesIO):
    status = 200


def test_fetch_key_only_in_transport_and_nonjson_is_sanitized(context, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", TOKEN)
    req = next(req for req in acs.ACS().plan(context) if req.params["kind"] == "acs")
    before = copy.deepcopy(req.params)
    def response(request, timeout):
        assert timeout == 60 and request.get_header("User-agent") == acs.ACS.user_agent
        assert urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)["key"] == [TOKEN]
        return Response(f"<html>URL key={TOKEN}</html>".encode())
    monkeypatch.setattr("urllib.request.urlopen", response)
    raw = acs.ACS().fetch(req, context)
    assert req.params == before and TOKEN not in repr(raw)
    with pytest.raises(ValueError) as exc:
        list(acs.ACS().normalize(raw))
    assert TOKEN not in str(exc.value)


@pytest.mark.parametrize("issue", ["urlerror", "http", "missing_key"])
def test_fetch_never_echoes_credentials_in_errors(context, monkeypatch, issue):
    monkeypatch.setenv("CENSUS_API_KEY", TOKEN)
    req = next(req for req in acs.ACS().plan(context) if req.params["kind"] == "acs")
    def error(*args, **kwargs):
        if issue == "http":
            raise urllib.error.HTTPError("https://example.test/?key=" + TOKEN, 400, TOKEN, {}, None)
        raise urllib.error.URLError("failed URL key=" + TOKEN)
    monkeypatch.setattr("urllib.request.urlopen", error)
    if issue == "missing_key":
        monkeypatch.delenv("CENSUS_API_KEY")
    with pytest.raises((ValueError, RuntimeError)) as exc:
        raw = acs.ACS().fetch(req, context)
        acs.ACS().follow_up(raw, context)
    assert TOKEN not in str(exc.value)


def transport_from_fixtures(context, monkeypatch, failures):
    planned = acs.ACS().plan(context)
    requests_by_query = {(req.params["url"], urllib.parse.urlencode(req.params["query"])): req for req in planned}
    attempts = {}
    monkeypatch.setenv("CENSUS_API_KEY", TOKEN)
    monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    def response(request, timeout):
        parsed = urllib.parse.urlsplit(request.full_url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        assert query.pop("key", None) == (TOKEN if parsed.netloc == "api.census.gov" else None)
        req = requests_by_query[(urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")),
                                 urllib.parse.urlencode(query))]
        attempts[req.key] = attempts.get(req.key, 0) + 1
        if req.key == "block_group_453_age" and attempts[req.key] <= failures:
            raise urllib.error.HTTPError(request.full_url, 503, TOKEN, {}, None)
        raw = adapter.read_fixture("acs", req)
        return Response(json.dumps(raw.body).encode())
    monkeypatch.setattr("urllib.request.urlopen", response)
    return attempts


def test_retry_is_counted_by_runner_and_budget(context, monkeypatch):
    attempts = transport_from_fixtures(context, monkeypatch, failures=1)
    run = runner.run("acs", mode="live", now=NOW)
    assert run.status == "success", run.errors
    assert run.calls_made == 27 and run.planned_calls == 27 and run.rows_out == 12
    assert attempts["block_group_453_age"] == 2 and sum(attempts.values()) == 27
    assert TOKEN not in run.model_dump_json()
    for path in (context.adapter_dir.parents[1] / "web/public/data/layers").glob("acs_*.geojson"):
        assert TOKEN not in path.read_text()
    assert TOKEN not in (context.adapter_dir.parents[1] / "data/runs/ingestion_runs.jsonl").read_text()


def test_retry_failure_preserves_previous_layers(context, monkeypatch):
    assert runner.run("acs", now=NOW).status == "success"
    folder = context.adapter_dir.parents[1] / "web/public/data/layers"
    previous = {p: p.read_bytes() for p in folder.glob("acs_*.geojson")}
    attempts = transport_from_fixtures(context, monkeypatch, failures=2)
    run = runner.run("acs", mode="live", now=NOW)
    assert run.status == "failed" and attempts["block_group_453_age"] == 2
    assert run.calls_made == 3 and TOKEN not in run.model_dump_json()
    assert {p: p.read_bytes() for p in previous} == previous


def test_client_errors_are_not_retried(context):
    req = next(req for req in acs.ACS().plan(context) if req.params["kind"] == "acs")
    with pytest.raises(ValueError, match="HTTP 429"):
        acs.ACS().follow_up(RawPayload(req, None, 429), context)


def test_generated_manifests_are_current_and_neutral(context, tmp_path):
    output = tmp_path / "generated"
    subprocess.run([sys.executable, str(ROOT / "adapters/acs/make_layers.py"), "--output", str(output)], check=True)
    files = list(output.glob("*.yaml"))
    assert len(files) == 42
    for file in files:
        assert file.read_bytes() == (ROOT / "layers" / file.name).read_bytes()
    layers = [layer for layer in load_layers() if layer.source == "acs"]
    assert len(layers) == 42
    for layer in layers:
        assert layer.demographic and not layer.default_visible and layer.refresh == "annual"
        assert layer.group == "People" and layer.data_bundle == "acs_" + layer.dataset
        assert layer.variant.key == layer.join == layer.dataset
        assert layer.variant.label == acs.metrics.SCALES[layer.dataset]
        assert layer.variant.family in acs.metrics.METRICS
        assert layer.style.type == "fill" and layer.style.paint["fill-opacity"] == .55
        metric = layer.variant.family
        assert layer.style.paint["fill-color"][:3] == ["case", ["==", ["get", metric], None], acs.metrics.MISSING]
        assert [item.color for item in layer.legend] == acs.metrics.BLUE + [acs.metrics.MISSING]
        assert all("estimate" in item.label.lower() for item in layer.legend)
        assert layer.legend[-1].label == "Estimate unavailable"
        assert "finer but noisier" in layer.description and "tracts are steadier" in layer.description
        assert layer.attribution == acs.metrics.ATTRIBUTION and layer.license == "Public domain"
        field = layer.popup[0]
        assert field.field == metric and field.moe_field == metric + "_moe"
        assert field.reliability_field == metric + "_reliability" and field.annotation_field == metric + "_annotation"
        assert {p.field for p in layer.popup[1:]} == {"geoid", "geography", "vintage"}


def test_demographics_guard_sees_every_new_field(context):
    fields = {metric + suffix for metric in acs.metrics.METRICS for suffix in ("", "_moe", "_reliability", "_annotation", "_display")}
    assert fields <= inputs.demographic_fields()
    with pytest.raises(inputs.DemographicInputError) as exc:
        inputs.assert_no_demographics("test_value_model", fields)
    assert all(field in str(exc.value) for field in fields)
    inputs.assert_no_demographics("geography_only", ["geoid", "geography", "vintage"])


def test_fixture_publication_and_shared_sources(context):
    run = runner.run("acs", now=NOW)
    assert run.status == "success", run.errors
    assert run.calls_made == 0 and run.planned_calls == 26 and run.rows_out == 12
    layers = [layer for layer in registry.compile_registry().layers if layer.source == "acs"]
    documents = {}
    for layer in layers:
        assert layer.freshness == "fixture_only" and layer.as_of == "2024-12-31"
        doc = json.loads((context.adapter_dir.parents[1] / "web/public" / layer.data_url).read_text())
        assert doc["test_data"] is True and doc["source_as_of"] == "2024-12-31"
        assert len(doc["features"]) == (9 if layer.dataset == "block_group" else 3)
        assert all(f["properties"]["geography"] == acs.metrics.SCALES[layer.dataset] for f in doc["features"])
        if layer.dataset in documents:
            assert doc == documents[layer.dataset]  # Same complete metric bundle at a scale.
        documents[layer.dataset] = doc
    # One file per scale, shared by every metric (no per-layer copies).
    assert {layer.data_url for layer in layers} == {
        "data/layers/acs_block_group.geojson", "data/layers/acs_tract.geojson"}
    published = sorted(p.name for p in (context.adapter_dir.parents[1] / "web/public/data/layers").glob("acs*"))
    assert published == ["acs_block_group.geojson", "acs_tract.geojson"]


def test_budget_and_live_gate(context, monkeypatch):
    budget = config.budgets().adapters["acs"]
    assert budget.per_day == 30 and budget.min_interval_seconds == 1
    # Ungated after the published re-run (run 40043682058, DECISIONS 2026-10-24).
    import yaml
    gates = yaml.safe_load((ROOT / "config/live_gates.yaml").read_text()).get("gated") or {}
    assert "acs" not in gates
