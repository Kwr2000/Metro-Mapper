import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Color, createExpression } from "@maplibre/maplibre-gl-style-spec";
import { areaClassLabel, chooseColour, colourBenchmarks, comparisonClass, comparisonHeader, comparisonLabels,
  comparisonLegend, comparisonPaint, DIRECTIONAL, MISSING_COLOUR, NEUTRAL, selectedBenchmark } from "../colour";
import { LayerPanel } from "../LayerPanel";
vi.mock("maplibre-gl", () => ({ default: {} }));
import { featureHtml } from "../MapView";
import { cleanView, encodeView, readView, registryView, type ViewState } from "../view-state";
import { type Benchmark, type Benchmarks } from "../benchmarks";
import type { CompiledLayer } from "../registry";
import { layer, registry } from "./workspace-fixtures";

const measure = layer("synthetic_measure", { compare: { field: "measure", benchmark_field: null, method: "ratio",
  breaks: [.67, .9, 1.1, 1.5], direction: "lower_is_better", unit: "" },
  style: { type: "fill", paint: { "fill-opacity": .55, "fill-color": "#abcdef" }, layout: {}, minzoom: null, maxzoom: null } });
const row: Benchmark = { field: "measure", geography: "texas", label: "Texas", value: 10, moe: null, period: "2025", source: "Synthetic source", note: null };
const data: Benchmarks = { test_data: true, synthetic: { measure: [row] } };
const difference = layer("synthetic_share", { demographic: true,
  popup: [{ ...measure.popup[0], format: "percent", moe_field: "measure_moe" }],
  compare: { ...measure.compare!, method: "difference", breaks: [-.1,-.03,.03,.1], direction: "neutral", unit: "pp" } });
function evaluated(l = measure, r = row, props: Record<string, unknown> = {}) {
  const result = createExpression(comparisonPaint(l, r), { type: "color", "property-type": "data-driven", transition: false, overridable: false });
  if (result.result === "error") throw new Error(JSON.stringify(result.value));
  return result.value.evaluate({zoom:0}, { type: 3, properties: props });
}
afterEach(cleanup);

