"""Native synthetic CSV privacy, tract-only validation and fail-closed publication."""
from copy import deepcopy
from datetime import datetime, timezone
import csv
import importlib.util
from io import BytesIO, StringIO
import itertools
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from mm import canonical, config, homes, inputs, runner, values
from mm.adapter import RawPayload, Request, RunContext
from mm.budget import CallBudget
from mm.manifests import load_layers
from mm.paths import paths
from mm.schemas import AreaFeature

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026,10,28,12,tzinfo=timezone.utc)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name,ROOT/path)
    result = importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


hmda = module("hmda_test_adapter","adapters/hmda/adapter.py")
fixtures = module("hmda_test_fixtures","adapters/hmda/make_fixtures.py")
helpers = module("hmda_home_helpers","pipeline/tests/test_homes.py")


def context(repo, mode="fixture"):
    return RunContext(mode,NOW,CallBudget.for_adapter("hmda",NOW),repo/"adapters/hmda")


def native_row(**changes):
    return {**dict(zip(values.HMDA_INPUTS,("2025","48453","48453000100","1","1","1",hmda.DWELLING,"1","405000"))),**changes}


def csv_bytes(rows, fields=None):
    output=StringIO(newline="");writer=csv.DictWriter(output,fieldnames=fields or values.HMDA_INPUTS,lineterminator="\r\n")
    writer.writeheader();writer.writerows(rows);return output.getvalue().encode()


def production_csv():
    # 30,323 synthetic loans, 300 tracts, every tract has at least 100 loans.
    counties=list(hmda.COUNTIES)
    return csv_bytes(native_row(county_code=counties[i%3],census_tract=counties[i%3]+f"{i//3%100+1:06d}") for i in range(30323))


def test_native_header_filters_tract_percentiles_and_count_only_audit(repo,capsys):
    ad=hmda.HMDA();assert ad.plan(context(repo))==[hmda.REQUEST]
    records=list(ad.normalize(RawPayload(hmda.REQUEST,fixtures.native_text())))
    tracts=[r for r in records if r.dataset=="hmda_tract"]
    assert len(tracts)==3
    assert tracts[1].properties=={"county":"Travis","tract":"48453000100","year":2025,"loans":30,
        "median_value":445000,"p25_value":375000,"p75_value":525000}
    assert all(r.geometry==hmda.EMPTY and r.source_as_of.isoformat()=="2025-12-31" for r in records)
    summary=records[-1].properties
    assert summary["rows_read"]==100 and summary["kept"]==90 and summary["tracts_30_loans"]==3
    assert sum(summary["skipped_by_reason"].values())==10
    assert set(summary["skipped_by_reason"])=={"action_taken","loan_purpose","lien_status","derived_dwelling_category","total_units",
        "value_exempt","value_na","value_blank","value_non_digits","tract_invalid"}
    assert ad.finalize(records)==records and ad.source_as_of([])==hmda.AS_OF
    assert "run note" in capsys.readouterr().out
    # Even-sized groups use nearest-rank, not the mean of the middle observations.
    parsed=hmda.parse(BytesIO(csv_bytes([native_row(property_value=str(v)) for v in (40000,10000,30000,20000)] +
        [native_row(county_code=c,census_tract=c+"000100") for c in ("48491","48209")])))["tracts"]
    assert parsed[1]["median_value"]==20000 and parsed[1]["p25_value"]==10000 and parsed[1]["p75_value"]==30000


@pytest.mark.parametrize("chunk_size",[1,2,7,65536])
def test_only_nine_cells_are_buffered_or_decoded_even_with_quoted_canaries(monkeypatch,chunk_size,capsys):
    private=("lei","derived_race","derived_ethnicity","derived_sex","income","debt_to_income_ratio",
        "applicant_age","co-applicant_age","applicant_credit_score_type","co-applicant_credit_score_type",
        "applicant_sex","co-applicant_sex","applicant_race-1","co-applicant_race-1",
        "applicant_ethnicity-1","co-applicant_ethnicity-1","tract_minority_population_percent",
        "ffiec_msa_md_median_family_income")
    fields=[private[0],*reversed(values.HMDA_INPUTS),*private[1:]]
    row={**native_row(),**{field:'CANARY_'+field+',"\r\nNEXT' for field in private}}
    payload=csv_bytes([row],fields).replace(b"CANARY_lei",b"\xff\xfeCANARY_lei")
    class Chunked(BytesIO):
        def read(self,n=-1):return super().read(min(n,chunk_size))
    decoded=[];original=hmda.decode_cell
    def guarded(name,value):
        assert name in values.HMDA_INPUTS and b"CANARY" not in value
        decoded.append(name);return original(name,value)
    monkeypatch.setattr(hmda,"decode_cell",guarded)
    rows=list(hmda.selected_rows(Chunked(payload)))
    assert rows==[native_row()] and set(decoded)==set(values.HMDA_INPUTS) and len(decoded)==9
    assert "CANARY" not in json.dumps(rows)+capsys.readouterr().out


