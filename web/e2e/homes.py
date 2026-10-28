"""Fixture-only home flow, shared by both viewport checks. No publisher requests."""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import urllib.request
from urllib.parse import quote, urlparse
from playwright.sync_api import expect

BANNED=re.compile(r'\b(fair value|good deal|overpriced|worth|bargain|undervalued|bad|avoid|deal)\b',re.I)


def prepare(web):
    root=web.parent
    # Use the real fixture publisher without reading stored live canonical files.
    prior=os.environ.get('MM_ROOT')
    original_open,original_socket=urllib.request.urlopen,socket.create_connection
    def blocked(*args,**kwargs):raise RuntimeError('Source networking disabled in fixture preparation')
    urllib.request.urlopen=blocked;socket.create_connection=blocked
    try:
        with tempfile.TemporaryDirectory(prefix='mm-home-e2e-') as folder:
            temp=Path(folder)
            for name in ['adapters','config','layers']:(temp/name).symlink_to(root/name,target_is_directory=True)
            os.environ['MM_ROOT']=str(temp)
            from mm import config,homes,area_score,area_price
            config.clear_cache();homes.publish();area_score.publish();area_price.publish()
            target=web/'public/data/homes'
            if target.exists():shutil.rmtree(target)
            shutil.copytree(temp/'web/public/data/homes',target)
            shutil.copyfile(temp/'web/public/data/area_score.json',web/'public/data/area_score.json')
            shutil.copyfile(temp/'web/public/data/area_price.json',web/'public/data/area_price.json')
    finally:
        urllib.request.urlopen=original_open;socket.create_connection=original_socket
        if prior is None:os.environ.pop('MM_ROOT',None)
        else:os.environ['MM_ROOT']=prior
        from mm import config
        config.clear_cache()
    # Vite derives the small ID locator files; the pipeline remains unchanged.
    subprocess.run(['npm','run','build'],cwd=web,check=True)
    for file in (web/'dist').rglob('*'):
        if file.suffix in {'.js','.html'}:assert not (re.compile(r'\b(fair value|good deal|overpriced|worth|bargain|undervalued)\b',re.I) if file.name.startswith('maplibre-') else BANNED).search(file.read_text()),f'Prohibited wording in {file.name}'


def read_homes(dist):
    result=[]
    for file in (dist/'data/homes/addr').glob('*.json'):
        doc=json.loads(file.read_text());result.extend(dict(zip(doc['fields'],row)) for row in doc['rows'])
    return result


