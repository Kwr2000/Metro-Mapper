"""Only allowed measures feed the area score; never demographics or elections."""
import argparse
from copy import deepcopy
import json

import pytest
from shapely.geometry import shape

from mm import area_score, canonical, cli, inputs
from mm.paths import paths
from mm.schemas import AreaFeature


def polygon(left=0,right=10,bottom=0,top=2):
    return {"type":"Polygon","coordinates":[[[left,bottom],[right,bottom],[right,top],[left,top],[left,bottom]]]}


def record(dataset,identity,properties=None,geometry=None):
    return {"dataset":dataset,"feature_id":identity,"geometry":geometry or polygon(),"properties":properties or {},"source_as_of":"2026-01-01"}


def records():
    ids=[f"48453000100{i}" for i in range(1,5)]
    data={source:[] for source in area_score.SOURCES}
    for i,identity in enumerate(ids):
        data["areas"].append(record("block_group",identity,geometry=polygon(i*10,i*10+8)))
        data["dps_agency"].append(record("block_group",identity,{"rate_part1":[10,20,20,None][i]}))
        data["fema_nfhl"].append(record("block_group",identity,{"flood_share_1pct":[0,.1,.2,None][i]}))
        data["access"].append(record("block_group",identity,{"walk_basket":[10,20,30,None][i],"bike_basket":[5,10,None,20][i],
            "walk_grocery":[1,2,3,None][i],"walk_park":[2,4,6,None][i],"transit_per_hour":[0,1,2,None][i]}))
    data["schools"]=[record("district","1",{"overall_score":80,"ratings_year":"2024–25"},polygon(-1,19)),
                     record("district","2",{"overall_score":None,"ratings_year":"2024–25"},polygon(19,50))]
    # Campus and benchmark values must not enter the district score.
    data["schools"].append(record("campus","99",{"overall_score":1000}))
    return data


def test_midrank_ties_flips_null_and_singleton():
    values={"a":10,"b":20,"c":20,"d":None}
    assert area_score.percentiles(values)=={"a":17,"b":67,"c":67,"d":None}
    assert area_score.percentiles(values,lower=True)=={"a":83,"b":33,"c":33,"d":None}
    assert area_score.percentiles({"one":4})=={"one":50}
    assert area_score.percentiles({"a":0,"b":0})=={"a":50,"b":50}
    assert area_score.percentiles({"a":None})=={"a":None}
    for value in (True,float("nan"),float("inf"),"10"):
        with pytest.raises(ValueError):area_score.percentiles({"a":value})


def test_district_assignment_uses_interior_point_not_overlap_or_campus():
    area=record("block_group","484530001001",geometry=polygon())
    # The midpoint is in the right district; no overlap averaging occurs.
    districts=[record("district","1",{"overall_score":10},polygon(-1,4)),record("district","2",{"overall_score":90},polygon(4,11))]
    assert shape(districts[1]["geometry"]).covers(shape(area["geometry"]).representative_point())
    assert area_score.district_values([area],districts)=={area["feature_id"]:90}
    districts[1]["properties"]["overall_score"]=None
    assert area_score.district_values([area],districts)[area["feature_id"]] is None
    assert area_score.district_values([area],[])[area["feature_id"]] is None
    # Shared boundary: choose stable district ID, independent of record order.
    districts[0]["geometry"]=polygon(-1,5);districts[1]["geometry"]=polygon(5,11)
    assert area_score.district_values([area],list(reversed(districts)))[area["feature_id"]]==10


def test_composite_percentiles_require_both_parts_and_transit_zero_is_measured(repo):
    doc=area_score.build(records())
    assert len(doc["rows"])==4 and [f["id"] for f in doc["factors"]]==["safety","schools","flood","daily","grocery_parks","transit"]
    a,b,c,d=doc["rows"].values()
    assert a[:6]==[83,50,83,83,83,17] and b[:6]==[33,50,50,50,50,50]
    assert c[3] is None and c[4]==17
    assert a[-1]==0 and a[5]==17 and d[-1] is None and d[5] is None
    assert all(len(row)==14 for row in doc["rows"].values())
    assert not doc["test_data"] and not any(f["test_data"] for f in doc["factors"])
    assert all(f["test_data"] for f in area_score.build(records(),fixtures=["areas"])["factors"])


def test_registered_input_allowlist_and_guarded_property_access(repo,monkeypatch):
    expected={"rate_part1","overall_score","flood_share_1pct","walk_basket","bike_basket","walk_grocery","walk_park","transit_per_hour"}
    assert set(inputs.SCORE_INPUTS["area_score"])==expected
    class Guarded(dict):
        def get(self,key,default=None):
            assert key in expected;return super().get(key,default)
        def __getitem__(self,key):
            assert key in expected;return super().__getitem__(key)
    data=records()
    for rows in data.values():
        for r in rows:r["properties"]=Guarded({**r["properties"],"bachelors_plus_share":"CANARY_DEMOGRAPHIC","margin_2024":"CANARY_ELECTION"})
    assert "CANARY" not in json.dumps(area_score.build(data))
    monkeypatch.setitem(inputs.SCORE_INPUTS,"area_score",[*expected,"bachelors_plus_share"])
    with pytest.raises(inputs.DemographicInputError):area_score.build(data)


def seed():
    for source,rows in records().items():canonical.write("area_feature",source,[AreaFeature.model_validate(r) for r in rows])


def test_stored_only_publish_size_determinism_and_missing_fixture_badges(repo,monkeypatch):
    seed();seen=[];original=area_score.source_records
    def allowlisted(source):
        assert source in area_score.SOURCES;seen.append(source);return original(source)
    monkeypatch.setattr(area_score,"source_records",allowlisted)
    first=area_score.publish();target=paths().web_public/"data/area_score.json";payload=target.read_bytes()
    assert set(seen)==set(area_score.SOURCES) and not first["test_data"] and len(payload)<1_000_000
    for f in first["factors"]:assert f["source"] and f["as_of"] and f["field"] and f["note"]
    for source,rows in records().items():canonical.write("area_feature",source,[AreaFeature.model_validate(r) for r in reversed(rows)])
    area_score.publish();assert target.read_bytes()==payload
    canonical.path_for("area_feature","access").unlink()
    mixed=area_score.publish();assert mixed["test_data"] and mixed["factors"][3]["test_data"] and not mixed["factors"][0]["test_data"]
    monkeypatch.setattr(area_score,"build",lambda *args,**kwargs:{"v":1,"rows":{},"padding":"x"*1_000_000})
    before=target.read_bytes()
    with pytest.raises(ValueError,match="1 MB"):area_score.publish()
    assert target.read_bytes()==before


def test_fixture_only_publish_never_loads_demographic_or_election_source(repo,monkeypatch):
    original=area_score.source_records;seen=[]
    def only(source):
        assert source in area_score.SOURCES;seen.append(source);return original(source)
    monkeypatch.setattr(area_score,"source_records",only)
    doc=area_score.publish();assert doc["test_data"] and len(doc["rows"])==8
    assert all(f["test_data"] for f in doc["factors"]) and len(seen)==5


@pytest.mark.slow
def test_mm_publish_calls_area_publisher_offline(repo):
    assert cli._cmd_publish(argparse.Namespace())==0
    document=json.loads((paths().web_public/"data/area_score.json").read_text())
    assert document["v"]==1 and document["test_data"] and len(document["rows"])==8
