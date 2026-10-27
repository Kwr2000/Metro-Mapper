"""Native numeric nested ZIPs, header-only guards, selective decoding and synthetic checks."""
import copy
from datetime import date, datetime, timezone
import gzip
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
from zipfile import ZipFile

import pytest
import yaml

from mm import adapter, canonical, config, runner
from mm.adapter import RawPayload, Request, RunContext
from mm.budget import CallBudget
from mm.manifests import load_layers
from mm.paths import paths
from mm.schemas import AreaFeature

ROOT = Path(__file__).resolve().parents[2]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path)
 result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
hays=module('hays_test','adapters/hays_cad/adapter.py')
fixtures=module('hays_fixtures','adapters/hays_cad/make_fixtures.py')
NOW=datetime(2026,10,27,12,tzinfo=timezone.utc)
# Independent transcription of the spec, separate from both implementation and fixture headers.
SELECTS={
 'property':set('PropertyID QuickRefID CurrMarketValue CurrLandValue CurrImprovmentValue SquareFootage NbhdCode NbhdDesc SitusPreDirectional SitusStreetNumber SitusStreetName SitusStreetSuffix SitusPostDirectional SitusCity SitusZip LegalAcres'.split()),
 'improvement':set('PropertyID InstanceID Type StateCode ImpValue'.split()),
 'segment':set('PropertyID InstanceID Type Area ActYrBuilt'.split()),
 'land':set('PropertyID Acres SquareFeet'.split())}

@pytest.fixture
def context(repo):
 return RunContext('fixture',NOW,CallBudget.for_adapter('hays_cad',NOW),repo/'adapters/hays_cad')


def parsed(tmp_path,source=None,order=None,headers=None):
 path=tmp_path/'test.zip';path.write_bytes(fixtures.tiny_zip(source,order,headers));return hays.parse_export(path)


def output(context,body):
 ad=hays.HaysCAD();req=ad.plan(context)[0];raw=RawPayload(req,body)
 ad.follow_up(raw,context);return ad,ad.finalize(list(ad.normalize(raw)))


def by_id(records):return {r.properties['prop_id']:r.properties for r in records if r.dataset=='property'}


def test_native_nested_zip_complete_records_and_summary(context,tmp_path):
 body=parsed(tmp_path);ad,records=output(context,body);p=by_id(records)
 assert set(p)=={'1001','1002','1003','1004','1005'}
 assert p['1001']['quickrefid']=='R1001' and p['1001']['hays_property_id']==1001
 assert p['1001']['category']=='single_family' and p['1001']['state_cd']=='A' and p['1001']['prop_type']=='R'
 assert p['1001']['market_value']==435395 and p['1001']['land_value']==100000 and p['1001']['improvement_value']==335395
 assert p['1001']['living_area']==2000 and p['1001']['ma_area']==2000 and p['1001']['year_built']==1998 and p['1001']['floors']==3
 assert p['1001']['situs']=='1008 S TEST ST W San Marcos 78666' and p['1001']['situs_suffix']=='ST W'
 assert p['1001']['hood_desc']=='TEST, CREEK "HOMES"'
 assert p['1001']['land_acres']==.3 and p['1002']['land_acres']==.5 and p['1003']['land_acres']==.4 and p['1005']['land_acres'] is None
 assert p['1005']['living_area'] is None and p['1005']['ma_area'] is None and p['1005']['year_built'] is None and p['1005']['floors']==0
 assert all(r.geometry==hays.EMPTY and r.source_as_of==date(2026,1,1) for r in records)
 expected={'county','prop_id','quickrefid','hays_property_id','geo_id','category','state_cd','prop_type','situs_number',
  'situs_prefix','situs_street','situs_suffix','situs_unit','situs_city','situs_zip','situs','hood_cd','hood_desc',
  'subdivision_code','subdivision','market_value','land_value','improvement_value','value_year','value_as_of','certified',
  'living_area','ma_area','hvac_area','adu_area','year_built','floors','land_acres','dwelling_count','has_adu','deed_date','partial_owner','udi_group'}
 for props in p.values():
  assert set(props)==expected and props['county']=='Hays'
  assert props['certified']=='2026-10-19' and props['value_as_of']=='2026-01-01' and props['value_year']==2026
  for field in ['geo_id','subdivision_code','subdivision','hvac_area','adu_area','dwelling_count','has_adu','deed_date','partial_owner','udi_group','situs_unit']:assert props[field] is None
 s=records[-1].properties
 assert s['rows_by_file']=={'property':12,'improvement':12,'segment':7,'land':4,'owner':None,'sales':None}
 assert s['distinct_property_ids']==11 and s['repeated_rows']==1 and s['conflicting_ids']==0 and s['invalid_quickref']==2
 assert s['skipped_by_code']=={'B|C':1,'M1|M':1,'X1|R':1,'(blank)|(blank)':1}
 assert s['kept_by_category']=={'single_family':1,'mobile_home':1,'two_to_four_units':1,'rural_home':1,'builder_inventory':1}
 assert s['living_area_present']==4 and s['living_area_coverage']==1 and s['ma_agreement']==1
 assert s['year_built_present']==4 and s['lot_size_present']==4 and s['parcel_match_share'] is None
 assert s['runtime_seconds']>=0 and s['peak_memory_mb']>0 and ad.source_as_of([])==date(2026,1,1)


