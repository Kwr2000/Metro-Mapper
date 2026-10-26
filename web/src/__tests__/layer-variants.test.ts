import { describe, expect, it } from "vitest";
import { normalizeLayerVariants, switchLayerVariant } from "../layer-variants";
import type { CompiledLayer, Registry } from "../registry";

const layer = (id: string, family: string, key: string): CompiledLayer => ({
  id, title: id, group: "People", description: "", source: "acs", geometry: "polygon", join: "block_group", publish: "geojson",
  style: { type: "fill", paint: {}, layout: {}, minzoom: null, maxzoom: null }, popup: [], popup_title: null, hover: [],
  variant: { family, key, label: key }, data_bundle: null, compare: null, legend: [], dataset: null, where: {}, as_of_field: null,
  coverage: "x", refresh: "annual", attribution: "x", license: "", disclaimer: "", demographic: true, default_visible: false,
  order: 1, data_url: "x", as_of: null, last_success: null, freshness: "fixture_only",
});
const registry = { groups: ["People"], layers: [layer("income_bg", "income", "bg"), layer("income_tract", "income", "tract"),
  layer("age_bg", "age", "bg"), layer("age_tract", "age", "tract")] } as unknown as Registry;

describe("area scale switch", () => {
  it("keeps the same metrics on when switching scale", () => {
    expect([...switchLayerVariant(registry, new Set(["income_bg"]), "People", "tract")]).toEqual(["income_tract"]);
  });
  it("never shows two scales of one group at once", () => {
    const got = normalizeLayerVariants(registry, new Set(["income_bg", "age_tract"]));
    expect(got.size).toBe(2);
    expect([...got].every((id) => id.endsWith("_bg")) || [...got].every((id) => id.endsWith("_tract"))).toBe(true);
  });
});
