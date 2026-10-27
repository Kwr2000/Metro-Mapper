"""Tiny real fixed-width ZIPs, slice guards and canaries; no data-source calls."""
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
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from mm import adapter, canonical, config, runner
from mm.adapter import RawPayload, RunContext
from mm.budget import CallBudget
from mm.manifests import load_layers
from mm.paths import paths
from mm.schemas import AreaFeature

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('tcad_under_test', ROOT/'adapters/tcad/adapter.py')
tcad = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tcad)
NOW = datetime(2026,10,25,12,tzinfo=timezone.utc)
# Independent transcription of the publisher's positions. Fixture writing must not derive
# offsets from adapter code, so a one-byte adapter offset error cannot pass this test.
PROP = {'prop_id':(1,12),'prop_type_cd':(13,17),'prop_val_yr':(18,22),'sup_num':(23,34),
    'geo_id':(547,596),'partial_owner':(679,679),'udi_group':(680,691),
    'situs_street_prefx':(1040,1049),'situs_street':(1050,1099),'situs_street_suffix':(1100,1109),
    'situs_city':(1110,1139),'situs_zip':(1140,1149),'abs_subdv_cd':(1676,1685),'hood_cd':(1686,1695),
    'land_hstd_val':(1796,1810),'land_non_hstd_val':(1811,1825),'imprv_hstd_val':(1826,1840),
    'imprv_non_hstd_val':(1841,1855),'deed_dt':(2034,2058),'imprv_state_cd':(2732,2741),
    'land_state_cd':(2742,2751),'land_acres':(2772,2791),'market_value':(4214,4227),
    'situs_num':(4460,4474),'situs_unit':(4475,4479)}
INFO = {'prop_id':(1,12),'prop_val_yr':(13,16),'imprv_id':(17,28),'imprv_type_cd':(29,38),
        'imprv_type_desc':(39,63),'imprv_state_cd':(64,68)}
DET = {'prop_id':(1,12),'prop_val_yr':(13,16),'imprv_id':(17,28),'imprv_det_id':(29,40),
       'imprv_det_type_cd':(41,50),'imprv_det_type_desc':(51,75),'yr_built':(86,89),'imprv_det_area':(94,108)}
SUB = {'abs_subdv_cd':(1,10),'abs_subdv_desc':(11,50)}
TOTALS = {'entity_cd':(13,17),'entity_name':(18,87),'num_real_mobile':(283,294),'sup_num':(809,820)}
LAYOUTS = {'PROP.TXT':(9922,PROP),'IMP_INFO.TXT':(114,INFO),'IMP_DET.TXT':(622,DET),
           'ABS_SUBD.TXT':(50,SUB),'TOTALS.TXT':(2491,TOTALS)}
CANARIES = ['CANARY_PERSON_OMEGA','CANARY_MAIL_ZETA','CANARY_CONFIDENTIAL_ETA','CANARY_UNUSED_MEMBER']


def native_prop(pid='000000000123', state='A1', **changes):
    return dict(prop_id=pid,prop_type_cd='R',prop_val_yr='02026',sup_num='000000000000',geo_id='TEST-GEO',
        partial_owner='T',udi_group='000000000007',situs_street_prefx='S',situs_street='8TH',
        situs_street_suffix='ST',situs_city='',situs_zip='78704',abs_subdv_cd='TEST01',hood_cd='H01',
        land_hstd_val='000000000111113',land_non_hstd_val='000000000222227',
        imprv_hstd_val='000000000333331',imprv_non_hstd_val='000000000444443',deed_dt='02-03-2020',
        imprv_state_cd=state,land_state_cd='C1',land_acres='00000000000000001435',
        market_value='00000001111114',situs_num='1008',situs_unit='',**changes)


def info(pid,iid,kind='100'):
    return dict(prop_id=str(pid).zfill(12),prop_val_yr='2026',imprv_id=str(iid).zfill(12),imprv_type_cd=kind)


def segment(pid,iid,code,area=1000,built='1990'):
    return dict(prop_id=str(pid).zfill(12),prop_val_yr='2026',imprv_id=str(iid).zfill(12),
                imprv_det_id='000000000001',imprv_det_type_cd=code,yr_built=built,imprv_det_area=f'{area:015.6f}')


