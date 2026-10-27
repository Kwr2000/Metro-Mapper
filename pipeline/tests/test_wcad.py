"""Native Socrata strings/omitted nulls; strict query allowlists and private-cell canaries."""
from collections import deque
import copy
from datetime import date, datetime, timezone
from decimal import Decimal
import gzip
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse

import pytest

from mm import adapter, canonical, config, runner
from mm.adapter import RawPayload, Request, RunContext
from mm.budget import CallBudget
from mm.manifests import load_layers
from mm.paths import paths
from mm.schemas import AreaFeature

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('wcad_under_test',ROOT/'adapters/wcad/adapter.py')
wcad = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(wcad)
FIXTURE_SPEC = importlib.util.spec_from_file_location('wcad_native_fixtures',ROOT/'adapters/wcad/make_fixtures.py')
fixtures = importlib.util.module_from_spec(FIXTURE_SPEC);FIXTURE_SPEC.loader.exec_module(fixtures)
NOW = datetime(2026,10,26,12,tzinfo=timezone.utc)
# Independent transcription of the task. Do not build the expected query from adapter constants.
SELECTS = {
 'property':'propertyid,quickrefid,propertytypecode,neighborhoodcode,neighborhooddesc,totalpropmktvalue,totallandmktvalue,totalimpmktvalue,totalsqftlivingarea,streetnumber,streetdirectional,streetname,streetsuffix,streetsuffixdirectional,unitnumber,city,zip,condobuilding,condounit,datadate',
 'improvement':'propertyid,fsptb,vtsgimp_impvalue',
 'segment':'propertyid,fsegtype,farea,factyear',
 'land':'propertyid, sum(faclandsize) AS acres, sum(fsftlandsize) AS sqft'}
IDS = {'property':'ai3c-c9pf','improvement':'2huh-jk3y','segment':'xs93-mfpk','land':'bens-i2m7'}
WHERES = {'property':'tax_year=2026','improvement':'adhoctaxyear=2026',
 'segment':"adhoctaxyear=2026 AND fsegtype in('MA','MA2','MA3','MA4')",'land':'adhoctaxyear=2026'}
FORBIDDEN = {'owner_name':'CANARY_OWNER_OMEGA','mail_address':'CANARY_MAIL_BETA',
 'legaldescription':'CANARY_LEGAL_GAMMA','propertycomment':'CANARY_COMMENT_DELTA',
 'dba':'CANARY_DBA_ZETA','address':'CANARY_ADDRESS_ETA','hs_exempt':'CANARY_EXEMPT_THETA',
 'salesratio':'CANARY_SALE_IOTA','ten_percent_cap':'CANARY_CAP_KAPPA'}


@pytest.fixture
def context(repo):
 return RunContext('fixture',NOW,CallBudget.for_adapter('wcad',NOW),repo/'adapters/wcad')


def body_for(req,source):
 kind,page=req.params['kind'],req.params['page']
 if page is None:return [{'count_propertyid' if kind=='land' else 'count':str(len(source[kind]))}]
 offset=req.params['query']['$offset'];limit=req.params['query']['$limit']
 return copy.deepcopy(source[kind][offset:offset+limit])


def inputs(context,source=None,change=None,ad=None):
 source=fixtures.source_rows() if source is None else source
 ad=ad or wcad.WCAD();queue=deque(ad.plan(context));raws=[];requests=[]
 while queue:
  req=queue.popleft();body=body_for(req,source)
  if change:change(req,body)
  raw=RawPayload(req,body);requests.append(req);raws.append(raw)
  queue.extendleft(reversed(ad.follow_up(raw,context)))
 return ad,raws,requests


def output(context,source=None,change=None):
 ad,raws,requests=inputs(context,source,change)
 records=[record for raw in raws for record in ad.normalize(raw)]
 return ad,ad.finalize(records),raws,requests


def by_id(records):return {r.properties['prop_id']:r.properties for r in records if r.dataset=='property'}


