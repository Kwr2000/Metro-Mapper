"""Small synthetic native TLC archives and precinct-grain, context-only publication."""
import copy
import csv
import gzip
import importlib.util
import json
from datetime import date, datetime, timezone, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

import pytest
import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping

from mm import adapter, canonical, config, inputs as score_inputs, publish, registry, runner
from mm.adapter import RawPayload, RunContext
from mm.budget import CallBudget
from mm.paths import paths

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("elections_under_test", ROOT / "adapters/elections/adapter.py")
el = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(el)
NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
CANARIES = ("SpanishSurnamePercent", "TotalPop", "DISCARDED_SURNAME_VALUE", "DISCARDED_POP_VALUE")


@pytest.fixture
def context(repo):
    return RunContext("fixture", NOW, CallBudget.for_adapter("elections", NOW), repo / "adapters/elections")


def inputs(context):
    ad = el.Elections()
    return ad, {req.key: adapter.read_fixture("elections", req) for req in ad.plan(context)}


def output(context, modify=None):
    ad, raws = inputs(context)
    if modify:
        modify(raws)
    return ad.finalize([rec for raw in raws.values() for rec in ad.normalize(raw)])


def rows(context, modify=None):
    return {r.feature_id: r.properties for r in output(context, modify) if r.dataset == "precinct"}


def native_zip(raws, omit=None, duplicate=False):
    """Raw ZIP includes the two native dropped columns, quoted commas and other offices."""
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        for filename, (_, kind) in el.MEMBERS.items():
            if filename == omit:
                continue
            table = copy.deepcopy(raws["election_data"].body["members"][filename])
            if kind == "VRTO":
                counties = {str(f["properties"]["VTDKEY"]): f["properties"]["CNTY"]
                            for f in raws["vtd_shapes"].body["features"]}
                table = [["County", "FIPS", "VTD", "CNTYVTD", "vtdkey", "TotalPop", "TotalVR", "SpanishSurnamePercent", "TotalTO"]] + [
                    [el.COUNTIES[counties[row[0]]], str(counties[row[0]]), "0001", "4530001", row[0],
                     "DISCARDED_POP_VALUE", row[1], "DISCARDED_SURNAME_VALUE", row[2]] for row in table[1:]]
                table.append(["Elsewhere", "1", "9999", "0019999", "999999", "ignored", "20", "ignored", "10"])
            else:
                table.append(["Travis", "453", "0001", "4530001", "101", 'Judge, Court of Appeals, Place 1',
                              'Synthetic, Quoted Candidate', "D", "", "123"])
                table.append(["Elsewhere", "1", "0001", "0010001", "999999", "President", "Other county candidate", "D", "", "300"])
                table[1][6] = "Synthetic, Quoted Presidential Candidate"
            # Native columns can move: parsers must use names, not positions.
            table = [list(reversed(row)) for row in table]
            text = StringIO(newline="")
            csv.writer(text).writerows(table)
            z.writestr("nested/" + filename, text.getvalue())
            if duplicate and kind == "VRTO":
                z.writestr("ambiguous/" + filename, text.getvalue())
        z.writestr("Unused_Election_Returns.csv", "not parsed")
    return buf.getvalue()


