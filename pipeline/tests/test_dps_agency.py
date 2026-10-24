"""Synthetic agency-only statistics: native tables, strict joins, honest spatial grain."""
import copy
import importlib.util
import json
import urllib.error
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pytest
import yaml
from shapely.geometry import box
from shapely import union_all

from mm import adapter, canonical, config, publish, registry, runner
from mm.adapter import RawPayload, RunContext, USER_AGENT
from mm.budget import CallBudget

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("dps_under_test", ROOT / "adapters/dps_agency/adapter.py")
dps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dps)
NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


@pytest.fixture
def context(repo):
    return RunContext("fixture", NOW, CallBudget.for_adapter("dps_agency", NOW), repo / "adapters/dps_agency")


def inputs(context):
    ad = dps.DPSAgency()
    return ad, {r.key: adapter.read_fixture(ad.id, r) for r in ad.plan(context)}


def output(context, mutate=None):
    ad, raws = inputs(context)
    if mutate:
        mutate(raws)
    return ad.finalize([r for raw in raws.values() for r in ad.normalize(raw)])


def rows(context, mutate=None):
    return {r.feature_id: r.properties for r in output(context, mutate) if r.dataset == "block_group"}


def table(raws, key="dps_615"):
    return raws[key].body["sheets"]["Index Crime"]


@pytest.mark.parametrize(("now", "year"), [
    (datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc), 2024),
    (datetime(2026, 7, 1, tzinfo=timezone.utc), 2025),
    (NOW, 2025), (datetime(2027, 1, 1, tzinfo=timezone.utc), 2025),
    (datetime(2026, 6, 30, 20, tzinfo=timezone(timedelta(hours=-5))), 2025),
])
def test_year_rule_utc(now, year):
    assert dps.report_year(now) == year


def test_plan_exact_five_requests_and_compatibility_agent(context):
    ad, raws = inputs(context)
    assert list(raws) == ["dps_615", "dps_613", "dps_652", "places", "block_groups"]
    assert ad.user_agent == "Mozilla/5.0 (compatible; metro-mapper/0.1 (+https://github.com/Kwr2000/metro-mapper))"
    assert ad.cadence == "annual" and not ad.recordable and not ad.retain_raw
    assert ad.source_as_of([]) == date(2025, 12, 31)
    for key in list(raws)[:3]:
        params = raws[key].request.params
        assert params["url"] == dps.DPS
        assert params["query"] == {"offenses": "", "startdate": "Jan - 2025", "enddate": "Dec - 2025",
                                   "reportId": int(key[4:])}
    places = raws["places"].request.params
    assert places["url"].endswith("/TIGERweb/tigerWMS_Current/MapServer/28/query")
    assert places["query"]["outFields"] == "GEOID,BASENAME"
    assert all(g in places["query"]["where"] for g, _ in dps.CITIES.values())
    bgs = raws["block_groups"].request.params
    assert bgs["url"].endswith("/Census2020/tigerWMS_Census2020/MapServer/8/query")
    assert bgs["query"] == {"where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields": "GEOID",
                            "outSR": 4326, "f": "geojson", "returnGeometry": "true"}


def tiny_xlsx():
    ns = dps.NS["s"]
    def sheet(rows):
        root = ET.Element("worksheet", xmlns=ns)
        data = ET.SubElement(root, "sheetData")
        for rownum, cells in rows:
            row = ET.SubElement(data, "row", r=str(rownum))
            for ref, kind, text in cells:
                cell = ET.SubElement(row, "c", r=ref, t=kind)
                if kind == "inlineStr":
                    ET.SubElement(ET.SubElement(cell, "is"), "t").text = text
                else:
                    ET.SubElement(cell, "v").text = text
        return ET.tostring(root)
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="{dps.NS["r"]}"><sheets>'
                   '<sheet name="Agency Table" sheetId="9" r:id="table"/>'
                   '<sheet name="Legend Info" sheetId="1" r:id="legend"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="legend" Target="/xl/worksheets/sheet1.xml"/>'
                   '<Relationship Id="table" Target="worksheets/sheet9.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}"><si><t>ORI</t></si>'
                   '<si><r><t>Human Trafficking</t></r><r><t>\nCommercial Sex Acts</t></r></si></sst>')
        z.writestr("xl/worksheets/sheet9.xml", sheet([(1, [("A1", "s", "0"), ("C1", "n", "1200"),
                    ("D1", "inlineStr", "Synthetic"), ("F1", "s", "1")]), (3, [("AA3", "n", "4.0")])]))
        z.writestr("xl/worksheets/sheet1.xml", sheet([(1, [("A1", "inlineStr", "Data Type: NIBRS")])]))
    return buf.getvalue()


