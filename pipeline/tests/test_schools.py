"""Schools use verified identifiers, source coordinates and safe selected columns."""
import copy
import gzip
import importlib.util
import json
import urllib.error
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from pyproj import Transformer
from shapely import transform
from shapely.geometry import box, mapping

from mm import adapter, canonical, config, privacy, registry, runner
from mm.adapter import RawPayload, RunContext
from mm.budget import CallBudget

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("schools_under_test", ROOT / "adapters/schools/adapter.py")
schools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schools)
NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


@pytest.fixture
def school_context(repo):
    return RunContext("fixture", NOW, CallBudget.for_adapter("schools", NOW), repo / "adapters/schools")


def inputs(context):
    ad = schools.Schools()
    requests = ad.plan(context)
    return ad, [record for req in requests for record in ad.normalize(adapter.read_fixture("schools", req))]


def output(context):
    ad, records = inputs(context)
    return ad.finalize(records)


@pytest.mark.parametrize(("value", "length", "expected"), [
    ("'001902001", 9, "001902001"), ("'481320000821", 12, "481320000821"),
    ("'001902", 6, "001902"), (" '001-902-001 ", 9, "001902001"),
])
def test_apostrophes_and_digits_preserve_leading_zeroes(value, length, expected):
    assert schools.digits(value, length) == expected


@pytest.mark.parametrize("value", [None, 1902001, "", "'123"])
def test_bad_identifiers_fail(value):
    with pytest.raises(ValueError):
        schools.digits(value, 9)


@pytest.mark.parametrize(("value", "expected"), [
    ("district.example.test", "https://district.example.test"),
    ("http://district.example.test/path", "http://district.example.test/path"),
    ("//district.example.test/path", "https://district.example.test/path"),
    ("javascript:alert(1)", None), ("https://name:password@example.test", None), (None, None), ("", None),
])
def test_website_prefix_and_safe_protocols(value, expected):
    assert schools.website(value) == expected


def test_exact_plan_and_selected_fields_never_request_people(school_context):
    ad = schools.Schools()
    requests = ad.plan(school_context)
    assert [req.key for req in requests] == ["districts", "block_groups", "campuses", "directory", "ratings"]
    assert len(requests) == 5
    assert [req.params["url"] for req in requests] == [
        schools.DISTRICTS, schools.BLOCK_GROUPS, schools.CAMPUSES, schools.ASKTED, schools.RATINGS]
    for req in requests:
        assert (school_context.adapter_dir / "fixtures" / (req.key + ".json")).is_file()
        query = req.params["query"]
        selection = query.get("outFields", query.get("$select"))
        assert selection == schools.FIELDS[req.params["kind"]]
        assert not any(word in selection.lower() for word in ("principal", "superintendent", "street", "phone", "email"))
        assert "*" not in selection and ad.follow_up(adapter.read_fixture("schools", req), school_context) == []
    assert requests[0].params["query"]["geometry"] == ",".join(map(str, config.app_config().study_bbox))
    assert requests[0].params["query"]["maxAllowableOffset"] == .0001
    assert requests[1].params["query"]["where"] == "STATE='48' AND COUNTY IN ('453','491','209')"
    assert requests[2].params["query"]["where"] == "STATE='TX' AND CNTY IN ('48453','48491','48209')"
    assert requests[3].params["query"] == {"$select": schools.FIELDS["directory"], "$where": "nces_school_id IS NOT NULL", "$limit": 20000}
    assert requests[4].params["query"] == {"$select": schools.FIELDS["rating"], "$where": "school_type != 'District'", "$limit": 20000}
    assert not ad.recordable and not ad.retain_raw


