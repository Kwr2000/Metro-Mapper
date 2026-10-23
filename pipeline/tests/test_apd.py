"""Aggregate-only APD reports: honest coverage, reconciled totals and tested rates."""
import copy
import gzip
import importlib.util
import json
import urllib.error
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely import transform
from shapely.geometry import box, mapping

from mm import adapter, canonical, config, privacy, publish, registry, runner
from mm.adapter import RawPayload, Request, RunContext
from mm.budget import CallBudget

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("apd_under_test", ROOT / "adapters/apd/adapter.py")
apd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apd)
NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


@pytest.fixture
def context(repo):
    return RunContext("fixture", NOW, CallBudget.for_adapter("apd", NOW), repo / "adapters/apd")


def inputs(context):
    ad = apd.APDReports()
    requests = ad.plan(context)
    return ad, {req.key: adapter.read_fixture("apd", req) for req in requests}


def output(context, modify=None):
    ad, raws = inputs(context)
    if modify:
        modify(raws)
    records = [rec for raw in raws.values() for rec in ad.normalize(raw)]
    return ad.finalize(records)


def rows(context):
    return {r.feature_id: r.properties for r in output(context) if r.dataset == "block_group"}


def geoid(i):
    return "48453" + f"{100 + i:06d}" + "1"


@pytest.mark.parametrize(("now", "start", "end"), [
    (NOW, "2025-10-01", "2026-10-01"),
    (datetime(2026, 1, 1, tzinfo=timezone.utc), "2025-01-01", "2026-01-01"),
    (datetime(2024, 3, 31, tzinfo=timezone.utc), "2023-03-01", "2024-03-01"),
    (datetime(2026, 10, 31, 23, 30, tzinfo=timezone(timedelta(hours=-5))), "2025-11-01", "2026-11-01"),
])
def test_last_twelve_full_months_in_utc(now, start, end):
    assert apd.period(now) == (date.fromisoformat(start), date.fromisoformat(end))


def test_four_call_plan_never_requests_individual_reports(context):
    ad, raws = inputs(context)
    requests = [raw.request for raw in raws.values()]
    assert len(requests) == 4
    assert [r.key for r in requests] == ["counts", "total", "block_groups", "city"]
    grouped, total, bgs, city = [r.params["query"] for r in requests]
    assert grouped == {"$select": "census_block_group,category_description,count(*) AS n",
                       "$group": "census_block_group,category_description", "$limit": 50000,
                       "$where": "rep_date >= '2025-10-01T00:00:00' AND rep_date < '2026-10-01T00:00:00'"}
    assert total == {"$select": "count(*) AS n", "$where": grouped["$where"]}
    assert bgs == {"where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID,POP100",
                   "outSR": 4326, "f": "geojson", "returnGeometry": "true"}
    assert city == {"where": "GEOID='4805000'", "outFields": "GEOID", "outSR": 4326,
                    "f": "geojson", "returnGeometry": "true"}
    assert requests[2].params["url"].endswith("/8/query") and requests[3].params["url"].endswith("/26/query")
    assert not ad.recordable and not ad.retain_raw
    assert ad.cadence == "monthly" and ad.source_as_of([]) == date(2026, 9, 30)


def test_counts_coverage_population_and_period(context, capsys):
    result = output(context)
    bgs = {r.feature_id: r for r in result if r.dataset == "block_group"}
    assert len(bgs) == 100
    outside = bgs[geoid(0)].properties
    assert outside["safety_note"] == apd.OUTSIDE and outside["apd_share"] == 0
    assert all(outside[field] is None for field in (*apd.COUNT_FIELDS, *apd.RATE_FIELDS))
    half = bgs[geoid(1)].properties
    assert half["apd_share"] == pytest.approx(.5, abs=1e-9)
    assert (half["violent"], half["property"], half["other"], half["total"]) == (2, 3, 2, 7)
    assert half["area_sq_mi"] == pytest.approx(1_000_000 / 1609.344 ** 2, rel=1e-8)
    small = bgs[geoid(2)].properties
    assert small["population_2020"] == 50 and small["safety_note"] == apd.TOO_FEW
    assert small["total"] == 10 and small["density_part1"] == 18
    assert all(small[field] is None for field in apd.RATE_FIELDS if field != "density_part1")
    zero = bgs[geoid(3)].properties
    assert all(zero[f] == 0 for f in apd.COUNT_FIELDS)
    assert zero["density_part1"] == zero["rate_part1_raw"] == zero["rate_violent_raw"] == 0
    # A real zero raw count may have a nonzero smoothed rate.
    assert zero["rate_part1"] > 0 and zero["safety_note"] is None
    assert all(r.properties["period"] == "2025-10-01 to 2026-09-30" for r in bgs.values())
    assert all(r.source_as_of == date(2026, 9, 30) and r.properties["as_of"] == "2026-09-30" for r in bgs.values())
    summary = next(r.properties for r in result if r.dataset == "run_summary")
    assert summary["without block group"] == 10
    assert summary["block groups with reports"] == 100 and summary["block groups in APD area"] == 99
    assert summary["out-of-county codes"] == summary["unmatched codes"] == 1
    assert "without block group=10" in capsys.readouterr().err


