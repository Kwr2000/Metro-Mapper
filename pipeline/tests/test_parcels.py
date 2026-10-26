"""Tiny native shapefiles: property-only ingestion, grouping, coverage and cleanup."""
import copy
import gzip
import importlib.util
import json
import urllib.error
from datetime import date, datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
import shapefile
from pyproj import CRS
from shapely.geometry import Point, box, mapping

from mm import adapter, canonical, config, privacy, runner
from mm.adapter import RawPayload, RunContext
from mm.budget import CallBudget
from mm.manifests import load_layers
from mm.paths import paths

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("parcels_under_test", ROOT / "adapters/parcels/adapter.py")
parcels = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(parcels)
NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
PRIVATE_FIELDS = ("OWNER_NAME", "NAME_CARE", "MAIL_ADDR", "LEGAL_DESC", "MKT_VALUE")
CANARIES = ("CANARY_OWNER", "CANARY_CARE", "CANARY_MAIL", "CANARY_LEGAL", "CANARY_UNUSED")


@pytest.fixture
def context(repo):
    return RunContext("fixture", NOW, CallBudget.for_adapter("parcels", NOW), repo / "adapters/parcels")


def inputs(context):
    ad = parcels.Parcels()
    return ad, {r.key: adapter.read_fixture("parcels", r) for r in ad.plan(context)}


def output(context, modify=None):
    ad, raws = inputs(context)
    if modify: modify(raws)
    return ad.finalize([r for raw in raws.values() for r in ad.normalize(raw)])


def tiny_zip(tmp_path, fips="48453", *, projection=4326, omit=None, duplicate=False, change=None, invalid_private=False):
    """Native field names/types, disjoint repeated polygons and personal-field canaries."""
    folder = tmp_path / ("source-" + fips); folder.mkdir(exist_ok=True)
    stem = "stratmap-2026-land-parcels-" + parcels.COUNTIES[fips].lower() + "_" + fips
    base = folder / stem
    fields = [("PROP_ID", "C", 10, 0), ("GEO_ID", "C", 50, 0), ("GIS_AREA", "F", 31, 15),
              ("GIS_AREA_U", "C", 8, 0), ("FIPS", "N", 11, 0), ("DATE_ACQ", "D", 8, 0), ("TAX_YEAR", "C", 4, 0)]
    fields += [(name, "C", 40, 0) for name in PRIVATE_FIELDS]
    acquired = date(2026, 2, 1) if fips == "48209" else date(2026, 7, 1)
    identity = "R070302" if fips == "48491" else "123"
    rows = [
        [identity, "", 1.1114, "Acres", int(fips), acquired, "2026"],
        ["456", "GEO-SINGLE", 2.2222, "Acres", int(fips), acquired, "2026"],
        [identity, "GEO-FIRST", 3.3334, "Acres", int(fips), acquired, "2026"],
        [identity, "GEO-CONFLICT", 4.4444, "Acres", int(fips), acquired, "2026"],
        ["", "", 0, "Acres", int(fips), acquired, "2026"],
        ["0", "", 0, "Acres", int(fips), acquired, "2026"],
    ]
    # Repeated ID's centroid falls in the gaps, but the representative point stays inside.
    geometries = [box(-97.8 + i*.02, 30.3, -97.79+i*.02, 30.31) for i in range(len(rows))]
    if change: change(rows, geometries)
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON) as writer:
        for field in fields:
            if field[0] != omit: writer.field(*field)
        for row, geom in zip(rows, geometries):
            coords = list(geom.exterior.coords)[::-1]
            writer.poly([coords])
            values = row + list(CANARIES)
            writer.record(*[v for field, v in zip(fields, values) if field[0] != omit])
    if invalid_private:
        # Invalid UTF-8 in an unselected DBF cell proves it is never decoded.
        dbf = base.with_suffix(".dbf")
        data = bytearray(dbf.read_bytes())
        header_len = int.from_bytes(data[8:10], "little")
        offset = 1 + sum(field[2] for field in fields[:7])
        data[header_len + offset] = 255
        dbf.write_bytes(data)
    base.with_suffix(".prj").write_text(CRS.from_epsg(projection).to_wkt(version="WKT1_ESRI"))
    archive = BytesIO()
    with ZipFile(archive, "w") as z:
        for suffix in ("shp", "shx", "dbf", "prj"):
            if omit == suffix: continue
            z.writestr("nested/" + stem + "." + suffix, base.with_suffix("." + suffix).read_bytes())
            if duplicate and suffix == "prj": z.writestr("elsewhere/" + stem + ".prj", base.with_suffix(".prj").read_bytes())
        z.writestr(stem + ".cpg", "UTF-8")
        z.writestr(stem + ".shp.xml", "CANARY_UNUSED metadata must not be extracted")
    return archive.getvalue(), geometries


