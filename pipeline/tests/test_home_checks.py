"""Synthetic native NFHL/OSM and hand-measured EPSG:5070 property checks."""
from copy import deepcopy
import json
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon, box, mapping, shape
from shapely import transform

from mm import canonical, homes
from mm.schemas import AreaFeature
from test_access import access, NOW as ACCESS_NOW
from test_fema_nfhl import flood, X, Y, BASE, feature, geometry, payload
from test_homes import seed, rows as published_rows

UNDO=Transformer.from_crs(5070,4326,always_xy=True).transform


def wgs(geom):
 def coordinates(xy):
  result=xy.copy();result[:,0],result[:,1]=UNDO(xy[:,0],xy[:,1]);return result
 return mapping(transform(geom,coordinates))


def flood_record(identity,geom,zones=('AE',)):
 return {'dataset':'flood_zone','feature_id':identity,'geometry':geometry(geom),
         'properties':{'zones':list(zones),'retrieved_at':'2026-10-28','effective_versions':['3.0']}}


def line_record(kind,distance,label='Test, road: é'):
 return {'dataset':'nuisance_line','feature_id':kind,'geometry':wgs(LineString([(X+distance,Y-500),(X+distance,Y+500)])),
         'properties':{'kind':kind,'ref':label,'osm_as_of':'2026-10-21'}}


def row(identity='48453:1',**changes):
 p=dict.fromkeys(homes.FIELDS);p.update(id=identity,county='Travis',category='single_family',hood_cd='TEST',
  lon=UNDO(X,Y)[0],lat=UNDO(X,Y)[1],placed='parcel',year_built=1985,land_acres=.2,range_flags='lot')
 p.update(changes);return [p[f] for f in homes.FIELDS]


def test_native_flood_dissolve_repair_nested_parts_simplification_and_size(repo,monkeypatch):
 from mm.adapter import RunContext
 from mm.budget import CallBudget
 ad=flood.FemaNFHL();ctx=RunContext('fixture',ACCESS_NOW,CallBudget.for_adapter('fema_nfhl',ACCESS_NOW),repo/'adapters/fema_nfhl')
 tiger,req=ad.plan(ctx)
 inputs=list(ad.normalize(payload(tiger,[{'type':'Feature','properties':{'GEOID':'484530001001'},'geometry':geometry(BASE)}])))
 invalid=Polygon([(X+10,Y+10),(X+100,Y+100),(X+10,Y+100),(X+100,Y+10),(X+10,Y+10)])
 invalid_feature=feature(BASE,zone='AE',sfha='T');invalid_feature['geometry']=wgs(invalid)
 fs=[feature(BASE),invalid_feature,feature(MultiPolygon([box(X+200,Y+200,X+300,Y+300)]),zone='AO',sfha='T'),feature(BASE,subtype=flood.PHRASE_02)]
 inputs.extend(ad.normalize(payload(req,fs)));result=ad.finalize(inputs);zones=[r for r in result if r.dataset=='flood_zone']
 assert len(zones)==2 and {r.feature_id for r in zones}=={'sfha','x02'}
 assert zones[0].properties['zones']==['AE','AO'] and zones[0].properties['retrieved_at']=='2026-10-24'
 for r in zones:
  assert r.geometry['type']=='MultiPolygon' and shape(r.geometry).is_valid
  def scalars(v):return [n for x in v for n in scalars(x)] if isinstance(v,(tuple,list)) else [v]
  assert all(n==round(n,6) for n in scalars(r.geometry['coordinates']))
 # A small redundant bend disappears at 2 m, while a hole stays a hole.
 props={'sfha':True,'annual_02':False,'zone':'AE','effective_version':'3'}
 jagged=Polygon([(X,Y),(X+100,Y),(X+100.5,Y+50),(X+100,Y+100),(X,Y+100),(X,Y)])
 simple=flood.flood_records([(jagged,props)],'2026-10-28')[0]
 assert len(shape(simple.geometry).geoms[0].exterior.coords)<len(jagged.exterior.coords)
 tiny=flood.flood_records([(box(X,Y,X+.001,Y+.001),props)],'2026-10-28')
 assert all(shape(r.geometry).is_valid for r in tiny)
 monkeypatch.setattr(flood,'MAX_ZONE_BYTES',10)
 with pytest.raises(ValueError,match='25 MB'):ad.finalize(inputs)