it("uses valid MapLibre ratio paint with lower-inclusive boundaries and never mutates Values paint", () => {
  const original = structuredClone(measure.style);
  for (const [value, index] of [[0,0],[6.7,1],[9,2],[11,3],[15,4],[50,4]]) {
    expect(comparisonClass(measure, { measure: value }, row)).toBe(index);
    expect(evaluated(measure,row,{measure:value})).toEqual(Color.parse(DIRECTIONAL[index]));
  }
  expect(measure.style).toEqual(original);
});
it("missing is grey, zero area is real, ratio zero benchmark is grey, difference zero benchmark is usable", () => {
  for (const value of [null, undefined, "10"]) {
    expect(comparisonClass(measure,{measure:value},row)).toBeNull();
    expect(evaluated(measure,row,{measure:value})).toEqual(Color.parse(MISSING_COLOUR));
  }
  expect(evaluated(measure,row,{measure:0})).toEqual(Color.parse(DIRECTIONAL[0]));
  expect(evaluated(measure,{...row,value:0},{measure:4})).toEqual(Color.parse(MISSING_COLOUR));
  expect(comparisonClass(measure,{measure:4},{...row,value:0})).toBeNull();
  expect(evaluated(difference,{...row,value:0},{measure:0})).toEqual(Color.parse(NEUTRAL[2]));
});
it("difference paint and popup classification agree, including MOE straddling, exact inclusion and null MOE", () => {
  const r = { ...row, value: .5 };
  for (const [value, index] of [[.2,0],[.4,1],[.48,2],[.54,3],[.7,4]]) {
    expect(comparisonClass(difference,{measure:value},r)).toBe(index);
    expect(evaluated(difference,r,{measure:value})).toEqual(Color.parse(NEUTRAL[index]));
  }
  for (const moe of [.3,.5]) {
    expect(comparisonClass(difference,{measure:.2,measure_moe:moe},r)).toBe(2);
    expect(evaluated(difference,r,{measure:.2,measure_moe:moe})).toEqual(Color.parse(NEUTRAL[2]));
    expect(areaClassLabel(difference,{measure:.2,measure_moe:moe},r)).toBe("About the same (within margin of error)");
  }
  expect(evaluated(difference,r,{measure:.2,measure_moe:null})).toEqual(Color.parse(NEUTRAL[0]));
  expect(comparisonClass(difference,{measure:.2,measure_moe:null},r)).toBe(0);
});
it("labels every method/direction, reverses only directional colours and uses percentage points", () => {
  expect(comparisonLabels(measure,row)).toEqual(["Under 0.67× Texas (better)", "0.67–0.9× (better)",
    "About the same as Texas (0.9–1.1×)", "1.1–1.5× (worse)", "Over 1.5× Texas (worse)"]);
  const higher = { ...measure, compare: { ...measure.compare!, direction: "higher_is_better" as const } };
  expect(comparisonLegend(higher,row)[0].color).toBe(DIRECTIONAL[4]);
  expect(comparisonLabels(higher,row)[4]).toContain("(better)");
  const neutral = { ...measure, compare: { ...measure.compare!, direction: "neutral" as const } };
  expect(comparisonLabels(neutral,row).join()).not.toMatch(/better|worse/);
  expect(comparisonLegend(neutral,row).slice(0,5).map((r) => r.color)).toEqual(NEUTRAL);
  expect(comparisonLabels(difference,row)).toEqual(["More than 10 pp below Texas", "3–10 pp below",
    "About the same as Texas (within 3 pp) · About the same (within margin of error)", "3–10 pp above", "More than 10 pp above Texas"]);
  const score: CompiledLayer = { ...measure, compare: { ...measure.compare!, method: "difference" as const, breaks: [-10,-3,3,10], unit: "points", direction: "higher_is_better" as const } };
  expect(comparisonLabels(score,row)[0]).toBe("More than 10 points below Texas (worse)");
  expect(comparisonLabels(score,row)[4]).toBe("More than 10 points above Texas (better)");
});
it("election margin labels are neutral and refer to shifts in party lead", () => {
  const margin: CompiledLayer = { ...difference, compare: { ...difference.compare!, field: "synthetic_margin", breaks: [-.2,-.05,.05,.2], unit: "pts" },
    popup: [{ ...difference.popup[0], field: "synthetic_margin", moe_field: null }] };
  expect(comparisonLabels(margin,row)).toEqual(["Over 20 pts more Democratic than Texas", "5–20 pts more Democratic",
    "About the same as Texas (within 5 pts)", "5–20 pts more Republican", "Over 20 pts more Republican than Texas"]);
  expect(comparisonLegend(margin,row).slice(0,5).map((r) => r.color)).toEqual(NEUTRAL);
});
it("only offers available source+field benchmarks in popup priority order and uses explicit field mappings", () => {
  const geographies = ["unknown_z","us","texas_cities_100k","texas","austin_city","unknown_a","peer_cities","austin_pd_area"];
  const available: Benchmarks = { test_data: false, synthetic: { scoped_measure: geographies.map((geography) => ({...row, geography})) } };
  const mapped = { ...measure, compare: { ...measure.compare!, benchmark_field: "scoped_measure" } };
  expect(colourBenchmarks(mapped,available).map((r) => r.geography)).toEqual(["austin_pd_area","austin_city","texas","us","peer_cities","texas_cities_100k","unknown_z","unknown_a"]);
  expect(colourBenchmarks(measure,available)).toEqual([]);
  expect(colourBenchmarks({...mapped,source:"absent"},available)).toEqual([]);
  expect(selectedBenchmark(measure,{[measure.id]:"unknown"},data)).toBeUndefined();
});
it("header keeps source/period, format, capped display, units and fixture prefix", () => {
  expect(comparisonHeader(measure,row,data)).toBe("Test data · Compared with Texas: 10 (2025, Synthetic source)");
  const l = { ...measure, popup: [{...measure.popup[0], label:"Rate per 1,000 residents"}] };
  expect(comparisonHeader(l,row,{test_data:false})).toBe("Compared with Texas: 10 per 1,000 residents (2025, Synthetic source)");
  expect(comparisonHeader(difference,{...row,value:.4},data)).toContain("40.0%");
  expect(comparisonHeader(measure,{...row,display:"250,000 or more"},data)).toContain("250,000 or more");
});
it("panel starts in Values, enters first comparison, selects geography and restores Values", () => {
  const onColour = vi.fn();
  const reg = registry([measure]);
  const props = {registry:reg,visible:new Set([measure.id]),onToggle:vi.fn(),onSwitchVariant:vi.fn(),choices:{},onColour,benchmarks:data};
  const { rerender } = render(<LayerPanel {...props} />);
  expect(screen.getByRole("button",{name:"Values"}).getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(screen.getByRole("button",{name:"Compared with"}));
  expect(onColour).toHaveBeenLastCalledWith(measure,"texas");
  rerender(<LayerPanel {...props} colour={{[measure.id]:"texas"}} />);
  expect(screen.getByText(/^Test data · Compared with Texas/)).toBeDefined();
  expect(within(screen.getByRole("list",{name:measure.title+" legend"})).getByText("Not available")).toBeDefined();
  fireEvent.change(screen.getByRole("combobox"),{target:{value:"texas"}});
  expect(onColour).toHaveBeenLastCalledWith(measure,"texas");
  fireEvent.click(screen.getByRole("button",{name:"Values"}));
  expect(onColour).toHaveBeenLastCalledWith(measure,"");
  rerender(<LayerPanel {...props} colour={{[measure.id]:"unknown"}} />);
  expect(screen.getByRole("button",{name:"Values"}).getAttribute("aria-pressed")).toBe("true");
  rerender(<LayerPanel {...props} benchmarks={{test_data:false}} />);
  expect(screen.queryByRole("button",{name:"Compared with"})).toBeNull();
});
it("popup keeps its existing Compared with line and adds an escaped class only under the colour row", () => {
  const html = featureHtml(measure,{measure:12},measure.popup,data,"texas");
  expect(html).toContain("Compared with: Test data · Texas 10");
  expect(html).toContain("Higher than Texas");
  expect(featureHtml(measure,{measure:12},measure.popup,data)).not.toContain("comparison-class");
  const unsafe = {...row,label:'<img src=x onerror=bad()>'};
  const host = document.createElement("div");
  host.innerHTML = featureHtml(measure,{measure:12},measure.popup,{test_data:false,synthetic:{measure:[unsafe]}},"texas");
  expect(host.querySelector("img")).toBeNull();
});
it("view state roundtrips, rejects bad ids, caps entries, discards unknowns, and families share a choice", () => {
  const sibling = {...measure,id:"synthetic_tract",variant:{family:"measure_family",key:"tract",label:"Tract"}};
  const first = {...measure,variant:{family:"measure_family",key:"bg",label:"Block group"}};
  const reg = registry([first,sibling]);
  const colour = chooseColour(reg,{},first,"texas");
  expect(colour).toEqual({[first.id]:"texas",[sibling.id]:"texas"});
  expect(chooseColour(reg,colour,sibling,"")).toEqual({});
  const view: ViewState = {camera:null,visible:[first.id],variants:{},filters:{},compare:[],colour};
  expect(readView(encodeView(view))).toEqual(view);
  expect(registryView(view,reg,data).colour).toEqual(colour);
  expect(registryView({...view,colour:{unknown:"texas",[first.id]:"absent"}},reg,data).colour).toEqual({});
  expect(cleanView({...view,colour:{"bad-id":"texas",valid:"bad/geo",other:42}})?.colour).toEqual({});
  const entries = Object.fromEntries(Array.from({length:110},(_,i)=>[`layer_${i}`,"texas"]));
  expect(Object.keys(cleanView({...view,colour:entries})!.colour)).toHaveLength(100);
  const legacy = {...view} as Partial<ViewState>; delete legacy.colour;
  expect(cleanView(legacy)?.colour).toEqual({});
});