def test_fixture_rebuild_and_zero_call_runner(repo,monkeypatch):
 monkeypatch.setattr(hays.urllib.request,'urlopen',lambda *a,**k:pytest.fail('no fixture fetching'))
 run=runner.run('hays_cad','fixture',NOW)
 assert run.status=='success' and run.calls_made==0 and run.planned_calls==1 and run.rows_out==6
 assert canonical.read('area_feature','hays_cad') is None
 subprocess.run([sys.executable,str(repo/'adapters/hays_cad/make_fixtures.py')],check=True)
 assert (repo/'adapters/hays_cad/fixtures/hays_cad_2026.json').read_bytes()==(ROOT/'adapters/hays_cad/fixtures/hays_cad_2026.json').read_bytes()
 assert not list(paths().web_public.rglob('*.geojson'))


def test_owner_sales_stop_at_header_and_only_allowlisted_cells_decode(tmp_path,context,monkeypatch,capsys):
 assert {k:set(v) for k,v in hays.COLUMNS.items()}==SELECTS
 original=ZipFile.open;opened=[];private=[]
 class HeaderOnly:
  def __init__(self,stream):self.stream=stream;self.calls=0
  def __enter__(self):return self
  def __exit__(self,*args):self.stream.close()
  def readline(self):
   self.calls+=1;assert self.calls==1
   return self.stream.readline()
  def __iter__(self):pytest.fail('private rows iterated')
  def read(self,*a):pytest.fail('private rows read')
 def guarded(z,name,*args,**kwargs):
  result=original(z,name,*args,**kwargs)
  # Only inner text files are eligible for a header guard, never guess kind by filename.
  filename=name.filename if hasattr(name,'filename') else name
  if filename.endswith('.txt') and kwargs.get('mode',args[0] if args else 'r')=='r':
   assert __import__('re').fullmatch(r'PropertyDataExport[0-9]+\.txt',filename)
   # Test fixture directory order: sales=0, owner=3. Production never uses these indices.
   opened.append(filename)
   if filename in {'PropertyDataExport1419107.txt','PropertyDataExport1419110.txt'}:
    result=HeaderOnly(result);private.append(result)
  return result
 monkeypatch.setattr(ZipFile,'open',guarded)
 body=parsed(tmp_path);_,records=output(context,body)
 assert len(opened)==6 and len(private)==2 and all(stream.calls==1 for stream in private)
 serialized=json.dumps(body)+json.dumps([r.model_dump(mode='json') for r in records])+capsys.readouterr().err
 for key,value in fixtures.CANARIES.items():assert value not in serialized
 # A bytes subclass refuses decoding of discarded fields, proving privacy before normalization.
 class Cell(bytearray):
  def decode(self,*a,**k):
   assert not any(v.encode() in self for v in fixtures.CANARIES.values())
   return super().decode(*a,**k)
 monkeypatch.setattr(hays,'bytearray',Cell,raising=False)
 for kind in SELECTS:
  rows=fixtures.source_rows()[kind];header=list(reversed(fixtures.HEADERS[kind]))
  import csv
  from io import StringIO
  text=StringIO(newline='');writer=csv.writer(text);writer.writerows([[r.get(k,'') for k in header] for r in rows])
  projected=list(hays.selected_rows(BytesIO(text.getvalue().encode('latin-1')),header,kind))
  assert all(set(r)==SELECTS[kind] for r in projected)