def test_four_call_plan_budgeted_urls_only(context):
    ad, raws = inputs(context)
    assert list(raws) == ["stratmap_48453", "stratmap_48491", "stratmap_48209", "block_groups"]
    assert ad.cadence == "annual" and not ad.retain_raw and not ad.recordable
    for fips in parcels.COUNTIES:
        assert raws["stratmap_"+fips].request.params == {"fips":fips, "url": parcels.S3.format(fips)}
    assert raws["block_groups"].request.params == {"url": parcels.TIGER, "query": {
        "where": "STATE='48' AND COUNTY IN ('453','491','209')", "outFields":"GEOID",
        "outSR":4326, "f":"geojson", "returnGeometry":"true"}}


def test_parser_reads_only_allowlist_unions_duplicates_first_geo_and_sums(context, tmp_path, monkeypatch):
    data, geometries = tiny_zip(tmp_path, invalid_private=True)
    archive = tmp_path / "archive.zip"; archive.write_bytes(data)
    selected, opened = [], []
    original = shapefile.Reader.iterRecords
    def spy(self, *args, **kwargs):
        selected.append(kwargs.get("fields"))
        yield from original(self, *args, **kwargs)
    monkeypatch.setattr(shapefile.Reader, "iterRecords", spy)
    def forbidden(*args, **kwargs): raise AssertionError("unrestricted DBF read")
    monkeypatch.setattr(shapefile.Reader, "records", forbidden)
    monkeypatch.setattr(shapefile.Reader, "record", forbidden)
    extracted = tmp_path / "extract"; extracted.mkdir()
    body = parcels.parse_parcels(archive, extracted, "48453")
    assert selected == [list(parcels.FIELDS)]
    assert set(p.suffix for p in extracted.iterdir()) == {".shp", ".shx", ".dbf", ".prj"}
    assert len(body["parcels"]) == 2
    first = next(row for row in body["parcels"] if row[0] == "123")
    assert first[1] == "GEO-FIRST" and first[2] == 8.889
    assert any(g.covers(Point(first[3:])) for g in (geometries[0], geometries[2], geometries[3]))
    assert not any(c in json.dumps(body) for c in (*CANARIES, *PRIVATE_FIELDS))
    assert body["skipped"] == {"records_read":6, "blank_ids":1, "zero_ids":1,
        "repeated_ids_merged":1, "repeated_records_merged":2, "geo_id_conflicts":1}
    assert body["date_acq"] == "2026-07-01" and body["tax_year"] == "2026"


@pytest.mark.parametrize("change, match", [
    (lambda rows, g: rows[0].__setitem__(3, "Meters"), "Acres"),
    (lambda rows, g: rows[0].__setitem__(4, 48491), "FIPS"),
    (lambda rows, g: rows[0].__setitem__(2, -1), "acreage"),
    (lambda rows, g: rows[0].__setitem__(5, None), "acquisition date"),
    (lambda rows, g: rows[0].__setitem__(6, "2025"), "TAX_YEAR"),
    (lambda rows, g: rows[0].__setitem__(5, date(2026, 1, 1)), "DATE_ACQ"),
])
def test_parser_metadata_failures(tmp_path, change, match):
    data, _ = tiny_zip(tmp_path, change=change)
    archive=tmp_path/"source.zip"; archive.write_bytes(data)
    with pytest.raises(ValueError, match=match): parcels.parse_parcels(archive, tmp_path, "48453")