def test_xlsx_workbook_order_rels_shared_inline_numeric_sparse_cells():
    body = dps.xlsx_body(tiny_xlsx())
    assert list(body["sheets"]) == ["Agency Table", "Legend Info"]
    table = body["sheets"]["Agency Table"]
    assert table[0] == ["ORI", "", "1200", "Synthetic", "", "Human Trafficking\nCommercial Sex Acts"]
    assert table[1] == [] and table[2] == [""] * 26 + ["4.0"]
    assert body["sheets"]["Legend Info"] == [["Data Type: NIBRS"]]


def test_fetch_native_workbook_and_default_census_user_agent(context, monkeypatch):
    ad, raws = inputs(context)
    calls = []
    class Response(BytesIO):
        status = 200
        headers = {}
    def fake(req, timeout):
        calls.append(req)
        return Response(tiny_xlsx() if "DownloadReportExcel" in req.full_url else json.dumps(raws["places"].body).encode())
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert ad.fetch(raws["dps_615"].request, context).body == dps.xlsx_body(tiny_xlsx())
    assert ad.fetch(raws["places"].request, context).body == raws["places"].body
    assert calls[0].get_header("User-agent") == ad.user_agent
    assert calls[1].get_header("User-agent") == USER_AGENT
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: Response(b"<html>runtime error</html>"))
    with pytest.raises(BadZipFile):
        ad.fetch(raws["dps_615"].request, context)