def source_rows():
    return {'PROP.TXT':[native_prop(),native_prop('000000000456','A4')],
        'IMP_INFO.TXT':[info(123,1),info(123,2),info(123,3,'120'),info(123,4,'21'),info(123,5,'00'),info(456,6)],
        'IMP_DET.TXT':[segment(123,1,'1ST',1000),segment(123,1,'2ND',600,'2000'),segment(123,1,'1/2',50,'2010'),
            segment(123,1,'FBSMT',200,'2020'),segment(123,1,'RSBLW',100,'2021'),segment(123,1,'095',1950),
            segment(123,2,'1ST',400,'1970'),segment(123,2,'095',400),segment(123,3,'1ST',300),segment(123,3,'2ND',50),
            segment(123,4,'1ST',200),segment(123,5,'1ST',9999),segment(123,5,'095',9999),
            segment(456,6,'1ST',1500,'2005'),segment(456,6,'095',1500)],
        'ABS_SUBD.TXT':[{'abs_subdv_cd':'TEST01','abs_subdv_desc':'THE GROVE AT TEST CREEK SEC 2'}],
        'TOTALS.TXT':[{'entity_cd':'03','entity_name':'TRAVIS COUNTY','num_real_mobile':'000000000002','sup_num':'000000000000'}]}


def fixed(member, row, *, private=True):
    length, fields = LAYOUTS[member]
    line = bytearray(b' '*length)
    for key,value in row.items():
        start,end = fields[key]
        cell = str(value).encode('latin-1')
        assert len(cell) <= end-start+1, key
        line[start-1:end] = cell.ljust(end-start+1,b' ')
    if private and member == 'PROP.TXT':
        for start,end,value in [(609,678,CANARIES[0]),(694,753,CANARIES[1]),(4931,5000,CANARIES[2]),
                                (2609,2609,'T'),(5464,5467,'2087')]:
            line[start-1:end] = value.encode().ljust(end-start+1,b' ')
    if member == 'IMP_INFO.TXT':
        line[68:69] = b'T'  # imprv_homesite, explicitly forbidden
    return bytes(line)+b'\r\n'


def tiny_zip(source=None, *, omit=None, duplicate=None, change_bytes=None, private=True):
    source = source or source_rows()
    result = BytesIO()
    with ZipFile(result,'w',compression=ZIP_DEFLATED,allowZip64=True) as z:
        for member,rows in source.items():
            if member == omit: continue
            content = b''.join(fixed(member,r,private=private) for r in rows)
            if change_bytes: content = change_bytes(member,content)
            # Force zip64 local headers even for a tiny member.
            with z.open('nested/'+member,'w',force_zip64=True) as target:
                target.write(content)
            if duplicate == member: z.writestr('other/'+member,content)
        for name in ['OWNER.TXT','AGENT.TXT','ARB.TXT','DEFERRAL.TXT','SKETCH_INFO.TXT']:
            z.writestr(name,CANARIES[3])
    return result.getvalue()


@pytest.fixture
def context(repo):
    return RunContext('fixture',NOW,CallBudget.for_adapter('tcad',NOW),repo/'adapters/tcad')


def planned(context, body=None):
    ad = tcad.TCAD()
    req = ad.plan(context)[0]
    raw = adapter.read_fixture('tcad',req) if body is None else RawPayload(req,body)
    return ad,req,raw


def normalized(context, body=None):
    ad,req,raw = planned(context,body)
    return ad,ad.finalize(list(ad.normalize(raw)))


def test_one_call_plan_and_exact_budget_gate(context):
    ad,req,raw = planned(context)
    assert req.key == 'tcad_2026' and req.params == {'url':tcad.URL}
    assert ad.cadence == 'annual' and not ad.recordable and not ad.retain_raw
    import yaml
    assert yaml.safe_load((ROOT/'config/budgets.yaml').read_text())['adapters']['tcad'] == {'per_day':2,'max_minutes':45}
    # Ungated after its first live check (run 40425025647, 2026-10-27).
    assert 'tcad' not in (yaml.safe_load((ROOT/'config/live_gates.yaml').read_text())['gated'] or {})
    assert not [l for l in load_layers() if l.source == 'tcad']