def test_non_wgs84_projection_and_missing_dbf_field_fail(tmp_path):
    for projection, omit, match in [(3857, None, "WGS84"), (4269, None, "WGS84"), (4326, "GEO_ID", "DBF field")]:
        data, _ = tiny_zip(tmp_path, projection=projection, omit=omit)
        archive = tmp_path/"source.zip"; archive.write_bytes(data)
        with pytest.raises(ValueError, match=match): parcels.parse_parcels(archive, tmp_path, "48453")


class Response(BytesIO):
    status = 200
    def __init__(self, data):
        super().__init__(data); self.headers={"Content-Length":str(len(data))}
    def read(self, size=-1):
        assert 0 < size <= 1024*1024
        return super().read(size)


def test_streaming_fetch_cleans_temp_files_and_canaries_before_return(context, tmp_path, monkeypatch):
    ad, raws = inputs(context)
    data,_=tiny_zip(tmp_path, invalid_private=True)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a,**kw:Response(data))
    raw=ad.fetch(raws["stratmap_48453"].request, context)
    assert raw.status==200
    assert not list(paths().raw.rglob("*"))
    assert not any(c in json.dumps(raw.body) for c in (*CANARIES, *PRIVATE_FIELDS))


@pytest.mark.parametrize("kind", ["not_zip", "missing_shp", "duplicate_prj", "bad_projection", "missing_field", "stream", "length", "http", "deadline"])
def test_download_parse_failures_clean_up_and_withhold_payload(context, tmp_path, monkeypatch, kind):
    ad,raws=inputs(context)
    data,_=tiny_zip(tmp_path, omit="shp" if kind=="missing_shp" else "PROP_ID" if kind=="missing_field" else None,
        duplicate=kind=="duplicate_prj", projection=3857 if kind=="bad_projection" else 4326)
    if kind=="not_zip": data=b"CANARY_OWNER not a ZIP"
    class Broken(Response):
        def read(self,size=-1):
            if kind=="stream":
                super().read(10)
                raise OSError("CANARY_MAIL transfer failure")
            return super().read(size)
    response=Broken(data)
    if kind=="length": response.headers["Content-Length"]=str(len(data)+1)
    if kind=="http": response.status=500
    if kind=="deadline": ad.started-=1800
    monkeypatch.setattr("urllib.request.urlopen", lambda *a,**kw:response)
    raw=ad.fetch(raws["stratmap_48453"].request,context)
    assert raw.status!=200 and not list(paths().raw.rglob("*"))
    assert not any(c in repr(raw.body) for c in CANARIES)
    with pytest.raises(ValueError,match="HTTP"): ad.follow_up(raw,context)


def test_points_identifiers_tract_latest_date_and_count_only_summary(context, capsys):
    result=output(context)
    rows=[r for r in result if r.dataset=="parcel"]
    assert len(rows)==6
    for rec in rows:
        props=rec.properties
        assert set(props)=={"county","prop_id","geo_id","acres","block_group","tract","parcel_as_of"}
        assert rec.feature_id==next(f for f,c in parcels.COUNTIES.items() if c==props["county"])+":"+props["prop_id"]
        assert props["block_group"].startswith(rec.feature_id[:5]) and props["tract"]==props["block_group"][:11]
        assert rec.geometry["type"]=="Point" and all(v==round(v,6) for v in rec.geometry["coordinates"])
        assert rec.source_as_of==date(2026,7,1)
        assert props["parcel_as_of"]==("2026-02-01" if props["county"]=="Hays" else "2026-07-01")
        assert not privacy.personal_keys(props)
    assert next(r for r in rows if r.feature_id=="48491:R070302").properties["prop_id"]=="R070302"
    assert next(r for r in rows if r.feature_id=="48453:00123").properties["prop_id"]=="00123"
    summary=next(r for r in result if r.dataset=="run_summary")
    assert summary.geometry==parcels.EMPTY and summary.properties["parcels"]==6
    assert summary.properties["runtime_seconds"]<1800 and summary.properties["peak_memory_mb"]>0
    assert summary.properties["counties"]["Travis"]["records_read"]==5
    assert '"blank_ids": 1' in capsys.readouterr().err


def hundred_points(raws, outside=1):
    for fips,count in (("48453",98),("48491",1),("48209",1)):
        body=raws["stratmap_"+fips].body
        base=body["parcels"][0]
        body["parcels"]=[[str(i+1),None,1,base[3],base[4]] for i in range(count)]
        body["skipped"]={**dict.fromkeys(parcels.COUNTERS,0),"records_read":count}
    for i in range(outside):raws["stratmap_48453"].body["parcels"][i][3:]=[-99,32]