@pytest.mark.parametrize('order',[
 ['property','improvement','segment','land','owner','sales'],['owner','land','sales','segment','improvement','property'],
 ['segment','sales','improvement','property','owner','land']])
def test_discovery_in_any_order(tmp_path,order):
 assert len(parsed(tmp_path,order=order)['properties'])==5


@pytest.mark.parametrize('order',[
 ['property','improvement','segment','land','owner'],['property','improvement','segment','land','owner','owner'],
 ['sales','improvement','segment','land','owner','sales']])
def test_missing_duplicate_kind_fails(tmp_path,order):
 with pytest.raises(ValueError,match='six|duplicate|missing'):parsed(tmp_path,order=order)


@pytest.mark.parametrize('kind,change',[('owner','unknown'),('property','missing'),('property','duplicate'),('property','ambiguous')])
def test_bad_headers_fail(tmp_path,kind,change):
 headers=copy.deepcopy(fixtures.HEADERS)
 if change=='unknown':headers[kind]=['SomethingElse']
 elif change=='missing':headers[kind].remove('QuickRefID')
 elif change=='duplicate':headers[kind].append('SquareFootage')
 else:headers[kind].append('ActYrBuilt')
 with pytest.raises(ValueError,match='header|columns'):parsed(tmp_path,headers=headers)


@pytest.mark.parametrize('code,typ,expected',[
 ('A','R','single_family'),('A1','R','single_family'),('A','M','mobile_home'),('A5','M','mobile_home'),
 ('B','R','two_to_four_units'),('E','R','rural_home'),('E','M','rural_home'),('O','R','builder_inventory'),
 ('B','C',None),('M1','M',None),('X1','R',None),('A5','R',None),('O','M',None),('A','I',None),('XE-11.182','R',None)])
def test_category_map(tmp_path,code,typ,expected):
 rows=fixtures.source_rows();rows['improvement']=[dict(PropertyID='1001',InstanceID='1',StateCode=code,Type=typ,ImpValue='10')]
 body=parsed(tmp_path,rows)
 if expected:
  p=hays.normalize_property(body['properties'][0]);assert p['category']==expected and p['state_cd']==code and p['prop_type']==typ
 else:
  assert not body['properties'] and body['summary']['skipped_by_code'][code+'|'+typ]==1


def test_highest_mapped_value_first_tie_and_skipped_highest(tmp_path):
 rows=fixtures.source_rows()
 rows['improvement'] += [dict(PropertyID='1001',InstanceID='4',Type='M',StateCode='A',ImpValue='300001'),
                         dict(PropertyID='1006',InstanceID='5',Type='R',StateCode='X2',ImpValue='300001')]
 body=parsed(tmp_path,rows);p=next(p for p in body['properties'] if p['PropertyID']=='1001')
 assert (p['StateCode'],p['Type'])==('A','M')
 assert body['summary']['skipped_by_code']['X2|R']==1
 rows['improvement'][-2]['ImpValue']='300000'
 p=next(p for p in parsed(tmp_path,rows)['properties'] if p['PropertyID']=='1001')
 assert (p['StateCode'],p['Type'])==('A','R')


@pytest.mark.parametrize('code',['MA','MA2','MAUPS9','MAADDN','MAENCL','MAUNLISTED'])
def test_all_ma_prefix_segments_contribute(tmp_path,code):
 rows=fixtures.source_rows();rows['segment']=[dict(PropertyID='1001',InstanceID='9',Type=code,Area='2000',ActYrBuilt='1980')]
 p=next(p for p in parsed(tmp_path,rows)['properties'] if p['PropertyID']=='1001')
 assert p['ma_area']==2000 and p['year_built']==1980 and p['floors']==1