def test_parser_actual_fixed_width_zip_and_living_year_rule(context):
    body = tcad.parse_export(BytesIO(tiny_zip()))
    ad,records = normalized(context,body)
    p = next(r.properties for r in records if r.feature_id == '48453:123')
    assert p['living_area'] == 2350 and p['adu_area'] == 550 and p['hvac_area'] == 2350
    assert p['year_built'] == 1990 and p['floors'] == 3 and p['dwelling_count'] == 2 and p['has_adu'] is True
    assert (p['land_value'],p['improvement_value'],p['market_value']) == (333340,777774,1111114)
    assert p['land_acres'] == .1435 and p['deed_date'] == '2020-02-03'
    assert p['situs'] == '1008 S 8TH ST 78704' and p['situs_city'] is None
    assert p['subdivision'] == 'The Grove at Test Creek Sec 2'
    assert p['partial_owner'] is True and p['udi_group'] == 7
    assert p['value_year'] == 2026 and p['value_as_of'] == '2026-01-01' and p['certified'] == '2026-07-18'
    assert all(r.geometry == tcad.EMPTY and r.source_as_of == date(2026,1,1) for r in records)
    assert ad.source_as_of([]) == date(2026,1,1)
    audit = records[-1].properties
    assert audit['kept_by_category'] == {'single_family':1,'condo':1}
    assert audit['hvac_agreement'] == 1 and audit['living_area_coverage'] == 1
    assert audit['partial_owner_records'] == 2 and audit['runtime_seconds'] >= 0 and audit['peak_memory_mb'] > 0
    assert audit['parcel_match_share'] is None
    expected = {'county','prop_id','geo_id','category','state_cd','prop_type','situs_number','situs_prefix','situs_street',
        'situs_suffix','situs_unit','situs_city','situs_zip','situs','hood_cd','subdivision_code','subdivision','market_value',
        'land_value','improvement_value','value_year','value_as_of','certified','land_acres','living_area','adu_area','hvac_area',
        'year_built','floors','dwelling_count','has_adu','deed_date','partial_owner','udi_group'}
    assert set(p) == expected


def test_only_spec_ranges_sliced_and_only_five_members_opened(monkeypatch,context,capsys):
    data, without_private = tiny_zip(), tiny_zip(private=False)
    slices = []
    class Guarded(bytes):
        def __getitem__(self,key):
            assert isinstance(key,slice) and key.step is None
            assert (key.start+1,key.stop) in self.allowed, (self.member,key)
            slices.append((self.member,key.start+1,key.stop))
            return super().__getitem__(key)
        def decode(self,*args,**kwargs):
            raise AssertionError('entire line must never be decoded')
        def removesuffix(self,suffix):
            result = Guarded(super().removesuffix(suffix))
            result.member,result.allowed = self.member,self.allowed
            return result
    opened, old_open = [], ZipFile.open
    class LinesOnly:
        def __init__(self,source,member): self.source,self.member = source,member
        def __enter__(self): return self
        def __exit__(self,*args): self.source.close()
        def __iter__(self):
            for line in self.source:
                wrapped = Guarded(line)
                wrapped.allowed = set(LAYOUTS[self.member][1].values())
                wrapped.member = self.member
                yield wrapped
    def open_allowed(self,name,*args,**kwargs):
        member = Path(name.filename if hasattr(name,'filename') else name).name
        assert member in LAYOUTS
        opened.append(member)
        return LinesOnly(old_open(self,name,*args,**kwargs),member)
    monkeypatch.setattr(ZipFile,'open',open_allowed)
    def forbidden(*a,**k): raise AssertionError('no extraction or whole-member reads')
    for method in ['extract','extractall','read']: monkeypatch.setattr(ZipFile,method,forbidden)
    body = tcad.parse_export(BytesIO(data))
    assert opened == ['TOTALS.TXT','ABS_SUBD.TXT','IMP_INFO.TXT','IMP_DET.TXT','PROP.TXT']
    assert slices and {m for m,_,_ in slices} == set(LAYOUTS)
    assert not any(m == 'IMP_INFO.TXT' and a <= 69 <= b for m,a,b in slices)
    _,records = normalized(context,body)
    text = json.dumps(body)+json.dumps([r.model_dump(mode='json') for r in records])+capsys.readouterr().err
    for value in [*CANARIES,'2087','111113','222227','333331','444443',*tcad.SPLITS]: assert value not in text
    # Changing forbidden flags/year/name does not affect any parsed fact or counter.
    assert body == tcad.parse_export(BytesIO(without_private))


