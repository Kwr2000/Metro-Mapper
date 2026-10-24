import type { FeatureCollection } from "geojson";
import type { CompiledLayer, Registry } from "./registry";
import { polygonContains, polygonFeatures, type PolygonFeature } from "./map-polygons";

export const PEOPLE = "People (context only)";
export const PEOPLE_NOTE = "Census estimates for context. They are not used in any score.";
export type LayerData = Record<string, FeatureCollection>;
export type Range = { min: number | null; max: number | null };
export type Filters = Record<string, Range>;
export const featureId = (f: PolygonFeature) => String(f.properties?.geoid ?? f.id ?? f.properties?.feature_id ?? "");
export const areaName = (f: PolygonFeature) => String(f.properties?.name ?? featureId(f));
export const featuresFor = (l: CompiledLayer, data: LayerData) => l.data_url && data[l.data_url] ? polygonFeatures(data[l.data_url]) : [];

/** Semantic registry fields identify the base areas; no source or layer id is special. */
export function areaLayer(registry: Registry): CompiledLayer | undefined {
  return registry.layers.find((l) => l.join === "block_group" && l.geometry === "polygon" && l.popup.some((p) => p.field === "name"));
}

export function contextGroups(registry: Registry, layers = registry.layers): [string, CompiledLayer[]][] {
  const groups: [string, CompiledLayer[]][] = registry.groups.map((g) => [g, layers.filter((l) => !l.demographic && l.group === g)]);
  groups.push([PEOPLE, layers.filter((l) => l.demographic)]);
  return groups.filter(([, ls]) => ls.length);
}

export function blockGroupLayers(registry: Registry): CompiledLayer[] {
  const seen = new Set<string>();
  return registry.layers.filter((l) => {
    if (l.join !== "block_group" || !l.data_url) return false;
    if (l.variant) {
      if (seen.has(l.variant.family)) return false;
      seen.add(l.variant.family);
    }
    return true;
  });
}

export function filterLayers(registry: Registry): CompiledLayer[] {
  return blockGroupLayers(registry).filter((l) => ["number", "percent", "currency"].includes(l.popup[0]?.format));
}

export function observedRange(layer: CompiledLayer, data: LayerData): Range | null {
  const field = layer.popup[0].field;
  const values = featuresFor(layer, data).map((f) => f.properties?.[field]).filter(numeric);
  return values.length ? { min: Math.min(...values), max: Math.max(...values) } : null;
}
export const numeric = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function matchAreas(areas: PolygonFeature[], layers: CompiledLayer[], filters: Filters, data: LayerData) {
  const matches = new Set(areas.map(featureId)), missing: Record<string, number> = {};
  for (const layer of layers) {
    const range = filters[layer.id]; if (!range) continue;
    const values = new Map(featuresFor(layer, data).map((f) => [featureId(f), f.properties?.[layer.popup[0].field]]));
    missing[layer.id] = 0;
    for (const area of areas) {
      const id = featureId(area), value = values.get(id);
      if (!numeric(value)) { missing[layer.id]++; matches.delete(id); }
      else if ((range.min !== null && value < range.min) || (range.max !== null && value > range.max)) matches.delete(id);
    }
  }
  return { matches, missing };
}

export function addCompare(ids: string[], id: string): { ids: string[]; message: string } {
  if (ids.includes(id)) return { ids, message: "Already in compare." };
  if (ids.length >= 4) return { ids, message: "Remove an area before adding another. Compare holds up to 4 areas." };
  return { ids: [...ids, id], message: "Added to compare." };
}

/** A scan line gives an interior point even for concave polygons, holes and islands.
 * A bounding-box centre or vertex average may fall outside the area. */
export function interiorPoint(feature: PolygonFeature): [number, number] | null {
  const polygons = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
  for (const rings of polygons) {
    const ys = [...new Set(rings.flat().map((p) => p[1]))].sort((a, b) => a - b);
    const middle = (ys[0] + ys[ys.length - 1]) / 2;
    const scans = [...(!ys.includes(middle) ? [middle] : []), ...ys.slice(1).map((y, i) => (y + ys[i]) / 2)];
    for (const y of scans) {
      const xs: number[] = [];
      for (const ring of rings) for (let i = 1; i < ring.length; i++) {
        const [x1, y1] = ring[i - 1], [x2, y2] = ring[i];
        if ((y1 > y) !== (y2 > y)) xs.push(x1 + (y - y1) * (x2 - x1) / (y2 - y1));
      }
      xs.sort((a, b) => a - b);
      let best: [number, number] | null = null, width = 0;
      for (let i = 1; i < xs.length; i++) {
        const point: [number, number] = [(xs[i - 1] + xs[i]) / 2, y];
        if (xs[i] - xs[i - 1] > width && polygonContains(point, feature.geometry)) { best = point; width = xs[i] - xs[i - 1]; }
      }
      if (best) return best;
    }
  }
  return null;
}