def test_join_notes_charter_and_source_coordinates(school_context, capsys):
    records = output(school_context)
    districts = [rec for rec in records if rec.dataset == "district"]
    campuses = {rec.feature_id: rec for rec in records if rec.dataset == "campus"}
    assert len(districts) == 20 and len(campuses) == 500
    assert all(rec.feature_id != "4899999" for rec in districts)
    raw_points = adapter.read_fixture("schools", schools.Schools().plan(school_context)[2]).body["features"]
    for row in raw_points:
        assert campuses[row["properties"]["NCESSCH"]].geometry == row["geometry"]
    first = campuses[raw_points[0]["properties"]["NCESSCH"]].properties
    assert first["campus_number"] == "001901001" and first["overall_rating"] == "A" and first["overall_score"] == 90
    assert first["charter"] == "Yes" and first["enrollment_note"] == "Open-enrollment charter: no attendance zone"
    second = campuses[raw_points[1]["properties"]["NCESSCH"]].properties
    assert second["overall_rating"] == "Not Rated" and second["rating_note"] == schools.NOT_RATED
    assert second["overall_score"] is None and second["academic_growth_score"] is None
    third = campuses[raw_points[2]["properties"]["NCESSCH"]].properties
    assert third["campus_number"] is not None and third["overall_rating"] is None
    assert third["rating_note"] == schools.NO_RATING and third["overall_score"] is None
    unmatched = campuses[raw_points[480]["properties"]["NCESSCH"]].properties
    assert unmatched["campus_number"] is None and unmatched["rating_note"] == schools.NO_RATING
    assert unmatched["district"] == "Leander ISD"
    assert all(rec.properties["ratings_year"] == "2024–25" for rec in campuses.values())
    assert schools.summary_counts(districts, list(campuses.values())) == {
        "districts kept": 20, "campuses": 500, "matched": 480, "rating rows": 450, "rated": 449, "not rated": 1, "unmatched": 20}
    report = capsys.readouterr().err
    for fragment in ("districts kept=20", "campuses=500", "matched=480", "rated=449", "not rated=1", "unmatched=20"):
        assert fragment in report


def test_finder_fallback_shortening_and_exact_name_guard(school_context):
    records = {rec.feature_id: rec for rec in output(school_context) if rec.dataset == "district"}
    leander = records["4800001"].properties
    assert leander["name"] == "Leander ISD" and leander["finder_link"] == "https://leanderisd.org/msaz"
    assert leander["finder_label"] == "School Zone Finder" and leander["tea_district_number"] == "001901"
    assert records["4800004"].properties["name"] == "Hays CISD"
    fallback = records["4800005"].properties
    assert fallback["finder_link"] == "https://district5.example.test" and fallback["finder_label"] == "District website"
    assert records["4800020"].properties["finder_link"] is None
    assert all(rec.properties["zone_note"] == schools.ZONE_NOTE for rec in records.values())
    assert leander["grades"] == "PK–12"
    path = school_context.adapter_dir / "finders.yaml"
    data = yaml.safe_load(path.read_text())
    data["Leander ISD"] = data.pop("Leander Independent School District")
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="finder key"):
        output(school_context)


def test_website_can_come_from_another_directory_campus_in_same_tea_district(school_context):
    ad, records = inputs(school_context)
    directory = next(rec for rec in records if rec.dataset == "school_directory_input" and rec.properties["tea_district_number"] == "020901")
    extra = directory.model_copy(update={"feature_id": "489999999999", "properties": {
        **directory.properties, "nces_id": "489999999999", "website": "https://fallback.example.test"}})
    result = ad.finalize([*records, extra])
    district = next(rec for rec in result if rec.dataset == "district" and rec.feature_id == "4800020")
    assert district.properties["finder_link"] == "https://fallback.example.test"


def test_unmatched_campus_with_unknown_leaid_has_no_invented_district(school_context):
    ad, records = inputs(school_context)
    unmatched_ids = {rec.feature_id for rec in records if rec.dataset == "school_campus_input"} - {
        rec.feature_id for rec in records if rec.dataset == "school_directory_input"}
    target = next(rec for rec in records if rec.dataset == "school_campus_input" and rec.feature_id in unmatched_ids)
    changed = target.model_copy(update={"properties": {**target.properties, "lea_id": "4899998"}})
    result = ad.finalize([changed if rec is target else rec for rec in records])
    campus = next(rec for rec in result if rec.dataset == "campus" and rec.feature_id == target.feature_id)
    assert campus.properties["district"] is None


