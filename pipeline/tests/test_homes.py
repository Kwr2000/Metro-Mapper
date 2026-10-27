"""Offline lookup contract, shared address vectors and transactional publication."""
import argparse
import copy
import json
from pathlib import Path

import pytest

from mm import adapter, canonical, cli, homes, privacy
from mm.paths import paths
from mm.schemas import AreaFeature

ROOT=Path(__file__).resolve().parents[2]
CASES=json.loads((ROOT/'pipeline/mm/data/address_cases.json').read_text())['cases']
EMPTY={'type':'GeometryCollection','geometries':[]}


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['id'])
def test_shared_address_vectors(case):
 assert homes.normalize_query(case['query'])==case['expected']
 if 'cad' in case:
  assert homes.address_parts(case['cad'])==case['expected']
  p=case['cad'];assert homes.normalize_street(p['situs_prefix'],p['situs_street'],p['situs_suffix'])==case['expected']['street_key']
 assert homes.address_key(case['expected'])=='|'.join(case['expected'][k] for k in ('number','street_key','unit','zip'))


def test_vectors_coverage_and_empty_parts():
 assert len(CASES)>=60 and {c['county'] for c in CASES}=={'Travis','Williamson','Hays'}
 assert json.loads((ROOT/'pipeline/mm/data/address_cases.json').read_text())['test_data']
 assert homes.address_key({'number':'','street_key':'TEST ST','unit':'','zip':''})=='|TEST ST||'
 assert homes.normalize_query('')=={'number':'','street_key':'','unit':'','zip':''}


def record(county,pid='1',**changes):
 fips=homes.COUNTIES[county][1]
 p={key:None for key in homes.KEEP}
 p.update(county=county,prop_id=pid,category='single_family',situs_number='00100',situs_prefix='South',
  situs_street='Eighth',situs_suffix='Street',situs_city='Austin',situs_zip='78704',situs='100 S 8th St Austin 78704',
  hood_cd='TEST01',hood_desc='Test neighborhood',market_value=400000,land_value=100000,improvement_value=300000,
  value_year=2026,value_as_of='2026-01-01',certified='2026-10-19',living_area=1800,year_built=1999,land_acres=.2,floors=1)
 p.update(changes)
 return AreaFeature(dataset='property',feature_id=f'{fips}:{pid}',geometry=EMPTY,properties=p,source_as_of='2026-01-01')


def parcel(r,point=(-97.700001,30.300001)):
 return AreaFeature(dataset='parcel',feature_id=r.feature_id,geometry={'type':'Point','coordinates':list(point)},
  properties={'county':r.properties['county'],'prop_id':r.properties['prop_id'],'block_group':'484530001001',
              'tract':'48453000100','parcel_as_of':'2026-07-01'})


def seed(repo):
 # Tiny P2-05 placement fixtures exercise the new columns, with one-home hood groups.
 import yaml
 config_path=repo/'config/value_range.yaml'
 cfg=yaml.safe_load(config_path.read_text());cfg['hood_min_group']=1
 config_path.write_text(yaml.safe_dump(cfg))
 data={};parcels=[]
 for county,(source,_,_) in homes.COUNTIES.items():
  props=[record(county,str(i)) for i in range(1,6)]
  summary=AreaFeature(dataset='run_summary',feature_id='2026',geometry=EMPTY,properties={'kept':5})
  data[source]=[*props,summary]
  # 4/5 placed in Travis; other counties all placed. No location inferred for a condo.
  if county=='Travis':props[-1].properties['category']='condo'
  parcels += [parcel(r,(-97.700001+index*.00001,30.300001)) for index,r in enumerate(props if county!='Travis' else props[:-1])]
  canonical.write('area_feature',source,data[source])
 canonical.write('area_feature','parcels',parcels)
 return data,parcels


