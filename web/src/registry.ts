// Everything the site knows about layers comes from registry.json.
// Nothing in this file names a specific layer: adding a layer is a manifest change.
import type { CompiledLayer, Registry } from "./generated/registry";
import type { HealthReport } from "./generated/health";

export type { CompiledLayer, Registry, HealthReport };

export async function loadJSON<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export const mapLayerId = (layerId: string) => `mm-${layerId}`;
export const mapSourceId = (layerId: string) => `mm-src-${layerId}`;
export const sourceFor = (layer: CompiledLayer) => layer.data_bundle ? `mm-bundle-${layer.data_bundle}` : mapSourceId(layer.id);

export interface MapSourceSpec {
  type: "geojson";
  data: string;
}

export interface MapLayerSpec {
  id: string;
  source: string;
  type: string;
  paint: Record<string, unknown>;
  layout: Record<string, unknown>;
  minzoom?: number;
  maxzoom?: number;
  metadata: { mmLayer: string };
}

/** Layers that can be drawn: published, styled, and with data on disk. */
export function drawable(reg: Registry): CompiledLayer[] {
  return reg.layers.filter((l) => l.style && l.data_url && l.publish === "geojson");
}

/** Pure translation from the registry to MapLibre sources and layers. */
export function buildMapLayers(
  reg: Registry,
  visible: ReadonlySet<string>,
  baseUrl = "",
): { sources: Record<string, MapSourceSpec>; layers: MapLayerSpec[] } {
  const sources: Record<string, MapSourceSpec> = {};
  const layers: MapLayerSpec[] = [];
  // Area fills must not hide point markers. Keep manifest order within each geometry kind.
  const ordered = drawable(reg).sort((a, b) => Number(a.geometry === "point") - Number(b.geometry === "point"));
  for (const l of ordered) {
    const style = l.style!;
    sources[sourceFor(l)] ??= { type: "geojson", data: baseUrl + l.data_url };
    const spec: MapLayerSpec = {
      id: mapLayerId(l.id),
      source: sourceFor(l),
      type: style.type,
      paint: { ...(style.paint ?? {}) },
      layout: { ...(style.layout ?? {}), visibility: visible.has(l.id) ? "visible" : "none" },
      metadata: { mmLayer: l.id },
    };
    if (style.minzoom != null) spec.minzoom = style.minzoom;
    if (style.maxzoom != null) spec.maxzoom = style.maxzoom;
    layers.push(spec);
  }
  return { sources, layers };
}

export function initialVisible(reg: Registry): Set<string> {
  return new Set(reg.layers.filter((l) => l.default_visible).map((l) => l.id));
}

export function layersByGroup(reg: Registry): [string, CompiledLayer[]][] {
  return reg.groups.map((g) => [g, reg.layers.filter((l) => l.group === g)]);
}

const FRESHNESS_LABEL: Record<CompiledLayer["freshness"], string> = {
  fresh: "Current",
  stale: "Stale",
  never_run: "No data yet",
  failing: "Source failing",
  not_scheduled: "Static",
  fixture_only: "Test data",
};

export function freshnessLabel(l: Pick<CompiledLayer, "freshness">): string {
  return FRESHNESS_LABEL[l.freshness];
}

/** Every layer and number shows its vintage. */
export function asOfLabel(l: Pick<CompiledLayer, "as_of">): string {
  return l.as_of ? `as of ${l.as_of}` : "no as-of date";
}

/** True when any visible layer shows test (fixture) data. */
export function showsTestData(reg: Registry, visible: ReadonlySet<string>): boolean {
  return reg.layers.some((l) => visible.has(l.id) && l.freshness === "fixture_only");
}

/** Missing values are "not available", never zero (AGENTS.md rule 3). */
export function formatValue(v: unknown, format: string): string {
  if (v === null || v === undefined || v === "") return "Not available";
  if (format === "currency" && typeof v === "number")
    return v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  if (format === "number" && typeof v === "number") return v.toLocaleString("en-US");
  if (format === "percent" && typeof v === "number") return `${(v * 100).toFixed(1)}%`;
  return String(v);
}
