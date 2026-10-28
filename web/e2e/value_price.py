"""Score vs price on coherent synthetic area publications; no data-source requests."""
import json
import re
from urllib.parse import quote, unquote, urlparse
from playwright.sync_api import expect
from shapely.geometry import shape
from homes import read_homes, BANNED


def smoke(browser,registry,width,height,url,dist,artifacts,plain_style):
    base=next(l for l in registry['layers'] if l['join']=='block_group' and any(p['field']=='name' for p in l['popup']))
    areas=json.loads((dist/base['data_url']).read_text())['features'];ids=[str(a.get('id') or a['properties']['geoid']) for a in areas]
    scores=json.loads((dist/'data/area_score.json').read_text());assert scores['test_data']
    scores['rows']={id:[None]*14 for id in ids}
    for i,id in enumerate(ids[:4]):scores['rows'][id]=[90 if i<2 else 10,90 if i in (1,2) else 10,50,50,50,50,1,2,3,4,5,6,7,8]
    prices={'v':1,'test_data':True,'as_of':'Synthetic CAD 2026-01-01, FHFA 2026-06-30','method':'Test data: single-family appraisal-based centres; unplaced homes excluded',
            'rows':{id:[10+i,1000 if i==4 else 300 if i%2 else 100] for i,id in enumerate(ids[:5])}}
    homes=read_homes(dist);unit=next(h for h in homes if h['unit'] and h['range_pct']);other=next(h for h in homes if h['county']=='Travis' and h['category']=='single_family')
    requests=[];violations=[];processing=False
    def route(r):
        parsed=urlparse(r.request.url);own=parsed.netloc==urlparse(url).netloc
        requests.append((r.request.method,r.request.url))
        if processing and (not own or not parsed.path.startswith('/data/') or parsed.query or r.request.post_data):
            violations.append(r.request.url);r.abort();return
        if not own:r.fulfill(content_type='application/json',body=json.dumps(plain_style));return
        path=parsed.path.lstrip('/')
        if path=='data/area_score.json':r.fulfill(content_type='application/json',body=json.dumps(scores))
        elif path=='data/area_price.json':r.fulfill(content_type='application/json',body=json.dumps(prices))
        elif path=='data/homes/meta.json':
            meta=json.loads((dist/path).read_text());meta['value_range']['published']=True
            meta['value_range']['calibration']['used']=False
            r.fulfill(content_type='application/json',body=json.dumps(meta))
        elif path.startswith('data/homes/addr/'):
            doc=json.loads((dist/path).read_text());fields=doc['fields']
            for row in doc['rows']:
                if row[fields.index('id')] in (unit['id'],other['id']):row[fields.index('block_group')]=ids[0] if row[0]==unit['id'] else ids[1]
            r.fulfill(content_type='application/json',body=json.dumps(doc))
        else:r.continue_()
    context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');context.route('**/*',route)
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
    point=shape(areas[0]['geometry']).representative_point()
    view={'version':1,'camera':{'center':[point.x,point.y],'zoom':12},'visible':[base['id']],'variants':{},'filters':{},'compare':[],'colour':{},'score':{'weights':[5,0,0,0,0,0],'colour':False}}
    page.goto(url+'/#/?v='+quote(json.dumps(view)),wait_until='networkidle');expect(page.get_by_test_id('map')).to_have_attribute('data-map-ready','true')
    tabs=page.get_by_role('navigation',name='Area tools tabs');tabs.get_by_role('button',name='Score',exact=True).click()
    panel=page.get_by_role('region',name='Good place to live',exact=True);mode=panel.get_by_role('checkbox',name='Score vs price',exact=True);mode.check()
    legend=panel.locator('[aria-label="Score vs price legend"]');expect(legend).to_contain_text('score 50; price per sq ft $200')
    for label in ('Higher score, lower price per sq ft','Higher score, higher price per sq ft','Lower score, lower price per sq ft','Lower score, higher price per sq ft'):expect(legend.get_by_text(label,exact=True)).to_be_visible()
    expect(panel.get_by_role('checkbox',name='Colour by score',exact=True)).not_to_be_checked()
    assert json.loads(unquote(page.url.split('v=',1)[1]))['score']['price'] is True
    mode.uncheck();expect(legend).to_have_count(0);mode.check();expect(legend).to_be_visible()
    legend.evaluate("el=>el.scrollIntoView({block:'center'})")
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(artifacts/f'score-price-mode-{width}x{height}.png'))
    panel.get_by_role('tab',name='Areas list',exact=True).click();listing=panel.get_by_role('region',name='Areas list',exact=True)
    slider=listing.get_by_role('slider',name='Max $ per sq ft');expect(slider).to_have_attribute('min','100');expect(slider).to_have_attribute('max','1000')
    slider.focus();slider.press('Home');expect(slider).to_have_value('100');expect(listing.locator('tbody tr')).to_have_count(2)
    expect(listing.locator('tbody tr').first).to_contain_text(ids[0])
    panel.get_by_role('tab',name='Weights',exact=True).click()
    safety=panel.get_by_role('slider',name='Safety',exact=True);safety.focus();safety.press('Home')
    school=panel.get_by_role('slider',name='Schools',exact=True);school.focus();school.press('End')
    panel.get_by_role('tab',name='Areas list',exact=True).click();expect(slider).to_have_value('100');expect(listing.locator('tbody tr').first).to_contain_text(ids[2])
    listing.get_by_role('table').evaluate("el=>el.scrollIntoView({block:'center'})")
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(artifacts/f'score-price-list-{width}x{height}.png'))
    listing.locator('tbody tr').first.get_by_role('link').click();expect(page.get_by_role('region',name='Selected area')).to_contain_text(ids[2])
    # The row zooms to the area; the normal map popup includes its price and sample count.
    node=page.get_by_test_id('map');page.wait_for_timeout(700)
    box=node.bounding_box();inset=page.get_by_role('complementary',name='Area tools').bounding_box()['height']+16 if width<760 else 0
    node.click(position={'x':box['width']/2,'y':(box['height']-inset)/2})
    popup=page.get_by_test_id('map-inspection');expect(popup).to_contain_text('Median appraisal-based $ per sq ft: $100 (n = 12 single-family homes)')
    page.get_by_role('button',name='Close popup',exact=True).click()
    # Restoring view-link weights must also carry through to the batch, without slider edits.
    page.evaluate("""() => {const v=JSON.parse(new URLSearchParams(location.hash.split('?')[1]).get('v'));v.score.weights=[0,1,0,0,0,0];location.hash='/?v='+encodeURIComponent(JSON.stringify(v));}""")
    page.wait_for_function("JSON.parse(localStorage.getItem('metro-mapper:area-score')).weights[1]===1")
    page.get_by_role('navigation',name='Pages').get_by_role('link',name='Check a home',exact=True).click();page.get_by_role('link',name='Check many listings',exact=True).click();page.wait_for_load_state('networkidle')
    processing=True
    def address(h):return f"{h['number']} {h['street_key']}"+(f" #{h['unit']}" if h['unit'] else '')+f" TX {h['zip']}"
    page.get_by_role('textbox',name='Addresses and asking prices').fill(address(unit)+' — $560000\n'+address(other)+' — $400000')
    page.get_by_role('button',name='Check pasted listings',exact=True).click();rows=page.locator('.batch-table tbody tr');expect(rows).to_have_count(2)
    expect(page.get_by_label('Sort by',exact=True)).to_have_value('default')
    page.get_by_label('Sort by',exact=True).select_option('areaScore');expect(rows.first).to_have_attribute('data-listing-key','0')
    cells=rows.first.locator('td');expect(cells.nth(cells.count()-4)).to_contain_text('10');expect(cells.nth(cells.count()-3)).to_contain_text('20 / 100')  # then Things to check, Sources
    page.get_by_role('button',name='Ascending',exact=True).click();expect(rows.first).to_have_attribute('data-listing-key','1')
    page.get_by_label('Sort by',exact=True).select_option('areaPercentile');expect(rows.first).to_have_attribute('data-listing-key','0')
    if width<760:cells.nth(cells.count()-3).evaluate("el=>el.scrollIntoView({block:'center'})")
    else:page.locator('.batch-table-wrap').evaluate('el=>{el.scrollIntoView({block:"start"});el.scrollLeft=el.scrollWidth;}')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(artifacts/f'score-price-batch-{width}x{height}.png'))
    assert not BANNED.search(page.locator('.batch-page').inner_text())
    assert sum(urlparse(r).path=='/data/area_score.json' for _,r in requests)==1
    assert sum(urlparse(r).path=='/data/area_price.json' for _,r in requests)==1
    assert not violations and not errors,(violations,errors)
    assert all(m=='GET' for m,_ in requests)
    context.close();print(f'PASS score vs price {width}×{height}: on/off, four classes, weight/list updates, slider, map link/popup, batch columns/sorts, no overflow or processing requests outside data/')
