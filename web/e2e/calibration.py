"""Synthetic accepted calibration on a home card and the batch table, at both sizes."""
import json
from urllib.parse import quote, urlparse
from playwright.sync_api import expect
from homes import read_homes, BANNED
from mm.values import value_range


def smoke(browser,width,height,url,dist,artifacts):
    home=next(h for h in read_homes(dist) if h['unit'] and h['range_pct'])
    meta=json.loads((dist/'data/homes/meta.json').read_text())
    assert meta['test_data']
    fips=home['id'].split(':')[0];tract=fips+'000100'
    cal={'v':1,'fit_year':2025,'test_year':2024,'test_data':True,
         'county':{c:1.05 for c in ('48453','48491','48209')},'tract':{tract:1.12}}
    state={'used':True};calls=[];errors=[]
    def route(r):
        parsed=urlparse(r.request.url)
        assert parsed.netloc==urlparse(url).netloc,'External request in calibration flow'
        path=parsed.path.lstrip('/');calls.append(path)
        if path=='data/homes/meta.json':
            document=json.loads(json.dumps(meta));vr=document['value_range'];vr['published']=True
            vr['calibration']={'used':state['used'],'fit_year':2025,'test_year':2024,'test_data':True,'method':'Synthetic fit on 2025, held-out check on 2024'}
            r.fulfill(content_type='application/json',body=json.dumps(document))
        elif path=='data/homes/calibration.json':
            r.fulfill(content_type='application/json',body=json.dumps(cal))
        elif path.startswith('data/homes/addr/'):
            document=json.loads((dist/path).read_text());fields=document['fields']
            for row in document['rows']:
                if row[fields.index('id')]==home['id']:
                    row[fields.index('block_group')]=tract+'1'
                    if state['used']:row[fields.index('range_flags')]=','.join(filter(None,[row[fields.index('range_flags')],'cal']))
            r.fulfill(content_type='application/json',body=json.dumps(document))
        else:r.continue_()
    context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');context.route('**/*',route)
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url+'/#/home?id='+quote(home['id']),wait_until='networkidle')
    vr=meta['value_range'];ends=value_range(home['market_value'],fips,home['range_pct'],vr['hpi']['factor'],vr['levels'],1.12)
    money=lambda v:f'${v:,.0f}'
    expect(page.locator('.home-range-number')).to_contain_text(money(ends['low'])+' – '+money(ends['high']))
    expect(page.get_by_text('Neighbourhood adjustment of +12% from 2025 home-purchase loans',exact=False).first).to_be_visible()
    page.get_by_text('How this is worked out',exact=True).click()
    expect(page.get_by_text('Multiply by neighbourhood factor',exact=False)).to_contain_text('checked on 2024')
    page.locator('.home-range-number').scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(artifacts/f'calibration-card-{width}x{height}.png'))
    page.get_by_role('link',name='Check many listings',exact=True).click()
    address=f"{home['number']} {home['street_key']} #{home['unit']} {home['zip']}"
    page.get_by_role('textbox',name='Addresses and asking prices').fill(address+' — $'+str(ends['mid']))
    page.get_by_role('button',name='Check pasted listings',exact=True).click()
    row=page.locator('.batch-table tbody tr');expect(row).to_have_count(1)
    expect(row).to_contain_text('Centre '+money(ends['mid']))
    expect(row).to_contain_text('Inside the range')
    expect(row).to_contain_text('Neighbourhood adjustment of +12% from 2025 home-purchase loans')
    assert calls.count('data/homes/calibration.json')==1,'Card and batch reuse the same cached static factors'
    assert not BANNED.search(page.locator('body').inner_text())
    # When hold-out selection is off, identity arithmetic applies and no factor file is loaded.
    state['used']=False;calls.clear()
    page.goto(url+'/#/home?id='+quote(home['id']),wait_until='networkidle');page.reload(wait_until='networkidle')
    base=value_range(home['market_value'],fips,home['range_pct'],vr['hpi']['factor'],vr['levels'])
    expect(page.locator('.home-range-number')).to_contain_text(money(base['low'])+' – '+money(base['high']))
    assert 'data/homes/calibration.json' not in calls
    assert not errors,errors
    context.close();print(f'PASS calibration {width}×{height}: shared tract factor, card/batch agreement, dates/flags, fallback, no external requests')
