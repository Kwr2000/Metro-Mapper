"""Build 25 made-up Redfin-shaped rows from the published synthetic home fixtures."""
import csv
import io
import json
from pathlib import Path

HEADERS=['SALE TYPE','SOLD DATE','PROPERTY TYPE','ADDRESS','CITY','STATE OR PROVINCE','ZIP OR POSTAL CODE',
         'PRICE','BEDS','BATHS','LOCATION','SQUARE FEET','LOT SIZE','YEAR BUILT','DAYS ON MARKET','$/SQUARE FEET',
         'HOA/MONTH','STATUS','URL (SEE DETAILS)','SOURCE','MLS#','FAVORITE','INTERESTED','LATITUDE','LONGITUDE','PRIVATE NOTES']


def native_rows(folder):
    meta=json.loads((folder/'meta.json').read_text());assert meta['test_data'],'Only synthetic home publications may build this fixture'
    homes=[]
    for path in sorted((folder/'addr').glob('*.json')):
        doc=json.loads(path.read_text());assert doc['test_data']
        homes.extend(dict(zip(doc['fields'],row)) for row in doc['rows'])
    homes=[h for h in homes if h['number'] and h['street_key']]
    assert homes
    rows=[]
    for i in range(25):
        h=homes[i%len(homes)];address=f"{h['number']} {h['street_key']}"+(f" #{h['unit']}" if h['unit'] else '')
        price=741239 if i==0 else round((h['market_value'] or 350000)*(.6+.06*(i%12)))
        rows.append({'SALE TYPE':'MLS Listing','SOLD DATE':'','PROPERTY TYPE':'Synthetic residential listing',
            'ADDRESS':address,'CITY':h['city'] or '','STATE OR PROVINCE':'TX','ZIP OR POSTAL CODE':h['zip'] or '',
            'PRICE':f'${price:,}','BEDS':str(2+i%4),'BATHS':'2.5','LOCATION':'Synthetic test neighbourhood',
            'SQUARE FEET':str(round(h['living_area']*1.2) if i==0 and h['living_area'] else h['living_area'] or ''),
            'LOT SIZE':'8000','YEAR BUILT':str(h['year_built'] or ''),'DAYS ON MARKET':str(i),'$/SQUARE FEET':'999',
            'HOA/MONTH':'' if i%4==0 else str(i*10),'STATUS':'Active',
            'URL (SEE DETAILS)':f'https://example.invalid/private-listing-{i}','SOURCE':'Synthetic Test data','MLS#':f'FAKE-{i}',
            'FAVORITE':'N','INTERESTED':'Y','LATITUDE':str(h['lat'] or ''),'LONGITUDE':str(h['lon'] or ''),
            'PRIVATE NOTES':'CANARY_OWNER_FILE_PRIVATE, with "quotes"\r\nand a second line'})
    return rows


def build(web):
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=HEADERS,lineterminator='\r\n')
    writer.writeheader();writer.writerows(native_rows(web/'public/data/homes'))
    writer.writerow({'SALE TYPE':'Synthetic publisher disclaimer — not a listing'})
    target=web/'e2e/fixtures/batch-25.csv';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(('\ufeff'+output.getvalue()).encode())


if __name__=='__main__':build(Path(__file__).resolve().parents[1])
