"""Shared formula vectors, synthetic FHFA TSV and hand-worked model checks."""
from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from mm import adapter, canonical, homes, inputs, runner, values
from mm.adapter import RawPayload, RunContext, Request
from mm.budget import CallBudget
from mm.manifests import load_layers
from mm.paths import paths
from mm.schemas import AreaFeature

ROOT=Path(__file__).resolve().parents[2]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
fhfa=module('fhfa_test','adapters/fhfa_hpi/adapter.py')
fixtures=module('fhfa_fixture','adapters/fhfa_hpi/make_fixtures.py')
CASES=json.loads((ROOT/'pipeline/mm/data/value_range_cases.json').read_text())['cases']
NOW=datetime(2026,10,27,12,tzinfo=timezone.utc)
BASE={'county':'Travis','category':'single_family','hood_cd':'TEST','market_value':100000,'improvement_value':80000,
      'value_year':2026,'year_built':2000,'land_acres':.2,'living_area':1000,'partial_owner':None}

@pytest.fixture
def context(repo):
 return RunContext('fixture',NOW,CallBudget.for_adapter('fhfa_hpi',NOW),repo/'adapters/fhfa_hpi')


def hpi_records(context,body=None):
 ad=fhfa.FHFAHPI();req=ad.plan(context)[0]
 records=list(ad.normalize(RawPayload(req,fixtures.native_text() if body is None else body)))
 return ad,records


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['id'])
def test_shared_reference_vectors(repo,case):
 assert len(CASES)>=30
 cfg=values.settings();p=case['home'];limits={(p['county'],p['category'],None):case['size_bounds']}
 pct,codes=values.annotation(p,limits,cfg,case["k"])
 result={'range_pct':pct,'range_flags':codes,**values.value_range(p['market_value'],values.COUNTY_FIPS[p['county']],pct,case['factor'],cfg['levels'],case['k'])}
 assert result==case['expected']
 assert values.flags(p,limits)==([] if codes is None else [c for c in codes.split(',') if c!='cal'])


def test_native_fhfa_shape_quotes_fields_dates_and_factor(context):
 body=fixtures.native_text();assert '\t"Austin-Round Rock-San Marcos, TX"\t' in body
 ad,recs=hpi_records(context)
 assert len(recs)==142 and {r.dataset for r in recs}=={'hpi'}
 assert all(r.geometry==fhfa.EMPTY and r.source_as_of==date(2026,6,30) for r in recs)
 assert recs[-1].feature_id=='12420:2026Q2' and recs[-1].properties['index_nsa']==693.01
 assert recs[-1].properties=={'cbsa':'12420','metro':'Austin-Round Rock-San Marcos, TX','year':2026,'quarter':2,'index_nsa':693.01,'index_sa':681.16}
 assert ad.source_as_of([])==date(2026,6,30)
 info=values.hpi_factor(recs,'2026-01-01')
 assert info['base_quarters']==['2025Q4','2026Q1'] and info['base_index']==668.665
 assert info['latest_index']==681.16 and info['factor']==pytest.approx(1.0186864872544548)
 assert info['latest_quarter']=='2026Q2' and info['as_of']=='2026-06-30'
 for serial,expected in [(2024*4,'2024-03-31'),(2024*4+1,'2024-06-30'),(2024*4+2,'2024-09-30'),(2024*4+3,'2024-12-31')]:assert values.quarter_end(serial).isoformat()==expected


@pytest.mark.parametrize('change',['comma','header','quote_header','gap','duplicate','missing_base','short','negative','zero','nan','badquarter','columns','quotes'])
def test_fhfa_bad_inputs_fail(change):
 body=fixtures.native_text();lines=body.splitlines()
 if change=='comma':body=body.replace('\t',',')
 elif change=='header':body=body.replace('index_sa','Index_SA',1)
 elif change=='quote_header':body=body.replace('cbsa','"cbsa"',1)
 elif change=='gap':lines.pop(2)
 elif change=='duplicate':lines.append(lines[5])
 elif change=='missing_base':lines=[line for line in lines if '\t2026\t1\t' not in line]
 elif change=='short':lines=lines[:140]
 elif change in {'negative','zero','nan'}:
  cells=lines[2].split('\t');cells[-1]={'negative':'-1','zero':'0','nan':'NaN'}[change];lines[2]='\t'.join(cells)
 elif change=='badquarter':lines[2]=lines[2].replace('\t1991\t2\t','\t1991\t5\t')
 elif change=='columns':lines[2]+='\textra'
 elif change=='quotes':lines[2]=lines[2].replace('"Austin','"Austin"x')
 if change not in {'comma','header','quote_header'}:body='\n'.join(lines)+'\n'
 with pytest.raises((ValueError,__import__('csv').Error)):fhfa.parse(body,date(2026,10,27))


