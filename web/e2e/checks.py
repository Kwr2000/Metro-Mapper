"""Synthetic per-home facts in cards and batch, at both supported viewports."""
import json
from urllib.parse import urlparse,quote
from pathlib import Path
from playwright.sync_api import expect
from homes import read_homes,BANNED


def smoke(browser,width,height,url,dist,artifacts):
    fixture=json.loads((Path(__file__).resolve().parents[2]/'pipeline/tests/fixtures/home_checks.json').read_text())
    homes=read_homes(dist);placed=next(h for h in homes if h['placed']=='parcel');unplaced=next(h for h in homes if h['placed'] is None and h['year_built'])
    enc=','.join(c['encoded'] for c in fixture['cases'] if c['encoded'].split(':')[0] not in ('flood02','pre1978','major_road'));requests=[];errors=[]
    def route(r):
        req=r.request;parsed=urlparse(req.url);requests.append(req.url)
        assert parsed.hostname=='127.0.0.1' and req.method=='GET' and not req.post_data
        path=parsed.path.lstrip('/')
        if path=='data/homes/meta.json':
            doc=json.loads((dist/path).read_text());doc['checks']=fixture['meta'];r.fulfill(content_type='application/json',body=json.dumps(doc))
        elif path.startswith('data/homes/addr/'):
            doc=json.loads((dist/path).read_text());fields=doc['fields']
            for row in doc['rows']:
                row[fields.index('checks')]=enc
                row[fields.index('year_built')]=1985
            r.fulfill(content_type='application/json',body=json.dumps(doc))
        else:r.continue_()
    context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');context.route('**/*',route)
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url+'/#/home?id='+quote(placed['id']),wait_until='networkidle')
    # Browser chrome may refresh its icon on a hash navigation. Inline it before the
    # strict import boundary so no unrelated favicon request can overlap processing.
    page.evaluate("""() => {document.querySelector('link[rel="icon"]').href='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"></svg>';}""")
    card=page.get_by_role('article',name='Home details');facts=card.get_by_role('region',name='Things to check')
    expect(facts.get_by_role('heading',name='Things to check',exact=True)).to_be_visible()
    expect(facts).to_contain_text('About 90 m from a highway (I 35). Traffic noise is likely.')
    expect(facts).to_contain_text('NFHL versions: 3.0');expect(facts).to_contain_text('OpenStreetMap contributors');expect(facts).to_contain_text('Test data')
    facts.get_by_text('About 90 m from a highway (I 35). Traffic noise is likely.',exact=True).scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(artifacts/f'checks-card-{width}x{height}.png'))
    # Same facts on the batch row; its import still makes only own data/ requests.
    page.get_by_role('link',name='Check many listings',exact=True).click();page.wait_for_load_state('networkidle');before=len(requests)
    def address(h):return f"{h['number']} {h['street_key']}"+(f" #{h['unit']}" if h['unit'] else '')+f" TX {h['zip']}"
    page.get_by_role('textbox',name='Addresses and asking prices').fill(address(placed)+' — $560000')
    page.get_by_role('button',name='Check pasted listings',exact=True).click();rows=page.locator('.batch-table tbody tr');expect(rows).to_have_count(1)
    expect(page.locator('.batch-table thead')).to_contain_text('Things to check')
    if width<760:expect(rows.first.get_by_text('Things to check',exact=True)).to_be_visible()
    detail=rows.first.locator('.batch-checks');detail.locator('summary').click();expect(detail).to_contain_text('About 90 m from a highway')
    expect(detail).to_contain_text('Built in 1985');expect(detail).to_contain_text('FEMA National Flood Hazard Layer')
    detail.scroll_into_view_if_needed()
    if width>=760:page.locator('.batch-table-wrap').evaluate('el=>{el.scrollLeft=el.scrollWidth;}')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(artifacts/f'checks-batch-{width}x{height}.png'))
    outside=[r for r in requests[before:] if not urlparse(r).path.startswith('/data/') or urlparse(r).query]
    assert not outside,outside
    page.goto(url+'/#/home?id='+quote(unplaced['id']),wait_until='networkidle');facts=page.get_by_role('region',name='Things to check')
    expect(facts).to_contain_text('Location checks not available (no map point)');expect(facts).not_to_contain_text('Traffic noise')
    expect(facts).to_contain_text('Built in 1985');assert not BANNED.search(page.locator('body').inner_text()) and not errors,errors
    context.close();print(f'PASS checks {width}×{height}: sourced facts, card/batch disclosure, unplaced home, no overflow, prohibited copy or external requests')
