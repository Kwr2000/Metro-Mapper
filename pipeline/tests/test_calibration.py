"""Hand-worked two-year calibration and strictly separated held-out selection."""
from copy import deepcopy
from datetime import date
import json

import pytest

from mm import canonical, homes, values
from mm.paths import paths
from mm.schemas import AreaFeature
from test_hmda import hmda, fixtures, context, csv_bytes, native_row, hpi_records, helpers
from mm.adapter import RawPayload
from io import BytesIO


def loan(tract, value, n=30, year=2025):
    return {"dataset":"hmda_tract","feature_id":f"{year}:{tract}",
            "properties":{"county":next(c for c,f in values.COUNTY_FIPS.items() if f==tract[:5]),
                          "tract":tract,"year":year,"loans":n,"median_value":value}}


def hpi():
    return [*hpi_records(),*[AreaFeature(dataset="hpi",feature_id=f"12420:2024Q{q}",geometry=hmda.EMPTY,
        properties={"cbsa":"12420","year":2024,"quarter":q,"index_sa":100}) for q in range(1,5)]]


def sample_data(fit_values, test_values):
    tracts=[f"48453{i:06}" for i in range(len(fit_values))]
    centres={t:[100000]*30 for t in tracts}
    records=[loan(t,v) for t,v in zip(tracts,fit_values)]+[loan(t,v,year=2024) for t,v in zip(tracts,test_values)]
    return centres,records


def test_shrinkage_hand_arithmetic_clamps_and_minima(repo):
    centres,records=sample_data([100000,144000,100000],[100000]*3)
    records += [loan("48453000003",4000000,10),loan("48453000004",1000,10),
                loan("48453000005",200000,9),loan("48453000006",200000)]
    centres.update({f"48453{i:06}":[100000]*30 for i in range(3,7)})
    centres["48453000006"].pop()
    fitted=values.fit_calibration(centres,records,hpi(),values.settings()["calibration"])
    assert fitted["county"]=={"48453":1,"48491":1,"48209":1}
    assert fitted["tract"]["48453000001"]==pytest.approx(1.2)  # sqrt(1.44), n=n0
    assert fitted["tract"]["48453000003"]==1.25
    assert fitted["tract"]["48453000004"]==.8
    assert "48453000005" not in fitted["tract"] and "48453000006" not in fitted["tract"]
    assert values.factor_for(None,"48453",fitted)==1
    assert values.factor_for("48491000001","48453",fitted)==1
    fallback=values.fit_calibration({"48453000100":[100000]*30},[loan("48453000100",121000)],hpi(),values.settings()["calibration"])
    assert values.factor_for(None,"48453",fallback)==1.21
    assert values.factor_for("48453009999","48453",fallback)==1.21


def test_test_year_values_and_counts_can_never_feed_fit(repo):
    centres,records=sample_data([120000,110000],[500000,300000])
    before=values.fit_calibration(centres,records,hpi(),values.settings()["calibration"])
    class NeverRead(dict):
        def __getitem__(self,key):
            assert key=="year",f"Test-year field entered fitting: {key}"
            return super().__getitem__(key)
    for record in records:
        if record["properties"]["year"]==2024:record["properties"]=NeverRead(year=2024)
    assert values.fit_calibration(centres,records,hpi(),values.settings()["calibration"])==before
    class HeldOutModel:
        dataset="hmda_tract"
        properties=NeverRead(year=2024)
        def model_dump(self,**kwargs):pytest.fail("Held-out model was serialized for fitting")
    models=[r if r["properties"]["year"]==2025 else HeldOutModel() for r in records]
    assert values.fit_calibration(centres,models,hpi(),values.settings()["calibration"])==before


def test_holdout_selects_calibration_even_if_uncalibrated_fit_check_fails(repo):
    centres,records=sample_data([120000],[120000]);cfg=values.settings()
    effective,report,info=values.calibrate(centres,centres,records,hpi(),{"factor":1},cfg)
    assert info["used"] and report["passed"] and not report["fit_year_result"]["passed"]
    assert report["hmda_year"]==2024 and report["fit_year_result"]["hmda_year"]==2025
    assert report["fit_year_calibrated"]["median_ratio"]==1
    assert report["holdout"]["calibrated"]["median_ratio"]==1
    assert report["holdout"]["calibrated"]["share_within_10"]==1
    assert report["holdout"]["uncalibrated"]["share_within_10"]==0
    assert effective["county"]["48453"]==1.2
    cfg["calibration"]["enabled"]=False
    effective,report,info=values.calibrate(centres,centres,records,hpi(),{"factor":1},cfg)
    assert not info["used"] and effective["tract"]=={} and report["fallback_reason"]


def test_not_lower_within_ten_percent_is_an_independent_holdout_gate(repo):
    centres,records=sample_data([100000,100000,115000,115000],[100000]*4)
    effective,report,info=values.calibrate(centres,centres,records,hpi(),{"factor":1},values.settings())
    hold=report["holdout"]
    assert hold["calibrated"]["passed"] and hold["calibrated"]["share_within_20"]==1
    assert hold["calibrated"]["share_within_10"]<hold["uncalibrated"]["share_within_10"]
    assert not info["used"] and not hold["passed"] and "±10%" in report["fallback_reason"]
    assert report["passed"]  # P2-08 check passes, so the uncalibrated ranges remain available.
    assert effective["tract"]=={} and set(effective["county"].values())=={1}
    equal=deepcopy(hold["calibrated"])
    assert values.holdout_passed(equal,equal)[0]