@pytest.mark.parametrize('code',['1ST','2ND','3RD','4TH','5TH','1/2','ADDL','FBSMT','RSBLW'])
def test_each_living_code(code):
    source = source_rows()
    source['IMP_DET.TXT'] = [segment(123,1,code,1000)]
    p = tcad.parse_export(BytesIO(tiny_zip(source)))['properties'][0]
    assert p['living_area'] == 1000 and p['dwelling_count'] == 1
    assert p['floors'] == (0 if code in {'FBSMT','RSBLW'} else 1)
    assert p['year_built'] == (None if code in {'FBSMT','RSBLW'} else 1990)


@pytest.mark.parametrize('code',['ATTIC','UBSMT','PBSMT','SO','011','012','013','630','631','031','041','051','061','DECK','POOL','STORAGE','250','251','252'])
def test_excluded_segments_never_add_area(code):
    source = source_rows()
    source['IMP_DET.TXT'].append(segment(123,1,code,9999))
    p = tcad.parse_export(BytesIO(tiny_zip(source)))['properties'][0]
    assert (p['living_area'],p['adu_area'],p['hvac_area'],p['year_built']) == (2350,550,2350,1990)


def test_largest_dwelling_then_largest_floor_and_first_ties():
    source = source_rows()
    source['IMP_DET.TXT'] += [segment(123,2,'2ND',3000,'1985'),segment(123,2,'3RD',3000,'2020')]
    p = tcad.parse_export(BytesIO(tiny_zip(source)))['properties'][0]
    assert p['year_built'] == 1985 and p['floors'] == 3
    source['IMP_DET.TXT'] = [segment(123,1,'1ST',500,'0000'),segment(123,1,'2ND',100,'2000')]
    p = tcad.parse_export(BytesIO(tiny_zip(source)))['properties'][0]
    assert p['year_built'] is None  # don't substitute a known year from the smaller floor


def test_categories_state_fallback_and_skip_counts(context):
    source = source_rows()
    source['PROP.TXT'] = [native_prop(str(i+1).zfill(12),code) for i,code in enumerate(tcad.CATEGORIES)]
    for i,code in enumerate(['B1','B5','C1','F1','D1','J1']): source['PROP.TXT'].append(native_prop(str(100+i),code))
    source['PROP.TXT'].append({**native_prop('999','A1'),'prop_type_cd':'P'})
    source['PROP.TXT'][0].update(imprv_state_cd='',land_state_cd='A1')
    source['TOTALS.TXT'][0]['num_real_mobile'] = str(len(source['PROP.TXT'])-1)
    body = tcad.parse_export(BytesIO(tiny_zip(source)))
    props = [tcad.normalize_property(p) for p in body['properties']]
    assert {p['state_cd']:p['category'] for p in props} == tcad.CATEGORIES
    assert body['summary']['skipped_by_state'] == {k:1 for k in ['A1','B1','B5','C1','F1','D1','J1']}
    assert body['summary']['records_read'] == len(source['PROP.TXT'])


def test_mobile_home_type_and_blank_optional_values(context):
    ad,req,raw = planned(context)
    r = raw.body['properties'][0]
    r.update(prop_type_cd='M',imprv_state_cd='A2',geo_id='',situs_num='',situs_street_prefx='',situs_street='',
             situs_street_suffix='',situs_zip='',situs_city='',situs_unit='',udi_group='',deed_dt='',abs_subdv_cd='',abs_subdv_desc=None,
             land_acres=None,market_value='',land_value=None,improvement_value=None,year_built=0)
    p = tcad.normalize_property(r)
    assert p['prop_type'] == 'M' and p['category'] == 'mobile_home' and p['year_built'] is None
    for key in ['geo_id','situs','situs_city','situs_zip','udi_group','deed_date','subdivision','subdivision_code',
                'land_acres','market_value','land_value','improvement_value']: assert p[key] is None


@pytest.mark.parametrize('member,field,value',[
    ('PROP.TXT','prop_val_yr','02025'),('PROP.TXT','sup_num','000000000001'),
    ('TOTALS.TXT','sup_num','1'),('TOTALS.TXT','num_real_mobile','100'),
    ('IMP_INFO.TXT','prop_val_yr','2025'),('IMP_DET.TXT','prop_val_yr','2025'),
    ('PROP.TXT','prop_id','not-an-id')])
def test_wrong_year_supplement_totals_or_id_fails(member,field,value):
    source = source_rows(); source[member][0][field] = value
    with pytest.raises(ValueError): tcad.parse_export(BytesIO(tiny_zip(source)))