@pytest.mark.parametrize('tags,kind',[
 ({'highway':'motorway'},'highway'),({'highway':'trunk'},'highway'),({'highway':'primary'},'major_road'),({'railway':'rail'},'rail'),
 ({'highway':'motorway_link'},None),({'highway':'trunk_link'},None),({'highway':'primary_link'},None),
 ({'railway':'abandoned'},None),({'railway':'disused'},None),({'railway':'rail','abandoned':'yes'},None),
 ({'railway':'rail','disused':'rail'},None),({'railway':'rail','service':'siding'},None),
 ({'railway':'rail','service':'yard'},None),({'railway':'rail','service':'spur'},None),
 ({'highway':'motorway','tunnel':'yes'},None),({'railway':'rail','tunnel':'yes'},None),
 ({'railway':'rail','abandoned':'no','tunnel':'no'},'rail')])
def test_osm_line_filter(tags,kind):assert access.line_kind(tags)==kind


def test_native_osm_collector_retains_only_public_tags_and_clips_without_shortcuts(repo):
 collector=access.OSMCollector([-98,30,-97,31])
 for id,point in enumerate([(-97.8,30.2),(-97.7,30.2),(-97.6,30.2)],1):
  collector.node(SimpleNamespace(id=id,tags={},location=SimpleNamespace(lon=point[0],lat=point[1])))
 for id,tags in enumerate([{'highway':'motorway','ref':'I 35','owner':'CANARY'}, {'railway':'rail'}, {'highway':'trunk_link'}, {'railway':'rail','service':'yard'}],1):
  collector.way(SimpleNamespace(id=id,tags=tags,nodes=[SimpleNamespace(ref=r) for r in [1,2,3]]))
 doc=collector.compact('2026-10-21');assert len(doc['nuisance_ways'])==2
 result=access.nuisance_records(doc,[-97.75,30,-97.65,31]);assert {r.properties['kind'] for r in result}=={'highway','rail'}
 assert all(-97.750001<=shape(r.geometry).bounds[0]<=shape(r.geometry).bounds[2]<=-97.649999 for r in result)
 assert 'CANARY' not in ''.join(r.model_dump_json() for r in result)


@pytest.mark.parametrize('kind,threshold',[('highway',150),('major_road',60),('rail',150)])
def test_exact_distance_boundaries_nearest_and_search_window(kind,threshold):
 lon,lat=UNDO(X,Y)
 for distance,included in [(threshold-.001,True),(threshold,True),(threshold+.001,False),(201,False)]:
  engine=homes.LocationChecks([], [line_record(kind,distance),line_record(kind,190,'Farther')])
  codes=engine.at(lon,lat);assert bool(codes)==included
  if included:
   assert int(codes[0].split(':')[1])==round(distance)
   assert unquote(codes[0].split(':')[2])=='Test, road: é'


def test_point_in_polygon_hole_boundary_precedence_and_encoding():
 lon,lat=UNDO(X,Y)
 sfha=flood_record('sfha',box(X-10,Y-10,X+10,Y+10));x02=flood_record('x02',box(X-20,Y-20,X+20,Y+20),('X',))
 lines=[line_record('highway',90),line_record('major_road',40),line_record('rail',120)]
 codes=homes.LocationChecks([sfha,x02],lines).at(lon,lat)
 assert codes[0]=='flood1:AE' and not any(c.startswith('major_road') for c in codes)
 assert 'highway:90:Test%2C road%3A %C3%A9' in codes and 'rail:120:Test%2C road%3A %C3%A9' in codes
 assert homes.LocationChecks([x02],[]).at(lon,lat)==['flood02']
 assert homes.LocationChecks([sfha],[]).at(*UNDO(X+10,Y))==['flood1:AE']
 hole=box(X-20,Y-20,X+20,Y+20).difference(box(X-2,Y-2,X+2,Y+2))
 assert homes.LocationChecks([flood_record('sfha',hole)],[]).at(lon,lat)==[]
 assert len(homes.check_label('é'*60))<=30 and unquote(homes.check_label('é'*60))=='é'*4+'...'