def test_outside_count_exact_99_percent_and_county_crossing(context):
    def modify(raws):
        hundred_points(raws)
        # A Travis record whose interior point falls in a Williamson BG keeps that real BG.
        raws["stratmap_48453"].body["parcels"][1][3:]=raws["stratmap_48491"].body["parcels"][0][3:]
    result=output(context,modify)
    outside=next(r for r in result if r.feature_id=="48453:1")
    assert outside.properties["block_group"] is outside.properties["tract"] is None
    assert next(r for r in result if r.feature_id=="48453:2").properties["block_group"].startswith("48491")
    summary=next(r for r in result if r.dataset=="run_summary").properties
    assert summary["points_without_block_group"]==summary["counties"]["Travis"]["points_without_block_group"]==1
    with pytest.raises(ValueError,match="99%"):
        output(context,lambda raws:hundred_points(raws,2))


@pytest.mark.parametrize("modify, match", [
    (lambda r:r["stratmap_48453"].body["parcels"].__setitem__(0,["0",None,1,-97.79,30.31]),"property ID"),
    (lambda r:r["stratmap_48453"].body["parcels"][0].__setitem__(2,-1),"acreage"),
    (lambda r:r["stratmap_48453"].body["parcels"][0].__setitem__(3,float("nan")),"coordinates"),
    (lambda r:r["stratmap_48453"].body["skipped"].__setitem__("records_read",100),"reconcile"),
    (lambda r:r["stratmap_48453"].body.__setitem__("OWNER_NAME","CANARY_OWNER"),"compact parcel response"),
    (lambda r:r["stratmap_48453"].body["parcels"].__setitem__(1,copy.deepcopy(r["stratmap_48453"].body["parcels"][0])),"duplicate"),
    (lambda r:r["block_groups"].body.__setitem__("exceededTransferLimit",True),"truncated"),
    (lambda r:r["block_groups"].body["features"].append(copy.deepcopy(r["block_groups"].body["features"][0])),"duplicate"),
])
def test_compact_schema_count_and_duplicate_guards(context,modify,match):
    with pytest.raises(ValueError,match=match):output(context,modify)


def test_live_kept_counts_and_deadline_guards_are_not_bypassed(context):
    ad,raws=inputs(context);ad.live=True
    with pytest.raises(ValueError,match="2%"):
        ad.finalize([r for raw in raws.values() for r in ad.normalize(raw)])
    parcels.count_checks(parcels.EXPECTED)
    for fips in parcels.COUNTIES:
        bad={**parcels.EXPECTED,fips:int(parcels.EXPECTED[fips]*.97)}
        with pytest.raises(ValueError,match="2%") :parcels.count_checks(bad)
    ad.started-=1800
    with pytest.raises(ValueError,match="30-minute"):ad.check_time()


def test_budget_live_gate_and_no_map_layer(context):
    budget=CallBudget.for_adapter("parcels",NOW)
    assert (budget.per_day,budget.min_interval_seconds,budget.max_minutes)==(6,5,30)
    assert not any(l.source=="parcels" for l in load_layers())
    (paths().config/"live_gates.yaml").write_text((ROOT/"config/live_gates.yaml").read_text());config.clear_cache()
    assert config.live_gates()["parcels"]=="awaiting Claude's first live check"
    run=runner.run("parcels","live",now=NOW)
    assert run.status=="skipped" and run.calls_made==0