@pytest.mark.parametrize(("share", "count"), [(.00499, 20), (.005, 21), (.00501, 21)])
def test_sliver_rule_uses_share_of_one_block_group(school_context, share, count):
    ad, records = inputs(school_context)
    bg = next(rec for rec in records if rec.dataset == "school_block_group_input")
    geom = schools.projected(bg.geometry)
    left, bottom, right, top = geom.bounds
    clipped = box(left, bottom, left + (right - left) * share, top)
    undo = Transformer.from_crs(5070, 4326, always_xy=True).transform
    def coordinates(xy):
        result = xy.copy()
        result[:, 0], result[:, 1] = undo(xy[:, 0], xy[:, 1])
        return result
    sliver = next(rec for rec in records if rec.feature_id == "4899999")
    replacement = sliver.model_copy(update={"geometry": mapping(transform(clipped, coordinates))})
    result = ad.finalize([replacement if rec is sliver else rec for rec in records])
    assert sum(rec.dataset == "district" for rec in result) == count


@pytest.mark.parametrize("guard", ["campuses", "districts", "matches", "ratings"])
def test_production_coverage_guards_fail_closed(school_context, guard):
    ad, records = inputs(school_context)
    if guard == "campuses":
        first = next(rec for rec in records if rec.dataset == "school_campus_input")
        records.remove(first)
    elif guard == "districts":
        records = [rec for rec in records if not (rec.dataset == "school_district_input" and rec.feature_id == "4800020")]
    elif guard == "matches":
        directories = [rec for rec in records if rec.dataset == "school_directory_input"]
        keep = {rec.feature_id for rec in directories[:449]}
        records = [rec for rec in records if rec.dataset != "school_directory_input" or rec.feature_id in keep]
    else:
        rating_ids = [rec.feature_id for rec in records if rec.dataset == "school_rating_input"]
        keep = set(rating_ids[:383])
        records = [rec for rec in records if rec.dataset != "school_rating_input" or rec.feature_id in keep]
    with pytest.raises(ValueError, match="fewer than|below"):
        ad.finalize(records)


def test_exact_match_and_rating_coverage_edges_pass(school_context):
    ad, records = inputs(school_context)
    keep_directory = {rec.feature_id for rec in records if rec.dataset == "school_directory_input"}
    keep_directory = set(sorted(keep_directory)[:450])
    records = [rec for rec in records if rec.dataset != "school_directory_input" or rec.feature_id in keep_directory]
    tea_ids = {rec.properties["campus_number"] for rec in records if rec.dataset == "school_directory_input"}
    available = [rec for rec in records if rec.dataset == "school_rating_input" and rec.feature_id in tea_ids]
    assert len(available) >= 360
    keep_ratings = {rec.feature_id for rec in available[:360]}
    records = [rec for rec in records if rec.dataset != "school_rating_input" or rec.feature_id in keep_ratings]
    result = ad.finalize(records)
    counts = schools.summary_counts([r for r in result if r.dataset == "district"], [r for r in result if r.dataset == "campus"])
    assert counts["matched"] == 450 and counts["rating rows"] == 360


def test_duplicate_conflicting_join_fails(school_context):
    ad, records = inputs(school_context)
    rec = next(rec for rec in records if rec.dataset == "school_directory_input")
    conflict = rec.model_copy(update={"properties": {**rec.properties, "campus_number": "999901001"}})
    with pytest.raises(ValueError, match="conflicting duplicate"):
        ad.finalize([*records, conflict])