@pytest.mark.parametrize("change",["missing","case","duplicate","short","long","quote","truncated","encoding","year","county"])
def test_bad_native_input_fails_without_echoing_cells(change):
    payload=fixtures.native_text().encode()
    if change=="missing":payload=payload.replace(b"activity_year",b"missing_year",1)
    if change=="case":payload=payload.replace(b"county_code",b"County_Code",1)
    if change=="duplicate":payload=payload.replace(b"property_value",b"activity_year",1)
    if change=="short":payload=payload.replace(b",305000\r\n",b"\r\n",1)
    if change=="long":payload=payload.replace(b",305000\r\n",b",305000,extra\r\n",1)
    if change=="quote":payload=payload.replace(b",305000\r\n",b',"305000"CANARY\r\n',1)
    if change=="truncated":payload=payload[:-2]+b',"CANARY'
    if change=="encoding":payload=payload.replace(b",305000\r\n",b",\xffCANARY\r\n",1)
    if change=="year":payload=payload.replace(b"2025,48453",b"2024,48453",1)
    if change=="county":payload=payload.replace(b"2025,48453",b"2025,99999",1)
    with pytest.raises(ValueError) as error:hmda.parse(BytesIO(payload))
    assert "CANARY" not in str(error.value)


def test_csv_bom_empty_lines_no_final_newline_and_schema_limits():
    payload=b"\xef\xbb\xbf"+fixtures.native_text().encode()
    assert hmda.parse(BytesIO(payload.rstrip(b"\r\n")+b"\r\n\r\n"))["summary"]["kept"]==90
    assert hmda.parse(BytesIO(payload.rstrip(b"\r\n")))["summary"]["kept"]==90
    with pytest.raises(ValueError,match="header"):list(hmda.selected_rows(BytesIO(b"")))
    with pytest.raises(ValueError,match="limit"):list(hmda.selected_rows(BytesIO(b"a"*4097)))
    with pytest.raises(ValueError,match="county"):hmda.parse(BytesIO(csv_bytes([native_row()])))


def test_full_scale_native_synthetic_stream_live_checks_and_boundaries():
    parsed=hmda.parse(BytesIO(production_csv()),live=True)
    assert parsed["summary"]["rows_read"]==30323 and parsed["summary"]["tracts_30_loans"]==300
    summary=parsed["summary"]
    for rows in (28807,31839):hmda.check_counts({**summary,"rows_read":rows,"tracts_30_loans":250},True)
    for rows in (28806,31840):
        with pytest.raises(ValueError,match="5 percent"):hmda.check_counts({**summary,"rows_read":rows},True)
    with pytest.raises(ValueError,match="250"):hmda.check_counts({**summary,"tracts_30_loans":249},True)
    with pytest.raises(ValueError,match="county"):hmda.check_counts({**summary,"counties":{"Travis":30323}},True)


def test_live_fetch_returns_aggregates_only_and_sanitizes_failures(repo,monkeypatch):
    class Response(BytesIO):status=200
    seen=[];responses=[];payload=production_csv()
    def serve(req,timeout):
        seen.append(req.full_url);response=Response(payload);responses.append(response);return response
    monkeypatch.setattr(hmda.urllib.request,"urlopen",serve)
    ad=hmda.HMDA();ad.plan(context(repo,"live"));raw=ad.fetch(hmda.REQUEST,context(repo,"live"))
    assert seen==[hmda.URL] and responses[0].closed and len(raw.body["tracts"])==300
    assert set(raw.body)=={"tracts","summary"} and "activity_year" not in json.dumps(raw.body)
    assert len(list(ad.normalize(raw)))==301 and not ad.retain_raw and not ad.recordable
    def fail(*args,**kwargs):raise RuntimeError("CANARY_EXCEPTION")
    monkeypatch.setattr(hmda.urllib.request,"urlopen",fail)
    failed=ad.fetch(hmda.REQUEST,context(repo,"live"));assert failed.status==502 and failed.body is None
    with pytest.raises(ValueError,match="withheld"):ad.follow_up(failed,context(repo))
    with pytest.raises(ValueError,match="unexpected"):ad.fetch(Request("wrong"),context(repo))