def test_mocked_live_storage_canaries_absent_saved_summary_and_failure_keeps_previous(context,tmp_path,monkeypatch,capsys):
    ad,raws=inputs(context)
    assert runner.run("parcels","fixture",now=NOW).status=="success"
    assert not canonical.read("area_feature","parcels")
    cls=type(adapter.load("parcels"))
    monkeypatch.setitem(cls.finalize.__globals__,"count_checks",lambda counts:None) # Tiny mocked live run only; production guard tested separately.
    blobs={f:tiny_zip(tmp_path,f)[0] for f in parcels.COUNTIES}
    class JsonResponse(BytesIO):status=200
    def fake(req,**kwargs):
        for f in parcels.COUNTIES:
            if f in req.full_url:return Response(blobs[f])
        return JsonResponse(json.dumps(raws["block_groups"].body).encode())
    monkeypatch.setattr("urllib.request.urlopen",fake)
    monkeypatch.setattr(adapter,"load",lambda _:cls())
    monkeypatch.setattr("mm.budget.time.sleep",lambda _:None)
    # Tiny native SHPs all use the same synthetic location; use one study polygon containing them.
    raws["block_groups"].body["features"][0]["geometry"]=mapping(box(-97.81,30.29,-97.65,30.32))
    live=runner.run("parcels","live",now=NOW)
    assert live.status=="success" and live.calls_made==4,live.errors
    stored=canonical.read("area_feature","parcels")
    assert len(stored)==7 and {r.dataset for r in stored}=={"parcel","run_summary"}
    assert not list(paths().raw.rglob("*"))
    audit_spec=importlib.util.spec_from_file_location("parcel_summary",ROOT/"tools/live_summary.py")
    audit=importlib.util.module_from_spec(audit_spec);audit_spec.loader.exec_module(audit)
    audit.main("parcels")
    logs=capsys.readouterr()
    for text in (logs.out,logs.err,live.model_dump_json(),*[r.model_dump_json() for r in stored]):
        assert not any(v in text for v in (*CANARIES,*PRIVATE_FIELDS))
    for file in paths().data.rglob("*"):
        if file.is_file():
            text=gzip.open(file,"rt").read() if file.suffix==".gz" else file.read_text()
            assert not any(v in text for v in (*CANARIES,*PRIVATE_FIELDS))
    assert 'counties=' in logs.out and '"records_read": 6' in logs.err
    assert not list(paths().published_layers.glob("*parcels*"))
    path=canonical.path_for("area_feature","parcels");previous=path.read_bytes()
    raws["block_groups"].body["features"][0]["geometry"]=mapping(box(-90,10,-89,11))
    failed=runner.run("parcels","live",now=NOW+timedelta(days=1))
    assert failed.status=="failed" and path.read_bytes()==previous


def test_valid_polygons_are_not_repaired_but_invalid_polygon_is_repaired(tmp_path, monkeypatch):
    from shapely.geometry import Polygon
    original=parcels.make_valid
    calls=[]
    def repair(geom):calls.append(geom);return original(geom)
    monkeypatch.setattr(parcels,"make_valid",repair)
    data,_=tiny_zip(tmp_path)
    archive=tmp_path/"source.zip";archive.write_bytes(data)
    parcels.parse_parcels(archive,tmp_path,"48453")
    assert not calls
    def invalid(rows,geoms):
        geoms[0]=Polygon([(-97.8,30.3),(-97.79,30.31),(-97.8,30.31),(-97.79,30.3),(-97.8,30.3)])
    data,_=tiny_zip(tmp_path,change=invalid);archive.write_bytes(data)
    body=parcels.parse_parcels(archive,tmp_path,"48453")
    assert len(calls)==1 and len(body["parcels"])==2


def test_boundary_point_is_covered_and_smallest_geoid_breaks_tie(context):
    def modify(raws):
        features=raws["block_groups"].body["features"]
        features[0]["geometry"]=mapping(box(-97.8,30.3,-97.79,30.35))
        features.append({"type":"Feature","properties":{"GEOID":"484530000001"},
                         "geometry":mapping(box(-97.79,30.3,-97.75,30.35))})
        raws["stratmap_48453"].body["parcels"][0][3]=-97.79
    result=output(context,modify)
    assert next(r for r in result if r.feature_id=="48453:00123").properties["block_group"]=="484530000001"


def test_two_percent_count_edges_need_no_large_synthetic_data():
    import math
    for fips,expected in parcels.EXPECTED.items():
        for count in (math.ceil(expected*.98),math.floor(expected*1.02)):
            parcels.count_checks({**parcels.EXPECTED,fips:count})
        for count in (math.ceil(expected*.98)-1,math.floor(expected*1.02)+1):
            with pytest.raises(ValueError,match="2%"):
                parcels.count_checks({**parcels.EXPECTED,fips:count})