@pytest.mark.parametrize(("share", "inside"), [(.49999, False), (.5, True), (.50001, True)])
def test_exact_half_share_in_equal_area_projection(context, share, inside):
    def modify(raws):
        geom = apd.projected(raws["block_groups"].body["features"][0]["geometry"])
        left, bottom, right, top = geom.bounds
        clipped = box(left, bottom, left + (right - left) * share, top)
        undo = Transformer.from_crs(5070, 4326, always_xy=True).transform
        def coordinates(xy):
            result = xy.copy()
            result[:, 0], result[:, 1] = undo(xy[:, 0], xy[:, 1])
            return result
        raws["city"].body["features"][0]["geometry"] = mapping(transform(clipped, coordinates))
    result = output(context, modify)
    target = next(r.properties for r in result if r.feature_id == geoid(0))
    assert target["apd_share"] == pytest.approx(share, abs=1e-8)
    assert (target["safety_note"] != apd.OUTSIDE) == inside


def test_hand_worked_empirical_bayes_and_nonpositive_variance():
    # n=(1,3), y=(10,90); m=25; weighted raw variance=75;
    # sampling variance=12.5; s²=62.5; w=(5/7,15/17).
    assert apd.smooth([10, 90], [1000, 3000]) == pytest.approx([100/7, 500/17])
    assert apd.smooth([2, 6], [1000, 3000]) == [2, 2]  # s² < 0
    assert apd.smooth([0, 0], [100, 1000]) == [0, 0]  # m=s²=0: no 0/0
    assert apd.smooth([7], [1000]) == [7]
    assert apd.smooth([], []) == []


def test_smoothing_eligibility_and_rounding(context):
    result = rows(context)
    eligible = [p for p in result.values() if p["safety_note"] is None]
    ns = [p["population_2020"] / 1000 for p in eligible]
    for field, count_fields in [("rate_part1", ["violent", "property"]), ("rate_violent", ["violent"])]:
        ys = [sum(p[f] for f in count_fields) for p in eligible]
        mean = sum(ys) / sum(ns)
        variance = max(0, sum(n * (y/n - mean)**2 for y,n in zip(ys,ns))/sum(ns) - mean/(sum(ns)/len(ns)))
        for p, y, n in zip(eligible, ys, ns):
            weight = variance/(variance + mean/n) if variance else 0
            assert p[field] == round(weight*y/n + (1-weight)*mean, 1)
            assert p[field + "_raw"] == round(y/n, 1)
    assert all(isinstance(p["density_part1"], int) for p in eligible)


def test_minimum_population_boundary(context):
    def modify(raws):
        raws["block_groups"].body["features"][2]["properties"]["POP100"] = 100
    target = next(r.properties for r in output(context, modify) if r.feature_id == geoid(2))
    assert target["safety_note"] is None and target["rate_part1_raw"] == 70
    assert target["rate_part1"] is not None


def test_totals_include_outside_city_unlocated_and_out_of_county(context):
    ad, raws = inputs(context)
    records = [r for raw in raws.values() for r in ad.normalize(raw)]
    result = ad.finalize(records)
    assert sum(r.properties["count"] for r in records if r.dataset == "counts_input") == int(raws["total"].body[0]["n"])
    summary = next(r.properties for r in result if r.dataset == "run_summary")
    # These reports must stay in reconciliation even though they are not displayed as counts.
    assert summary["reports in period"] > sum(r.properties["total"] or 0 for r in result if r.dataset == "block_group")
    raws["total"].body[0]["n"] = str(summary["reports in period"] - 1)
    with pytest.raises(ValueError, match="do not equal"):
        ad.finalize([r for raw in raws.values() for r in ad.normalize(raw)])


def test_vintage_guard_counts_distinct_codes_including_out_of_county(context):
    # Fixture is exactly 99 matching codes out of 100 non-null codes.
    assert output(context)
    def modify(raws):
        raws["counts"].body.append({"census_block_group": "4539999991", "category_description": None, "n": "1"})
        raws["total"].body[0]["n"] = str(int(raws["total"].body[0]["n"]) + 1)
    with pytest.raises(ValueError, match="below 99%"):
        output(context, modify)