def documents():
 folder=paths().web_public/'data/homes'
 return {str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*.json')}


def rows():
 return [dict(zip(doc['fields'],row)) for file in (paths().web_public/'data/homes/addr').glob('*.json')
         for doc in [json.loads(file.read_text())] for row in doc['rows']]


def lookup(query):
 folder=paths().web_public/'data/homes';meta=json.loads((folder/'meta.json').read_text())
 q=homes.normalize_query(query);base=homes.shard_id(q['street_key'])
 candidates=meta['shards'].get(base,[])
 shard=base if candidates==[base] else base+'-'+homes.shard_third(q['street_key'])
 if shard not in candidates:return []
 doc=json.loads((folder/'addr'/f'{shard}.json').read_text())
 return [row for row in doc['rows'] if homes.matches(row,q)]


def test_merge_exact_points_counts_compact_contract_meta_and_roundtrip(repo):
 data,parcels=seed(repo);meta=homes.publish()
 assert not meta['test_data'] and meta['shard_count']==1
 assert meta['counties']['Travis']['homes']==5 and meta['counties']['Travis']['placed']==4
 assert meta['counties']['Travis']['unplaced_by_category']=={'condo':1}
 assert meta['counties']['Hays']['placed']==5 and meta['counties']['Williamson']['placed']==5
 assert meta['hood_desc']=={county:{'TEST01':'Test neighborhood'} for county in homes.COUNTIES}
 for county in homes.COUNTIES:
  assert meta['counties'][county]['source_as_of']==['2026-01-01'] and meta['counties'][county]['round_trip_misses']==0
  assert meta['counties'][county]['certified']==['2026-10-19']
 published=rows();assert len(published)==15 and all(r['number']=='100' and r['street_key']=='S 8TH ST' for r in published)
 assert homes.FIELDS==['id','number','street_key','unit','zip','situs','city','county','category','lon','lat','block_group',
  'hood_cd','living_area','year_built','land_acres','floors','market_value','land_value','improvement_value','value_year','certified','placed','range_pct','range_flags']
 points={r.feature_id:r.geometry['coordinates'] for r in parcels}
 for r in published:
  assert set(r)==set(homes.FIELDS) and r['unit'] is None and r['city']=='Austin'
  if r['id'] in points:
   assert [r['lon'],r['lat']]==points[r['id']] and r['placed']=='parcel'
  else:assert r['lon'] is None and r['lat'] is None and r['block_group'] is None and r['placed'] is None
  assert r['id'] in {match[0] for match in lookup(r['situs'])}
 assert len(lookup('100 SOUTH EIGHTH STREET, Austin TX 78704'))==15
 grid=[row for cell in meta['cells'] for row in json.loads((paths().web_public/'data/homes/grid'/f'{cell}.json').read_text())['rows']]
 assert len(grid)==14 and len({r[0] for r in grid})==14
 assert all(r[3]=='8T' for r in grid)
 assert homes.harmonize(data['tcad'][0].model_dump(mode='json'),parcels[0].model_dump(mode='json'))['tract']=='48453000100'


def test_shard_rules_split_and_ordering(repo,monkeypatch):
 seed(repo)
 assert homes.shard_id('NORTH LAMAR BLVD')=='LA' and homes.shard_id('FM 1626')=='FM'
 assert homes.shard_id('8TH ST')=='8T' and homes.shard_id('')=='00'
 assert homes.shard_id('A ST')=='A0' and homes.shard_id('S A ST E')=='A0' and homes.shard_id('A')=='A0' and homes.shard_id('S ST JOHN ST')=='ST'
 assert homes.shard_third('AB')=='0'
 records=list(canonical.read('area_feature','wcad'))
 for i,r in enumerate(records[:-1]):
  r.properties.update(situs_street='AB'+('C' if i%2 else 'D'),situs_prefix=None,situs_suffix='DR',
   situs_number=['10','2','1-2','1','2'][i],situs=f"{['10','2','1-2','1','2'][i]} AB{'C' if i%2 else 'D'} DR Austin 78704")
 canonical.write('area_feature','wcad',records)
 monkeypatch.setattr(homes,'MAX_SHARD_BYTES',1000)
 meta=homes.publish();assert meta['shards']['AB']==['AB-C','AB-D']
 folder=paths().web_public/'data/homes'
 assert not (folder/'addr/AB.json').exists()
 doc=json.loads((folder/'addr/AB-D.json').read_text());assert [r[1] for r in doc['rows']]==['1-2','2','10']
 for r in rows():assert r['id'] in {x[0] for x in lookup(r['situs'])}
 for cell in meta['cells']:
  for r in json.loads((folder/'grid'/f'{cell}.json').read_text())['rows']:
   assert (folder/'addr'/f'{r[3]}.json').is_file()


def test_lookup_returns_all_units_and_optional_zip(repo):
 data,_=seed(repo)
 records=data['wcad']
 for index,r in enumerate(records[:-1]):
  unit=str(index+1);r.properties.update(situs_unit=unit,situs=f'100 S 8TH ST #{unit}, Austin TX 78704')
 canonical.write('area_feature','wcad',records);homes.publish()
 assert len(lookup('100 S 8th St'))==15
 assert len(lookup('100 S 8th St #2'))==1
 assert not lookup('100 S 8th St #2, Austin TX 99999')
 assert not lookup('999 Unknown Ln')


def test_missing_values_stay_null_observed_zero_not_invented(repo,monkeypatch):
 data,_=seed(repo)
 original=homes.source_records
 monkeypatch.setattr(homes,'source_records',lambda source:(original(source)[0],True))
 for r in data['wcad'][:-1]:
  for key in ['living_area','land_acres','year_built','market_value','land_value','improvement_value','floors']:r.properties[key]=None
 canonical.write('area_feature','wcad',data['wcad']);homes.publish()
 for r in rows():
  if r['county']=='Williamson':
   assert all(r[k] is None for k in ['living_area','land_acres','year_built','market_value','land_value','improvement_value','floors'])


def test_determinism_reverse_input_and_stale_files_removed(repo,monkeypatch):
 data,_=seed(repo);homes.publish();before=documents()
 original=homes.source_records
 def reversed_records(source):
  records,fixture=original(source);return iter(reversed(list(records))),fixture
 monkeypatch.setattr(homes,'source_records',reversed_records)
 (paths().web_public/'data/homes/stale.json').write_text('stale')
 homes.publish();assert documents()==before


@pytest.mark.parametrize('failure',['count','missing_summary','duplicate_summary','duplicate_id','parcel_duplicate','placement','roundtrip','size','privacy','point','county'])
def test_validation_failure_preserves_last_build(repo,monkeypatch,failure):
 data,parcels=seed(repo);homes.publish();before=documents()
 if failure=='count':data['wcad'][-1].properties['kept']=6
 if failure=='missing_summary':data['wcad'].pop()
 if failure=='duplicate_summary':data['wcad'].append(data['wcad'][-1])
 if failure=='duplicate_id':data['wcad'].insert(1,data['wcad'][0])
 if failure=='county':data['wcad'][0].properties['county']='Hays'
 if failure=='placement':parcels=[p for p in parcels if p.feature_id!='48491:1']
 if failure=='parcel_duplicate':parcels.append(parcels[0])
 if failure=='point':parcels[0].geometry={'type':'GeometryCollection','geometries':[]}
 if failure=='roundtrip':data['wcad'][0].properties['situs']='999 WRONG ST'
 if failure=='size':monkeypatch.setattr(homes,'MAX_TOTAL_BYTES',10)
 if failure=='privacy':monkeypatch.setattr(homes,'FIELDS',homes.FIELDS+['owner_name'])
 canonical.write('area_feature','wcad',data['wcad']);canonical.write('area_feature','parcels',parcels)
 with pytest.raises((ValueError,privacy.PrivacyError)):homes.publish()
 assert documents()==before
 assert not list((paths().web_public/'data').glob('.homes-*'))


def test_failed_install_restores_last_build(repo,monkeypatch):
 seed(repo);homes.publish();before=documents();original=homes.os.replace
 def fail(source,destination):
  if Path(source).name=='homes' and Path(destination).name=='homes':raise OSError('synthetic install failure')
  return original(source,destination)
 monkeypatch.setattr(homes.os,'replace',fail)
 with pytest.raises(OSError):homes.publish()
 assert documents()==before


def test_output_allowlist_strips_private_and_demographic_extras(repo):
 data,_=seed(repo)
 for r in data['wcad'][:-1]:r.properties.update(owner_name='CANARY_OWNER',mail_address='CANARY_MAIL',hs_exempt='CANARY_EXEMPT',legal_description='CANARY_LEGAL',race_share='CANARY_DEMOGRAPHIC',deed_number='CANARY_DEED')
 canonical.write('area_feature','wcad',data['wcad']);homes.publish()
 for payload in documents().values():assert b'CANARY' not in payload
 assert not privacy.personal_keys(homes.FIELDS)


def test_grid_and_nearest_with_adjacent_cells_and_30m_limit():
 assert homes.cell_id(-97.700001,30.300001)=='-9771_3030'
 assert homes.cell_id(-97.699999,30.299999)=='-9770_3029'
 candidates=[['a',-97.70001,30.3,'AB'],['b',-97.69999,30.3,'AB'],['far',-97.69,30.3,'AB']]
 assert {r[0] for r in homes.nearest(candidates,-97.7,30.3)}=={'a','b'}
 assert homes.nearest([candidates[-1]],-97.7,30.3)==[] and homes.nearest([],-97.7,30.3)==[]
 assert homes.nearest([['near',-97.7,30.30026,'AB']],-97.7,30.3)
 assert not homes.nearest([['outside',-97.7,30.30028,'AB']],-97.7,30.3)


def test_fixture_fallback_and_mixed_county_flags(repo):
 # Existing adapter fixtures deliberately do not share parcel IDs; never invent a match.
 meta=homes.publish()
 assert meta['test_data'] and all(c['test_data'] for c in meta['counties'].values())
 assert [meta['counties'][c]['homes'] for c in homes.COUNTIES]==[2,6,5]
 assert not canonical.path_for('area_feature','tcad').exists()
 assert all(json.loads(data)['test_data'] for name,data in documents().items() if name.startswith('addr/'))
 seed(repo);canonical.path_for('area_feature','hays_cad').unlink()
 meta=homes.publish()
 assert meta['test_data'] and meta['counties']['Hays']['test_data']
 assert not meta['counties']['Travis']['test_data'] and not meta['counties']['Williamson']['test_data']
 canonical.path_for('area_feature','parcels').unlink();meta=homes.publish()
 assert all(c['test_data'] for c in meta['counties'].values())


@pytest.mark.slow
def test_mm_publish_fixtures_produces_homes_without_network(repo,monkeypatch):
 monkeypatch.setattr('urllib.request.urlopen',lambda *args,**kw:pytest.fail('publish used network'))
 assert cli._cmd_publish(argparse.Namespace())==0
 assert (paths().web_public/'data/homes/meta.json').is_file()
 assert json.loads((paths().web_public/'data/homes/meta.json').read_text())['test_data']


def test_embedded_cad_unit_markers_are_separate():
 p={'situs_number':'00123','situs_prefix':'N','situs_street':'TEST #0002','situs_suffix':'DR','situs_unit':None,'situs_zip':'78701'}
 assert homes.address_parts(p)=={'number':'123','street_key':'N TEST DR','unit':'2','zip':'78701'}
 p.update(situs_street='TEST',situs_suffix='DR APARTMENT 0002')
 assert homes.address_parts(p)['street_key']=='N TEST DR' and homes.address_parts(p)['unit']=='2'


def test_actual_two_megabyte_boundary_without_large_fixture(repo,monkeypatch):
 seed(repo);homes.publish()
 doc=json.loads((paths().web_public/'data/homes/addr/8T.json').read_text())
 boundary=len(homes.encoded(doc))
 monkeypatch.setattr(homes,'MAX_SHARD_BYTES',boundary)
 assert homes.publish()['shards']['8T']==['8T']
 monkeypatch.setattr(homes,'MAX_SHARD_BYTES',boundary-1)
 assert homes.publish()['shards']['8T']==['8T-H']


def test_99_percent_roundtrip_and_placement_boundaries_without_large_fixture(repo):
 # Synthetic 100-row counties: exactly 99% roundtrip and each required placed share.
 _,parcels=seed(repo);data={};new_parcels=[]
 for county,(source,_,threshold) in homes.COUNTIES.items():
  recs=[record(county,str(i)) for i in range(100)]
  recs[0].properties['situs']='999 WRONG ST'
  canonical.write('area_feature',source,[*recs,AreaFeature(dataset='run_summary',feature_id='2026',geometry=EMPTY,properties={'kept':100})])
  data[source]=recs
  new_parcels.extend(parcel(r) for r in recs[:threshold])
 canonical.write('area_feature','parcels',new_parcels)
 meta=homes.publish();assert all(c['round_trip_misses']==1 for c in meta['counties'].values())
 data['tcad'][1].properties['situs']='999 WRONG ST'
 canonical.write('area_feature','tcad',[*data['tcad'],AreaFeature(dataset='run_summary',feature_id='2026',geometry=EMPTY,properties={'kept':100})])
 with pytest.raises(ValueError,match='round-trip'):homes.publish()


@pytest.mark.parametrize('value',['400000',True,-1,float('nan'),float('inf')])
def test_bad_numeric_properties_fail_closed(value):
 r=record('Travis').model_dump(mode='json');r['properties']['market_value']=value
 with pytest.raises(ValueError,match='numeric'):homes.harmonize(r,None)