def shape_zip(tmp_path, omit=None):
    """Tiny real SHP/SHX/DBF/PRJ in TLC's published NAD83 Lambert projection."""
    crs = CRS.from_proj4('+proj=lcc +lat_1=27.41666666666667 +lat_2=34.91666666666667 +lat_0=31.16666666666667 +lon_0=-100 +x_0=1000000 +y_0=1000000 +datum=NAD83 +units=m +no_defs')
    project = Transformer.from_crs(4326, crs, always_xy=True).transform
    base = tmp_path / "VTDs_24PG"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON) as writer:
        for name, typ, width in (("CNTY", "N", 3), ("COLOR", "N", 3), ("VTD", "C", 6), ("CNTYKEY", "N", 6),
                                 ("VTDKEY", "N", 10), ("CNTYVTD", "C", 12), ("Shape_area", "N", 20), ("Shape_len", "N", 20)):
            writer.field(name, typ, size=width)
        for i, county in enumerate((453, 491, 209, 1)):
            west, south = -97.75 + i * .01, 30.3
            # Clockwise exterior ring (SHP convention).
            ring = [[west, south], [west, south + .005], [west + .005, south + .005], [west + .005, south], [west, south]]
            writer.poly([[project(lon, lat) for lon, lat in ring]])
            writer.record(county, 1, f"{i + 1:04d}", county, 101 + i, f"{county}0001", 100, 40)
    base.with_suffix(".prj").write_text(crs.to_wkt(version="WKT1_ESRI"))
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        for suffix in ("shp", "shx", "dbf", "prj"):
            if suffix != omit:
                z.writestr("folder/" + base.with_suffix("." + suffix).name, base.with_suffix("." + suffix).read_bytes())
        z.writestr("not-required.txt", "not extracted")
    return buf.getvalue()


def test_plan_only_two_budgeted_downloads(context):
    ad, raws = inputs(context)
    assert list(raws) == ["election_data", "vtd_shapes"]
    assert [r.request.params for r in raws.values()] == [{"url": el.DATA_URL}, {"url": el.SHAPES_URL}]
    assert ad.cadence == "annual" and not ad.retain_raw and not ad.recordable
    assert ad.source_as_of([]) == date(2024, 11, 5)


def test_csv_native_quoting_county_office_filter_and_drop_before_kept(context, tmp_path):
    ad, raws = inputs(context)
    path = tmp_path / "data.zip"; path.write_bytes(native_zip(raws))
    body = el.parse_election_zip(path)
    assert set(body["members"]) == set(el.MEMBERS)
    serialized = json.dumps(body)
    assert not any(token in serialized for token in (*CANARIES, "Other county candidate", "Court of Appeals"))
    assert "Synthetic, Quoted Presidential Candidate" in serialized
    assert body["members"]["2024_General_Election_VRTO.csv"][0] == list(el.VRTO)
    assert len(body["members"]["2024_General_Election_VRTO.csv"]) == 7
    parsed = list(ad.normalize(RawPayload(raws["election_data"].request, body)))
    assert not any(token in json.dumps([r.model_dump(mode="json") for r in parsed]) for token in CANARIES)


def test_native_shapefile_prj_reprojection_fields_and_county_filter(tmp_path):
    archive = tmp_path / "shapes.zip"; archive.write_bytes(shape_zip(tmp_path))
    folder = tmp_path / "extract"; folder.mkdir()
    body = el.parse_shape_zip(archive, folder)
    assert len(body["features"]) == 3
    assert all(set(f["properties"]) == set(el.SHAPE_FIELDS) for f in body["features"])
    assert {f["properties"]["CNTY"] for f in body["features"]} == set(el.COUNTIES)
    first = el.polygon(body["features"][0]["geometry"])
    assert first.bounds == pytest.approx((-97.75, 30.3, -97.745, 30.305), abs=1e-8)
    assert not (folder / "not-required.txt").exists()


class Response(BytesIO):
    status = 200
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
    def read(self, size=-1):
        assert 0 < size <= 1024 * 1024  # The whole large download must never be read at once.
        return super().read(size)


def test_fetch_streams_both_zips_and_deletes_all_temp_files(context, tmp_path, monkeypatch):
    ad, raws = inputs(context)
    blobs = {el.DATA_URL: native_zip(raws), el.SHAPES_URL: shape_zip(tmp_path)}
    requests = []
    def fake(req, timeout):
        requests.append(req)
        assert timeout == 180
        return Response(blobs[req.full_url])
    monkeypatch.setattr("urllib.request.urlopen", fake)
    for raw in raws.values():
        fetched = ad.fetch(raw.request, context)
        assert fetched.status == 200
        assert not list(paths().raw.rglob("*"))
        assert not any(token in json.dumps(fetched.body) for token in CANARIES)
    assert len(requests) == 2 and all(r.get_header("User-agent") == ad.user_agent for r in requests)