def test_native_fixtures_and_complete_canonical_shape(context):
 ad=wcad.WCAD();queue=deque(ad.plan(context));raws=[]
 while queue:
  req=queue.popleft();raw=adapter.read_fixture('wcad',req)
  assert isinstance(raw.body,list) and all(isinstance(v,str) for row in raw.body for v in row.values())
  assert all(v is not None and v!='' for row in raw.body for v in row.values())
  raws.append(raw);queue.extendleft(reversed(ad.follow_up(raw,context)))
 records=ad.finalize([r for raw in raws for r in ad.normalize(raw)])
 assert len(raws)==8 and all(raw.body==[] for raw in raws)
 p=by_id(records);assert set(p)=={f'R{i}' for i in range(1001,1007)}
 assert p['R1001']['wcad_property_id']==1001 and p['R1001']['state_cd']=='A9'
 assert p['R1001']['category']=='single_family' and p['R1002']['category']=='condo'
 assert p['R1001']['market_value']==435394 and p['R1001']['land_value']==100000 and p['R1001']['improvement_value']==335394
 assert p['R1001']['living_area']==2000 and p['R1001']['ma_area']==2000 and p['R1001']['year_built']==1998 and p['R1001']['floors']==2
 assert p['R1001']['situs']=='1008 S TEST ST Round Rock 78664'
 assert p['R1002']['situs_unit']=='0201' and p['R1002']['condo_building']=='02'
 assert p['R1003']['situs_city'] is None and p['R1006']['living_area'] is None and p['R1006']['floors']==0
 assert all(v['certified']=='2026-10-22' and v['value_as_of']=='2026-01-01' and v['value_year']==2026 for v in p.values())
 for props in p.values():
  for field in ['geo_id','subdivision_code','subdivision','hvac_area','adu_area','dwelling_count','has_adu','deed_date','partial_owner','udi_group']:assert props[field] is None
 assert all(r.geometry==wcad.EMPTY and r.source_as_of==date(2026,1,1) for r in records)
 expected={'county','prop_id','wcad_property_id','geo_id','category','state_cd','prop_type','situs_number','situs_prefix',
  'situs_street','situs_suffix','situs_unit','situs_city','situs_zip','situs','condo_building','hood_cd','hood_desc',
  'subdivision_code','subdivision','market_value','land_value','improvement_value','value_year','value_as_of','certified',
  'living_area','ma_area','hvac_area','adu_area','year_built','floors','land_acres','dwelling_count','has_adu','deed_date','partial_owner','udi_group'}
 assert set(p['R1001'])==expected
 summary=records[-1].properties
 assert summary['datasets']=={'property':{'rows':10,'distinct_ids':9},'improvement':{'rows':10,'distinct_ids':8},
  'segment':{'rows':6,'distinct_ids':5},'land':{'rows':5,'distinct_ids':5}}
 assert summary['repeated_rows']==1 and summary['kept']==6 and summary['ma_agreement']==1
 assert summary['skipped_by_code']=={'A7':1,'M1':1,'no improvement':1}
 assert summary['living_area_present']==5 and summary['year_built_present']==5 and summary['lot_size_present']==3
 assert summary['parcel_match_share'] is None and summary['runtime_seconds']>=0 and summary['peak_memory_mb']>0
 assert ad.source_as_of(raws)==date(2026,1,1)