def test_missing_test_year_and_bad_fit_records_fall_back(repo):
    centres,records=sample_data([100000],[100000])
    for changed in (records[:1],records[1:],[*records,records[0]]):
        effective,report,info=values.calibrate(centres,centres,changed,hpi(),{"factor":1},values.settings())
        assert not info["used"] and not effective["tract"] and report["fallback_reason"]
    records[0]["properties"]["loans"]=9
    _,report,info=values.calibrate(centres,centres,records,hpi(),{"factor":1},values.settings())
    assert not info["used"] and "fitting minimums" in report["fallback_reason"]


def test_cal_flag_threshold_does_not_change_width_or_exclusions(repo):
    cfg=values.settings();home={"county":"Travis","category":"single_family","market_value":100000,
        "improvement_value":80000,"value_year":2026,"year_built":2000,"land_acres":.2,"living_area":2000}
    for k,expected in [(1.1,"cal"),(.9,"cal"),(1.09999,None),(.90001,None)]:
        assert values.annotation(home,{},cfg,k)==(10,expected)
    assert values.annotation({**home,"category":"condo"},{},cfg,1.2)==(20,"condo,cal")
    assert values.annotation({**home,"market_value":0},{},cfg,1.2)==(None,"no_value")


def test_two_native_years_unique_ids_and_both_count_only_summaries(repo,capsys):
    ad=hmda.HMDA();requests=ad.plan(context(repo));assert len(requests)==2
    records=[]
    for req,year in zip(requests,(2025,2024)):
        assert req.key==f"purchase_{year}" and f"years={year}" in req.params["url"]
        batch=list(ad.normalize(RawPayload(req,fixtures.native_text(year))))
        assert {r.properties["year"] for r in batch if r.dataset=="hmda_tract"}=={year}
        assert {r.source_as_of for r in batch}=={date(year,12,31)}
        records.extend(batch)
    assert len({(r.dataset,r.feature_id) for r in records})==8
    ad.finalize(records);assert "2024" in capsys.readouterr().out
    with pytest.raises(ValueError,match="both year"):ad.finalize(records[:4])


def test_two_live_calls_are_reduced_to_aggregates_before_return(repo,monkeypatch):
    # Both complete native-scale responses are synthetic and served entirely in memory.
    from test_hmda import production_csv
    class Response(BytesIO):status=200
    payloads={2025:production_csv(),2024:csv_bytes(native_row(activity_year="2024",county_code=c,
        census_tract=c+f"{i//3%100+1:06d}") for i in range(32641) for c in [list(hmda.COUNTIES)[i%3]])}
    seen=[]
    def fetch(req,timeout):
        year=2024 if "years=2024" in req.full_url else 2025
        seen.append(year);return Response(payloads[year])
    monkeypatch.setattr(hmda.urllib.request,"urlopen",fetch)
    ad=hmda.HMDA();ctx=context(repo,"live");records=[]
    for req in ad.plan(ctx):
        raw=ad.fetch(req,ctx);assert raw.status==200 and set(raw.body)=={"tracts","summary"}
        records.extend(ad.normalize(raw))
    assert seen==[2025,2024] and len(records)==602
    assert len(ad.finalize(records))==602


def test_published_calibration_shape_flags_hoods_and_unplaced_county_fallback(repo):
    helpers.seed(repo);parcels=[];aggregates=[]
    for county,(source,fips,_) in homes.COUNTIES.items():
        rows=[helpers.record(county,str(i)) for i in range(40)]
        for r in rows:r.properties.update(market_value=100000,living_area=2000)
        canonical.write("area_feature",source,[*rows,AreaFeature(dataset="run_summary",feature_id="2026",geometry=hmda.EMPTY,properties={"kept":40})])
        for r in (rows[:-1] if county=="Travis" else rows):
            parcel=helpers.parcel(r);parcel.properties.update(tract=fips+"000100",block_group=fips+"0001001");parcels.append(parcel)
        value=120000
        for year in (2025,2024):
            r=loan(fips+"000100",value,year=year)
            aggregates.append(AreaFeature(**r,geometry=hmda.EMPTY,source_as_of=date(year,12,31)))
    canonical.write("area_feature","parcels",parcels)
    canonical.write("area_feature","fhfa_hpi",hpi())
    canonical.write("area_feature","hmda",aggregates)
    meta=homes.publish();folder=paths().web_public/"data/homes"
    cal=json.loads((folder/"calibration.json").read_text())
    assert meta["value_range"]["published"] and meta["value_range"]["calibration"]["used"]
    assert cal["v"]==1 and cal["fit_year"]==2025 and cal["test_year"]==2024 and len(cal["tract"])==3
    assert cal["test_data"] is False
    assert all(r["range_pct"]==10 and r["range_flags"]=="cal" for r in helpers.rows())
    stats=json.loads((folder/"hoods.json").read_text())["rows"]
    assert len(stats)==3 and all(s["p50"]==60 for s in stats)  # calibrated centre 120k / 2000 sq ft
    before=helpers.documents();homes.publish();assert helpers.documents()==before