@pytest.mark.parametrize("kind", ["not_zip", "missing_csv", "duplicate_csv", "missing_prj", "stream_error", "length", "http", "deadline"])
def test_fetch_failures_delete_downloads_and_partial_extractions(context, tmp_path, monkeypatch, kind):
    ad, raws = inputs(context)
    req = raws["vtd_shapes" if kind == "missing_prj" else "election_data"].request
    data = (b"not a zip" if kind == "not_zip" else shape_zip(tmp_path, omit="prj") if kind == "missing_prj" else
            native_zip(raws, omit="2020_General_Election_VRTO.csv" if kind == "missing_csv" else None,
                       duplicate=kind == "duplicate_csv"))
    class Broken(Response):
        def read(self, size=-1):
            if kind == "stream_error":
                super().read(10)
                raise OSError("synthetic transfer failure")
            return super().read(size)
    response = Broken(data)
    if kind == "length":
        response.headers["Content-Length"] = str(len(data) + 1)
    if kind == "http":
        response.status = 500
    if kind == "deadline":
        ad.started -= 901
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: response)
    result = ad.fetch(req, context)
    assert result.status != 200
    assert not list(paths().raw.rglob("*"))
    with pytest.raises(ValueError, match="HTTP"):
        list(ad.normalize(result))


def test_votes_shares_margin_and_turnout_hand_worked(context):
    r = rows(context)
    p = r["101"]
    assert [p[f"pres_2024_{k}"] for k in ("dem", "rep", "other", "total")] == [60, 30, 10, 100]
    assert [p[f"pres_2024_{k}"] for k in ("dem_share", "rep_share", "margin")] == [.6, .3, -.3]
    assert p["registered_2024"] == 200 and p["ballots_2024"] == 120 and p["turnout_2024"] == .6
    assert p["turnout_2020"] is None and f"2020: {el.TURNOUT}" == p["election_note"]
    assert p["pres_2020_margin"] == -.1
    assert r["106"]["pres_2024_dem_share"] == .333
    assert r["106"]["pres_2024_rep_share"] == .608
    assert r["106"]["pres_2024_margin"] == .275
    assert r["104"]["turnout_2020"] == .917
    assert p["county"] == "Travis" and p["precinct"] == "Travis precinct 0001"
    assert all(v["source_note"] == el.SOURCE_NOTE for v in r.values())


def test_suppression_is_per_election_and_keeps_registered_turnout(context):
    r = rows(context)
    for vtd in ("102", "103", "105"):
        p = r[vtd]
        assert all(p[f"pres_2024_{k}"] is None for k in ("dem", "rep", "other", "total", "dem_share", "rep_share", "margin"))
        assert f"2024: {el.SMALL}" in p["election_note"]
    assert r["102"]["registered_2024"] == 50 and r["102"]["ballots_2024"] == 49 and r["102"]["turnout_2024"] == .98
    assert r["102"]["pres_2020_total"] == 50  # Exact threshold is shown, with no 2020 small note.
    assert r["104"]["pres_2024_total"] == 50 and r["104"]["election_note"] is None
    assert r["103"]["turnout_2024"] is r["103"]["turnout_2020"] is None
    assert r["106"]["election_note"] == f"2020: {el.SMALL}; 2020: {el.TURNOUT}"
    assert r["106"]["pres_2024_total"] == 51 and r["106"]["pres_2020_total"] is None


def test_count_only_summary_includes_unsuppressed_totals(context, capsys):
    result = output(context)
    summary = next(r for r in result if r.dataset == "run_summary")
    p = summary.properties
    assert summary.geometry == el.EMPTY and summary.source_as_of == el.AS_OF
    assert p["precincts"] == 6 and p["precincts per county"] == {"Travis": 2, "Williamson": 2, "Hays": 2}
    assert p["presidential totals by party and year"]["2024"] == {"D": 124, "R": 107, "L": 12, "G": 6, "W": 5}
    assert p["registered by year"] == {"2024": 650, "2020": 500}
    assert p["ballots by year"] == {"2024": 404, "2020": 372}
    assert p["precincts under 50 votes by year"] == {"2024": 3, "2020": 2}
    assert p["runtime_seconds"] >= 0 and p["peak_memory_mb"] > 0
    assert '"precincts": 6' in capsys.readouterr().err
    assert not any(token in json.dumps(p) for token in CANARIES)