def test_synthetic_personal_column_never_enters_canonical_or_published(school_context):
    ad, records = inputs(school_context)
    assert "school_principal" in (school_context.adapter_dir / "fixtures/directory.json").read_text()
    for rec in [*records, *ad.finalize(records)]:
        serialized = rec.model_dump_json()
        assert "school_principal" not in serialized and "SYNTHETIC PRIVATE VALUE" not in serialized
        assert privacy.personal_keys(rec.properties) == []
    run = runner.run("schools", now=NOW)
    assert run.status == "success", run.errors
    for path in (school_context.adapter_dir.parents[1] / "web/public/data/layers").glob("school_*.geojson"):
        assert "school_principal" not in path.read_text() and "SYNTHETIC PRIVATE VALUE" not in path.read_text()


@pytest.mark.parametrize("kind", ["district", "block_group", "campus", "directory", "rating"])
@pytest.mark.parametrize("issue", ["http", "not_json", "missing_field"])
def test_bad_responses_fail(school_context, kind, issue):
    ad = schools.Schools()
    req = next(req for req in ad.plan(school_context) if req.params["kind"] == kind)
    raw = adapter.read_fixture("schools", req)
    body = copy.deepcopy(raw.body)
    if issue == "http":
        raw = RawPayload(req, body, 503)
    elif issue == "not_json":
        raw = RawPayload(req, "<html>service unavailable</html>")
    else:
        field = schools.FIELDS[kind].split(",")[0]
        if isinstance(body, list):
            for row in body:
                row.pop(field, None)
        else:
            del body["features"][0]["properties"][field]
        raw = RawPayload(req, body)
    with pytest.raises(ValueError):
        list(ad.normalize(raw))


@pytest.mark.parametrize("kind", ["district", "block_group", "campus"])
def test_transfer_limit_fails(school_context, kind):
    ad = schools.Schools()
    req = next(req for req in ad.plan(school_context) if req.params["kind"] == kind)
    raw = adapter.read_fixture("schools", req)
    raw.body["exceededTransferLimit"] = True
    with pytest.raises(ValueError, match="exceededTransferLimit"):
        ad.follow_up(raw, school_context)


def test_socrata_omitted_null_fields_are_missing_not_zero(school_context):
    ad = schools.Schools()
    req = ad.plan(school_context)[4]
    raw = adapter.read_fixture("schools", req)
    for key in [key for key in raw.body[0] if key.endswith("_score")]:
        del raw.body[0][key]
    [rec, *rest] = list(ad.normalize(raw))
    assert rec.properties["overall_score"] is None and rec.properties["academic_growth_score"] is None
    assert schools.score(0) == 0 and schools.score("--") is None


