import { validColours } from "./colour";
import { EMPTY_BENCHMARKS, type Benchmarks } from "./benchmarks";
import type { Registry } from "./registry";
import { filterLayers, type Filters } from "./areas";

export type Camera = { center: [number, number]; zoom: number };
export type ViewState = { camera: Camera | null; visible: string[]; variants: Record<string, string>; filters: Filters; compare: string[]; colour: Record<string, string> };
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Explicit allowlist at every level. Personal state is never part of this format. */
export function cleanView(value: unknown): ViewState | null {
  if (!record(value)) return null;
  const c = value.camera;
  const camera = record(c) && Array.isArray(c.center) && c.center.length === 2 && c.center.every(finite) &&
    Math.abs(c.center[0]) <= 180 && Math.abs(c.center[1]) <= 85.05113 && finite(c.zoom) && c.zoom >= 0 && c.zoom <= 24
    ? { center: [c.center[0], c.center[1]] as [number, number], zoom: c.zoom } : null;
  const visible = Array.isArray(value.visible) ? [...new Set(value.visible.filter((x): x is string => typeof x === "string" && /^[a-z0-9_]+$/.test(x)))].slice(0, 500) : [];
  const compare = Array.isArray(value.compare) ? [...new Set(value.compare.filter((x): x is string => typeof x === "string" && /^\d{12}$/.test(x)))].slice(0, 4) : [];
  const variants: Record<string, string> = {}, filters: Filters = {};
  if (record(value.variants)) for (const [group, key] of Object.entries(value.variants).slice(0, 100)) if (typeof key === "string") variants[group] = key;
  if (record(value.filters)) for (const [id, range] of Object.entries(value.filters).slice(0, 100)) {
    if (record(range) && (range.min === null || finite(range.min)) && (range.max === null || finite(range.max)) &&
        !(finite(range.min) && finite(range.max) && range.min > range.max)) filters[id] = { min: range.min, max: range.max };
  }
  const colour = record(value.colour) ? Object.fromEntries(Object.entries(value.colour).slice(0, 100)
    .filter(([id, geo]) => /^[a-z0-9_]+$/.test(id) && typeof geo === "string" && /^[a-z0-9_]+$/.test(geo))) as Record<string, string> : {};
  return { camera, visible, variants, filters, compare, colour };
}

export function encodeView(view: ViewState): string {
  return "#/?v=" + encodeURIComponent(JSON.stringify({ version: 1, ...cleanView(view) }));
}
export function readView(hash: string): ViewState | null {
  try {
    if (hash.length > 100000) return null;
    const raw = new URLSearchParams(hash.split("?")[1] ?? "").get("v");
    if (!raw) return null;
    const value = JSON.parse(raw);
    return value.version === 1 ? cleanView(value) : null;
  } catch { return null; }
}
export function registryView(view: ViewState, registry: Registry, benchmarks: Benchmarks = EMPTY_BENCHMARKS): ViewState {
  const known = new Set(registry.layers.map((l) => l.id)), eligible = new Set(filterLayers(registry).map((l) => l.id));
  return { ...view, colour: validColours(view.colour, registry, benchmarks), visible: view.visible.filter((id) => known.has(id)),
    filters: Object.fromEntries(Object.entries(view.filters).filter(([id]) => eligible.has(id))),
    variants: Object.fromEntries(Object.entries(view.variants).filter(([group, key]) => registry.layers.some((l) => l.group === group && l.variant?.key === key))) };
}
