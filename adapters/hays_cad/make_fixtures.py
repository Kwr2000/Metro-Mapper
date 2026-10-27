"""Small synthetic monthly-export cells; never fetches or reads real data."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import json
from tempfile import TemporaryDirectory
from io import BytesIO, StringIO
import csv
from zipfile import ZipFile, ZIP_DEFLATED

# Header transcription deliberately independent of the parser allowlist.
HEADERS = {
 'property': ['PropertyID','QuickRefID','CurrMarketValue','CurrLandValue','CurrImprovmentValue','SquareFootage',
  'NbhdCode','NbhdDesc','SitusPreDirectional','SitusStreetNumber','SitusStreetName','SitusStreetSuffix',
  'SitusPostDirectional','SitusCity','SitusZip','LegalAcres','LegalDesc','Situs','TaxingUnitList','LeaseNumber','MarketValue'],
 'improvement':['PropertyID','InstanceID','Type','StateCode','ImpValue','Description'],
 'segment':['PropertyID','InstanceID','Type','Area','ActYrBuilt','EffYrBuilt','Bedrooms'],
 'land':['PropertyID','LandType','Acres','SquareFeet'],
 'owner':['PropertyID','OwnerName','MailAddress','Exemptions'],
 'sales':['PropertyID','PrevOwnerName','SaleDate','Instrument'],
}
CANARIES = {'LegalDesc':'CANARY_LEGAL_PERSON', 'Situs':'CANARY_FREE_SITUS', 'TaxingUnitList':'CANARY_TAX_UNITS',
 'LeaseNumber':'CANARY_LEASE', 'MarketValue':'CANARY_PRIOR_VALUE', 'OwnerName':'CANARY_OWNER',
 'MailAddress':'CANARY_MAIL', 'Exemptions':'CANARY_EXEMPT', 'PrevOwnerName':'CANARY_PREVIOUS_OWNER'}


def source_rows():
 property_rows=[]
 for pid in range(1001,1012):
  row={field:'' for field in HEADERS['property']}
  row.update(PropertyID=str(pid),QuickRefID='R'+str(pid),CurrMarketValue='435394.60',CurrLandValue='100000',
   CurrImprovmentValue='335394.60',SquareFootage='2000',NbhdCode='T01',NbhdDesc='TEST, CREEK "HOMES"',
   SitusPreDirectional='S',SitusStreetNumber='1008',SitusStreetName='TEST',SitusStreetSuffix='ST',
   SitusPostDirectional='W',SitusCity='San Marcos',SitusZip='78666',LegalAcres='0.4')
  row.update({k:v for k,v in CANARIES.items() if k in row})
  property_rows.append(row)
 property_rows[4]['SquareFootage']=''
 property_rows[4]['LegalAcres']=''
 property_rows[9]['QuickRefID']='M1010'
 property_rows[10]['QuickRefID']='P1011'
 improvements=[]
 for pid,code,typ in [(1001,'A','R'),(1002,'A5','M'),(1003,'B','R'),(1004,'E','R'),(1005,'O','R'),
                      (1006,'B','C'),(1007,'M1','M'),(1008,'X1','R'),(1010,'A','R'),(1011,'A','M')]:
  improvements.append(dict(PropertyID=str(pid),InstanceID='1',StateCode=code,Type=typ,ImpValue='300000'))
 # A commercial improvement with more value must not replace a mapped home.
 improvements.extend([dict(PropertyID='1001',InstanceID='2',StateCode='B',Type='C',ImpValue='999999'),
                      dict(PropertyID='1001',InstanceID='3',StateCode='E',Type='R',ImpValue='300000')])
 segments=[dict(PropertyID=str(pid),InstanceID='1',Type='MA',Area='2000',ActYrBuilt='2001') for pid in range(1002,1005)]
 segments += [dict(PropertyID='1001',InstanceID='1',Type=code,Area=area,ActYrBuilt=year) for code,area,year in
              [('MA','1400','1998'),('MAUPS9','400','2005'),('MAADDN','200','2010'),('GAR','9999','2020')]]
 land=[dict(PropertyID='1001',LandType='R',Acres='0.1',SquareFeet='999999'),
       dict(PropertyID='1001',LandType='R',Acres='0.2',SquareFeet='0'),
       dict(PropertyID='1002',LandType='R',Acres='0',SquareFeet='21780'),
       dict(PropertyID='1005',LandType='R',Acres='0',SquareFeet='0')]
 return {'property':[*property_rows,deepcopy(property_rows[0])], 'improvement':improvements,'segment':segments,'land':land,
         'owner':[dict(PropertyID='1001',**{k:v for k,v in CANARIES.items() if k in HEADERS['owner']})],
         'sales':[dict(PropertyID='1001',PrevOwnerName=CANARIES['PrevOwnerName'],SaleDate='01-01-2020',Instrument='TEST')]}


def tiny_zip(rows=None, order=None, headers=None):
 rows=source_rows() if rows is None else rows
 headers=HEADERS if headers is None else headers
 outer=BytesIO()
 with ZipFile(outer,'w',ZIP_DEFLATED) as archive:
  for index,kind in enumerate(order or ['sales','segment','land','owner','property','improvement']):
   content=StringIO(newline='');writer=csv.writer(content,lineterminator='\r\n')
   writer.writerow(headers[kind])
   writer.writerows([[row.get(field,'') for field in headers[kind]] for row in rows[kind]])
   nested=BytesIO()
   with ZipFile(nested,'w',ZIP_DEFLATED) as z:
    z.writestr(f'PropertyDataExport{1419107+index}.txt',content.getvalue().encode('latin-1'))
   archive.writestr(f'PropertyDataExport{1419207+index}.zip',nested.getvalue())
 return outer.getvalue()


if __name__=='__main__':
 folder=Path(__file__).resolve().parent
 spec=importlib.util.spec_from_file_location('hays_fixture_parser',folder/'adapter.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 with TemporaryDirectory() as temp:
  path=Path(temp)/'synthetic.zip';path.write_bytes(tiny_zip())
  body=module.parse_export(path)
 (folder/'fixtures/hays_cad_2026.json').write_text(json.dumps({'status':200,'body':body},indent=2)+'\n')