def test_age_small_lot_missing_and_group_minimum_no_county_fallback():
 sample=[row(f'48453:{i}',land_acres=(i+1)/100,year_built=y,placed=None,lon=None,lat=None) for i,y in enumerate([1977,1978,1989,1990,None]+[2000]*15)]
 extra=[row('48453:large',hood_cd='OTHER',land_acres=.0001,year_built=None),row('48453:condo',category='condo',land_acres=.0001,year_built=None)]
 buckets={'TE':sample+extra};meta=homes.annotate_checks(buckets,[],[],False,False)
 codes=[r[25] or '' for r in sample]
 assert 'pre1978' in codes[0] and 'old_systems' not in codes[0]
 assert 'old_systems' in codes[1] and 'old_systems' in codes[2] and all(x not in codes[3] for x in ['pre1978','old_systems'])
 assert 'pre1978' not in codes[4] and 'old_systems' not in codes[4]
 assert 'small_lot' in codes[0] and all('small_lot' not in c for c in codes[1:])
 assert all('small_lot' not in (r[25] or '') for r in extra) and all('range_flags' in c for c in codes)
 assert not meta['sources']['fema']['available'] and not meta['sources']['osm']['available']
 sample.pop();homes.annotate_checks({'TE':sample},[],[],False,False);assert all('small_lot' not in (r[25] or '') for r in sample)


def test_publish_checks_column_sources_size_guard_and_no_fixture_substitution_for_old_stored_data(repo,monkeypatch):
 seed(repo);first=homes.publish();assert first['checks']['sources']['fema']['test_data']
 assert all('checks' in r for r in published_rows())
 # Existing live canonical files lack the new geometry: explicitly unavailable until reruns.
 canonical.write('area_feature','fema_nfhl',[]);canonical.write('area_feature','access',[])
 second=homes.publish();assert not second['checks']['sources']['fema']['available'] and not second['checks']['test_data']
 from test_homes import documents
 before=documents();monkeypatch.setattr(homes,'MAX_TOTAL_BYTES',10)
 with pytest.raises(ValueError,match='size limit'):homes.publish()
 assert documents()==before and homes.MAX_SHARD_BYTES==2_000_000


def test_shared_web_fact_templates_match_publisher():
 from pathlib import Path
 fixture=json.loads((Path(__file__).parent/'fixtures/home_checks.json').read_text())
 assert fixture['test_data'] and fixture['meta']['texts']==homes.CHECK_TEXTS
 assert fixture['meta']['thresholds']==homes.CHECK_THRESHOLDS
 assert fixture['meta']['header']==homes.CHECK_HEADER


def test_fixture_scale_storage_estimates(repo):
 # 2,000 disjoint native-scale rectangles: extrapolate vertex cost, not real coverage.
 hazards=[]
 for i in range(2000):
  x=X+(i%100)*40;y=Y+(i//100)*40
  hazards.append((box(x,y,x+20,y+20),{'sfha':i%2==0,'annual_02':i%2==1,'zone':'AE' if i%2==0 else 'X','effective_version':'3.0'}))
 records=flood.flood_records(hazards,'2026-10-28')
 stored=sum(len(r.model_dump_json().encode())+1 for r in records)
 # Current 40-call budget allows at most 39 FEMA pages after the Census call.
 flood_estimate=round(stored*39000/2000)
 assert flood_estimate<25_000_000
 # Dense fixture scenario: every home lies in SFHA and near a highway and rail.
 # Other existing home bytes use the documented P3-02 offline-publication baseline.
 sample=[row(f'48453:{i}',year_built=1985,land_acres=.01 if i%20==0 else .2) for i in range(1000)]
 buckets={'TE':sample};zones=[flood_record('sfha',box(X-10,Y-10,X+10,Y+10),('A','AE','AO'))]
 homes.annotate_checks(buckets,zones,[line_record('highway',90,'I 35'),line_record('rail',120,'Synthetic Railway')],True,True)
 document={'v':1,'test_data':True,'fields':homes.FIELDS,'rows':sample}
 previous={'v':1,'test_data':True,'fields':homes.FIELDS[:-1],'rows':[r[:-1] for r in sample]}
 extra=len(homes.encoded(document))-len(homes.encoded(previous))
 homes_estimate=197_497_779+round(extra*710480/1000)+4000
 # Reserve 30 bytes/home for the browser build's ID locators as well.
 with_locators=homes_estimate+710480*30
 assert with_locators<300_000_000
 print('fixture-scale storage estimates: '+json.dumps({'synthetic_polygons':2000,'flood_zone_bytes':stored,
  'at_39000_similar_polygons_bytes':flood_estimate,'synthetic_homes':1000,'checks_added_bytes':extra,
  'at_710480_homes_bytes':homes_estimate,'including_locator_reserve_bytes':with_locators},sort_keys=True))
