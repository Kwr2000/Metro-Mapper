/** Manifest-driven comparison colours. Classes are display only: never filter or rank inputs. */
import type { CompiledLayer, Registry } from "./registry";
import type { LayerCompare } from "./generated/registry";
import { formatValue } from "./registry";
import { EMPTY_BENCHMARKS, type Benchmark, type Benchmarks } from "./benchmarks";

export const MISSING_COLOUR = "#bdbdbd";
export const NEUTRAL = ["#8c510a", "#d8b365", "#f5f5f5", "#5ab4ac", "#01665e"];
export const DIRECTIONAL = ["#1a9641", "#a6d96a", "#f7f7f7", "#fdae61", "#d7191c"];
const PRIORITY = ["austin_pd_area", "austin_city", "texas", "us", "peer_cities", "texas_cities_100k"];
export function colourBenchmarks(layer: CompiledLayer, data: Benchmarks = EMPTY_BENCHMARKS): Benchmark[] {
  const source = data[layer.source], compare = layer.compare;
  if (!compare || !source || typeof source !== "object") return [];
  const rows = source[compare.benchmark_field ?? compare.field] ?? [];
  return rows.filter((r) => Number.isFinite(r.value)).map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const priority = (id: string) => { const i = PRIORITY.indexOf(id); return i < 0 ? PRIORITY.length : i; };
      return priority(a.row.geography) - priority(b.row.geography) || a.index - b.index;
    }).map(({ row }) => row);
}
export function selectedBenchmark(layer: CompiledLayer, colour: Record<string, string>, data?: Benchmarks): Benchmark | undefined {
  return colourBenchmarks(layer, data).find((r) => r.geography === colour[layer.id]);
}
/** A family shares its geography choice; actual values still come from each variant's field. */
export function chooseColour(registry: Registry, colour: Record<string, string>, layer: CompiledLayer, geography: string): Record<string, string> {
  const next = { ...colour };
  for (const member of registry.layers) if (member.id === layer.id || (layer.variant && member.variant?.family === layer.variant.family)) {
    if (geography && member.compare) next[member.id] = geography; else delete next[member.id];
  }
  return next;
}
export function validColours(colour: Record<string, string>, registry: Registry, data: Benchmarks): Record<string, string> {
  return Object.fromEntries(Object.entries(colour).filter(([id, geo]) => {
    const layer = registry.layers.find((l) => l.id === id);
    return layer && colourBenchmarks(layer, data).some((r) => r.geography === geo);
  }));
}
export function palette(compare: LayerCompare): string[] {
  return compare.direction === "neutral" ? NEUTRAL : compare.direction === "lower_is_better" ? DIRECTIONAL : [...DIRECTIONAL].reverse();
}
const popupRow = (layer: CompiledLayer) => layer.popup.find((row) => row.field === layer.compare?.field);
function withinMoe(layer: CompiledLayer, properties: Record<string, unknown>, value: number, benchmark: number): boolean {
  const moe = properties[popupRow(layer)?.moe_field ?? ""];
  return typeof moe === "number" && Number.isFinite(moe) && value - moe <= benchmark && value + moe >= benchmark;
}
export function comparisonClass(layer: CompiledLayer, properties: Record<string, unknown> | null, row: Benchmark): number | null {
  const c = layer.compare, value = c && properties?.[c.field];
  if (!c || typeof value !== "number" || !Number.isFinite(value) || (c.method === "ratio" && row.value === 0)) return null;
  if (withinMoe(layer, properties!, value, row.value)) return 2;
  const measure = c.method === "ratio" ? value / row.value : value - row.value;
  const i = c.breaks.findIndex((cut) => measure < cut);
  return i < 0 ? 4 : i;
}
/** Protect numeric operations from null/missing properties; step uses lower-inclusive stops. */
export function comparisonPaint(layer: CompiledLayer, row: Benchmark): unknown[] {
  const c = layer.compare!, colors = palette(c), value = ["number", ["get", c.field], 0];
  const missing: unknown[] = ["any", ["!=", ["typeof", ["get", c.field]], "number"], c.method === "ratio" && row.value === 0];
  const step: unknown[] = ["step", [c.method === "ratio" ? "/" : "-", value, row.value || (c.method === "ratio" ? 1 : 0)], colors[0]];
  c.breaks.forEach((cut, i) => step.push(cut, colors[i + 1]));
  const moeField = popupRow(layer)?.moe_field;
  if (!moeField) return ["case", missing, MISSING_COLOUR, step];
  const moe = ["number", ["get", moeField], 0];
  return ["case", missing, MISSING_COLOUR,
    ["all", ["==", ["typeof", ["get", moeField]], "number"],
      ["<=", ["-", value, moe], row.value], [">=", ["+", value, moe], row.value]], colors[2], step];
}
function electionMargin(layer: CompiledLayer): boolean {
  // Canonical margin fields are fractions with a positive Republican lead, as in the popup.
  return layer.compare?.direction === "neutral" && layer.compare.unit === "pts" &&
    layer.compare.field.endsWith("_margin") && popupRow(layer)?.format === "percent";
}
const number = (n: number) => Number(n.toPrecision(10)).toLocaleString("en-US");
export function comparisonLabels(layer: CompiledLayer, row: Benchmark): string[] {
  const c = layer.compare!, b = c.breaks, label = row.label;
  let labels: string[];
  if (c.method === "ratio") labels = [`Under ${number(b[0])}× ${label}`, `${number(b[0])}–${number(b[1])}×`,
    `About the same as ${label} (${number(b[1])}–${number(b[2])}×)`, `${number(b[2])}–${number(b[3])}×`, `Over ${number(b[3])}× ${label}`];
  else {
    const scale = popupRow(layer)?.format === "percent" ? 100 : 1;
    const outer = number(b[3] * scale), inner = number(b[2] * scale), unit = c.unit;
    labels = electionMargin(layer) ? [`Over ${outer} pts more Democratic than ${label}`, `${inner}–${outer} pts more Democratic`,
      `About the same as ${label} (within ${inner} pts)`, `${inner}–${outer} pts more Republican`, `Over ${outer} pts more Republican than ${label}`] :
      [`More than ${outer} ${unit} below ${label}`, `${inner}–${outer} ${unit} below`, `About the same as ${label} (within ${inner} ${unit})`,
        `${inner}–${outer} ${unit} above`, `More than ${outer} ${unit} above ${label}`];
  }
  if (popupRow(layer)?.moe_field) labels[2] += " · About the same (within margin of error)";
  if (c.direction !== "neutral") labels = labels.map((text, i) => i === 2 ? text :
    `${text} (${(c.direction === "lower_is_better") === (i < 2) ? "better" : "worse"})`);
  return labels;
}
export function comparisonLegend(layer: CompiledLayer, row: Benchmark) {
  const colors = palette(layer.compare!);
  return [...comparisonLabels(layer, row).map((label, i) => ({ label, color: colors[i], outline: null })),
    { label: "Not available", color: MISSING_COLOUR, outline: null }];
}
export function comparisonHeader(layer: CompiledLayer, row: Benchmark, data: Benchmarks): string {
  const field = popupRow(layer)!;
  const units = field.label.match(/per (?:1,000(?: residents)?|square mile)/i)?.[0] ??
    (/minutes/i.test(field.label) ? "minutes" : "");
  return `${data.test_data ? "Test data · " : ""}Compared with ${row.label}: ${row.display || formatValue(row.value, field.benchmark_format ?? field.format)}${units ? " " + units : ""} (${row.period}, ${row.source})`;
}
export function areaClassLabel(layer: CompiledLayer, properties: Record<string, unknown> | null, row: Benchmark): string {
  const index = comparisonClass(layer, properties, row);
  if (index === null) return "Not available";
  if (properties && withinMoe(layer, properties, properties[layer.compare!.field] as number, row.value)) return "About the same (within margin of error)";
  const label = comparisonLabels(layer, row)[index];
  if (index === 2 || electionMargin(layer)) return label;
  return `${index < 2 ? "Lower" : "Higher"} than ${row.label} (${label})`;
}
