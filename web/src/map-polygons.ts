/** Local point-in-polygon over loaded GeoJSON. A bounding-box tree prunes geometry work. */
import type { Feature, GeoJSON, Polygon, MultiPolygon, Position } from "geojson";

export type PolygonFeature = Feature<Polygon | MultiPolygon>;
type Bounds = [number, number, number, number];
interface Entry { feature: PolygonFeature; bounds: Bounds }
interface Node { bounds: Bounds; entries?: Entry[]; left?: Node; right?: Node }
const within = ([x, y]: Position, b: Bounds) => x >= b[0] && y >= b[1] && x <= b[2] && y <= b[3];
function bounds(feature: PolygonFeature): Bounds {
  const b: Bounds = [Infinity, Infinity, -Infinity, -Infinity];
  const polygons = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
  for (const polygon of polygons) for (const ring of polygon) for (const [x, y] of ring) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    b[0] = Math.min(b[0], x); b[1] = Math.min(b[1], y); b[2] = Math.max(b[2], x); b[3] = Math.max(b[3], y);
  }
  return b;
}
function tree(entries: Entry[]): Node | null {
  if (!entries.length) return null;
  const b: Bounds = [Infinity, Infinity, -Infinity, -Infinity];
  for (const { bounds: e } of entries) { b[0] = Math.min(b[0], e[0]); b[1] = Math.min(b[1], e[1]); b[2] = Math.max(b[2], e[2]); b[3] = Math.max(b[3], e[3]); }
  if (entries.length <= 8) return { bounds: b, entries };
  const axis = b[2] - b[0] > b[3] - b[1] ? 0 : 1;
  entries.sort((a, z) => (a.bounds[axis] + a.bounds[axis + 2]) - (z.bounds[axis] + z.bounds[axis + 2]));
  const middle = Math.floor(entries.length / 2);
  return { bounds: b, left: tree(entries.slice(0, middle))!, right: tree(entries.slice(middle))! };
}
/** -1 outside, 0 on boundary, 1 inside. Hole boundaries belong to the polygon boundary. */
function ringContains([x, y]: Position, ring: Position[]): -1 | 0 | 1 {
  if (ring.length < 3) return -1;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if (![xi, yi, xj, yj].every(Number.isFinite)) continue;
    const cross = (x - xi) * (yj - yi) - (y - yi) * (xj - xi);
    if (Math.abs(cross) < 1e-12 && x >= Math.min(xi, xj) - 1e-10 && x <= Math.max(xi, xj) + 1e-10 &&
      y >= Math.min(yi, yj) - 1e-10 && y <= Math.max(yi, yj) + 1e-10) return 0;
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside ? 1 : -1;
}
export function polygonContains(point: Position, geometry: Polygon | MultiPolygon): boolean {
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons.some(([outer, ...holes]) => outer && ringContains(point, outer) >= 0 && !holes.some((hole) => ringContains(point, hole) === 1));
}
export interface PolygonIndex {
  count: number;
  query: (point: Position) => { features: PolygonFeature[]; candidates: number };
}
export function polygonFeatures(data: GeoJSON): PolygonFeature[] {
  const features = data.type === "FeatureCollection" ? data.features : data.type === "Feature" ? [data] : [];
  return features.filter((f): f is PolygonFeature => f.geometry?.type === "Polygon" || f.geometry?.type === "MultiPolygon");
}
function index(entries: Entry[]): PolygonIndex {
  const root = tree(entries);
  return { count: entries.length, query(point) {
    const features: PolygonFeature[] = []; let candidates = 0;
    function visit(node?: Node | null) {
      if (!node || !within(point, node.bounds)) return;
      if (node.entries) {
        for (const e of node.entries) if (within(point, e.bounds)) {
          candidates++; if (polygonContains(point, e.feature.geometry)) features.push(e.feature);
        }
      } else { visit(node.left); visit(node.right); }
    }
    visit(root); return { features, candidates };
  } };
}
export function buildPolygonIndex(data: GeoJSON): PolygonIndex {
  return index(polygonFeatures(data).map((feature) => ({ feature, bounds: bounds(feature) })));
}
/** Yield between batches while indexing large publications; clicks never fetch data. */
export async function buildPolygonIndexIdle(data: GeoJSON, cancelled: () => boolean): Promise<PolygonIndex | null> {
  const features = polygonFeatures(data), entries: Entry[] = [];
  for (let start = 0; start < features.length; start += 128) {
    if (cancelled()) return null;
    if (start) await new Promise<void>((resolve) => {
      if (typeof requestIdleCallback === "function") requestIdleCallback(() => resolve(), { timeout: 100 });
      else setTimeout(resolve, 0);
    });
    for (const feature of features.slice(start, start + 128)) entries.push({ feature, bounds: bounds(feature) });
  }
  return cancelled() ? null : index(entries);
}
