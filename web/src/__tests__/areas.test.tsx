import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { addCompare, contextGroups, featureId, filterLayers, interiorPoint, matchAreas, observedRange, PEOPLE } from "../areas";
import { polygonContains, polygonFeatures } from "../map-polygons";
import { FiltersPanel } from "../FiltersPanel";
import { collection, ids, layer, registry } from "./workspace-fixtures";

afterEach(cleanup);
describe("registry filters", () => {
  it("uses numeric block-group fields and one block-group variant per family", () => {
    const reg = registry([layer("context_tract", { demographic: true, join: "tract", variant: { family: "x", key: "tract", label: "Tract" } }),
      layer("context_bg", { demographic: true, group: "People", variant: { family: "x", key: "bg", label: "BG" } }),
      layer("numeric"), layer("text", { popup: [{ ...layer("x").popup[0], format: "text" }] }), layer("points", { join: "point" }),
      layer("percentage", { popup: [{ ...layer("x").popup[0], format: "percent" }] }),
      layer("money", { popup: [{ ...layer("x").popup[0], format: "currency" }] })]);
    expect(filterLayers(reg).map((l) => l.id)).toEqual(["context_bg", "numeric", "percentage", "money"]);
    const grouped = contextGroups(reg, filterLayers(reg));
    expect(grouped.map(([name]) => name)).toEqual(["Environment", PEOPLE]);
    expect(grouped.at(-1)![1].every((l) => l.demographic)).toBe(true);
  });
  it("matches inclusive ranges, distinguishes zero from missing and intersects filters", () => {
    const a = layer("numeric"), b = layer("percent", { popup: [{ ...a.popup[0], field: "share", format: "percent" }] });
    const data = { [a.data_url!]: collection, [b.data_url!]: collection }, areas = polygonFeatures(collection);
    expect(observedRange(a, data)).toEqual({ min: 0, max: 10 });
    const result = matchAreas(areas, [a,b], { numeric: { min: 0, max: 5 }, percent: { min: .2, max: .8 } }, data);
    expect([...result.matches]).toEqual([ids[1]]);
    expect(result.missing).toEqual({ numeric: 2, percent: 2 });
    expect(matchAreas(areas, [a], {}, data).matches.size).toBe(5);
    expect([...matchAreas(areas, [a], { numeric: { min: null, max: 0 } }, data).matches]).toEqual([ids[0]]);
  });
  it("renders context collapsed and unchecked with dates, neutral wording and percentage units", () => {
    const demographic = layer("context", { demographic: true, group: "People", popup: [{ ...layer("x").popup[0], field: "share", label: "Share", format: "percent" }] });
    let filters = {};
    const { rerender } = render(<FiltersPanel registry={registry([demographic])} data={{ [demographic.data_url!]: collection }} errors={{}} filters={filters} missing={{}} onChange={(f) => { filters = f; }} />);
    const section = screen.getByText(PEOPLE).closest("details")!;
    expect(section.open).toBe(false);
    expect(section.textContent).toContain("for context only. They are not used in any score or ranking.");
    section.open = true;
    const checkbox = screen.getByRole("checkbox");
    expect((checkbox as HTMLInputElement).checked).toBe(false);
    fireEvent.click(checkbox);
    rerender(<FiltersPanel registry={registry([demographic])} data={{ [demographic.data_url!]: collection }} errors={{}} filters={filters} missing={{ context: 2 }} onChange={(f) => { filters = f; }} />);
    expect((screen.getByRole("spinbutton", { name: "Share min" }) as HTMLInputElement).value).toBe("10");
    fireEvent.change(screen.getByRole("spinbutton", { name: "Share max" }), { target: { value: "40" } });
    expect(filters).toEqual({ context: { min: .1, max: .4 } });
    expect(screen.getByText(/2 areas have no value/)).toBeDefined();
    expect(screen.getByText(/as of 2026-01-01/)).toBeDefined();
    expect(screen.queryAllByRole("button", { name: /sort|rank/i })).toHaveLength(0);
  });
});
describe("comparison and geography", () => {
  it("holds four distinct ids in chosen order and asks for removal before a fifth", () => {
    let chosen: string[] = [];
    for (const id of ids.slice(0,4)) chosen = addCompare(chosen,id).ids;
    expect(chosen).toEqual(ids.slice(0,4));
    expect(addCompare(chosen,ids[4]).ids).toBe(chosen);
    expect(addCompare(chosen,ids[4]).message).toMatch(/Remove an area/);
    expect(addCompare(chosen,ids[0]).ids).toBe(chosen);
  });
  it("finds a true interior point rather than a centre in a hole or concavity", () => {
    const hole = structuredClone(polygonFeatures(collection)[0]);
    hole.geometry = { type: "Polygon", coordinates: [[[0,0],[4,0],[4,4],[0,4],[0,0]], [[1,1],[3,1],[3,3],[1,3],[1,1]]] };
    const point = interiorPoint(hole)!;
    expect(polygonContains(point,hole.geometry)).toBe(true);
    expect(point[0] < 1 || point[0] > 3 || point[1] < 1 || point[1] > 3).toBe(true);
    const concave = { ...hole, geometry: { type: "MultiPolygon" as const, coordinates: [[[[0,0],[4,0],[4,1],[1,1],[1,4],[0,4],[0,0]]]] } };
    expect(polygonContains(interiorPoint(concave)!,concave.geometry)).toBe(true);
    expect(featureId(hole)).toBe(ids[0]);
  });
});