def test_every_request_has_exact_dataset_select_filter_order_and_paging(context,monkeypatch):
 monkeypatch.setattr(wcad,'PAGE_SIZE',2)
 ad,records,raws,requests=output(context)
 assert len(requests)==23  # exact multiples request an empty final page; land ends on a short page
 for req in requests:
  kind,page=req.params['kind'],req.params['page'];query=req.params['query']
  assert wcad.DATASETS[kind]==IDS[kind] and query['$where']==WHERES[kind]
  if page is None:
   # The portal names an unaliased distinct count 'count_distinct_propertyid' (checked 2026-10-26).
   assert query['$select']==('count(distinct propertyid) AS count_propertyid' if kind=='land' else 'count(*)')
   assert set(query)=={'$select','$where'}
  else:
   assert query['$select']==SELECTS[kind]
   assert query['$order']==('propertyid' if kind=='land' else 'propertyid,:id')
   assert query['$limit']==2 and query['$offset']==2*page
   if kind=='land':assert query['$group']=='propertyid'
   else:assert '$group' not in query
 assert [r.key for r in requests if r.params['kind']=='land']==['land_count','land_p0','land_p1','land_p2']
 assert 'property_p5' in [r.key for r in requests]
 assert len(by_id(records))==6
 # The source's real row counts need 18 calls with the production limit.
 assert sum(1+n//100000+1 for n in [323073,254565,337824,287677])==18


@pytest.mark.parametrize('kind',list(IDS))
def test_fetch_urls_select_only_the_four_named_datasets(context,monkeypatch,kind):
 source=fixtures.source_rows();seen=[]
 class Response(BytesIO):
  status=200
  def __init__(self,body):super().__init__(json.dumps(body).encode())
 def serve(req,timeout):
  url=urllib.parse.urlsplit(req.full_url);query=urllib.parse.parse_qs(url.query)
  assert url.scheme=='https' and url.netloc=='data.wcad.org' and url.path==f'/resource/{IDS[kind]}.json'
  assert query['$where']==[WHERES[kind]] and timeout==180
  seen.append(query)
  count=query['$select'][0].startswith('count(')
  return Response(body_for(wcad.request(kind,None if count else 0),source))
 monkeypatch.setattr(wcad.urllib.request,'urlopen',serve)
 ad=wcad.WCAD();ad.plan(context)
 for req in [wcad.request(kind),wcad.request(kind,0)]:assert ad.fetch(req,context).status==200
 assert len(seen)==2 and seen[1]['$select']==[SELECTS[kind]]


@pytest.mark.parametrize('change',[{'kind':'owner'},{'url':'https://data.wcad.org/resource/yeqp-u7bx.json'},
 {'query':{'$select':'legaldescription,owner_name'}},{'query':{'$select':'*'}},{'page':-1}])
def test_forged_requests_fail_before_transport(context,monkeypatch,change):
 ad=wcad.WCAD();ad.plan(context);req=wcad.request('property',0)
 params={**req.params,**change}
 monkeypatch.setattr(wcad.urllib.request,'urlopen',lambda *a,**k:pytest.fail('forbidden request reached transport'))
 with pytest.raises(ValueError):ad.fetch(Request(req.key,params),context)


def test_canaries_and_extra_fields_never_accessed_stored_or_logged(context,capsys):
 class Allowlisted(dict):
  def __getitem__(self,key):
   assert key not in FORBIDDEN, 'private cell was accessed'
   return super().__getitem__(key)
 for kind in IDS:
  req=wcad.request(kind,0)
  native=fixtures.source_rows()[kind][0]
  safe=wcad.selected_body(req,[Allowlisted({**native,**FORBIDDEN})])[0]
  assert set(safe)<=set(native)
 source=fixtures.source_rows()
 for rows in source.values():
  for row in rows:row.update(FORBIDDEN)
 # Identical selected cells still deduplicate when extra private cells differ.
 source['property'][1]['owner_name']='CANARY_DIFFERENT_OWNER'
 ad,records,raws,requests=output(context,source)
 assert all(raw.body==[] for raw in raws)
 target=canonical.write('area_feature','wcad',records)
 text=gzip.decompress(target.read_bytes()).decode()+capsys.readouterr().err
 for value in [*FORBIDDEN.values(),'CANARY_DIFFERENT_OWNER',*FORBIDDEN.keys()]:assert value not in text
 assert not list(paths().raw.rglob('*'))


@pytest.mark.parametrize('count',['9','11'])
def test_changed_count_fails_closed(context,count,monkeypatch):
 monkeypatch.setattr(wcad,'PAGE_SIZE',2)
 def change(req,body):
  if req.key=='property_count':body[0]['count']=count
 with pytest.raises(ValueError,match='differ from count'):output(context,change=change)


def test_conflicting_selected_duplicate_fails(context):
 for field,value in [('datadate','2026-10-23T01:00:00.000'),('totalpropmktvalue','435395.000000'),('streetname','OTHER')]:
  source=fixtures.source_rows();source['property'][1][field]=value
  with pytest.raises(ValueError,match='conflicting repeated'):output(context,source)


def test_category_highest_mapped_value_ties_and_missing_values(context):
 source=fixtures.source_rows()
 source['improvement'].insert(3,{'propertyid':'1001.000000','fsptb':'B2','vtsgimp_impvalue':'200000.000000'})
 assert by_id(output(context,source)[1])['R1001']['state_cd']=='A9'  # first tie wins; unmapped A3 has higher value
 source['improvement'].insert(4,{'propertyid':'1001.000000','fsptb':'E2','vtsgimp_impvalue':'200001.000000'})
 assert by_id(output(context,source)[1])['R1001']['category']=='rural_home'
 source['improvement'][4].pop('vtsgimp_impvalue')
 assert by_id(output(context,source)[1])['R1001']['state_cd']=='A9'


@pytest.mark.parametrize('code,category',[('A1','single_family'),('A9','single_family'),('A8','condo'),('A2','mobile_home'),('A5','mobile_home'),
 ('B2','two_to_four_units'),('B3','two_to_four_units'),('B4','two_to_four_units'),('E1','rural_home'),('E2','rural_home'),('O1','builder_inventory')])
def test_all_mapped_categories(context,code,category):
 source=fixtures.source_rows();source['improvement'][2]['fsptb']=code
 assert by_id(output(context,source)[1])['R1001']['category']==category


def test_m1_personal_mobile_stays_skipped_even_with_main_area(context):
 source=fixtures.source_rows()
 source['segment'].append({'propertyid':'1008.000000','fsegtype':'MA','farea':'2000.000000','factyear':'1999.000000'})
 records=output(context,source)[1]
 assert 'M1008' not in by_id(records) and records[-1].properties['skipped_by_code']['M1']==1


def test_area_year_floors_main_codes_and_largest_segment_tie(context):
 source=fixtures.source_rows();source['segment'].insert(2,{'propertyid':'1001.000000','fsegtype':'MA3','farea':'1500.000000','factyear':'2015.000000'})
 source['segment'].insert(3,{'propertyid':'1001.000000','fsegtype':'MA4','farea':'500.000000','factyear':'2020.000000'})
 source['property'][0]['totalsqftlivingarea']=source['property'][1]['totalsqftlivingarea']='4000.400000'
 p=by_id(output(context,source)[1])['R1001']
 assert p['living_area']==4000 and p['ma_area']==4000 and p['year_built']==1998 and p['floors']==4
 source['segment'][0].pop('factyear')
 assert by_id(output(context,source)[1])['R1001']['year_built'] is None
 source['segment'][0]['factyear']='0.000000'
 assert by_id(output(context,source)[1])['R1001']['year_built'] is None


def test_omitted_numeric_optional_cells_preserve_null_and_genuine_zero(context):
 source=fixtures.source_rows()
 for row in source['property']:
  for field in ['totalpropmktvalue','totallandmktvalue','totalimpmktvalue','neighborhooddesc','streetnumber','streetdirectional','streetname','streetsuffix','city','zip']:
   row.pop(field,None)
 source['property'][0]['totalpropmktvalue']=source['property'][1]['totalpropmktvalue']='0.000000'
 records=output(context,source)[1];p=by_id(records)['R1001']
 assert p['market_value']==0 and p['land_value'] is None and p['improvement_value'] is None
 assert p['hood_desc'] is None and p['situs'] is None


def test_address_parts_unit_fallback_and_acreage(context):
 source=fixtures.source_rows();source['property'][0].update(streetsuffixdirectional='NW',unitnumber='001')
 source['property'][1]=copy.deepcopy(source['property'][0])
 p=by_id(output(context,source)[1])
 assert p['R1001']['situs_suffix']=='ST NW' and p['R1001']['situs_unit']=='001'
 assert p['R1001']['situs']=='1008 S TEST ST NW 001 Round Rock 78664'
 assert p['R1002']['situs_unit']=='0201' and p['R1002']['land_acres'] is None
 assert p['R1001']['land_acres']==.15 and p['R1003']['land_acres']==6.891 and p['R1005']['land_acres']==.1
 assert p['R1004']['land_acres'] is None and p['R1006']['land_acres'] is None
 assert wcad.acres((Decimal('0.00001'),None)) is None and wcad.acres((None,Decimal(1))) is None


@pytest.mark.parametrize('identity',['M1001','r1001','R12A','123','R-1',''])
def test_kept_quickref_pattern(context,identity):
 source=fixtures.source_rows()
 for row in source['property'][:2]:
  if identity:row['quickrefid']=identity
  else:row.pop('quickrefid')
 with pytest.raises(ValueError,match='quickrefid'):output(context,source)


@pytest.mark.parametrize('kind,field',[('property','propertyid'),('property','totalpropmktvalue'),('property','totallandmktvalue'),
 ('property','totalimpmktvalue'),('property','totalsqftlivingarea'),('improvement','vtsgimp_impvalue'),
 ('segment','farea'),('segment','factyear'),('land','acres'),('land','sqft')])
def test_nonnumeric_cells_fail_even_if_otherwise_skipped(context,kind,field):
 source=fixtures.source_rows();source[kind][0][field]='not-a-number'
 with pytest.raises(ValueError):output(context,source)


@pytest.mark.parametrize('value',[True,10,10.0,None])
def test_native_present_values_must_be_strings(context,value):
 source=fixtures.source_rows();source['property'][0]['totalpropmktvalue']=value
 with pytest.raises(ValueError,match='must be strings'):output(context,source)


@pytest.mark.parametrize('value',['NaN','Infinity','-1',''])
def test_invalid_numeric_strings_rejected(value):
 with pytest.raises(ValueError):wcad.number(value)


def test_bad_dates_missing_dates_and_nonintegral_ids_years(context):
 source=fixtures.source_rows();source['property'][0]['datadate']='bad date'
 with pytest.raises(ValueError,match='datadate'):output(context,source)
 source=fixtures.source_rows()
 for row in source['property']:row.pop('datadate')
 with pytest.raises(ValueError,match='datadate'):output(context,source)
 for kind,field in [('property','propertyid'),('segment','factyear')]:
  source=fixtures.source_rows();source[kind][0][field]='1.5'
  with pytest.raises(ValueError,match='nonintegral'):output(context,source)


def test_guard_boundaries_without_large_synthetic_data():
 for distinct in [313055,319443,325831]:wcad.volume_checks(distinct,215000)
 for distinct in [313054,325832]:
  with pytest.raises(ValueError,match='distinct'):wcad.volume_checks(distinct,236087)
 for kept in [215000,255000]:wcad.volume_checks(319443,kept)
 for kept in [214999,255001]:
  with pytest.raises(ValueError,match='kept count'):wcad.volume_checks(319443,kept)
 p={'category':'single_family','living_area':1000,'ma_area':1001,'year_built':1990,'land_acres':None}
 assert wcad.quality_counts([p])['ma_agree']==1
 assert wcad.quality_counts([{**p,'ma_area':1001.01}])['ma_agree']==0
 for count in [97,100]:wcad.quality_checks({'single_family_condo':100,'single_family_condo_with_living_area':count,'ma_comparable':100,'ma_agree':count})
 for field in ['single_family_condo_with_living_area','ma_agree']:
  counts={'single_family_condo':100,'single_family_condo_with_living_area':100,'ma_comparable':100,'ma_agree':100};counts[field]=96
  with pytest.raises(ValueError,match='97%'):wcad.quality_checks(counts)


def test_quality_checks_also_apply_to_fixtures(context):
 for field,value in [('totalsqftlivingarea','0.000000'),('totalsqftlivingarea','9000.000000')]:
  source=fixtures.source_rows()
  for row in source['property'][:2]:row[field]=value
  with pytest.raises(ValueError,match='97%'):output(context,source)


def test_bad_page_order_repeated_group_and_non_main_segment_fail(context):
 source=fixtures.source_rows();source['property'][0],source['property'][2]=source['property'][2],source['property'][0]
 with pytest.raises(ValueError,match='ordered'):output(context,source)
 source=fixtures.source_rows();source['land'].insert(1,copy.deepcopy(source['land'][0]))
 with pytest.raises(ValueError,match='grouped'):output(context,source)
 source=fixtures.source_rows();source['segment'][0]['fsegtype']='GARAGE'
 with pytest.raises(ValueError,match='non-main'):output(context,source)


def test_exact_budget_live_gate_and_no_layer(context):
 import yaml
 assert yaml.safe_load((ROOT/'config/budgets.yaml').read_text())['adapters']['wcad']=={'per_day':40,'min_interval_seconds':2}
 # Ungated after Claude's first live check, run 40559703311 (2026-10-27).
 assert 'wcad' not in (yaml.safe_load((ROOT/'config/live_gates.yaml').read_text())['gated'] or {})
 ad=wcad.WCAD();assert ad.cadence=='annual' and not ad.retain_raw and not ad.recordable
 assert not [l for l in load_layers() if l.source=='wcad']


def test_fixture_runner_and_regeneration(repo,monkeypatch):
 monkeypatch.setattr(wcad.urllib.request,'urlopen',lambda *a,**k:pytest.fail('fixtures must never fetch'))
 result=runner.run('wcad',mode='fixture',now=NOW)
 assert result.status=='success' and result.calls_made==0 and result.planned_calls==8 and result.rows_out==7
 assert canonical.read('area_feature','wcad') is None
 subprocess.run([sys.executable,str(repo/'adapters/wcad/make_fixtures.py')],check=True)
 for file in (ROOT/'adapters/wcad/fixtures').glob('*.json'):assert file.read_bytes()==(repo/'adapters/wcad/fixtures'/file.name).read_bytes()
 assert not list(paths().web_public.rglob('*.geojson'))


def test_mock_live_all_requests_canaries_match_summary_and_failed_run_keeps_last_good(repo,monkeypatch,capsys):
 source=fixtures.source_rows()
 for rows in source.values():
  for row in rows:row.update(FORBIDDEN)
 seen=[]
 class Response(BytesIO):
  status=200
  def __init__(self,body):super().__init__(json.dumps(body).encode())
 def serve(req,timeout):
  parsed=urllib.parse.urlsplit(req.full_url);query=urllib.parse.parse_qs(parsed.query)
  assert parsed.netloc=='data.wcad.org'
  kind=next(k for k,v in IDS.items() if parsed.path==f'/resource/{v}.json')
  assert query['$where']==[WHERES[kind]]
  page=None if query['$select'][0].startswith('count(') else int(query['$offset'][0])//wcad.PAGE_SIZE
  assert query['$select'][0]==(('count(distinct propertyid) AS count_propertyid' if kind=='land' else 'count(*)') if page is None else SELECTS[kind])
  seen.append((kind,page));return Response(body_for(wcad.request(kind,page),source))
 monkeypatch.setattr(wcad.urllib.request,'urlopen',serve)
 monkeypatch.setattr(wcad,'volume_checks',lambda distinct,kept:None)  # tiny run; production boundaries tested above
 monkeypatch.setattr('mm.budget.time.sleep',lambda seconds:None)
 original_load=adapter.load
 monkeypatch.setattr(adapter,'load',lambda identity:wcad.WCAD() if identity=='wcad' else original_load(identity))
 base=[AreaFeature(dataset='parcel',feature_id=f'{fips}:{pid}',geometry={'type':'Point','coordinates':[-97.7,30.3]},
       properties={'county':county,'prop_id':pid}) for fips,county,pid in [('48491','Williamson','R1001'),('48491','Williamson','R1002'),('48453','Travis','R1003')]]
 canonical.write('area_feature','parcels',base)
 result=runner.run('wcad',mode='live',now=NOW)
 assert result.status=='success' and result.calls_made==8 and len(seen)==8 and result.rows_out==7
 records=canonical.read('area_feature','wcad');summary=next(r.properties for r in records if r.dataset=='run_summary')
 assert summary['parcel_matches']==2 and summary['parcel_match_share']==pytest.approx(2/6)
 target=canonical.path_for('area_feature','wcad');before=target.read_bytes()
 spec=importlib.util.spec_from_file_location('wcad_summary',ROOT/'tools/live_summary.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 assert module.main('wcad')==0 and 'parcel_match_share=' in capsys.readouterr().out
 source['property'][1]['totalpropmktvalue']='435395.000000'
 failed=runner.run('wcad',mode='live',now=NOW)
 assert failed.status=='failed' and target.read_bytes()==before
 for folder in [repo/'data',paths().web_public]:
  for file in folder.rglob('*'):
   if file.is_file():
    data=gzip.decompress(file.read_bytes()) if file.suffix=='.gz' else file.read_bytes()
    for value in FORBIDDEN.values():assert value.encode() not in data
 assert not list(paths().raw.rglob('*'))
 assert not any(value in capsys.readouterr().err for value in FORBIDDEN.values())


def test_fixture_mode_ignores_live_canonical_parcels(context,monkeypatch):
 target=paths().canonical/'area_feature/parcels.ndjson.gz';target.parent.mkdir(parents=True);target.write_bytes(b'not synthetic')
 monkeypatch.setattr(wcad.gzip,'open',lambda *a,**k:pytest.fail('fixture cannot read live parcel data'))
 assert output(context)[1][-1].properties['parcel_match_share'] is None


@pytest.mark.parametrize('kind',['http','body_error','transport','json'])
def test_failed_source_response_is_sanitized(context,monkeypatch,kind):
 class Response(BytesIO):
  status=503 if kind=='http' else 200
  def __init__(self):super().__init__(b'not-json' if kind=='json' else json.dumps({'message':FORBIDDEN['owner_name']}).encode())
 def serve(*a,**k):
  if kind=='transport':raise OSError(FORBIDDEN['owner_name'])
  return Response()
 monkeypatch.setattr(wcad.urllib.request,'urlopen',serve)
 ad=wcad.WCAD();req=ad.plan(context)[0];raw=ad.fetch(req,context)
 assert raw.status!=200 and FORBIDDEN['owner_name'] not in json.dumps(raw.body)
 with pytest.raises(ValueError):ad.follow_up(raw,context)


def test_skipped_code_uses_highest_value_and_first_tie(context):
 source=fixtures.source_rows()
 source['improvement'].insert(-1,{'propertyid':'1007.000000','fsptb':'A3','vtsgimp_impvalue':'200000.000000'})
 source['improvement'].insert(-1,{'propertyid':'1007.000000','fsptb':'M1','vtsgimp_impvalue':'200000.000000'})
 summary=output(context,source)[1][-1].properties
 assert summary['skipped_by_code']=={'A3':1,'M1':1,'no improvement':1}


def test_duplicate_quickref_and_invalid_grouped_or_count_responses(context):
 source=fixtures.source_rows();source['property'][2]['quickrefid']='R1001'
 with pytest.raises(ValueError,match='quickrefid'):output(context,source)
 ad=wcad.WCAD();req=ad.plan(context)[0]
 for body in [[],[{'count':'1'},{'count':'1'}],[{'count':'bad'}],[{}]]:
  with pytest.raises(ValueError):ad.follow_up(RawPayload(req,body),context)
 req=wcad.request('property',0)
 with pytest.raises(ValueError,match='missing'):ad.follow_up(RawPayload(req,[]),context)
 with pytest.raises(ValueError,match='array'):wcad.selected_body(req,{'error':'private'})


def test_omitted_area_years_have_no_imputed_check_value(context):
 source=fixtures.source_rows()
 for row in source['segment']:
  row.pop('farea');row.pop('factyear')
 p=by_id(output(context,source)[1])['R1001']
 assert p['ma_area'] is None and p['year_built'] is None and p['floors']==2
 counts=output(context,source)[1][-1].properties
 assert counts['ma_comparable']==0 and counts['ma_agreement'] is None


def test_quickref_is_independent_of_numeric_propertyid_and_keeps_padding(context):
 source=fixtures.source_rows()
 for row in source['property'][:2]:row['quickrefid']='R070302'
 p=by_id(output(context,source)[1])['R070302']
 assert p['wcad_property_id']==1001 and p['prop_id']=='R070302'
 assert p['living_area']==2000 and p['land_acres']==.15  # aggregates join on propertyid, identity uses quickrefid