@pytest.mark.parametrize('member',LAYOUTS)
def test_wrong_line_lengths_fail(member):
    def change(name,data): return data[1:] if name == member else data
    with pytest.raises(ValueError,match='length'):
        tcad.parse_export(BytesIO(tiny_zip(change_bytes=change)))


@pytest.mark.parametrize('kind',['missing','duplicate'])
def test_missing_or_duplicate_required_member_fails(kind):
    with pytest.raises(ValueError,match='missing or duplicate'):
        tcad.parse_export(BytesIO(tiny_zip(**{'omit' if kind=='missing' else 'duplicate':'IMP_DET.TXT'})))


def test_mobile_home_rows_count_for_totals_but_are_not_kept(context,monkeypatch):
    # Real file: TOTALS "real/mobile" includes mobile homes coded MH (owner: MH stays skipped).
    source = source_rows()
    mobile = native_prop('000000000789', 'A2'); mobile['prop_type_cd'] = 'MH'
    source['PROP.TXT'].append(mobile)
    source['TOTALS.TXT'][0]['num_real_mobile'] = '000000000003'
    body = tcad.parse_export(BytesIO(tiny_zip(source)))
    assert [p['prop_id'] for p in body['properties']] == ['123', '456']
    assert body['summary']['real_mobile'] == 3 and body['summary']['mobile_home_rows'] == 1
    assert body['summary']['skipped_by_state'] == {'A2': 1}
    # A real mismatch names the counts and the row types (aggregates only), nothing else.
    source['TOTALS.TXT'][0]['num_real_mobile'] = '000000000100'
    with pytest.raises(ValueError) as error: tcad.parse_export(BytesIO(tiny_zip(source)))
    text = str(error.value)
    assert 'count 3 outside 2% of TOTALS 100' in text and 'rows by type R 2, MH 1' in text
    # ... and a failed live fetch passes that text on (letters, digits and a few symbols only).
    ad,req,_ = planned(context)
    class Response(BytesIO):
        status=200
        headers={}
    monkeypatch.setattr(tcad.urllib.request,'urlopen',lambda *a,**k:Response(tiny_zip(source)))
    raw = ad.fetch(req,context)
    with pytest.raises(ValueError, match='rows by type R 2, MH 1'): ad.follow_up(raw,context)


def test_partial_owner_repeat_rows_keep_the_first_and_are_counted():
    # Real shape (probe 2026-10-26): adjacent rows for one property, partial_owner T, same udi_group,
    # same facts (the market value can differ slightly).
    source = source_rows()
    again = copy.deepcopy(source['PROP.TXT'][0]); again['market_value'] = '00000001111000'
    source['PROP.TXT'].insert(1, again)
    body = tcad.parse_export(BytesIO(tiny_zip(source)))
    assert [p['prop_id'] for p in body['properties']] == ['123', '456'] and body['summary']['repeated_rows'] == 1
    assert body['summary']['records_read'] == 3 and body['properties'][0]['market_value'] == '00000001111114'
    # A skipped (non-residential) repeat is counted too, and the counts reconcile in finalize.
    for change in [{'imprv_state_cd': 'A4'}, {'udi_group': '000000000008'}, {'prop_type_cd': 'M'}]:
        source = source_rows(); other = copy.deepcopy(source['PROP.TXT'][0]); other.update(change)
        source['PROP.TXT'].insert(1, other)
        with pytest.raises(ValueError, match='duplicate'): tcad.parse_export(BytesIO(tiny_zip(source)))


def test_blank_improvement_type_is_a_dwelling_not_a_failure():
    # Real shape: one 2026 IMP_INFO row has a blank imprv_type_cd (found in the first live check).
    source = source_rows()
    source['IMP_INFO.TXT'].append(info(123,7,''))
    source['IMP_DET.TXT'].append(segment(123,7,'1ST',400,'1980'))
    p = next(r for r in tcad.parse_export(BytesIO(tiny_zip(source)))['properties'] if r['prop_id'] == '123')
    assert p['living_area'] == 2750 and p['dwelling_count'] == 3 and p['adu_area'] == 550


