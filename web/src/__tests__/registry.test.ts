import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  asOfLabel, buildMapLayers, formatValue, freshnessLabel, initialVisible, layersByGroup, mapLayerId,
  showsTestData, type Registry,
} from "../registry";

// The compiled registry from `mm build` (CI runs it before these tests).
const registry = JSON.parse(readFileSync(join(__dirname, "../../public/registry.json"), "utf8")) as Registry;

describe("registry → map", () => {
  it("draws every published layer from the registry", () => {
    const { sources, layers } = buildMapLayers(registry, initialVisible(registry));
    const drawableIds = registry.layers.filter((l) => l.data_url && l.style).map((l) => l.id);
    expect(drawableIds.length).toBeGreaterThan(0);
    expect([...new Set(layers.map((l) => l.metadata.mmLayer))].sort()).toEqual([...drawableIds].sort());
    for (const l of layers) expect(sources[l.source]).toBeDefined();
  });

  it("draws a layer added to the registry with no code change", () => {
    const base = registry.layers[0];
    const extended: Registry = { ...registry, layers: [...registry.layers, { ...base, id: "brand_new_layer", title: "Brand new" }] };
    const added = buildMapLayers(extended, new Set(["brand_new_layer"])).layers.find((l) => l.id === mapLayerId("brand_new_layer"));
    expect(added?.layout.visibility).toBe("visible");
    expect(added?.type).toBe(base.style!.type);
  });

  it("respects visibility and default_visible", () => {
    expect(buildMapLayers(registry, new Set()).layers.every((l) => l.layout.visibility === "none")).toBe(true);
    const defaults = initialVisible(registry);
    for (const l of registry.layers) expect(defaults.has(l.id)).toBe(l.default_visible);
  });

  it("keeps points above polygons without changing order within a kind", () => {
    const base = { ...registry.layers[0], id: "point_marker", geometry: "point" as const,
      style: { type: "circle" as const, paint: {}, layout: {}, minzoom: null, maxzoom: null } };
    const poly = { ...base, id: "area_fill", geometry: "polygon" as const, style: { ...base.style!, type: "fill" as const } };
    const reg: Registry = { ...registry, layers: [base, poly] };
    expect(buildMapLayers(reg, new Set()).layers.map((l) => l.metadata.mmLayer)).toEqual(["area_fill", base.id]);
  });

  it("groups layers in registry order", () => {
    expect(layersByGroup(registry).map(([g]) => g)).toEqual(registry.groups);
  });
});

describe("honest labels", () => {
  it("every layer shows a freshness label and an as-of label", () => {
    for (const l of registry.layers) {
      expect(freshnessLabel(l)).toBeTruthy();
      expect(asOfLabel(l)).toMatch(/as of|no as-of date/);
    }
  });

  it("fixture builds are labeled Test data", () => {
    // Layers that publish no file (comparison-only metadata) take their freshness from the run
    // log, so a live run of their source must not break this check.
    expect(registry.layers.filter((l) => l.publish !== "none").every((l) => l.freshness === "fixture_only")).toBe(true);
    expect(freshnessLabel({ freshness: "fixture_only" })).toBe("Test data");
    expect(showsTestData(registry, initialVisible(registry))).toBe(true);
    expect(showsTestData(registry, new Set())).toBe(false);
  });

  it("missing values read as Not available, never zero", () => {
    for (const fmt of ["text", "number", "currency", "percent"]) {
      expect(formatValue(null, fmt)).toBe("Not available");
      expect(formatValue(undefined, fmt)).toBe("Not available");
    }
    expect(formatValue(0, "number")).toBe("0");
    expect(formatValue(0.125, "percent")).toBe("12.5%");
  });
});