def member_rows(raws, kind="Returns", year=2024):
    return raws["election_data"].body["members"][f"{year}_General_Election_{kind}.csv"]


@pytest.mark.parametrize("modify,match", [
    (lambda r: r["vtd_shapes"].body["features"].pop(), "returns key/county"),
    (lambda r: member_rows(r, "VRTO").pop(), "match both ways"),
    (lambda r: member_rows(r, "VRTO").append(["999", "100", "50"]), "match both ways"),
    (lambda r: member_rows(r).__setitem__(slice(1, None), [row for row in member_rows(r)[1:] if row[4] != "101"]), "match both ways"),
    (lambda r: member_rows(r)[1].__setitem__(4, "999"), "returns key/county"),
    (lambda r: member_rows(r)[1].__setitem__(1, "491"), "returns key/county"),
    (lambda r: member_rows(r)[1].__setitem__(7, "X"), "office/party"),
    (lambda r: member_rows(r)[1].__setitem__(5, "Governor"), "office/party"),
    (lambda r: member_rows(r)[1].__setitem__(9, "-1"), "nonnegative integer"),
    (lambda r: member_rows(r, "VRTO")[1].__setitem__(1, "1.2"), "nonnegative integer"),
    (lambda r: member_rows(r, "VRTO")[1].__setitem__(2, ""), "nonnegative integer"),
    (lambda r: member_rows(r, "VRTO")[0].append("TotalPop"), "retained election headers"),
    (lambda r: member_rows(r).append(copy.deepcopy(member_rows(r)[1])), "duplicate election"),
    (lambda r: member_rows(r, "VRTO").append(copy.deepcopy(member_rows(r, "VRTO")[1])), "duplicate election"),
    (lambda r: r["vtd_shapes"].body["features"].append(copy.deepcopy(r["vtd_shapes"].body["features"][0])), "duplicate election"),
    (lambda r: member_rows(r).__delitem__(1), "one Democratic and one Republican"),
    (lambda r: r["election_data"].body["members"].pop("2020_General_Election_VRTO.csv"), "missing election CSV"),
])
def test_key_schema_and_count_failures(context, modify, match):
    with pytest.raises(ValueError, match=match):
        output(context, modify)


def test_different_second_democratic_candidate_is_also_duplicate(context):
    def modify(raws):
        row = copy.deepcopy(member_rows(raws)[1]); row[6] = "Different candidate"
        member_rows(raws).append(row)
    with pytest.raises(ValueError, match="one Democratic and one Republican"):
        output(context, modify)


@pytest.mark.parametrize("count", [522, 584])
def test_production_count_guard(count):
    with pytest.raises(ValueError, match="precinct count"):
        el.production_checks(count, {2024: {"D": 612262, "R": 384529}})


@pytest.mark.parametrize("count", [523, 553, 583])
def test_production_totals_guard_and_edges(count):
    el.production_checks(count, {2024: {"D": 612262, "R": 384529}})
    for party in ("D", "R"):
        totals = {2024: {"D": 612262, "R": 384529}}
        totals[2024][party] = round(totals[2024][party] * 1.011)
        with pytest.raises(ValueError, match="totals outside 1%"):
            el.production_checks(count, totals)


def test_live_mode_always_enforces_production_checks(context):
    ad, raws = inputs(context)
    ad.live = True
    with pytest.raises(ValueError, match="precinct count"):
        ad.finalize([r for raw in raws.values() for r in ad.normalize(raw)])