def test_manifest_budget_gate_fixture_runner_and_rebuild(repo,monkeypatch,capsys):
    expected={"activity_year","county_code","census_tract","action_taken","loan_purpose","lien_status","derived_dwelling_category","total_units","property_value"}
    assert set(values.HMDA_INPUTS)==expected and len(values.HMDA_INPUTS)==9
    inputs.assert_no_demographics("hmda_validation",values.HMDA_INPUTS)
    with pytest.raises(inputs.DemographicInputError):inputs.assert_no_demographics("hmda_validation",[*values.HMDA_INPUTS,"bachelors_plus_share"])
    layer=next(l for l in load_layers() if l.source=="hmda")
    assert layer.publish=="none" and layer.refresh=="annual" and layer.geometry=="none" and layer.license=="Public domain"
    assert yaml.safe_load((ROOT/"config/budgets.yaml").read_text())["adapters"]["hmda"]=={"per_day":6}
    assert yaml.safe_load((ROOT/"config/live_gates.yaml").read_text())["gated"]["hmda"]=="awaiting Claude's first live check"
    # Plant native-column canaries in the runner fixture; neither logs nor records may keep them.
    rows=list(csv.DictReader(StringIO(fixtures.native_text())))
    fields=[*values.HMDA_INPUTS,"lei","applicant_age","derived_race"]
    body=csv_bytes([{**row,"lei":"CANARY_LENDER","applicant_age":"CANARY_AGE","derived_race":"CANARY_RACE"} for row in rows],fields).decode()
    path=repo/"adapters/hmda/fixtures/purchase_2025.json";path.write_text(json.dumps({"status":200,"body":body}))
    run=runner.run("hmda","fixture",NOW)
    assert run.status=="success" and run.calls_made==0 and run.planned_calls==1 and run.rows_out==4
    assert "CANARY" not in capsys.readouterr().out+run.model_dump_json()
    assert canonical.read("area_feature","hmda") is None and not (paths().raw/"hmda").exists()
    (repo/"config/live_gates.yaml").write_text("gated:\n  hmda: awaiting Claude's first live check\n");config.clear_cache()
    skipped=runner.run("hmda","live",NOW);assert skipped.status=="skipped" and skipped.calls_made==0
    subprocess.run([sys.executable,str(repo/"adapters/hmda/make_fixtures.py")],check=True)
    assert path.read_bytes()==(ROOT/"adapters/hmda/fixtures/purchase_2025.json").read_bytes()


def hpi_records(real_numbers=False):
    numbers=(705.28,683.03,677,680.77) if real_numbers else (100,100,100,100)
    periods=[(2025,q,value) for q,value in enumerate(numbers,1)]+[(2026,1,656.56 if real_numbers else 100),(2026,2,681.16 if real_numbers else 100)]
    return [AreaFeature(dataset="hpi",feature_id=f"12420:{y}Q{q}",geometry=hmda.EMPTY,
        properties={"cbsa":"12420","year":y,"quarter":q,"index_sa":v}) for y,q,v in periods]


def tract_record(tract="48453000100",loans=30,value=100000):
    return AreaFeature(dataset="hmda_tract",feature_id=tract,geometry=hmda.EMPTY,source_as_of=hmda.AS_OF,
        properties={"county":hmda.COUNTIES[tract[:5]],"tract":tract,"year":2025,"loans":loans,
                    "median_value":value,"p25_value":value,"p75_value":value})


@pytest.mark.parametrize("ratios,passed",[
    ([.90],True),([1.10],True),([.89999],False),([1.10001],False),
    ([.80,.90,1.10,1.30],True),([.70,.90,1.10,1.20],True),
    ([.79999,.90,1.10,1.20001],False),([.70,.90,1.10,1.30],False),
])
def test_hand_worked_ratio_median_and_inclusive_75_percent_boundary(repo,ratios,passed):
    records=[tract_record("48453"+f"{i:06d}") for i in range(len(ratios))]
    centres={r.feature_id:[round(ratio*100000,3)]*30 for r,ratio in zip(records,ratios)}
    result=values.hmda_check(centres,records,hpi_records())
    assert result["passed"] is passed and result["tracts"]==len(ratios)
    assert result["thresholds"]==values.HMDA_THRESHOLDS and result["hmda_loans"]==30*len(ratios)
    if len(ratios)==4 and passed:assert result["share_within_20"]==.75