def smoke(browser,registry,width,height,url,dist,artifacts,plain_style):
    homes=read_homes(dist);unit=next(h for h in homes if h['unit'] and h['category']=='condo')
    placed=next(h for h in homes if h['placed']=='parcel')
    base=next(l for l in registry['layers'] if l['join']=='block_group' and any(p['field']=='name' for p in l['popup']))
    published=False;requests=[];request_urls=[];external=[]
    meta=json.loads((dist/'data/homes/meta.json').read_text());assert meta['test_data']
    def route(request):
        parsed=urlparse(request.request.url)
        if parsed.hostname!='127.0.0.1':external.append(request.request.url);request.fulfill(status=200,content_type='application/json',body=json.dumps(plain_style));return
        path=parsed.path.lstrip('/');requests.append(path);request_urls.append(request.request.url)
        if path==base['data_url']:
            # Independent pipeline fixtures use different block-group IDs. Make a coherent
            # synthetic web join without changing any adapter or pipeline fixture.
            document=json.loads((dist/base['data_url']).read_text())
            item=document['features'][0];item['id']=placed['block_group'];item['properties']['geoid']=placed['block_group'];item['properties']['name']='Test home area';item['properties']['county']=placed['county']
            x,y=placed['lon'],placed['lat'];item['geometry']={'type':'Polygon','coordinates':[[[x-.001,y-.001],[x+.001,y-.001],[x+.001,y+.001],[x-.001,y+.001],[x-.001,y-.001]]]}
            request.fulfill(content_type='application/json',body=json.dumps(document))
        elif path=='data/homes/meta.json':
            document=json.loads(json.dumps(meta));document['value_range']['published']=published
            request.fulfill(content_type='application/json',body=json.dumps(document))
        elif path=='data/homes/hoods.json':
            request.fulfill(content_type='application/json',body=json.dumps({'v':1,'test_data':True,'rows':[{
                'county':unit['county'],'hood_cd':unit['hood_cd'],'category':'condo','n':20,
                'p10':100,'p25':150,'p50':200,'p75':300,'p90':400}]}))
        else:request.continue_()
    context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');context.route('**/*',route)
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(url+'/#/home',wait_until='networkidle')
    expect(page.get_by_role('heading',name='Check a home',exact=True)).to_be_visible()
    assert not external,'The standalone home page must not initialize the external basemap'
    address=f"{unit['number']} {unit['street_key']} #{unit['unit']}, {unit['city']} TX {unit['zip']}"
    page.get_by_role('searchbox').fill(address);page.get_by_role('searchbox').press('Enter')
    card=page.get_by_role('article',name='Home details');expect(card).to_be_visible()
    expect(card.get_by_role('heading',name=unit['situs'],exact=True)).to_be_focused()
    expect(card.get_by_text('The value range is being validated and will appear here.',exact=True)).to_be_visible()
    assert len([p for p in requests if p.startswith('data/homes/addr/')])==1
    assert requests.count('data/homes/meta.json')==1
    assert not [p for p in requests if p=='data/homes/hoods.json']
    assert not BANNED.search(page.locator('body').inner_text())
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(artifacts/f'home-hidden-{width}x{height}.png'))
    # A missing address shows the exact normalized search and a useful hint.
    page.get_by_role('searchbox').fill('9999 Missing Road');page.get_by_role('searchbox').press('Enter')
    expect(page.get_by_text('Not found in the 2026 appraisal records for Travis, Williamson and Hays counties',exact=True)).to_be_visible()
    expect(page.get_by_text('Try without the unit or ZIP.',exact=True)).to_be_visible()
    # No unit returns multiple records; all selection works with only the keyboard.
    page.get_by_role('searchbox').fill(f"{unit['number']} {unit['street_key']} {unit['zip']}");page.get_by_role('searchbox').press('Enter')
    matches=page.get_by_role('region',name='Matching homes');expect(matches).to_be_visible()
    expect(matches.get_by_role('button').first).to_be_focused();page.keyboard.press('ArrowDown');expect(matches.get_by_role('button').nth(1)).to_be_focused();page.keyboard.press('Enter')
    expect(card).to_be_visible()
    # Fresh-browser ID-only links use a locator bucket plus one address shard.
    share=url+'/#/home?id='+quote(unit['id']);fresh=browser.new_context(viewport={'width':width,'height':height});fresh_requests=[]
    def fresh_route(r):
        if urlparse(r.request.url).hostname!='127.0.0.1':raise AssertionError('External request on a home link')
        fresh_requests.append(urlparse(r.request.url).path);r.continue_()
    fresh.route('**/*',fresh_route);other=fresh.new_page();other.goto(share,wait_until='networkidle')
    expect(other.get_by_role('heading',name=unit['situs'],exact=True)).to_be_focused()
    expect(other.get_by_role('spinbutton',name='Asking price (optional)')).to_have_value('')
    assert len([p for p in fresh_requests if '/addr/' in p])==1 and len([p for p in fresh_requests if '/ids/' in p])==1
    fresh.close()
    # A test-only published flag enables the reference range and disclosure.
    published=True;page.goto(share,wait_until='networkidle');page.reload(wait_until='networkidle')
    expect(card.get_by_text('How this is worked out',exact=True)).to_be_visible()
    price=str(unit['living_area']*280);asking=card.get_by_role('spinbutton',name='Asking price (optional)');asking.fill(price)
    expect(card.get_by_text(re.compile('higher than about 70%'))).to_be_visible()
    expect(card.get_by_text(re.compile('The asking price is (below|inside|above)'))).to_be_visible()
    assert price not in page.url and price not in card.get_by_role('link',name='Link to this home').get_attribute('href')
    assert not any(price in r for r in request_urls)
    page.reload(wait_until='networkidle');expect(asking).to_have_value(price)
    card.get_by_text('How this is worked out',exact=True).click();expect(card.locator('details')).to_have_attribute('open','')
    card.get_by_role('heading',name='Appraisal-based value range',exact=True).scroll_into_view_if_needed()
    assert not BANNED.search(page.locator('body').inner_text())
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(artifacts/f'home-range-{width}x{height}.png'))
    # At zoom 16, an actual canvas click finds a home from the small fixture grid.
    view={'version':1,'camera':{'center':[placed['lon'],placed['lat']],'zoom':16},'visible':[base['id']],'variants':{},'filters':{},'compare':[]}
    page.goto(url+'/#/?v='+quote(json.dumps(view)),wait_until='networkidle');page.reload(wait_until='networkidle')
    map_node=page.get_by_test_id('map');expect(map_node).to_have_attribute('data-map-ready','true')
    if width<760:page.get_by_role('navigation',name='Area tools tabs').get_by_role('button',name='Layers',exact=True).click()
    inset=page.get_by_role('complementary',name='Area tools').bounding_box()['height']+16 if width<760 else 0
    box=map_node.bounding_box();page.wait_for_timeout(700)
    map_node.click(position={'x':box['width']/2,'y':(box['height']-inset)/2})
    panel=page.get_by_role('complementary',name='Home panel');expect(panel).to_be_visible()
    expect(panel.get_by_role('heading',name=placed['situs'],exact=True)).to_be_focused()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(artifacts/f'home-map-{width}x{height}.png'))
    # A later desktop click outside 30 m restores area inspection. On phones the sheet
    # covers the map, so its close control returns keyboard focus to the map instead.
    if width>=760:map_node.click(position={'x':30,'y':30})
    else:panel.get_by_role('button',name='Close home details',exact=True).click()
    expect(panel).not_to_be_visible()
    if width<760:expect(map_node).to_be_focused()
    inset=page.get_by_role('complementary',name='Area tools').bounding_box()['height']+16 if width<760 else 0
    map_node.click(position={'x':box['width']/2,'y':(box['height']-inset)/2})
    expect(panel).to_be_visible()
    panel.get_by_role('button',name='Show on map',exact=True).click();expect(page.get_by_role('region',name='Selected area')).to_be_visible()
    assert not BANNED.search(page.locator('body').inner_text()) and not errors,errors
    context.close();print(f'PASS homes {width}×{height}: unit/ambiguous search, fresh ID link, hidden/shown range, private price reload, nearest map home, no overflow/prohibited copy')
