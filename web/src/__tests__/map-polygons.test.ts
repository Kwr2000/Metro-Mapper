import { describe, expect, it } from "vitest";
import { buildPolygonIndex, polygonContains } from "../map-polygons";

const square = { type: "Polygon" as const, coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]], [[0.5, 0.5], [1, 0.5], [1, 1], [0.5, 1], [0.5, 0.5]]] };

describe("point in polygon", () => {
  it("handles holes and boundaries", () => {
    expect(polygonContains([1.5, 1.5], square)).toBe(true);
    expect(polygonContains([0.75, 0.75], square)).toBe(false); // in the hole
    expect(polygonContains([0, 1], square)).toBe(true); // on the boundary
    expect(polygonContains([3, 3], square)).toBe(false);
  });

  it("indexes many features", () => {
    const features = Array.from({ length: 50 }, (_, i) => ({ type: "Feature" as const, properties: { i },
      geometry: { type: "Polygon" as const, coordinates: [[[i, 0], [i + 1, 0], [i + 1, 1], [i, 1], [i, 0]]] } }));
    const index = buildPolygonIndex({ type: "FeatureCollection", features });
    expect(index.query([10.5, 0.5]).features.map((f) => f.properties?.i)).toEqual([10]);
  });
});