def test_null_socrata_group_columns_can_be_omitted(context):
    def modify(raws):
        for row in raws["counts"].body:
            for key in ("census_block_group", "category_description"):
                if row[key] is None:
                    del row[key]
    assert output(context, modify) == output(context)


def test_unknown_category_fixture_fails(context):
    ad, raws = inputs(context)
    failure = adapter.read_fixture("apd", Request("counts_unknown_category")).body
    with pytest.raises(ValueError, match="unknown APD category"):
        list(ad.normalize(RawPayload(raws["counts"].request, failure)))


@pytest.mark.parametrize("key", ["counts", "total", "block_groups", "city"])
@pytest.mark.parametrize("issue", ["http", "non_json", "missing_field", "empty"])
def test_bad_responses_fail_closed(context, key, issue):
    ad, raws = inputs(context)
    raw = raws[key]
    if issue == "http":
        raw = RawPayload(raw.request, raw.body, status=503)
    elif issue == "non_json":
        raw = RawPayload(raw.request, "<html>Unavailable</html>")
    elif issue == "empty":
        raw = RawPayload(raw.request, [] if isinstance(raw.body, list) else {"type": "FeatureCollection", "features": []})
        if key == "counts":
            # An empty group response is legitimate only when the independent total is 0.
            records = [r for other in raws.values() if other is not raws[key] for r in ad.normalize(other)]
            with pytest.raises(ValueError, match="do not equal"):
                ad.finalize(records)
            return
    elif isinstance(raw.body, list):
        del raw.body[0]["n"]
    else:
        del raw.body["features"][0]["properties"]["GEOID"]
    with pytest.raises(ValueError):
        ad.follow_up(raw, context)


@pytest.mark.parametrize(("key", "extra"), [("counts", "incident_report_number"), ("counts", "address"), ("total", "rep_date")])
def test_response_with_incident_fields_is_rejected_before_storage(context, key, extra):
    ad, raws = inputs(context)
    raws[key].body[0][extra] = "SYNTHETIC NEVER STORE"
    with pytest.raises(ValueError, match="non-aggregate"):
        list(ad.normalize(raws[key]))


def test_no_aggregate_paging_or_incident_fallback(context):
    ad, raws = inputs(context)
    raws["counts"].body[:] = [raws["counts"].body[0]] * 50000
    with pytest.raises(ValueError, match="truncated"):
        ad.follow_up(raws["counts"], context)
    for key in ["block_groups", "city"]:
        raws[key].body["exceededTransferLimit"] = True
        with pytest.raises(ValueError, match="exceededTransferLimit"):
            ad.follow_up(raws[key], context)


def test_duplicate_group_rows_and_invalid_codes_fail(context):
    def duplicate(raws):
        raws["counts"].body.append(raws["counts"].body[0])
    with pytest.raises(ValueError, match="duplicate"):
        output(context, duplicate)
    def bad_code(raws):
        raws["counts"].body[0]["census_block_group"] = "484530011011"
    with pytest.raises(ValueError, match="block-group code"):
        output(context, bad_code)


@pytest.mark.parametrize("value", [-1, "1.5", 1.5, True, None, "", "nan"])
def test_counts_and_population_require_nonnegative_integers(value):
    with pytest.raises(ValueError):
        apd.integer(value)


