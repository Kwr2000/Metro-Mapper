"""Local fixture-only browser checks. No external requests or data-source access."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import quote, urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect
import homes as home_checks

WEB = Path(__file__).resolve().parents[1]
DIST = WEB / "dist"
ARTIFACTS = Path(__file__).parent / "artifacts"
URL = "http://127.0.0.1:4173"
PLAIN_STYLE = {"version": 8, "sources": {}, "layers": [{"id": "background", "type": "background", "paint": {"background-color": "#eef0f2"}}]}


def read_data(layer):
    return json.loads((DIST / layer["data_url"]).read_text())["features"]


def identity(feature):
    return str(feature["properties"].get("geoid", feature.get("id")))


def tab(page, name):
    button = page.get_by_role("navigation", name="Area tools tabs").get_by_role("button", name=re.compile("^" + name))
    if button.get_attribute("aria-pressed") != "true":
        button.click()


def no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal page overflow"


def smoke(browser, registry, base, chosen_filter, width, height):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    # External calls are fulfilled locally before any request reaches the network.
    context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else
                  route.fulfill(status=200, content_type="application/json", body=json.dumps(PLAIN_STYLE)))
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    areas = read_data(base)
    coordinates = areas[0]["geometry"]["coordinates"]
    while isinstance(coordinates[0][0], list):
        coordinates = coordinates[0]
    xs, ys = [p[0] for p in coordinates], [p[1] for p in coordinates]
    view = {"version": 1, "camera": {"center": [(min(xs)+max(xs))/2, (min(ys)+max(ys))/2], "zoom": 12},
            "visible": [base["id"]], "variants": {}, "filters": {}, "compare": []}
    page.goto(URL + "/#/?v=" + quote(json.dumps(view)), wait_until="networkidle")
    expect(page.get_by_test_id("map")).to_have_attribute("data-map-ready", "true")
    expect(page.get_by_test_id("match-count")).to_contain_text(f"of {len(areas):,} areas match")
    # A real map click offers the required actions, independently of the area picker.
    if width < 760:
        page.get_by_role("navigation", name="Area tools tabs").get_by_role("button", name="Layers", exact=True).click()
    inset = page.get_by_role("complementary",name="Area tools").bounding_box()["height"] + 16 if width < 760 else 0
    page.get_by_test_id("map").click(position={"x": page.get_by_test_id("map").bounding_box()["width"] / 2,
                                              "y": (page.get_by_test_id("map").bounding_box()["height"] - inset) / 2})
    expect(page.get_by_role("region", name="Selected area")).to_be_visible()
    page.get_by_role("button", name="Close selected area").click()
    page.get_by_role("button", name="Close popup").click()
    expect(page.get_by_test_id("map-inspection")).to_have_count(0)  # the × really closes it
    tab(page,"Layers")
    # A new layer is addressed only through registry metadata, never a fixed id.
    page.locator(f'[data-layer-id="{chosen_filter["id"]}"] input[type=checkbox]').check()
    tab(page,"Filters")
    row = page.locator(f'[data-filter-id="{chosen_filter["id"]}"]')
    if chosen_filter["demographic"]:
        row.locator("xpath=..").locator("summary").click()
    row.locator('input[type="checkbox"]').check()
    maximum = row.locator('input[type="number"]').nth(1)
    expect(maximum).to_be_visible()
    values = [f["properties"].get(chosen_filter["popup"][0]["field"]) for f in read_data(chosen_filter)]
    values = [v for v in values if isinstance(v,(int,float))]
    limit = (min(values)+max(values))/2
    if chosen_filter["popup"][0]["format"] == "percent":
        limit *= 100
    maximum.fill(str(limit))
    page.wait_for_function("total => { const s=document.querySelector('[data-testid=match-count]').textContent; return /areas match/.test(s) && Number(s.split(' of ')[0].replaceAll(',','')) < total; }", arg=len(areas))
    # Centre the evidence image on an actual match, rather than an excluded area.
    raw_limit = limit / 100 if chosen_filter["popup"][0]["format"] == "percent" else limit
    eligible = {identity(f) for f in read_data(chosen_filter) if isinstance(f["properties"].get(chosen_filter["popup"][0]["field"]),(int,float))
                and f["properties"][chosen_filter["popup"][0]["field"]] <= raw_limit}
    match = next((f for f in areas if identity(f) in eligible),None)
    if match:
        coords = match["geometry"]["coordinates"]
        while isinstance(coords[0][0],list):
            coords = coords[0]
        camera = {"center": [(min(p[0] for p in coords)+max(p[0] for p in coords))/2,
                             (min(p[1] for p in coords)+max(p[1] for p in coords))/2], "zoom": 13}
        page.evaluate("""camera => { const v=JSON.parse(new URLSearchParams(location.hash.split('?')[1]).get('v')); v.camera=camera; location.hash='/?v='+encodeURIComponent(JSON.stringify(v)); }""", camera)
        page.wait_for_timeout(700)  # Wait for the application's bounded camera transition.
    no_overflow(page)
    page.screenshot(path=str(ARTIFACTS / f"filters-{width}x{height}.png"))
    tab(page,"Compare")
    for area in areas[:2]:
        page.get_by_role("combobox", name="Choose area").select_option(identity(area))
        page.get_by_role("button", name="Add selected area to compare", exact=True).click()
    page.get_by_role("button", name="Compare", exact=True).click()
    dialog = page.get_by_role("dialog", name="Area comparison")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_text("People (context only)",exact=True)).to_be_visible()
    expect(dialog.locator("th").filter(has_text=str(areas[0]["properties"]["name"])).first).to_be_attached()
    if width > 760:
        expect(dialog.get_by_role("columnheader", name="Compared with", exact=True).first).to_be_visible()
    else:
        comparison = dialog.locator('.comparison-benchmarks[data-area="Compared with"]').filter(has_text="2020–2024").first
        expect(comparison).to_be_visible()
        assert comparison.evaluate("el => getComputedStyle(el, '::before').content") == '"Compared with"'
    expect(dialog.locator(".comparison-benchmarks").filter(has_text="2020–2024").first).to_be_attached()
    expect(dialog.locator(".comparison-benchmarks").filter(has_text="U.S. Census Bureau").first).to_be_attached()
    no_overflow(page)
    page.screenshot(path=str(ARTIFACTS / f"compare-{width}x{height}.png"))
    page.get_by_role("button", name="Close comparison").click()
    page.get_by_role("button", name="Save selected area", exact=True).click()
    tab(page,"Shortlist")
    note = page.get_by_role("textbox", name=re.compile("Private note for"))
    note.fill("PRIVATE smoke note")
    assert "PRIVATE" not in page.url
    shared_url = page.url
    page.reload(wait_until="networkidle")
    tab(page,"Shortlist")
    expect(page.get_by_role("textbox", name=re.compile("Private note for"))).to_have_value("PRIVATE smoke note")
    tab(page,"Compare")
    expect(page.get_by_role("region", name="Compare tray")).to_contain_text("(2/4)")
    fresh = browser.new_context(viewport={"width": width,"height": height})
    fresh.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else
                route.fulfill(status=200, content_type="application/json", body=json.dumps(PLAIN_STYLE)))
    other = fresh.new_page()
    other.goto(shared_url, wait_until="networkidle")
    tab(other,"Shortlist")
    expect(other.get_by_text("No saved areas.",exact=False)).to_be_visible()
    tab(other,"Compare")
    expect(other.get_by_role("region", name="Compare tray")).to_contain_text("(2/4)")
    no_overflow(page)
    assert not errors, errors
    fresh.close()
    context.close()
    print(f"PASS {width}×{height}: filter, map click, compare, private shortlist, reload, shared view, no overflow")


def colour_smoke(browser, registry, width, height):
    benchmarks = json.loads((DIST / "benchmarks.json").read_text())
    assert benchmarks["test_data"], "Comparison smoke requires synthetic benchmarks"
    eligible = [l for l in registry["layers"] if l.get("compare") and l.get("data_url")
                and benchmarks.get(l["source"], {}).get(l["compare"].get("benchmark_field") or l["compare"]["field"])]
    directional = next(l for l in eligible if l["compare"]["direction"] == "lower_is_better"
                       and l["geometry"] == "polygon" and any(r["geography"] == "texas" for r in
                       benchmarks[l["source"]][l["compare"].get("benchmark_field") or l["compare"]["field"]]))
    neutral = next(l for l in eligible if l["demographic"] and l["compare"]["unit"] == "pp")
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else
                  route.fulfill(status=200, content_type="application/json", body=json.dumps(PLAIN_STYLE)))
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    for layer, name in [(directional, "directional"), (neutral, "neutral")]:
        field = layer["compare"]["field"]
        feature = next(f for f in read_data(layer) if isinstance(f["properties"].get(field), (int, float)))
        coords = feature["geometry"]["coordinates"]
        while isinstance(coords[0][0], list):
            coords = coords[0]
        view = {"version": 1, "camera": {"center": [(min(p[0] for p in coords)+max(p[0] for p in coords))/2,
                                                      (min(p[1] for p in coords)+max(p[1] for p in coords))/2], "zoom": 12},
                "visible": [layer["id"]], "variants": {}, "filters": {}, "compare": [], "colour": {}}
        page.goto(URL + "/#/?v=" + quote(json.dumps(view)), wait_until="networkidle")
        expect(page.get_by_test_id("map")).to_have_attribute("data-map-ready", "true")
        tab(page, "Layers")
        panel_row = page.locator(f'[data-layer-id="{layer["id"]}"]')
        group = panel_row.locator("xpath=ancestor::details[1]")
        if group.get_attribute("open") is None:
            group.locator("summary").click()
        control = panel_row.get_by_role("group", name=layer["title"] + " colour")
        control.scroll_into_view_if_needed()
        expect(control.get_by_role("button", name="Values", exact=True)).to_have_attribute("aria-pressed", "true")
        no_overflow(page)
        page.screenshot(path=str(ARTIFACTS / f"colour-{name}-values-{width}x{height}.png"))
        control.get_by_role("button", name="Compared with", exact=True).click()
        if name == "directional":
            control.get_by_role("combobox").select_option("texas")
        expect(control.get_by_role("button", name="Compared with", exact=True)).to_have_attribute("aria-pressed", "true")
        expect(panel_row.locator(".comparison-header")).to_contain_text("Test data · Compared with")
        expect(panel_row.get_by_role("list", name=layer["title"] + " legend")).to_contain_text("About the same")
        legend = panel_row.get_by_role("list", name=layer["title"] + " legend").inner_text()
        if name == "neutral":
            assert "better" not in legend and "worse" not in legend
            assert "within margin of error" in legend
        else:
            assert "(better)" in legend and "(worse)" in legend
        no_overflow(page)
        page.wait_for_timeout(300)  # Let the map finish its paint transition for the evidence image.
        page.screenshot(path=str(ARTIFACTS / f"colour-{name}-compared-{width}x{height}.png"))
        chosen = control.get_by_role("combobox").input_value()
        page.reload(wait_until="networkidle")
        tab(page, "Layers")
        group = panel_row.locator("xpath=ancestor::details[1]")
        if group.get_attribute("open") is None:
            group.locator("summary").click()
        expect(control.get_by_role("button", name="Compared with", exact=True)).to_have_attribute("aria-pressed", "true")
        expect(control.get_by_role("combobox")).to_have_value(chosen)
        control.get_by_role("button", name="Values", exact=True).click()
        expect(panel_row.locator(".comparison-header")).to_have_count(0)
        assert not errors, errors
    context.close()
    print(f"PASS {width}×{height}: directional/neutral Values and Compared with, legends, shared mode/reload, no map errors or overflow")


def main():
    home_checks.prepare(WEB)
    registry = json.loads((DIST / "registry.json").read_text())
    assert all(l["freshness"] == "fixture_only" for l in registry["layers"] if l["publish"] != "none"), "Run make test first: smoke requires fixture data"
    base = next(l for l in registry["layers"] if l["join"] == "block_group" and any(p["field"] == "name" for p in l["popup"]))
    candidates = [l for l in registry["layers"] if l["join"] == "block_group" and l["popup"] and l["popup"][0]["format"] in {"number","percent","currency"}]
    chosen = next(l for l in candidates if len({f["properties"].get(l["popup"][0]["field"]) for f in read_data(l)
                                               if isinstance(f["properties"].get(l["popup"][0]["field"]),(int,float))}) > 1)
    ARTIFACTS.mkdir(exist_ok=True)
    with (ARTIFACTS / "preview.log").open("w") as log:
        server = subprocess.Popen(["node","node_modules/vite/bin/vite.js","preview","--host","127.0.0.1","--port","4173","--strictPort"],cwd=WEB,stdout=log,stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Preview failed; see artifacts/preview.log")
                try:
                    with urlopen(URL,timeout=1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("Preview did not start")
            with sync_playwright() as p:
                executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
                browser = p.chromium.launch(headless=True, executable_path=executable,
                    args=["--no-sandbox","--enable-unsafe-swiftshader","--use-gl=angle","--use-angle=swiftshader"])
                for width,height in [(1440,900),(390,844)]:
                    smoke(browser,registry,base,chosen,width,height)
                    colour_smoke(browser,registry,width,height)
                    home_checks.smoke(browser,registry,width,height,URL,DIST,ARTIFACTS,PLAIN_STYLE)
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