def test_duplicate_properties_improvements_and_missing_improvement_fail():
    for member in ['PROP.TXT','IMP_INFO.TXT']:
        source=source_rows();source[member].append(copy.deepcopy(source[member][0]))
        if member=='PROP.TXT': source[member][-1]['partial_owner']='F'  # only partial-owner repeats are allowed
        with pytest.raises(ValueError,match='duplicate'): tcad.parse_export(BytesIO(tiny_zip(source)))
    source=source_rows();source['IMP_DET.TXT'][0]['imprv_id']='999'
    with pytest.raises(ValueError,match='no improvement'): tcad.parse_export(BytesIO(tiny_zip(source)))


def test_ratio_guards_exact_thresholds_without_large_fixtures():
    for count in [980,1000,1020]: tcad.check_counts({'real_mobile':count,'totals_num_real_mobile':1000},330000,True)
    for count in [979,1021]:
        with pytest.raises(ValueError,match='TOTALS'): tcad.check_counts({'real_mobile':count,'totals_num_real_mobile':1000},330000,True)
    for n in [330000,430000]:tcad.check_counts({'real_mobile':1000,'totals_num_real_mobile':1000},n,True)
    for n in [329999,430001]:
        with pytest.raises(ValueError,match='kept count'):tcad.check_counts({'real_mobile':1000,'totals_num_real_mobile':1000},n,True)
    for covered in [97,100]:tcad.quality_checks({'single_family_condo':100,'single_family_condo_with_living_area':covered,'hvac_comparable':100,'hvac_agree':covered})
    for which in ['single_family_condo_with_living_area','hvac_agree']:
        counts={'single_family_condo':100,'single_family_condo_with_living_area':100,'hvac_comparable':100,'hvac_agree':100};counts[which]=96
        with pytest.raises(ValueError,match='97%'):tcad.quality_checks(counts)


def test_hvac_two_percent_and_missing_denominators():
    p={'category':'single_family','living_area':1000,'hvac_area':1020,'partial_owner':False}
    assert tcad.quality_counts([p])['hvac_agree'] == 1
    assert tcad.quality_counts([{**p,'hvac_area':1021}])['hvac_agree'] == 0
    empty=tcad.quality_counts([{**p,'category':'builder_inventory','living_area':None,'hvac_area':None}])
    assert empty['hvac_agreement'] is None and empty['living_area_coverage'] is None


def test_quality_failures_in_fixture_mode(context):
    for field,value in [('living_area',None),('hvac_area',5000)]:
        ad,req,raw = planned(context);raw.body['properties'][0][field]=value
        with pytest.raises(ValueError,match='97%'):ad.finalize(list(ad.normalize(raw)))


def test_compact_response_rejects_unknown_fields_bad_date_and_malformed_values(context):
    for key,value in [('owner_name',CANARIES[0]),('land_hstd_val',123)]:
        ad,req,raw=planned(context);raw.body['properties'][0][key]=value
        with pytest.raises(ValueError,match='fields'):list(ad.normalize(raw))
    for key,value in [('deed_dt','invalid'),('land_acres',-1),('market_value','bad'),('partial_owner','?'),('sup_num','1'),('prop_val_yr','2025')]:
        ad,req,raw=planned(context);raw.body['properties'][0][key]=value
        with pytest.raises(ValueError):list(ad.normalize(raw))


class Response(BytesIO):
    status=200
    def __init__(self,data):
        super().__init__(data);self.headers={'Content-Length':str(len(data))};self.read_sizes=[]
    def read(self,size=-1):
        assert 0 < size <= 1024*1024
        self.read_sizes.append(size)
        return super().read(size)


def test_fetch_streams_cleans_and_canaries_absent_in_outputs(context,monkeypatch,capsys):
    data=tiny_zip();response=Response(data)
    def serve(request,timeout):
        assert request.full_url == tcad.URL and timeout == 180
        assert request.get_header('Accept-encoding') == 'identity'
        return response
    monkeypatch.setattr(tcad.urllib.request,'urlopen',serve)
    ad,req,raw=planned(context)
    raw=ad.fetch(req,context)
    assert raw.status == 200 and response.read_sizes
    assert not list(paths().raw.rglob('*'))
    records=ad.finalize(list(ad.normalize(raw)))
    path=canonical.write('area_feature','tcad',records)
    output=gzip.decompress(path.read_bytes()).decode()+capsys.readouterr().err
    for value in [*CANARIES,'2087','111113','222227','333331','444443']:assert value not in output
    assert not [p for p in paths().web_public.rglob('*') if p.is_file()]


