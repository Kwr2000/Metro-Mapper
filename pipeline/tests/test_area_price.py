"""Synthetic published-home inputs only: medians, exclusions, privacy and atomic size cap."""
from copy import deepcopy
import json

import pytest

from mm import area_price, inputs
from mm.paths import paths

FIELDS=["category","market_value","living_area","block_group","range_pct","id","CANARY_PEOPLE"]
A,B,C,D=["48453"+f"{i:06d}"+"1" for i in range(1,5)]


def metadata():
    return {"test_data":True,"counties":{"Travis":{"value_as_of":["2026-01-01"]}},
            "value_range":{"published":True,"test_data":False,"hpi":{"factor":1,"as_of":"2026-06-30"},
                           "levels":{"48453":1},"study_year":2024}}


def document():
    rows=[]
    def add(group,values):
        for v in values:rows.append(["single_family",v,1000,group,10,f"48453:{len(rows)}","CANARY"])
    add(A,range(100000,1000001,100000));add(B,[100000]*9)
    add(C,[100000]*5+[101000]*5);add(D,[101000]*5+[102000]*5)
    for field,value in [(0,"condo"),(2,None),(2,0),(3,None),(4,None),(1,0)]:
        row=list(rows[0]);row[field]=value;row[5]=f"48453:{len(rows)}";rows.append(row)
    return {"v":1,"test_data":True,"fields":FIELDS,"rows":rows}


def test_ordinary_medians_inclusive_ten_homes_exclusions_and_whole_dollar_ties(repo):
    result=area_price.build(metadata(),[document()])
    assert result["rows"]=={A:[10,550],C:[10,100],D:[10,102]}
    assert result["test_data"] and "without a block-group location" in result["method"]
    assert "2026-01-01" in result["as_of"] and "2026-06-30" in result["as_of"] and "2024" in result["as_of"]
    assert "CANARY" not in json.dumps(result)


def test_unpublished_ranges_have_no_area_prices(repo):
    meta=metadata();meta["value_range"]["published"]=False
    def never():
        pytest.fail("Unpublished home rows were read");yield
    result=area_price.build(meta,never());assert result["rows"]=={} and "unpublished" in result["method"]


def test_accepted_calibration_matches_the_home_formula_and_uses_county_fallback(repo):
    meta=metadata();meta["value_range"]["calibration"]={"used":True}
    cal={"v":1,"fit_year":2025,"test_year":2024,"test_data":True,
         "county":{"48453":1.1},"tract":{A[:11]:1.2}}
    result=area_price.build(meta,[document()],cal)
    assert result["rows"]=={A:[10,660],C:[10,110],D:[10,112]}
    assert "2025" in result["as_of"] and "2024" in result["as_of"]
    with pytest.raises(ValueError,match="calibration"):area_price.build(meta,[document()])
    meta["value_range"]["calibration"]["used"]=False
    assert area_price.build(meta,[document()],cal)["rows"][A]==[10,550]


def test_only_allowlisted_home_cells_are_read_and_demographic_inputs_are_guarded(repo,monkeypatch):
    class Cells(list):
        def __getitem__(self,index):
            assert index<6,"Read People cell";return super().__getitem__(index)
    doc=document();doc["rows"]=[Cells(row) for row in doc["rows"]]
    assert area_price.build(metadata(),[doc])["rows"][A]==[10,550]
    assert set(inputs.SCORE_INPUTS["area_price"])==set(area_price.INPUTS)
    monkeypatch.setitem(inputs.SCORE_INPUTS,"area_price",[*area_price.INPUTS,"bachelors_plus_share"])
    with pytest.raises(inputs.DemographicInputError):area_price.build(metadata(),[doc])


def test_publish_is_deterministic_offline_and_size_failure_keeps_previous(repo,monkeypatch):
    folder=paths().web_public/"data/homes";(folder/"addr").mkdir(parents=True)
    (folder/"meta.json").write_text(json.dumps(metadata()));(folder/"addr/TE.json").write_text(json.dumps(document()))
    from mm import adapter, canonical
    def no_source(*args,**kwargs):pytest.fail("Source access from area price publisher")
    monkeypatch.setattr(adapter,"load",no_source);monkeypatch.setattr(canonical,"read",no_source)
    first=area_price.publish();target=folder.parent/"area_price.json";before=target.read_bytes()
    assert len(before)<100000 and json.loads(before)==first
    area_price.publish();assert target.read_bytes()==before
    monkeypatch.setattr(area_price,"build",lambda *args:{"padding":"x"*100000})
    with pytest.raises(ValueError,match="100 KB"):area_price.publish()
    assert target.read_bytes()==before


def test_duplicate_and_invalid_geographies_fail_closed(repo):
    doc=document();doc["rows"].append(doc["rows"][0])
    with pytest.raises(ValueError,match="duplicate"):area_price.build(metadata(),[doc])
    doc=document();doc["rows"][0][3]="not-a-geoid"
    with pytest.raises(ValueError,match="geography"):area_price.build(metadata(),[doc])