def test_fhfa_recency_calendar_nine_months_boundary_and_future():
 fhfa.parse(fixtures.native_text(),date(2027,3,30))
 with pytest.raises(ValueError,match='nine months'):fhfa.parse(fixtures.native_text(),date(2027,4,1))
 with pytest.raises(ValueError,match='nine months'):fhfa.parse(fixtures.native_text(),date(2026,5,31))


def test_factor_missing_base_gaps_duplicates_positive_and_bounds(context):
 _,records=hpi_records(context)
 with pytest.raises(ValueError,match='latest'):values.hpi_factor([],'2026-01-01')
 for missing in [-2,-3]:
  changed=records.copy();changed.pop(missing)
  with pytest.raises(ValueError,match='base'):values.hpi_factor(changed,'2026-01-01')
 changed=records.copy();changed.pop(2)
 with pytest.raises(ValueError,match='gaps'):values.hpi_factor(changed,'2026-01-01')
 with pytest.raises(ValueError,match='duplicate'):values.hpi_factor([*records,records[0]],'2026-01-01')
 for factor in [.8,1.2,.799,1.201]:
  changed=deepcopy(records);changed[-1].properties['index_sa']=668.665*factor
  if factor in [.8,1.2]:assert values.hpi_factor(changed,'2026-01-01')['factor']==pytest.approx(factor)
  else:
   with pytest.raises(ValueError,match='factor'):values.hpi_factor(changed,'2026-01-01')
 changed=deepcopy(records);changed[-1].properties['index_sa']=0
 with pytest.raises(ValueError,match='nonpositive'):values.hpi_factor(changed,'2026-01-01')


def test_nearest_rank_size_edges_and_19_20_group_fallback(repo):
 homeset=[{**BASE,'living_area':i,'hood_cd':'ENOUGH'} for i in range(1,21)]
 homeset += [{**BASE,'living_area':100+i,'hood_cd':'SMALL'} for i in range(1,20)]
 limits=values.size_bounds(homeset)
 assert limits[('Travis','single_family','ENOUGH')]==(1,19)
 assert ('Travis','single_family','SMALL') not in limits
 assert limits[('Travis','single_family',None)]==(2,118)
 assert 'size' in values.flags({**BASE,'hood_cd':'SMALL','living_area':119},limits)
 assert 'size' not in values.flags({**BASE,'hood_cd':'SMALL','living_area':118},limits)
 assert 'size' not in values.flags({**BASE,'hood_cd':'ENOUGH','living_area':1},limits)
 assert 'size' in values.flags({**BASE,'hood_cd':'ENOUGH','living_area':20},limits)
 homeset.append({**BASE,'hood_cd':'SMALL','living_area':120})
 assert values.size_bounds(homeset)[('Travis','single_family','SMALL')]==(101,119)
 assert values.size_bounds([{**BASE,'living_area':None},{**BASE,'living_area':0}])=={}


def test_hood_percentiles_hand_worked_and_others_group(repo):
 cfg=values.settings();hs=[{**BASE,'market_value':100000+i*10000} for i in range(10)]
 expected={'county':'Travis','hood_cd':'TEST','category':'single_family','n':10,'p10':100,'p25':120,'p50':140,'p75':170,'p90':180}
 assert values.hood_stats(hs,1,cfg['levels'])==[expected]
 assert values.hood_stats(hs[:9],1,cfg['levels'])==[]
 other=[{**h,'category':'mobile_home' if i<5 else 'rural_home'} for i,h in enumerate(hs)]
 assert values.hood_stats(other,1,cfg['levels'])==[{**expected,'category':'other'}]
 excluded=[{**BASE,'market_value':None},{**BASE,'improvement_value':0},{**BASE,'partial_owner':True},{**BASE,'living_area':None}]
 assert values.hood_stats(hs+excluded,1,cfg['levels'])==[expected]