def test_geometry_simplifies_five_metres_and_rounds_to_six_decimals(context):
    ad, raws = inputs(context)
    rec = next(ad.normalize(raws["vtd_shapes"]))
    assert el.polygon(rec.geometry).is_valid
    def all_numbers(v):
        if isinstance(v, (tuple, list)):
            return [num for part in v for num in all_numbers(part)]
        return [v]
    assert all(round(v, 6) == v for v in all_numbers(rec.geometry["coordinates"]))
    # Add a 1m bump on the edge of a 1km square; the same areas tolerance removes it.
    projected = box(-168000, 804000, -167000, 805000)
    from shapely.geometry import Polygon
    bumped = Polygon([(-168000, 804000), (-167500, 803999), (-167000, 804000),
                      (-167000, 805000), (-168000, 805000), (-168000, 804000)])
    output_geom = el.polygon(el.display_geometry(mapping(el.reproject(bumped, el.TO_WGS84))))
    assert len(output_geom.exterior.coords) == 5


def test_context_layers_guard_no_block_group_join_and_shared_bundle(context):
    layers = [l for l in registry.load_layers() if l.source == "elections"]
    assert len(layers) == 2
    for layer in layers:
        assert layer.demographic and not layer.default_visible and layer.group == "People"
        assert layer.join == layer.dataset == "precinct" and layer.data_bundle == "elections_precinct"
        assert layer.refresh == "annual" and layer.license == "CC BY (Texas Legislative Council)"
        assert layer.attribution == "Texas Legislative Council, Capitol Data Portal"
        assert "Texas has no party registration" in layer.description
        assert next(p for p in layer.popup if p.field == "election_note").hide_if_empty
        assert all(p.field not in {"geoid", "block_group", "tract"} for p in layer.popup)
        fields = layer.fields() - {"county"}
        assert fields <= score_inputs.demographic_fields()
        with pytest.raises(score_inputs.DemographicInputError):
            score_inputs.assert_no_demographics("test_score", fields)
    vote = next(l for l in layers if l.id == "elections_president_2024")
    assert vote.style.paint["fill-color"] == ["case", ["==", ["get", "pres_2024_margin"], None], "#bdbdbd",
        ["step", ["get", "pres_2024_margin"], "#2166ac", -.4, "#67a9cf", -.2, "#d1e5f0", -.05,
         "#f7f7f7", .05, "#fddbc7", .2, "#ef8a62", .4, "#b2182b"]]
    assert [v.label for v in vote.legend] == ["Democratic lead 40+ pts", "Democratic lead 20–40", "Democratic lead 5–20",
        "Within 5 pts", "Republican lead 5–20", "Republican lead 20–40", "Republican lead 40+ pts", "Not shown"]
    turnout = next(l for l in layers if l.id == "elections_turnout_2024")
    assert turnout.style.paint["fill-color"][3] == ["step", ["get", "turnout_2024"], "#eff3ff", .5, "#bdd7e7", .6, "#6baed6", .7, "#3182bd", .8, "#08519c"]


def test_budget_and_live_gate(context):
    budget = CallBudget.for_adapter("elections", NOW)
    assert (budget.per_day, budget.min_interval_seconds, budget.max_minutes) == (4, 5, 15)
    (paths().config / "live_gates.yaml").write_text((ROOT / "config/live_gates.yaml").read_text())
    config.clear_cache()
    assert config.live_gates()["elections"] == "awaiting Claude's first live check"
    run = runner.run("elections", "live", now=NOW)
    assert run.status == "skipped" and run.calls_made == 0


