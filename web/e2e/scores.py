"""Synthetic score UI at both sizes; only the site's static files are requested."""
import json
from urllib.parse import quote, unquote, urlparse
from playwright.sync_api import expect
from shapely.geometry import shape


def smoke(browser,registry,width,height,url,dist,artifacts,plain_style):
    base=next(l for l in registry['layers'] if l['join']=='block_group' and any(p['field']=='name' for p in l['popup']))
    areas=json.loads((dist/base['data_url']).read_text())['features']
    data=json.loads((dist/'data/area_score.json').read_text());assert data['test_data']
    # Native adapter fixtures have independent GEOIDs. Supply an explicitly Test data
    # score document for the web join, exercising complete/partial/unavailable rows.
    ids=[str(f.get('id') or f['properties']['geoid']) for f in areas]
    data['rows']={identity:[90,20,70,60,50,0,10,80,.1,15,5,10,20,0] for identity in ids}
    data['rows'][ids[1]][0]=None
    if len(ids)>2:data['rows'][ids[2]][:4]=[None]*4
    point=shape(areas[0]['geometry']).representative_point()
    view={'version':1,'camera':{'center':[point.x,point.y],'zoom':12},'visible':[base['id']],'variants':{},'filters':{},'compare':[],'colour':{}}
    requests=[]
    def route(r):
        parsed=urlparse(r.request.url)
        if parsed.hostname!='127.0.0.1':r.fulfill(status=200,content_type='application/json',body=json.dumps(plain_style));return
        requests.append((r.request.method,r.request.url))
        if parsed.path=='/data/area_score.json':r.fulfill(content_type='application/json',body=json.dumps(data))
        else:r.continue_()
    context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');context.route('**/*',route)
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
    page.goto(url+'/#/?v='+quote(json.dumps(view)),wait_until='networkidle')
    expect(page.get_by_test_id('map')).to_have_attribute('data-map-ready','true')
    tabs=page.get_by_role('navigation',name='Area tools tabs');tabs.get_by_role('button',name='Score',exact=True).click()
    panel=page.get_by_role('region',name='Good place to live',exact=True)
    expect(panel).to_be_visible()
    assert [node.input_value() for node in panel.get_by_role('slider').all()]==['3','3','3','2','2','1']
    safety=panel.get_by_role('slider',name='Safety',exact=True);safety.focus();safety.press('End');expect(safety).to_have_value('5')
    mode=panel.get_by_role('checkbox',name='Colour by score');mode.check();expect(mode).to_be_checked()
    expect(panel.get_by_text('Test data',exact=True)).to_be_visible()
    expect(panel.get_by_text('Lighter fill: partial',exact=False)).to_be_attached()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(artifacts/f'score-panel-{width}x{height}.png'))
    page.reload(wait_until='networkidle');tabs.get_by_role('button',name='Score',exact=True).click()
    expect(safety).to_have_value('5');expect(mode).to_be_checked()
    shared=page.url;shared_score=json.loads(unquote(shared.split('v=',1)[1]))['score']
    assert shared_score=={'weights':[5,3,3,2,2,1],'colour':True}
    # Turning on a People layer changes no score settings or score data.
    people=next(l for l in registry['layers'] if l['demographic'] and l['data_url'])
    tabs.get_by_role('button',name='Layers',exact=True).click();row=page.locator(f'[data-layer-id="{people["id"]}"]')
    group=row.locator('xpath=ancestor::details[1]')
    if group.get_attribute('open') is None:group.locator('summary').click()
    row.get_by_role('checkbox').check()
    assert json.loads(unquote(page.url.split('v=',1)[1]))['score']==shared_score
    tabs.get_by_role('button',name='Score',exact=True).click()
    tabs.get_by_role('button',name='Score',exact=True).click()  # fold the tools to inspect the map
    node=page.get_by_test_id('map');box=node.bounding_box()
    inset=page.get_by_role('complementary',name='Area tools').bounding_box()['height']+16 if width<760 else 0
    page.wait_for_timeout(600)
    node.click(position={'x':box['width']/2,'y':(box['height']-inset)/2})
    popup=page.get_by_test_id('map-inspection');expect(popup).to_be_visible()
    expect(popup.get_by_role('heading',name='Good place to live: 59 / 100 (your weights)',exact=True)).to_be_visible()
    popup.get_by_text('Score breakdown',exact=True).click()
    expect(popup).to_contain_text('Agency-wide rate')
    expect(popup).to_contain_text('Part I reports per 1,000 residents')
    expect(popup).to_contain_text('2025-12-31')
    expect(popup).to_contain_text('Weight 5')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(artifacts/f'score-popup-{width}x{height}.png'))
    fresh=browser.new_context(viewport={'width':width,'height':height});fresh.route('**/*',route)
    other=fresh.new_page();other.goto(shared,wait_until='networkidle')
    other.get_by_role('navigation',name='Area tools tabs').get_by_role('button',name='Score',exact=True).click()
    expect(other.get_by_role('slider',name='Safety',exact=True)).to_have_value('5')
    expect(other.get_by_role('checkbox',name='Colour by score')).to_be_checked()
    assert all(method=='GET' for method,_ in requests) and not errors,errors
    fresh.close();context.close()
    print(f'PASS scores {width}×{height}: defaults/sliders, browser reload, fresh shared weights, score mode/legend, popup sources, People independence, no overflow')