def test_largest_segment_year_ties_zero_missing_and_non_main_exclusion(tmp_path):
 rows=fixtures.source_rows()
 rows['segment']=[dict(PropertyID='1001',InstanceID='1',Type=code,Area=area,ActYrBuilt=built)
  for code,area,built in [('MA','1000','0'),('MA2','1000','2010'),('GAR','10000','2020'),('ma','99999','2024')]]
 p=next(p for p in parsed(tmp_path,rows)['properties'] if p['PropertyID']=='1001')
 assert p['ma_area']==2000 and p['year_built'] is None and p['floors']==2
 rows['segment'][0]['Area']='';rows['segment'][1]['ActYrBuilt']=''
 p=next(p for p in parsed(tmp_path,rows)['properties'] if p['PropertyID']=='1001')
 assert p['ma_area']==1000 and p['year_built'] is None and p['floors']==2


@pytest.mark.parametrize('acres,sqft,legal,expected',[
 ('0.2','43560','9',.2),('0','43560','9',1),('','0','0.25',.25),('','','',None),
 ('0','0','0',None),('0.00001','0','1',None),('0','0.001','1',None),('0.123456','0','0',.1235)])
def test_land_precedence_and_never_zero(tmp_path,acres,sqft,legal,expected):
 rows=fixtures.source_rows();rows['property'][0]['LegalAcres']=legal;rows['property'][-1]=copy.deepcopy(rows['property'][0])
 rows['land']=[dict(PropertyID='1001',LandType='R',Acres=acres,SquareFeet=sqft)]
 p=next(p for p in parsed(tmp_path,rows)['properties'] if p['PropertyID']=='1001')
 assert p['land_acres']==expected


def test_quickref_digits_are_independent_of_propertyid(tmp_path):
 rows=fixtures.source_rows();rows['property'][0]['QuickRefID']='R070302';rows['property'][-1]=copy.deepcopy(rows['property'][0])
 p=hays.normalize_property(parsed(tmp_path,rows)['properties'][0])
 assert p['prop_id']=='070302' and p['quickrefid']=='R070302' and p['hays_property_id']==1001


@pytest.mark.parametrize('quickref',['','M123','P123','N123','R','R1.2','r123'])
def test_invalid_quickref_skipped_counted(tmp_path,quickref):
 rows=fixtures.source_rows();rows['property'][1]['QuickRefID']=quickref
 body=parsed(tmp_path,rows)
 assert len(body['properties'])==4 and body['summary']['invalid_quickref']==3


def test_duplicates_compare_every_read_cell_conflicts_stay_skipped(tmp_path,context):
 rows=fixtures.source_rows();rows['property'][-1]['LegalDesc']='different ignored private value'
 assert len(parsed(tmp_path,rows)['properties'])==5
 for field in SELECTS['property']-{'PropertyID'}:
  rows=fixtures.source_rows();rows['property'][-1][field]+='changed'
  rows['property'].append(copy.deepcopy(rows['property'][0]))  # original again cannot restore conflicted ID
  body=parsed(tmp_path,rows)
  assert len(body['properties'])==4 and body['summary']['conflicting_ids']==1 and body['summary']['repeated_rows']==2
  _,records=output(context,body);assert '1001' not in by_id(records)
 rows=fixtures.source_rows();rows['property'][1]['QuickRefID']='R1001'
 with pytest.raises(ValueError,match='repeated QuickRefID'):parsed(tmp_path,rows)


def test_csv_quoting_latin1_multiline_discard_and_reordered_columns(tmp_path):
 rows=fixtures.source_rows()
 for row in rows['property']:
  row['NbhdDesc']='Café, "test"\r\nnew line'
  row['LegalDesc']='CANARY_LEGAL_PERSON, "quoted"\r\nprivate next line'
 headers={kind:list(reversed(fields)) for kind,fields in fixtures.HEADERS.items()}
 body=parsed(tmp_path,rows,headers=headers)
 assert body['properties'][0]['NbhdDesc']=='Café, "test"\r\nnew line'
 assert 'CANARY_LEGAL_PERSON' not in json.dumps(body)