def test_tract_minima_empty_overlap_county_warning_and_ordinary_median(repo):
    records=[tract_record("48453000100",29),tract_record("48453000200"),tract_record("48453000300")]
    centres={r.feature_id:[100000]*30 for r in records};centres["48453000200"].pop()
    result=values.hmda_check(centres,records,hpi_records());assert result["passed"] and result["tracts"]==1
    result=values.hmda_check({},records,hpi_records());assert not result["passed"] and result["median_ratio"] is None and result["share_within_20"] is None
    records=[tract_record(c+"000100") for c in hmda.COUNTIES]
    centres={r.feature_id:[value]*30 for r,value in zip(records,(85000,100000,100000))}
    result=values.hmda_check(centres,records,hpi_records())
    assert result["passed"] and result["per_county"]["Travis"]["warning"]
    assert result["per_county"]["Williamson"]["warning"] is None
    result=values.hmda_check({records[0].feature_id:[90000]*15+[110000]*15},records[:1],hpi_records())
    assert result["median_ratio"]==1


def test_hmda_fhfa_four_quarter_adjustment_and_unavailable_data(repo):
    records=hpi_records(True);adjustment=values.hmda_adjustment(records,2025)
    assert adjustment["base_index"]==686.52 and adjustment["factor"]==pytest.approx(.992192507137447)
    assert adjustment["factor"]==pytest.approx(681.16/686.52)
    assert adjustment["base_quarters"]==["2025Q1","2025Q2","2025Q3","2025Q4"]
    assert adjustment["latest_quarter"]=="2026Q2" and adjustment["as_of"]=="2026-06-30"
    result=values.hmda_check({"48453000100":[100000]*30},[tract_record()],records)
    assert result["median_ratio"]==pytest.approx(686.52/681.16)
    for bad in ([],records[1:],[*records,records[0]]):
        result=values.hmda_check({},[],bad);assert not result["passed"] and result["adjustment"] is None and result["reasons"]
    invalid=deepcopy(records);invalid[0].properties["index_sa"]=0
    with pytest.raises(ValueError):values.hmda_adjustment(invalid,2025)
    duplicate=values.hmda_check({},[tract_record(),tract_record()],records)
    assert not duplicate["passed"] and "duplicated" in duplicate["reasons"][0]


@pytest.mark.parametrize("configured,passed,test_data,live",list(itertools.product([False,True],repeat=4)))
def test_publication_truth_table(configured,passed,test_data,live):
    assert values.ranges_published(configured,{"passed":passed},test_data,live)==(configured and passed and not test_data and live)


def test_homes_validation_metadata_effective_switch_and_failure_keeps_facts(repo,monkeypatch):
    helpers.seed(repo)
    compared=[];original=values.hmda_check
    def observe(centres,*args,**kwargs):
        compared.append({tract:len(rows) for tract,rows in centres.items()})
        return original(centres,*args,**kwargs)
    monkeypatch.setattr(values,"hmda_check",observe)
    parcels=[];tracts=[]
    for county,(source,fips,_) in homes.COUNTIES.items():
        rows=[helpers.record(county,str(i)) for i in range(100)]
        for r in rows[:2]:r.properties["market_value"]=0
        rows[2].properties["category"]="condo"
        canonical.write("area_feature",source,[*rows,AreaFeature(dataset="run_summary",feature_id="2026",geometry=hmda.EMPTY,properties={"kept":100})])
        for r in rows:
            if r.feature_id==fips+":3":continue
            p=helpers.parcel(r);p.properties["tract"]=fips+"000100";parcels.append(p)
        tracts.append(tract_record(fips+"000100",30,400000 if county!="Williamson" else 415000))
    canonical.write("area_feature","parcels",parcels)
    canonical.write("area_feature","fhfa_hpi",hpi_records())
    canonical.write("area_feature","hmda",tracts)
    meta=homes.publish();report=meta["value_range"]["validation"]
    assert meta["value_range"]["published"] is True and report["passed"] is True and report["test_data"] is False
    assert report["tracts"]==3 and report["hmda_loans"]==90 and report["hmda_year"]==2025
    assert report["per_county"]["Travis"]["tracts"]==1
    assert compared[0]=={fips+"000100":96 for _,fips,_ in homes.COUNTIES.values()}
    assert report["note"]==values.HMDA_NOTE and report["thresholds"]["min_homes"]==30
    assert len(helpers.rows())==300 and all("tract" not in row for row in helpers.rows())
    before=helpers.documents();homes.publish();assert helpers.documents()==before
    canonical.path_for("area_feature","hmda").unlink()
    meta=homes.publish();assert not meta["value_range"]["published"] and meta["value_range"]["validation"]["test_data"]
    assert not meta["value_range"]["test_data"]
    for r in tracts:r.properties["median_value"]=10000000
    canonical.write("area_feature","hmda",tracts)
    meta=homes.publish();assert not meta["value_range"]["published"] and not meta["value_range"]["validation"]["passed"]
    assert len(helpers.rows())==300 and all(row["market_value"] is not None for row in helpers.rows())
    assert json.loads((paths().web_public/"data/homes/meta.json").read_text())["value_range"]["published"] is False