def test_fetch_uses_only_planned_query_and_gzip(school_context, monkeypatch):
    class Response(BytesIO):
        status = 200
        headers = {"Content-Encoding": "gzip"}
    ad = schools.Schools()
    req = ad.plan(school_context)[3]
    def response(request, timeout):
        assert timeout == 90 and request.get_header("User-agent") == ad.user_agent
        assert request.get_header("Accept-encoding") == "gzip"
        assert "school_principal" not in request.full_url and "%24select=school_number" in request.full_url
        return Response(gzip.compress(b'[]'))
    monkeypatch.setattr("urllib.request.urlopen", response)
    assert ad.fetch(req, school_context).body == []
    def error(*args, **kwargs):
        raise urllib.error.HTTPError(schools.ASKTED, 500, "Unavailable", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", error)
    with pytest.raises(ValueError, match="HTTP 500"):
        ad.follow_up(ad.fetch(req, school_context), school_context)


def test_layer_manifests_and_fixture_labeling(school_context):
    run = runner.run("schools", now=NOW)
    assert run.status == "success" and run.calls_made == 0 and run.planned_calls == 5 and run.rows_out == 520
    layers = {layer.id: layer for layer in registry.compile_registry().layers if layer.source == "schools"}
    assert set(layers) == {"school_districts", "school_campuses"}
    for layer in layers.values():
        assert layer.freshness == "fixture_only" and layer.group == "Schools"
        assert layer.refresh == "annual" and not layer.default_visible
        doc = json.loads((school_context.adapter_dir.parents[1] / "web/public" / layer.data_url).read_text())
        assert doc["test_data"] is True
        assert len(doc["features"]) == (20 if layer.dataset == "district" else 500)
    district, campus = layers["school_districts"], layers["school_campuses"]
    assert district.style.type == "fill" and district.style.paint["fill-opacity"] == 0
    assert district.style.paint["fill-outline-color"] == "#454545"
    assert district.popup[2].format == "link" and district.popup[2].annotation_field == "finder_label"
    assert campus.style.paint["circle-radius"] == 5 and campus.style.paint["circle-stroke-color"] == "#ffffff"
    assert [item.color for item in campus.legend] == ["#3f007d", "#6a51a3", "#9e9ac8", "#cbc9e2", "#f2f0f7", "#bdbdbd"]
    assert [item.label for item in campus.legend] == ["A", "B", "C", "D", "F", "Not rated / not available"]
    fields = [field.field for field in campus.popup]
    assert fields.index("academic_growth_rating") < fields.index("school_progress_rating") < fields.index("student_achievement_rating")
    assert campus.attribution == "NCES EDGE; Texas Education Agency via data.texas.gov"
    assert campus.popup_title == "TEA accountability ratings, 2024–25"
    assert campus.description == ("Public campuses (NCES 2024–25) with TEA 2024–25 ratings. "
        "A campus's rating is not a promise about the school that serves a given address.")


def test_failed_join_keeps_last_published_layers(school_context):
    assert runner.run("schools", now=NOW).status == "success"
    folder = school_context.adapter_dir.parents[1] / "web/public/data/layers"
    previous = {path: path.read_bytes() for path in folder.glob("school_*.geojson")}
    req = schools.Schools().plan(school_context)[3]
    raw = adapter.read_fixture("schools", req)
    raw.body[:] = raw.body[:400]
    (school_context.adapter_dir / "fixtures/directory.json").write_text(json.dumps({"status": 200, "body": raw.body}))
    run = runner.run("schools", now=NOW)
    assert run.status == "failed" and "below 90%" in " ".join(run.errors)
    assert {path: path.read_bytes() for path in previous} == previous


def test_live_summary_reports_counts_without_saving_private_raws(school_context, monkeypatch, capsys):
    ad = schools.Schools()
    ad.plan(school_context)
    original = adapter.load
    monkeypatch.setattr(ad, "fetch", lambda req, ctx: adapter.read_fixture("schools", req))
    monkeypatch.setattr(adapter, "load", lambda identity: ad if identity == "schools" else original(identity))
    monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    run = runner.run("schools", mode="live", now=NOW)
    assert run.status == "success" and run.calls_made == 5
    assert not (school_context.adapter_dir.parents[1] / "data/raw").exists()
    for rec in canonical.read("area_feature", "schools"):
        assert "SYNTHETIC PRIVATE VALUE" not in rec.model_dump_json()
    module_spec = importlib.util.spec_from_file_location("school_live_summary", ROOT / "tools/live_summary.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    assert module.main("schools") == 0
    report = capsys.readouterr().out
    assert "districts kept=20" in report and "campuses=500; matched=480; rating rows=450; rated=449; not rated=1; unmatched=20" in report
    assert "SYNTHETIC PRIVATE VALUE" not in report and "school_principal" not in report


def test_budget_and_live_gate(school_context, monkeypatch):
    budget = config.budgets().adapters["schools"]
    assert budget.per_day == 10 and budget.min_interval_seconds == 1
    (school_context.adapter_dir.parents[1] / "config/live_gates.yaml").write_text((ROOT / "config/live_gates.yaml").read_text())
    config.clear_cache()
    monkeypatch.delenv("MM_LIVE_CHECK", raising=False)
    run = runner.run("schools", mode="live", now=NOW)
    assert run.status == "skipped" and run.calls_made == 0
    assert "awaiting Claude's first live check" in " ".join(run.notes)