@pytest.mark.parametrize('data',[b'1,"unterminated\n',b'1,"closed"junk\n',b'1,bad"quote\n',b'1,too,many\n',b'1\n'])
def test_bad_csv_fails(data):
 with pytest.raises(ValueError):list(hays.selected_rows(BytesIO(data),['PropertyID','Acres'],'land'))


def test_selected_reader_no_final_newline_and_empty_cells():
 rows=list(hays.selected_rows(BytesIO(b'1001,,0\r\n1002,"2.5",10'),['PropertyID','Acres','SquareFeet'],'land'))
 assert rows==[{'PropertyID':'1001','Acres':'','SquareFeet':'0'},{'PropertyID':'1002','Acres':'2.5','SquareFeet':'10'}]


@pytest.mark.parametrize('value',['NaN','Infinity','-1','not a number'])
def test_invalid_numbers_fail(tmp_path,value):
 rows=fixtures.source_rows();rows['segment'][0]['Area']=value
 with pytest.raises(ValueError,match='numeric'):parsed(tmp_path,rows)
 rows=fixtures.source_rows();rows['property'][1]['CurrMarketValue']=value
 with pytest.raises(ValueError,match='numeric'):hays.normalize_property(parsed(tmp_path,rows)['properties'][1])


def test_quality_boundaries_and_volumes_without_big_fixture():
 for rows in [131862,134553,137244]:hays.volume_checks(rows,90000)
 for rows in [131861,137245]:
  with pytest.raises(ValueError,match='rows'):hays.volume_checks(rows,90000)
 for kept in [82000,100000]:hays.volume_checks(134553,kept)
 for kept in [81999,100001]:
  with pytest.raises(ValueError,match='kept'):hays.volume_checks(134553,kept)
 counts={'single_family':100,'single_family_with_living_area':95,'ma_comparable':100,'ma_agree':95}
 hays.quality_checks(counts)
 for field in ['single_family_with_living_area','ma_agree']:
  with pytest.raises(ValueError,match='95'):hays.quality_checks({**counts,field:94})
 p={'category':'single_family','living_area':1000,'ma_area':1001,'year_built':None,'land_acres':None}
 assert hays.quality_counts([p])['ma_agree']==1
 assert hays.quality_counts([{**p,'ma_area':1001.01}])['ma_agree']==0
 assert hays.quality_counts([])['living_area_coverage'] is None and hays.quality_counts([])['ma_agreement'] is None
 # A missing builder area never lowers the single-family-only coverage gate.
 hays.quality_checks(hays.quality_counts([p,{**p,'category':'builder_inventory','living_area':None}]))


@pytest.mark.parametrize('area',['0','','9000'])
def test_quality_checks_apply_to_fixture_mode(tmp_path,context,area):
 rows=fixtures.source_rows()
 for row in rows['property']:
  if row['PropertyID']=='1001':row['SquareFootage']=area
 with pytest.raises(ValueError,match='95'):output(context,parsed(tmp_path,rows))


class Response(BytesIO):
 status=200
 def __init__(self,data,length=None):
  super().__init__(data);self.headers={'Content-Length':str(len(data) if length is None else length)}


@pytest.mark.parametrize('failure',[None,'zip','truncated','transport','http','status'])
def test_fetch_cleanup_success_errors_and_no_private_exception(context,monkeypatch,failure):
 data=fixtures.tiny_zip() if failure!='zip' else b'CANARY_OWNER'
 def serve(req,timeout):
  assert req.full_url==hays.URL and timeout==180
  if failure=='transport':raise OSError('CANARY_OWNER')
  if failure=='http':raise urllib.error.HTTPError(hays.URL,503,'CANARY_OWNER',{},None)
  response=Response(data,length=len(data)+1 if failure=='truncated' else None)
  if failure=='status':response.status=503
  return response
 monkeypatch.setattr(hays.urllib.request,'urlopen',serve)
 ad=hays.HaysCAD();req=ad.plan(context)[0];raw=ad.fetch(req,context)
 assert not list(paths().raw.rglob('*'))
 assert 'CANARY' not in json.dumps(raw.body)
 if failure:
  assert raw.status!=200
  with pytest.raises(ValueError):ad.follow_up(raw,context)
 else:assert len(raw.body['properties'])==5
 with pytest.raises(ValueError):ad.fetch(Request('other',{'url':'https://example.com'}),context)