def test_fetch_aggregate_only_gzip_and_http_error(context, monkeypatch):
    ad, raws = inputs(context)
    req = raws["counts"].request
    class Response(BytesIO):
        status = 200
        headers = {"Content-Encoding": "gzip"}
    def response(request, timeout):
        assert timeout == 90 and request.get_header("User-agent") == ad.user_agent
        assert request.get_header("Accept-encoding") == "gzip"
        assert "count%28%2A%29+AS+n" in request.full_url
        return Response(gzip.compress(b'[{"n":"0"}]'))
    monkeypatch.setattr("urllib.request.urlopen", response)
    assert ad.fetch(req, context).body == [{"n": "0"}]
    unsafe = copy.deepcopy(req)
    unsafe.params["query"]["$select"] = "*"
    with pytest.raises(ValueError, match="aggregate-only"):
        ad.fetch(unsafe, context)
    unsafe_total = copy.deepcopy(raws["total"].request)
    unsafe_total.params["query"]["$group"] = "incident_report_number"
    with pytest.raises(ValueError, match="aggregate-only"):
        ad.fetch(unsafe_total, context)
    def error(*args, **kwargs):
        raise urllib.error.HTTPError(apd.APD, 500, "Unavailable", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", error)
    with pytest.raises(ValueError, match="HTTP 500"):
        ad.follow_up(ad.fetch(req, context), context)


def test_shared_bundle_manifests_and_test_data(context):
    run = runner.run("apd", now=NOW)
    assert run.status == "success", run.errors
    assert run.planned_calls == 4 and run.calls_made == 0 and run.rows_out == 101
    layers = [r for r in registry.compile_registry().layers if r.source == "apd"]
    assert {r.id for r in layers} == {"apd_part1_rate", "apd_part1_density"}
    assert len({r.data_url for r in layers}) == 1
    for layer in layers:
        assert layer.data_bundle == "apd_block_group" and layer.dataset == "block_group"
        assert layer.freshness == "fixture_only" and not layer.default_visible and layer.refresh == "monthly"
        assert layer.group == "Safety" and layer.license == "Public domain"
        assert layer.attribution == "City of Austin, Texas - data.austintexas.gov (APD Crime Reports); U.S. Census Bureau"
        assert "Reports are not convictions" in layer.description and "Austin-wide rate" in layer.description
        assert "Not specific to any street" in layer.description
        assert [r.color for r in layer.legend] == ["#feedde", "#fdbe85", "#fd8d3c", "#e6550d", "#a63603", "#bdbdbd"]
        assert layer.legend[-1].label == "Not available"
        steps = layer.style.paint["fill-color"][-1]
        assert steps[3::2] == ([10,25,50,100] if layer.id.endswith("rate") else [25,75,150,300])
        assert [r.field for r in layer.popup] == ["rate_part1", "rate_part1_raw", "rate_violent", "rate_violent_raw", "density_part1",
                                                "violent", "property", "other", "total", "population_2020", "period", "safety_note", "geoid"]
        doc = json.loads(publish.published_path(layer).read_text())
        assert doc["test_data"] is True and len(doc["features"]) == 100
        assert doc["source_as_of"] == "2026-09-30"
        assert all(not privacy.personal_keys(r["properties"]) for r in doc["features"])


def test_failed_totals_preserve_both_previous_layers(context):
    assert runner.run("apd", now=NOW).status == "success"
    folder = context.adapter_dir.parents[1] / "web/public/data/layers"
    previous = {path: path.read_bytes() for path in folder.glob("apd_*.geojson")}
    path = context.adapter_dir / "fixtures/total.json"
    path.write_text('{"body":[{"n":"0"}]}')
    run = runner.run("apd", now=NOW)
    assert run.status == "failed" and "do not equal" in " ".join(run.errors)
    assert previous and {path: path.read_bytes() for path in previous} == previous


def test_mocked_live_summary_only_aggregate_canonical_no_raws(context, monkeypatch, capsys):
    ad = apd.APDReports()
    original = adapter.load
    monkeypatch.setattr(ad, "fetch", lambda req, ctx: adapter.read_fixture("apd", req))
    monkeypatch.setattr(adapter, "load", lambda identity: ad if identity == "apd" else original(identity))
    monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    run = runner.run("apd", mode="live", now=NOW)
    assert run.status == "success" and run.calls_made == 4, run.errors
    records = canonical.read("area_feature", "apd")
    assert {r.dataset for r in records} == {"block_group", "run_summary"}
    assert not (context.adapter_dir.parents[1] / "data/raw").exists()
    assert all(not privacy.personal_keys(r.properties) for r in records)
    spec = importlib.util.spec_from_file_location("apd_live_summary", ROOT / "tools/live_summary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main("apd") == 0
    summary = capsys.readouterr().out
    for fragment in ["without block group=10", "block groups with reports=100", "block groups in APD area=99",
                     "out-of-county codes=1", "period start=2025-10-01", "period end=2026-09-30"]:
        assert fragment in summary


def test_budget_and_live_gate(context, monkeypatch):
    budget = config.budgets().adapters["apd"]
    assert budget.per_day == 10 and budget.min_interval_seconds == 1
    # Ungated after Claude's first live check (run 40041503825, DECISIONS 2026-10-23).
    import yaml
    gates = yaml.safe_load((ROOT / "config/live_gates.yaml").read_text()).get("gated") or {}
    assert "apd" not in gates


def test_zero_report_period_has_real_zeroes_without_division_by_zero(context):
    def modify(raws):
        raws["counts"].body.clear()
        raws["total"].body[0]["n"] = "0"
    result = output(context, modify)
    for rec in result:
        if rec.dataset == "block_group" and rec.properties["safety_note"] is None:
            assert all(rec.properties[f] == 0 for f in (*apd.COUNT_FIELDS, *apd.RATE_FIELDS))


def test_self_intersecting_city_polygon_is_repaired():
    # A bow-tie like the one in TIGER's Austin city limits (live run 40041187416).
    bowtie = {"type": "Polygon", "coordinates": [[[-97.8, 30.2], [-97.7, 30.3], [-97.7, 30.2],
                                                  [-97.8, 30.3], [-97.8, 30.2]]]}
    geom = apd.projected(bowtie)
    assert geom.is_valid and geom.area > 0
