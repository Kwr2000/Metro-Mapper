import type { FeatureCollection } from "geojson";
import type { CompiledLayer, Registry } from "../registry";

export function layer(id: string, patch: Partial<CompiledLayer> = {}): CompiledLayer {
  return { id, title: id, group: "Environment", description: "Description", source: "synthetic", geometry: "polygon", join: "block_group", publish: "geojson",
    style: { type: "fill", paint: {}, layout: {}, minzoom: null, maxzoom: null }, popup: [{ field: "measure", label: "Measure", format: "number", moe_field: null, reliability_field: null, annotation_field: null, display_field: null }],
    popup_title: null, hover: [], variant: null, data_bundle: null, legend: [], dataset: null, where: {}, as_of_field: null, coverage: "test", refresh: "annual",
    attribution: "Synthetic source", license: "Public domain", disclaimer: "", demographic: false, default_visible: false, order: 1,
    data_url: `data/layers/${id}.geojson`, as_of: "2026-01-01", last_success: null, freshness: "fixture_only", ...patch };
}
export const ids = ["484530001001", "484530001002", "484530001003", "484530001004", "484530001005"];
export const collection: FeatureCollection = { type: "FeatureCollection", features: ids.map((id, i) => ({ type: "Feature", id,
  properties: { geoid: id, name: `Area ${i + 1}`, measure: [0, 5, 10, null, null][i], share: [.1, .2, .8, null, null][i] },
  geometry: { type: "Polygon", coordinates: [[[i,0],[i+1,0],[i+1,1],[i,1],[i,0]]] } })) };
export const registry = (layers: CompiledLayer[]): Registry => ({ version: 1, site_title: "Test map", groups: ["Areas", "People", "Environment"], layers,
  basemap: { style_url: "unused", attribution: "Test", center: [0,0], zoom: 8 }, generated_at: "2026-01-01" }) as unknown as Registry;