def test_mock_live_persistence_last_good_canaries_and_parcel_report(repo,monkeypatch,capsys):
 rows=fixtures.source_rows();requests=[]
 def serve(req,timeout):requests.append(req.full_url);return Response(fixtures.tiny_zip(rows))
 monkeypatch.setattr(hays.urllib.request,'urlopen',serve)
 monkeypatch.setattr(hays,'volume_checks',lambda count,kept:None)
 original=adapter.load
 monkeypatch.setattr(adapter,'load',lambda key:hays.HaysCAD() if key=='hays_cad' else original(key))
 parcels=[AreaFeature(dataset='parcel',feature_id=f'{fips}:{pid}',geometry={'type':'Point','coordinates':[-97.7,30.3]},
  properties={'county':county,'prop_id':pid}) for fips,county,pid in [('48209','Hays','1001'),('48209','Hays','1002'),('48453','Travis','1003')]]
 canonical.write('area_feature','parcels',parcels)
 run=runner.run('hays_cad','live',NOW)
 assert run.status=='success' and run.calls_made==1 and run.planned_calls==1 and run.rows_out==6
 assert requests==[hays.URL]
 records=canonical.read('area_feature','hays_cad');s=records[-1].properties
 assert s['parcel_matches']==2 and s['parcel_match_share']==.4
 target=canonical.path_for('area_feature','hays_cad');before=target.read_bytes()
 summary=module('hays_summary','tools/live_summary.py')
 assert summary.main('hays_cad')==0 and 'ma_agreement=' in capsys.readouterr().out
 for row in rows['property']:
  if row['PropertyID']=='1001':row['SquareFootage']='99999'
 failed=runner.run('hays_cad','live',NOW)
 assert failed.status=='failed' and target.read_bytes()==before
 for folder in [repo/'data',paths().web_public]:
  for file in folder.rglob('*'):
   if file.is_file():
    data=gzip.decompress(file.read_bytes()) if file.suffix=='.gz' else file.read_bytes()
    for value in fixtures.CANARIES.values():assert value.encode() not in data
 assert not list(paths().raw.rglob('*'))
 assert not any(value in capsys.readouterr().err for value in fixtures.CANARIES.values())


def test_fixture_never_reads_live_parcels(context,monkeypatch):
 target=paths().canonical/'area_feature/parcels.ndjson.gz';target.parent.mkdir(parents=True);target.write_bytes(b'not synthetic')
 monkeypatch.setattr(hays.gzip,'open',lambda *a,**k:pytest.fail('fixture read real parcels'))
 body=json.loads((context.adapter_dir/'fixtures/hays_cad_2026.json').read_text())['body']
 assert output(context,body)[1][-1].properties['parcel_match_share'] is None


def test_exact_budget_gate_and_no_layer(context):
 assert yaml.safe_load((ROOT/'config/budgets.yaml').read_text())['adapters']['hays_cad']=={'per_day':2}
 assert yaml.safe_load((ROOT/'config/live_gates.yaml').read_text())['gated']['hays_cad']=="awaiting Claude's first live check"
 assert not [layer for layer in load_layers() if layer.source=='hays_cad']
 ad=hays.HaysCAD();assert ad.cadence=='annual' and not ad.retain_raw and not ad.recordable
 config.clear_cache()
 (context.adapter_dir.parents[1]/'config/live_gates.yaml').write_text('gated:\n  hays_cad: awaiting first check\n')
 config.clear_cache();run=runner.run('hays_cad','live',NOW)
 assert run.status=='skipped' and run.calls_made==0


def test_real_exempt_codes_with_statute_suffix_are_valid_skip_keys():
 # The real improvement file has codes such as "XE-11.182" (probe 40559789367, 2026-10-27).
 import re
 for code in ('XE-11.182','XJ-11.21','XR-11.30','A','M1'):
  assert re.fullmatch(hays.CODE,code)
 assert not re.fullmatch(hays.CODE,'xe 11')