def test_quality_thresholds_and_recomputation(repo):
 cfg=values.settings();hs=[dict(BASE) for _ in range(100)]
 for h in hs[:3]:h['market_value']=0
 _,stats,counts=values.prepare(hs,1,cfg,test_data=False)
 assert counts['with_range']==97 and counts['hood_stats_coverage']==1 and stats[0]['n']==97
 hs[3]['market_value']=0
 with pytest.raises(ValueError,match='97 percent'):values.prepare(hs,1,cfg,test_data=False)
 hs=[dict(BASE) for _ in range(100)]
 for h in hs[:10]:h['living_area']=None
 assert values.prepare(hs,1,cfg,test_data=False)[2]['hood_stats_coverage']==.9
 hs[10]['living_area']=None
 with pytest.raises(ValueError,match='90 percent'):values.prepare(hs,1,cfg,test_data=False)
 # Tiny CAD fixtures cannot form ten-home hood groups; only production coverage gates relax.
 values.prepare(hs[:1],1,cfg,test_data=True)
 with pytest.raises(ValueError,match='recomputation'):values.validate_annotation(BASE,20,'lot',{},cfg)


def test_declared_inputs_runtime_guard_and_no_other_fields_accessed(repo):
 expected={'county','category','hood_cd','market_value','improvement_value','value_year','year_built','land_acres','living_area','partial_owner','cbsa','year','quarter','index_sa'}
 assert set(inputs.SCORE_INPUTS['value_range'])==expected
 inputs.assert_no_demographics('value_range',expected)
 class Guarded(dict):
  def __getitem__(self,key):assert key in expected;return super().__getitem__(key)
  def get(self,key,default=None):assert key in expected;return super().get(key,default)
 cfg=values.settings();values.prepare([Guarded(BASE)]*20,1,cfg,test_data=False)
 with pytest.raises(inputs.DemographicInputError):inputs.assert_no_demographics('value_range',[*expected,'bachelors_plus_share'])


def test_monthly_no_publish_manifest_budget_gate_fixture_and_rebuild(context,repo):
 ad,recs=hpi_records(context)
 layer=next(l for l in load_layers() if l.source=='fhfa_hpi')
 assert layer.publish=='none' and layer.geometry=='none' and layer.refresh=='monthly' and layer.license=='Public domain'
 assert yaml.safe_load((ROOT/'config/budgets.yaml').read_text())['adapters']['fhfa_hpi']=={'per_day':2}
 # Ungated after Claude's first live check, run 40607922630 (2026-10-28).
 assert 'fhfa_hpi' not in (yaml.safe_load((ROOT/'config/live_gates.yaml').read_text())['gated'] or {})
 run=runner.run('fhfa_hpi','fixture',NOW)
 assert run.status=='success' and run.planned_calls==1 and run.calls_made==0 and run.rows_out==142
 assert canonical.read('area_feature','fhfa_hpi') is None
 subprocess.run([sys.executable,str(repo/'adapters/fhfa_hpi/make_fixtures.py')],check=True)
 assert (repo/'adapters/fhfa_hpi/fixtures/austin_hpi.json').read_bytes()==(ROOT/'adapters/fhfa_hpi/fixtures/austin_hpi.json').read_bytes()


def test_fhfa_fetch_exact_url_one_call_and_failed_sanitization(context,monkeypatch):
 class Response(BytesIO):status=200
 seen=[]
 def serve(req,timeout):seen.append(req.full_url);return Response(fixtures.native_text().encode())
 monkeypatch.setattr(fhfa.urllib.request,'urlopen',serve)
 ad=fhfa.FHFAHPI();req=ad.plan(context)[0];raw=ad.fetch(req,context)
 assert seen==[fhfa.URL] and len(list(ad.normalize(raw)))==142
 def fail(*a,**k):raise OSError('CANARY_PRIVATE_EXCEPTION')
 monkeypatch.setattr(fhfa.urllib.request,'urlopen',fail)
 raw=ad.fetch(req,context);assert raw.status==502 and raw.body is None
 with pytest.raises(ValueError):ad.follow_up(raw,context)
 with pytest.raises(ValueError):ad.fetch(Request('wrong'),context)


def test_reference_formula_rejects_invalid_inputs(repo):
 levels=values.settings()['levels']
 for bad in [-1,float('nan'),float('inf'),True]:
  with pytest.raises(ValueError):values.value_range(bad,'48453',10,1,levels)
 with pytest.raises(ValueError):values.value_range(100000,'48453',15,1,levels)
 assert values.value_range(0,'48453',None,1,levels)=={'low':None,'mid':None,'high':None}