@pytest.mark.parametrize('failure',['not_zip','short','stream','http','parse','deadline'])
def test_fetch_error_cleanup_and_sanitized_errors(context,monkeypatch,failure):
    data=tiny_zip(omit='PROP.TXT') if failure=='parse' else tiny_zip()
    response=Response(b'not a zip' if failure=='not_zip' else data)
    if failure=='short':response.headers['Content-Length']=str(len(data)+1)
    if failure=='stream':
        def broken(size):raise OSError(CANARIES[0])
        response.read=broken
    if failure=='http':response.status=503
    monkeypatch.setattr(tcad.urllib.request,'urlopen',lambda *a,**k:response)
    ad,req,raw=planned(context)
    if failure=='deadline':ad.started-=2700
    raw=ad.fetch(req,context)
    assert raw.status != 200 and not list(paths().raw.rglob('*'))
    with pytest.raises(ValueError):ad.follow_up(raw,context)
    with pytest.raises(ValueError):list(ad.normalize(raw))
    assert not any(value in json.dumps(raw.body) for value in CANARIES)


def test_failed_check_names_the_adapter_message_but_never_source_text(context,monkeypatch):
    ad,req,_=planned(context)
    class Response(BytesIO):
        status=200
        headers={}
    def run(exc_or_data):
        if isinstance(exc_or_data,bytes):
            monkeypatch.setattr(tcad.urllib.request,'urlopen',lambda *a,**k:Response(exc_or_data))
        else:
            monkeypatch.setattr(tcad.urllib.request,'urlopen',lambda *a,**k:(_ for _ in ()).throw(exc_or_data))
        raw=ad.fetch(req,context)
        with pytest.raises(ValueError) as error: ad.follow_up(raw,context)
        return str(error.value)
    assert 'missing or duplicate TCAD required ZIP member' in run(tiny_zip(omit='PROP.TXT'))
    for hostile in [ValueError('invalid literal for int() with base 10: '+repr(CANARIES[0])),
                    ValueError('TCAD '+CANARIES[1]), OSError(CANARIES[2]), ValueError('SMITH JOHN 123 MAIN ST')]:
        message=run(hostile)
        assert not any(c in message for c in CANARIES) and 'SMITH' not in message and "'" not in message


def test_fixture_run_and_regenerated_fixtures(repo,monkeypatch):
    monkeypatch.setattr(tcad.urllib.request,'urlopen',lambda *a,**k:pytest.fail('fixture must never fetch'))
    run=runner.run('tcad',mode='fixture',now=NOW)
    assert run.status=='success' and run.rows_out==3 and run.calls_made==0 and run.source_as_of==date(2026,1,1)
    assert canonical.read('area_feature','tcad') is None
    assert not list(paths().web_public.rglob('*.geojson'))
    assert json.loads((paths().web_public/'data/benchmarks/tcad.json').read_text())['records'] == []
    subprocess.run([sys.executable,str(repo/'adapters/tcad/make_fixtures.py')],check=True)
    assert (repo/'adapters/tcad/fixtures/tcad_2026.json').read_bytes()==(ROOT/'adapters/tcad/fixtures/tcad_2026.json').read_bytes()


def test_fixture_does_not_read_live_parcels(context,monkeypatch):
    target=paths().canonical/'area_feature/parcels.ndjson.gz';target.parent.mkdir(parents=True);target.write_bytes(b'not a fixture')
    monkeypatch.setattr(tcad.gzip,'open',lambda *a,**k:pytest.fail('fixture must not consult live canonical data'))
    _,records=normalized(context)
    assert records[-1].properties['parcel_match_share'] is None


