import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { benchmarkHtml, comparisons, type Benchmark, type Benchmarks } from "../benchmarks";
import { LayerPanel } from "../LayerPanel";
import { CompareTable } from "../ComparePanel";
import { collection, ids, layer, registry } from "./workspace-fixtures";
import { polygonFeatures } from "../map-polygons";

const l = layer("measure_layer", { source: "synthetic", demographic: true });
const f = { ...l.popup[0], format: "currency" as const };
const row = (geography: string, label: string, value: number): Benchmark => ({ field: "measure", geography, label, value, moe: 100, period: "2020–2024", source: "Synthetic Census source", note: null });
const data: Benchmarks = { test_data: false, synthetic: { measure: [row("us", "US", 80000), row("texas", "Texas", 78000), row("austin_city", "Austin city", 93000), row("travis", "Travis County", 96000), row("peer_cities", "Similar-size cities", 90000)] } };
afterEach(cleanup);

it("popup shows at most four in requested order, with all values/MOEs/source/period on hover", () => {
  const host = document.createElement("div"); host.innerHTML = benchmarkHtml(l, f, data);
  const line = host.querySelector("small")!;
  expect(line.textContent).toBe("Compared with: Austin city $93,000 · Texas $78,000 · US $80,000 · Similar-size cities $90,000");
  expect(line.title).toContain("Travis County $96,000 ± $100 (90% MOE) · 2020–2024 · Synthetic Census source");
  expect(line.textContent).not.toMatch(/better|worse|rank|score/);
});

it("missing benchmark creates no line, genuine zero is shown, and fixture benchmarks are labeled", () => {
  expect(benchmarkHtml(l, { ...f, field: "missing" }, data)).toBe("");
  const zero: Benchmarks = { test_data: true, synthetic: { measure: [row("three_county", "Three-county typical home", 0)] } };
  expect(benchmarkHtml(l, f, zero)).toContain("Compared with: Test data · Three-county typical home $0");
});

it("uses manifest school scope and percentage format and preserves Census capped displays", () => {
  const fixture: Benchmarks = { test_data: false, synthetic: { district_score: [{ ...row("texas", "Texas (A or B)", .75), moe: null }], measure: [{ ...row("us", "US", 250000), display: "$250,000 or more" }] } };
  const mapped = { ...f, benchmark_field: "district_score", benchmark_format: "percent" as const };
  expect(comparisons(l, mapped, fixture)).toHaveLength(1);
  expect(benchmarkHtml(l, mapped, fixture)).toContain("Texas (A or B) 75.0%");
  expect(benchmarkHtml(l, f, fixture)).toContain("$250,000 or more");
});

it("comparison HTML escapes source, note and label, and renders all geographies with dates", () => {
  const unsafe: Benchmarks = { test_data: false, synthetic: { measure: [{ ...row("texas", '<img src=x onerror="bad()">', 1), note: "<script>bad()</script>" }] } };
  const host = document.createElement("div");host.innerHTML = benchmarkHtml(l, f, unsafe, true);
  expect(host.querySelector("script, img")).toBeNull();
  expect(host.textContent).toContain("<script>bad()</script>");
  expect(benchmarkHtml(l, f, data, true)).toContain("Travis County");
});

it("comparison table adds a neutral Compared with column and full benchmark source/period", () => {
  HTMLDialogElement.prototype.showModal = vi.fn(function(this: HTMLDialogElement) { this.setAttribute("open", ""); }); HTMLDialogElement.prototype.close = vi.fn();
  render(<CompareTable registry={registry([l])} areas={polygonFeatures(collection)} ids={[ids[0]]}
    data={{ [l.data_url!]: collection }} errors={{}} benchmarks={data} onClose={() => {}} />);
  expect(screen.getByRole("columnheader", { name: "Compared with" })).toBeDefined();
  expect(screen.getByText(/Travis County.*Synthetic Census source/)).toBeDefined();
  expect(screen.queryAllByRole("button", { name: /sort|rank/i })).toHaveLength(0);
  expect(screen.getByText("People (context only)")).toBeDefined();
});

it("non-spatial benchmark metadata is not offered as a map toggle", () => {
  const metadata = layer("comparison_metadata", { publish: "none", geometry: "none", style: null, data_url: null });
  render(<LayerPanel registry={registry([layer("visible_measure"), metadata])} visible={new Set()} onToggle={() => {}} onSwitchVariant={() => {}} choices={{}} />);
  expect(screen.queryByText("comparison_metadata")).toBeNull();
  expect(screen.getByRole("checkbox", { name: "visible_measure" })).toBeDefined();
});