def test_runner_shared_publication_and_saved_count_only_summary(context, monkeypatch, capsys):
    result = runner.run("elections", "fixture", now=NOW)
    assert result.status == "success", result.errors
    layers = [l for l in registry.load_layers() if l.source == "elections"]
    assert publish.published_path(layers[0]) == publish.published_path(layers[1])
    doc = json.loads(publish.published_path(layers[0]).read_text())
    assert doc["test_data"] and len(doc["features"]) == 6
    assert all(f["properties"]["vtdkey"] == str(f["id"]) for f in doc["features"])
    assert not canonical.read("area_feature", "elections")
    cls = type(adapter.load("elections"))
    ad, raws = inputs(context)
    monkeypatch.setitem(cls.finalize.__globals__, "production_checks", lambda *a: None)  # Guard tested above; mock only scale for this tiny run.
    monkeypatch.setattr(cls, "fetch", lambda self, req, ctx: raws[req.key])
    monkeypatch.setattr(adapter, "load", lambda _: cls())
    monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    live = runner.run("elections", "live", now=NOW)
    assert live.status == "success" and live.calls_made == 2, live.errors
    records = canonical.read("area_feature", "elections")
    assert {r.dataset for r in records} == {"precinct", "run_summary"}
    spec = importlib.util.spec_from_file_location("elections_live_summary", ROOT / "tools/live_summary.py")
    summary = importlib.util.module_from_spec(spec); spec.loader.exec_module(summary)
    summary.main("elections")
    assert "precincts=6" in capsys.readouterr().out
    for root in (paths().canonical, paths().web_public, paths().raw):
        for file in root.rglob("*"):
            if file.is_file():
                text = gzip.open(file, "rt").read() if file.suffix == ".gz" else file.read_text()
                assert not any(token in text for token in CANARIES)
    previous = publish.published_path(layers[0]).read_bytes()
    raws["vtd_shapes"].body["features"].pop()
    failed = runner.run("elections", "live", now=NOW + timedelta(days=1))
    assert failed.status == "failed"
    assert publish.published_path(layers[0]).read_bytes() == previous



def test_full_size_synthetic_live_guards_pass_and_detect_wrong_totals(context):
    ad, raws = inputs(context)
    ad.live = True
    shape_template = copy.deepcopy(raws["vtd_shapes"].body["features"][0])
    features = []
    members = {name: [list(el.RETURNS if kind == "Returns" else el.VRTO)] for name, (_, kind) in el.MEMBERS.items()}
    for i in range(553):
        county = (453, 491, 209)[i % 3]
        vtd, vtdkey = f"{i + 1:04d}", str(1000 + i)
        feature = copy.deepcopy(shape_template)
        feature["properties"] = {"CNTY": county, "VTD": vtd, "VTDKEY": int(vtdkey), "CNTYVTD": f"{county}{vtd}"}
        features.append(feature)
        for filename, (year, kind) in el.MEMBERS.items():
            if kind == "VRTO":
                members[filename].append([vtdkey, "5000", "3000"])
            else:
                for party, expected in (("D", 612262), ("R", 384529)):
                    count = expected // 553 + (i < expected % 553) if year == 2024 else 500
                    members[filename].append([el.COUNTIES[county], str(county), vtd, f"{county}{vtd}",
                                             vtdkey, "President", "Synthetic " + party, party, "", str(count)])
    raw_shapes = RawPayload(raws["vtd_shapes"].request, {"type": "FeatureCollection", "features": features})
    raw_data = RawPayload(raws["election_data"].request, {"members": members})
    normalized = [r for raw in (raw_shapes, raw_data) for r in ad.normalize(raw)]
    result = ad.finalize(normalized)
    assert sum(r.dataset == "precinct" for r in result) == 553
    audit = next(r.properties for r in result if r.dataset == "run_summary")
    assert audit["presidential totals by party and year"]["2024"]["D"] == 612262
    assert audit["presidential totals by party and year"]["2024"]["R"] == 384529
    changed = copy.deepcopy(normalized)
    one = next(r for r in changed if r.dataset == "returns_2024_input" and r.properties["party"] == "D")
    one.properties["votes"] += 6123
    with pytest.raises(ValueError, match="totals outside 1%"):
        ad.finalize(changed)


def test_nearest_even_rounding_uses_unrounded_vote_margin(context):
    def modify(raws):
        t = member_rows(raws)
        first = [row for row in t[1:] if row[4] == "101"]
        # 201 / 2000 = .1005 -> .101 in binary Python rounding; use exact .0625 tie instead.
        values = {"D": 125, "R": 1000, "L": 875, "G": 0, "W": 0}
        for row in first:
            row[9] = str(values[row[7]])
    row = rows(context, modify)["101"]
    assert row["pres_2024_dem_share"] == .062
    assert row["pres_2024_rep_share"] == .5
    assert row["pres_2024_margin"] == .438  # Unrounded .4375 tie rounds even.