def test_http_errors_fail_closed(context, monkeypatch):
    ad, raws = inputs(context)
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(dps.DPS, 500, "runtime error", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", fail)
    raw = ad.fetch(raws["dps_615"].request, context)
    assert raw.status == 500
    with pytest.raises(ValueError, match="HTTP 500"):
        list(ad.normalize(raw))


def test_native_headers_pairing_sums_and_change(context):
    ad, raws = inputs(context)
    agencies = {r.feature_id: r.properties for raw in list(raws.values())[:3] for r in ad.normalize(raw)}
    assert len(agencies) == 29  # 28 mapped plus one zero-population university, elsewhere ignored.
    a = agencies["TX2270100"]
    assert (a["violent"], a["property"], a["part1"]) == (10, 15, 25)
    assert a["reported_total"] == 33  # Trafficking and arson remain excluded from Part I.
    assert (a["rate_part1"], a["rate_violent"]) == (1.2, .5)  # 1.25 nearest-even.
    assert a["part1_prev"] == 10 and a["part1_change"] == 150.0
    assert agencies["TX2460500"]["part1_prev"] is agencies["TX2460500"]["part1_change"] is None
    assert agencies["TX2460400"]["safety_note"] == dps.SMALL
    assert agencies["TX2272500"]["rate_part1"] is None
    assert agencies["TX2270000"]["agency"] == "Travis County Sheriff's Office"
    assert agencies["TX2460500"]["agency"] == "Round Rock PD"


def test_zero_previous_count_change_is_missing(context):
    def modify(raws):
        table(raws)[3][3:10] = ["0"] * 7
    row = rows(context, modify)["484530001001"]
    assert row["part1_prev"] == 0 and row["part1_change"] is None


@pytest.mark.parametrize("mutate,match", [
    (lambda r: table(r)[1].__setitem__(3, "Unknown offense"), "unknown DPS header"),
    (lambda r: table(r)[1].__setitem__(3, "Rape"), "duplicate DPS header"),
    (lambda r: table(r)[1].pop(), "missing DPS header"),
    (lambda r: table(r).__delitem__(slice(2, 5)), "missing mapped DPS ORI"),
    (lambda r: table(r).extend(copy.deepcopy(table(r)[2:5])), "duplicate agency"),
    (lambda r: table(r)[2].__setitem__(2, "0"), "positive population"),
    (lambda r: table(r)[4].__setitem__(3, ""), "nonnegative integer"),
    (lambda r: table(r).__delitem__(4), "missing DPS current-year"),
    (lambda r: table(r)[3].__setitem__(1, "Number of Offenses - 2023"), "unexpected or duplicate"),
    (lambda r: table(r).insert(4, copy.deepcopy(table(r)[3])), "unexpected or duplicate"),
    (lambda r: table(r).__delitem__(2), "unpaired DPS year"),
    (lambda r: r["places"].body["features"].pop(), "missing current place"),
    (lambda r: r["places"].body["features"].append(copy.deepcopy(r["places"].body["features"][0])), "duplicate agency/place"),
    (lambda r: r["places"].body["features"][0]["properties"].__setitem__("BASENAME", "Wrong"), "GEOID/BASENAME"),
    (lambda r: r["places"].body.__setitem__("exceededTransferLimit", True), "truncated TIGER"),
    (lambda r: r["block_groups"].body["features"][0]["properties"].__setitem__("GEOID", "invalid"), "study block group"),
    (lambda r: r["block_groups"].body["features"].append(copy.deepcopy(r["block_groups"].body["features"][0])), "duplicate agency/place/block"),
])
def test_strict_table_and_geography_failures(context, mutate, match):
    with pytest.raises(ValueError, match=match):
        output(context, mutate)


def test_new_positive_population_agency_fails(context):
    def modify(raws):
        t = table(raws, "dps_652")
        row = next(r for r in t if r and r[0] == "TX2272500")
        row[2] = "1"
    with pytest.raises(ValueError, match="new agency: update the table"):
        output(context, modify)


def test_assignment_same_agency_across_counties_sheriffs_and_split(context, capsys):
    result = output(context)
    bgs = {r.feature_id: r.properties for r in result if r.dataset == "block_group"}
    assert bgs["484530001001"]["ori"] == bgs["484910001001"]["ori"] == "TX2270100"
    assert bgs["484910001001"]["county"] == "Williamson"
    assert bgs["482090001001"]["ori"] == "TX1050000"  # Outside mapped cities, including no-PD cities.
    assert bgs["484910001002"]["ori"] == "TX2460000"
    half = bgs["484530001003"]
    assert half["ori"] == "TX2270100" and half["agency_share"] == .5
    split = bgs["484530001002"]
    assert all(split[f] is None for f in dps.SAFETY_FIELDS)
    assert split["safety_note"] == dps.SPLIT
    assert dps.SHERIFF_COVERAGE in bgs["482090001001"]["coverage_note"]
    assert all(dps.COVERAGE in r["coverage_note"] for r in bgs.values())
    assert all(r["year"] == 2025 and r["period"] == "2025 (calendar year)" and r["retrieved"] == "2026-10-24" for r in bgs.values())
    # Counts and rates are the full agency totals on every assigned BG, independent of share/county.
    agency_rows = [r for r in bgs.values() if r["ori"] == "TX2270100"]
    assert len(agency_rows) == 3
    for field in ("violent", "property", "part1", "rate_part1", "rate_violent", "agency_population", "part1_prev", "part1_change"):
        assert len({r[field] for r in agency_rows}) == 1
    summary = next(r for r in result if r.dataset == "run_summary")
    assert summary.source_as_of == date(2025, 12, 31) and summary.geometry == dps.EMPTY
    assert summary.properties["agencies mapped"] == 28 and summary.properties["places matched"] == 25
    assert summary.properties["split block groups"] == 1
    assert summary.properties["block groups per agency"]["TX2270100"] == 3
    assert len(summary.properties["block groups per agency"]) == 28
    assert summary.properties["unmapped agency totals"] == {"TX2272500": {"violent": 10, "property": 55, "part1": 65, "reported_total": 73}}
    assert all(r["ori"] != "TX2272500" for r in bgs.values())
    assert '"unmapped agency totals"' in capsys.readouterr().err


@pytest.mark.parametrize("share,inside", [(.5 - 2e-9, False), (.5 - .5e-9, True), (.5, True), (.5 + 2e-9, True)])
def test_unrounded_half_tolerance_city_and_sheriff(share, inside):
    geom = box(0, 0, 1, 1)
    city = box(0, 0, share, 1)
    cities = {"TX2270100": city}
    ori, value = dps.assign(geom, cities, city, "453")
    assert ori == ("TX2270100" if inside else "TX2270000")
    assert value == pytest.approx(share if inside else 1 - share)
    # Sheriff threshold is independent of rounded share, even when no single city reaches half.
    cities = {"a": box(0, 0, .3, 1), "b": box(.3, 0, 1 - share, 1)}
    ori, value = dps.assign(geom, cities, union_all(list(cities.values())), "453")
    assert ori == ("TX2270000" if inside else None)


def test_equal_city_halves_use_stable_ori_tie():
    geom = box(0, 0, 1, 1)
    cities = {"TX2270200": box(.5, 0, 1, 1), "TX2270100": box(0, 0, .5, 1)}
    assert dps.assign(geom, cities, union_all(list(cities.values())), "453") == ("TX2270100", .5)


def test_places_repaired_block_groups_strict(context):
    def modify(raws):
        raws["places"].body["features"][0]["geometry"] = {"type": "Polygon", "coordinates": [
            [[-98, 30], [-97, 31], [-98, 31], [-97, 30], [-98, 30]]]}
    output(context, modify)
    def bad(raws):
        modify(raws)
        raws["block_groups"].body["features"][0]["geometry"] = raws["places"].body["features"][0]["geometry"]
    with pytest.raises(ValueError, match="invalid TIGER polygon"):
        output(context, bad)


def test_budget_live_gate_and_manifest(context, monkeypatch):
    gate = context.adapter_dir.parents[1] / "config/live_gates.yaml"
    gate.write_text((ROOT / "config/live_gates.yaml").read_text())
    config.clear_cache()
    budget = CallBudget.for_adapter("dps_agency", NOW)
    assert budget.per_day == 10 and budget.min_interval_seconds == 2
    assert config.live_gates()["dps_agency"] == "awaiting Claude's first live check"
    assert runner.run("dps_agency", "live", now=NOW).status == "skipped"
    layer = next(l for l in registry.load_layers() if l.id == "safety_agency_rate")
    assert layer.source == "dps_agency" and layer.refresh == "annual"
    assert layer.dataset == layer.join == "block_group" and not layer.default_visible
    assert layer.license == "" and "agency-wide" in layer.title
    assert "not specific to any street" in layer.description and "Reports are not convictions" in layer.description
    assert [l.label for l in layer.legend] == ["Below 10", "10 to below 20", "20 to below 30", "30 to below 50", "50 or more", "Not available"]
    assert layer.style.paint["fill-color"][3] == ["step", ["get", "rate_part1"], "#feedde", 10, "#fdbe85", 20, "#fd8d3c", 30, "#e6550d", 50, "#a63603"]
    assert next(p for p in layer.popup if p.field == "rate_part1").annotation_field == "retrieved"


def test_fixture_runner_publish_and_mocked_live_summary(context, monkeypatch, capsys):
    ad, raws = inputs(context)
    run = runner.run("dps_agency", "fixture", now=NOW)
    assert run.status == "success", run.errors
    layer = next(l for l in registry.load_layers() if l.source == "dps_agency")
    doc = json.loads(publish.published_path(layer).read_text())
    assert doc["test_data"] and len(doc["features"]) == 7
    assert not canonical.read("area_feature", "dps_agency")
    monkeypatch.setattr("mm.budget.time.sleep", lambda n: None)
    cls = type(adapter.load("dps_agency"))
    monkeypatch.setattr(cls, "fetch", lambda self, req, ctx: raws[req.key])
    monkeypatch.setattr(adapter, "load", lambda _: cls())
    live = runner.run("dps_agency", "live", now=NOW)
    assert live.status == "success" and live.calls_made == 5, live.errors
    assert not list((context.adapter_dir.parents[1] / "data/raw").rglob("*"))
    records = canonical.read("area_feature", "dps_agency")
    assert {r.dataset for r in records} == {"block_group", "run_summary"}
    spec = importlib.util.spec_from_file_location("dps_live_summary", ROOT / "tools/live_summary.py")
    summary = importlib.util.module_from_spec(spec); spec.loader.exec_module(summary)
    summary.main("dps_agency")
    assert "agencies mapped=28" in capsys.readouterr().out
    # A broken subsequent response cannot replace the previous successful published data.
    previous = publish.published_path(layer).read_bytes()
    raws["places"].body["features"].pop()
    bad = runner.run("dps_agency", "live", now=NOW + timedelta(days=1))
    assert bad.status == "failed"
    assert publish.published_path(layer).read_bytes() == previous


def test_header_positions_and_shared_string_number_formats(context):
    def modify(raws):
        t = table(raws)
        # Formatting in a shared string may contain grouping commas or a zero decimal.
        t[2][2] = "20,000"
        t[4][3] = "1.0"
        for i, row in enumerate(t[1:], 1):
            padded = row + [""] * (15 - len(row))
            padded[3], padded[7] = padded[7], padded[3]
            t[i] = padded
        t[1][6] = "Aggravated\n-Assault"
    row = rows(context, modify)["484530001001"]
    assert row["violent"] == 10 and row["property"] == 15
    assert row["rate_part1"] == 1.2 and row["agency_population"] == 20000


@pytest.mark.parametrize("value", ["", "-1", "NaN", "1,23", "1.5", "  "])
def test_missing_or_invalid_counts_never_become_zero(value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        dps.integer(value)


def test_nearest_even_rate_and_change(context):
    def modify(raws):
        t = table(raws)
        t[2][2] = "2000"
        t[3][3:10] = ["1", "0", "0", "0", "1", "1", "13"]  # 16 previously.
        t[4][3:10] = ["1", "0", "0", "0", "1", "1", "15"]  # 18 -> +12.5%.
    row = rows(context, modify)["484530001001"]
    assert row["rate_violent"] == .5 and row["rate_part1"] == 9.0
    assert row["part1_change"] == 12.5 and row["safety_note"] == dps.SMALL


def test_out_of_area_agencies_are_ignored_even_with_unusable_counts(context):
    def modify(raws):
        t = table(raws, "dps_652")
        pos = next(i for i, row in enumerate(t) if row and row[0] == "TX0010100")
        t[pos][2] = ""
        t[pos + 1][3:10] = [""] * 7
        t.pop(pos + 2)  # Missing current-year row elsewhere must not block the three counties.
    result = output(context, modify)
    assert next(r.properties for r in result if r.dataset == "run_summary")["agencies mapped"] == 28


def test_alphanumeric_oris_are_accepted(context):
    """Real 2025 files hold ORIs such as TXDPD0000 and TX227289E (checked 2026-10-24)."""
    def modify(raws):
        t = table(raws, "dps_652")
        header_width = len(t[1])
        blank = [""] * (header_width - 3)
        counts = ["0"] * (header_width - 4) + [""]
        t.extend([["TXDPD0000", "DALLAS PD", "1331217", *blank],
                  ["", "Number of Offenses - 2025", "", *counts],
                  ["TX227289E", "AUSTIN COMMUNITY COLLEGE PD", "0", *blank],
                  ["", "Number of Offenses - 2025", "", *counts]])
    result = output(context, modify)
    summary = next(r.properties for r in result if r.dataset == "run_summary")
    assert "TX227289E" in summary["unmapped agency totals"]
    assert "TXDPD0000" not in summary["unmapped agency totals"]