def test_homes_columns_hidden_metadata_provenance_and_determinism(repo):
 helper=module('homes_value_helpers','pipeline/tests/test_homes.py');helper.seed(repo)
 first=homes.publish();folder=paths().web_public/'data/homes'
 assert first['value_range']['published'] is False and first['value_range']['test_data'] is True
 assert not first['test_data'] and json.loads((folder/'hoods.json').read_text())['test_data']
 assert first['value_range']['hpi']['base_index']==668.665
 assert first['value_range']['study_year']==2024 and first['value_range']['levels']['48491']==.96
 assert first['value_range']['year_over_year_note']==values.YEAR_NOTE
 assert first['value_range']['rules']['size_min_group']==20 and first['value_range']['rules']['hood_min_group']==1
 assert 'nearest rank' in first['value_range']['size_note']
 for p in helper.rows():
  assert p['range_pct'] in (10,20) and p['range_flags'] in (None,'condo')
  assert not {'low','mid','high','partial_owner'} & p.keys()
 forbidden=('fair value','worth','estimate of sale price','good deal')
 assert not any(word in json.dumps(first['value_range']).lower() for word in forbidden)
 before=helper.documents();homes.publish();assert helper.documents()==before
 # Canonical HPI provenance switches off the HPI fixture flag, without any source calls.
 canonical.write('area_feature','fhfa_hpi',hpi_records(RunContext('fixture',NOW,CallBudget.for_adapter('fhfa_hpi',NOW),repo/'adapters/fhfa_hpi'))[1])
 live=homes.publish()
 assert not live['value_range']['test_data'] and not json.loads((folder/'hoods.json').read_text())['test_data']


def test_partial_input_only_tcad_is_not_published(repo):
 helper=module('homes_partial_helpers','pipeline/tests/test_homes.py');helper.seed(repo)
 recs=[helper.record('Travis',str(i),partial_owner=(i==0)) for i in range(100)]
 canonical.write('area_feature','tcad',[*recs,AreaFeature(dataset='run_summary',feature_id='2026',geometry=fhfa.EMPTY,properties={'kept':100})])
 parcels=[r for r in canonical.read('area_feature','parcels') if r.properties.get('county')!='Travis']
 canonical.write('area_feature','parcels',[*parcels,*[helper.parcel(r) for r in recs]])
 meta=homes.publish();rows=helper.rows();partials=[r for r in rows if r['range_flags']=='partial']
 assert len(partials)==1 and partials[0]['range_pct'] is None
 assert meta['value_range']['counties']['Travis']['with_range']==99
 assert all('partial_owner' not in r for r in rows)


@pytest.mark.parametrize('failure',['range','hoods','factor','recompute'])
def test_value_checks_preserve_previous_home_build(repo,monkeypatch,failure):
 helper=module('homes_fail_helpers','pipeline/tests/test_homes.py');data,_=helper.seed(repo);homes.publish();before=helper.documents()
 if failure=='range':
  data['tcad'][0].properties['improvement_value']=0
  canonical.write('area_feature','tcad',data['tcad'])
 elif failure=='hoods':
  for r in data['tcad'][:-1]:r.properties['hood_cd']=None
  canonical.write('area_feature','tcad',data['tcad'])
 elif failure=='factor':
  cfg=values.settings();cfg['hood_min_group']=1
  recs=hpi_records(RunContext('fixture',NOW,CallBudget.for_adapter('fhfa_hpi',NOW),repo/'adapters/fhfa_hpi'))[1]
  recs[-1].properties['index_sa']=1000
  canonical.write('area_feature','fhfa_hpi',recs)
 else:
  original=values.prepare
  def corrupted(*args,**kwargs):
   annotations,stats,counts=original(*args,**kwargs);annotations[0]=(20,'lot');return annotations,stats,counts
  monkeypatch.setattr(values,'prepare',corrupted)
 with pytest.raises(ValueError):homes.publish()
 assert helper.documents()==before



def test_parcel_fixture_cannot_relax_real_cad_range_gate(repo):
 helper=module('homes_parcel_gate_helpers','pipeline/tests/test_homes.py');data,_=helper.seed(repo)
 canonical.path_for('area_feature','parcels').unlink()
 data['tcad'][0].properties['improvement_value']=0
 canonical.write('area_feature','tcad',data['tcad'])
 with pytest.raises(ValueError,match='97 percent'):homes.publish()


def test_builder_inventory_is_left_out_of_the_range_coverage_check(repo):
 # Real Travis 2026: 10,411 of 13,043 builder-inventory homes have no building value on January 1.
 cfg=values.settings();hs=[dict(BASE) for _ in range(100)]
 for h in hs[:3]:h['market_value']=0
 hs+=[{**BASE,'category':'builder_inventory','improvement_value':0} for _ in range(50)]
 _,_,counts=values.prepare(hs,1,cfg,test_data=False)
 assert counts['coverage_homes']==100 and counts['coverage_with_range']==97 and counts['with_range']==97
 hs[3]['market_value']=0
 with pytest.raises(ValueError,match='builder inventory excluded'):values.prepare(hs,1,cfg,test_data=False)
