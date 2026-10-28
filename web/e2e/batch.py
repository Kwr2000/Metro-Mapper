"""Owner-file checks using 25 synthetic Redfin-shaped fixture listings only."""
import csv
import io
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect
from homes import BANNED
from mm.values import value_range


def smoke(browser, width, height, url, dist, artifacts, plain_style):
    fixture = Path(__file__).parent / 'fixtures/batch-25.csv'
    imported = list(csv.DictReader(io.StringIO(fixture.read_text(encoding='utf-8-sig'))))[:25]
    homes = []
    for file in sorted((dist / 'data/homes/addr').glob('*.json')):
        doc = json.loads(file.read_text())
        assert doc['test_data']
        homes.extend(dict(zip(doc['fields'], row)) for row in doc['rows'])
    homes = [h for h in homes if h['number'] and h['street_key']]
    targets = [homes[i % len(homes)] for i in range(25)]
    meta = json.loads((dist / 'data/homes/meta.json').read_text())
    assert meta['test_data']
    hood_rows = {(h['county'], h['hood_cd'], h['category'] if h['category'] in {'single_family', 'condo'} else 'other') for h in homes}
    hoods = {'v': 1, 'test_data': True, 'rows': [dict(county=c, hood_cd=h, category=k,
             n=20, p10=100, p25=150, p50=200, p75=300, p90=400) for c, h, k in sorted(hood_rows)]}
    state = {'processing': False, 'published': True}
    violations, requests, errors = [], [], []

    def route(r):
        req = r.request
        parsed = urlparse(req.url)
        own = parsed.scheme == 'http' and parsed.netloc == urlparse(url).netloc
        if state['processing']:
            requests.append(req.url)
            if not own or not parsed.path.startswith('/data/') or parsed.query or req.method != 'GET' or req.post_data:
                violations.append((req.method, req.url))
                r.abort()
                return
        if not own:
            r.fulfill(content_type='application/json', body=json.dumps(plain_style))
        elif parsed.path == '/data/homes/meta.json':
            document = json.loads(json.dumps(meta))
            document['value_range']['published'] = state['published']
            r.fulfill(content_type='application/json', body=json.dumps(document))
        elif parsed.path == '/data/homes/hoods.json':
            r.fulfill(content_type='application/json', body=json.dumps(hoods))
        else:
            r.continue_()

    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce', accept_downloads=True)
    context.route('**/*', route)
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
    # Visit the map first: its tile/style machinery must stop before file processing.
    page.goto(url + '/#/', wait_until='networkidle')
    expect(page.get_by_test_id('map')).to_have_attribute('data-map-ready', 'true')
    map_view = page.evaluate("JSON.parse(new URLSearchParams(location.hash.split('?')[1]).get('v'))")
    page.get_by_role('navigation', name='Pages').get_by_role('link', name='Check a home', exact=True).click()
    page.get_by_role('link', name='Check many listings', exact=True).click()
    expect(page.get_by_test_id('map')).to_have_count(0)
    expect(page.get_by_text('Your file stays in this browser. Nothing is uploaded or saved unless you choose Save.', exact=True)).to_be_visible()
    page.wait_for_load_state('networkidle')
    state['processing'] = True
    page.get_by_label('Choose Redfin CSV').set_input_files(fixture)
    expect(page.get_by_role('heading', name='Listing results', exact=True)).to_be_visible()
    for i, home in enumerate(targets):
        picker = page.get_by_role('combobox', name=f'Choose appraisal record for listing {i+1}', exact=True)
        if picker.count():
            picker.select_option(home['id'])
            picker.locator('xpath=ancestor::li[1]').get_by_role('button', name='Use this record', exact=True).click()
    expect(page.get_by_role('status').filter(has_text='25 matched listings shown · 0 need attention')).to_be_visible()
    rows = page.locator('.batch-table tbody tr')
    expect(rows).to_have_count(25)
    def percentile(psf):
        points = [(100, 10), (150, 25), (200, 50), (300, 75), (400, 90)]
        if psf <= 100:
            return 10
        for (a, p), (b, q) in zip(points, points[1:]):
            if psf <= b:
                return p + (psf-a)/(b-a)*(q-p)
        return 90
    def order(i):
        h = targets[i]
        price = float(imported[i]['PRICE'].replace('$', '').replace(',', ''))
        vr = meta['value_range']
        ends = value_range(h['market_value'], h['id'].split(':')[0], h['range_pct'], vr['hpi']['factor'], vr['levels'])
        p = None if ends['mid'] is None else (min(price-ends['low'], 0) + max(price-ends['high'], 0))/ends['mid']*100
        pct = None if not h['living_area'] else percentile(price/h['living_area'])
        return (p is None, p or 0, pct is None, pct or 0, i)
    assert rows.evaluate_all('(els)=>els.map(e=>Number(e.dataset.listingKey))') == sorted(range(25), key=order)
    assert not violations, violations
    assert len({p for p in requests if '/addr/' in p}) <= len(meta['shards'])
    assert not page.evaluate("Object.keys(localStorage).some(k=>k.startsWith('metro-mapper:batch-list:') || k.includes('asking:'))")
    assert '741239' not in page.url
    assert 'CANARY_OWNER_FILE_PRIVATE' not in page.locator('body').inner_text()
    expect(page.get_by_text('Ignored column headers:', exact=False)).to_contain_text('PRIVATE NOTES')
    first = page.locator('tr[data-listing-key="0"]')
    expect(first).to_contain_text('More than 10% different')
    links = rows.get_by_role('link', name='Listing', exact=True)
    assert links.count() == 25
    assert all(links.nth(i).get_attribute('target') == '_blank' for i in range(25))
    assert all('id=' in href and '741239' not in href for href in rows.get_by_role('link', name='Home card', exact=True).evaluate_all('(els)=>els.map(e=>e.getAttribute("href"))'))
    # All numeric sorting is available on phones as well as in desktop headers.
    page.get_by_label('Sort by', exact=True).select_option('days')
    expect(rows.first).to_have_attribute('data-listing-key', '0')
    page.get_by_role('button', name='Ascending', exact=True).click()
    expect(rows.first).to_have_attribute('data-listing-key', '24')
    page.get_by_label('County', exact=True).select_option('Hays')
    expect(rows).to_have_count(sum(h['county'] == 'Hays' for h in targets))
    page.get_by_label('County', exact=True).select_option('')
    page.get_by_label('Category', exact=True).select_option('condo')
    expect(rows).to_have_count(sum(h['category'] == 'condo' for h in targets))
    page.get_by_label('Category', exact=True).select_option('')
    page.get_by_label('Has a range', exact=True).check()
    expect(rows).to_have_count(sum(h['range_pct'] is not None for h in targets))
    page.get_by_label('Has a range', exact=True).uncheck()
    page.get_by_label('Sort by', exact=True).select_option('default')
    page.locator('.batch-controls').evaluate("el=>el.scrollIntoView({block:'start'})")
    page.evaluate('window.scrollBy(0,-150)')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Batch page overflow'
    if width < 760:
        assert rows.first.evaluate('getComputedStyle(document.querySelector(".batch-table tbody tr")).display') == 'block'
    assert not BANNED.search(page.locator('body').inner_text())
    page.screenshot(path=str(artifacts / f'batch-{width}x{height}.png'))
    if width < 760:
        rows.first.locator('td').nth(8).evaluate("el=>el.scrollIntoView({block:'start'})")
        page.evaluate('window.scrollBy(0,-150)')
    else:
        page.locator('.batch-table-wrap').evaluate('el=>el.scrollLeft=1100')
    page.screenshot(path=str(artifacts / f'batch-comparison-{width}x{height}.png'))
    page.get_by_label('List name', exact=True).fill('Fixture list')
    page.get_by_role('button', name='Save list', exact=True).click()
    expect(page.get_by_text('List saved in this browser.', exact=True)).to_be_visible()
    stored = page.evaluate("localStorage.getItem('metro-mapper:batch-list:Fixture%20list')")
    assert '741239' in stored and 'CANARY_OWNER_FILE_PRIVATE' not in stored
    state['processing'] = False
    page.reload(wait_until='networkidle')
    expect(page.get_by_role('heading', name='Listing results', exact=True)).to_have_count(0)
    page.get_by_label('Saved lists', exact=True).select_option('Fixture list')
    state['processing'] = True
    page.get_by_role('button', name='Restore list', exact=True).click()
    expect(page.get_by_role('status').filter(has_text='25 matched listings shown · 0 need attention')).to_be_visible()
    expect(rows).to_have_count(25)
    with page.expect_download() as download:
        page.get_by_role('button', name='Export table CSV', exact=True).click()
    exported = artifacts / f'batch-export-{width}.csv'
    download.value.save_as(exported)
    text = exported.read_text(encoding='utf-8-sig')
    output = list(csv.DictReader(io.StringIO(text)))
    assert len(output) == 25 and 'Range low' in output[0]
    assert sorted(r['Home id'] for r in output) == sorted(h['id'] for h in targets)
    assert 'CANARY_OWNER_FILE_PRIVATE' not in text
    assert all(r['Test data'] == 'Test data' for r in output)
    # Publication is authoritative even when restored inputs were saved with ranges on.
    state.update(processing=False, published=False)
    page.reload(wait_until='networkidle')
    page.get_by_label('Saved lists', exact=True).select_option('Fixture list')
    state['processing'] = True
    page.get_by_role('button', name='Restore list', exact=True).click()
    expect(rows).to_have_count(25)
    expect(page.get_by_role('columnheader', name='Position', exact=True)).to_have_count(0)
    expect(page.get_by_role('columnheader', name='Appraisal-based value range', exact=True)).to_have_count(0)
    expect(page.get_by_role('columnheader', name='Range width / flags', exact=True)).to_have_count(0)
    expect(page.get_by_text('The value range is being validated and will appear here.', exact=False)).to_be_visible()
    # The percentile still supplies the batch spec's non-range default order.
    cells = rows.locator('td:nth-child(11)').all_text_contents()
    percentiles = [int(''.join(c for c in s if c.isdigit())) if any(c.isdigit() for c in s) else None for s in cells]
    assert percentiles == sorted(percentiles, key=lambda n: (n is None, n or 0))
    page.get_by_role('button', name='Clear all listings', exact=True).click()
    expect(rows).to_have_count(0)
    assert not page.evaluate("Object.keys(localStorage).some(k=>k.startsWith('metro-mapper:batch-list:'))")
    assert not violations, violations
    assert not errors, errors
    assert not any('741239' in r or 'CANARY_OWNER_FILE_PRIVATE' in r or 'example.invalid' in r for r in requests)
    # The full 350-row limit also yields during lookup and incremental rendering.
    unique = next(h for h in homes if h['id'] == '48453:123')
    query = f"{unique['number']} {unique['street_key']}, TX {unique['zip']} — $500,000"
    page.get_by_role('textbox', name='Addresses and asking prices').fill('\n'.join([query]*350))
    page.evaluate("""() => { window.batchLongTasks=[]; window.batchObserver=new PerformanceObserver(list=>window.batchLongTasks.push(...list.getEntries().map(e=>e.duration))); window.batchObserver.observe({type:'longtask'}); window.batchStarted=performance.now(); }""")
    page.get_by_role('button', name='Check pasted listings', exact=True).click()
    expect(rows).to_have_count(350, timeout=15000)
    page.wait_for_timeout(100)  # Let the final long-task observer entry be delivered.
    elapsed, longest = page.evaluate("[performance.now()-window.batchStarted,Math.max(0,...window.batchLongTasks)]")
    page.evaluate('window.batchObserver.disconnect()')
    assert elapsed < 10000, f'350 rows took {elapsed:.0f}ms'
    assert longest < 200, f'Long main-thread task: {longest:.0f}ms'
    assert not violations, violations
    page.get_by_role('button', name='Clear all listings', exact=True).click()
    state['processing'] = False
    page.get_by_role('navigation', name='Pages').get_by_role('link', name='Map', exact=True).click()
    expect(page.get_by_test_id('map')).to_have_attribute('data-map-ready', 'true')
    returned = page.evaluate("JSON.parse(new URLSearchParams(location.hash.split('?')[1]).get('v'))")
    assert all(returned.get(k) == map_view.get(k) for k in ['visible', 'filters', 'compare', 'colour', 'score'])
    context.close()
    print(f'PASS {width}×{height}: 25-row CSV, explicit matches, sorts/filters, save/restore/clear, export, publication gate, own-data requests only; 350 rows {elapsed:.0f}ms, longest task {longest:.0f}ms')