def test_mock_live_canonical_match_and_failure_keeps_previous(repo,monkeypatch,capsys):
    real_checks=tcad.check_counts
    # parse_export invokes non-volume checks before live finalization too.
    monkeypatch.setattr(tcad,'check_counts',lambda counts,kept,live: real_checks(counts,kept,False))
    original_load=adapter.load
    monkeypatch.setattr(adapter,'load',lambda identity:tcad.TCAD() if identity=='tcad' else original_load(identity))
    monkeypatch.setattr(tcad.urllib.request,'urlopen',lambda *a,**k:Response(tiny_zip()))
    base=[AreaFeature(dataset='parcel',feature_id=fips+':'+pid,geometry={'type':'Point','coordinates':[-97.7,30.3]},
          properties={'county':county,'prop_id':pid}) for fips,county,pid in [('48453','Travis','000123'),('48453','Travis','888'),('48209','Hays','456')]]
    canonical.write('area_feature','parcels',base)
    run=runner.run('tcad',mode='live',now=NOW)
    assert run.status=='success' and run.calls_made==1 and run.rows_out==3
    records=canonical.read('area_feature','tcad');summary=next(r for r in records if r.dataset=='run_summary')
    assert summary.properties['parcel_matches']==1 and summary.properties['parcel_match_share']==.5
    path=canonical.path_for('area_feature','tcad');before=path.read_bytes()
    output=gzip.decompress(before).decode()+capsys.readouterr().err
    for value in CANARIES:assert value not in output
    assert not list(paths().raw.rglob('*'))
    from importlib.util import spec_from_file_location,module_from_spec
    spec=spec_from_file_location('tcad_summary',ROOT/'tools/live_summary.py');module=module_from_spec(spec);spec.loader.exec_module(module)
    assert module.main('tcad')==0 and 'parcel_match_share=0.5' in capsys.readouterr().out
    source=source_rows();source['PROP.TXT'][0]['sup_num']='1'
    monkeypatch.setattr(tcad.urllib.request,'urlopen',lambda *a,**k:Response(tiny_zip(source)))
    failed=runner.run('tcad',mode='live',now=NOW)
    assert failed.status=='failed' and failed.calls_made==1 and path.read_bytes()==before
    assert not list(paths().raw.rglob('*'))
    for directory in [repo/'data',paths().web_public]:
        for file in directory.rglob('*'):
            if file.is_file():
                payload=gzip.decompress(file.read_bytes()) if file.suffix=='.gz' else file.read_bytes()
                for canary in CANARIES:assert canary.encode() not in payload
    assert not any(canary in capsys.readouterr().err for canary in CANARIES)


def test_rounding_adu_presence_missing_values_and_latin1(context):
    source=source_rows()
    source['PROP.TXT'][0].update(land_hstd_val='',land_acres='',deed_dt='',situs_street='CAFÉ')
    source['IMP_DET.TXT']=[segment(123,1,'1ST',1000.4),segment(123,1,'1ST',200.4),segment(123,1,'095',1200.8),segment(456,6,'1ST',1500)]
    body=tcad.parse_export(BytesIO(tiny_zip(source)))
    p=tcad.normalize_property(body['properties'][0])
    assert p['living_area']==1201 and p['hvac_area']==1200.8 and p['floors']==1
    assert p['adu_area'] is None and p['has_adu'] is True and p['dwelling_count']==1
    assert p['land_value'] is None and p['land_acres'] is None and p['deed_date'] is None
    assert p['situs_street']=='CAFÉ'


def test_runtime_limit_applies_to_finalization(context):
    ad,req,raw=planned(context)
    records=list(ad.normalize(raw))
    ad.started-=2700
    with pytest.raises(ValueError,match='45-minute'):ad.finalize(records)


def test_totals_requires_one_county_and_subdivisions_cannot_conflict():
    for rows in [[],[{'entity_cd':'04','sup_num':'0','num_real_mobile':'2'}]]:
        source=source_rows();source['TOTALS.TXT']=rows
        with pytest.raises(ValueError,match='TOTALS'):tcad.parse_export(BytesIO(tiny_zip(source)))
    source=source_rows();source['TOTALS.TXT']*=2
    with pytest.raises(ValueError,match='TOTALS'):tcad.parse_export(BytesIO(tiny_zip(source)))
    source=source_rows();source['ABS_SUBD.TXT'].append({'abs_subdv_cd':'TEST01','abs_subdv_desc':'DIFFERENT'})
    with pytest.raises(ValueError,match='subdivision'):tcad.parse_export(BytesIO(tiny_zip(source)))


def test_counts_reconcile_and_property_ids_are_unique(context):
    for key in ['records_read','real_mobile']:
        ad,req,raw=planned(context);raw.body['summary'][key]=0
        with pytest.raises(ValueError,match='reconcile'):ad.finalize(list(ad.normalize(raw)))
    ad,req,raw=planned(context);raw.body['properties'][1]['prop_id']=raw.body['properties'][0]['prop_id']
    with pytest.raises(ValueError,match='duplicate'):ad.finalize(list(ad.normalize(raw)))
