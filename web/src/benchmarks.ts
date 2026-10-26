import type { CompiledLayer } from "./registry";
import { formatValue } from "./registry";
import type { PopupField } from "./generated/registry";
import { escapeHtml } from "./popup";

export interface Benchmark {
  field: string; geography: string; label: string; value: number; moe: number | null;
  period: string; source: string; note: string | null; display?: string | null;
}
export interface Benchmarks { test_data: boolean; [source: string]: boolean | Record<string, Benchmark[]> }
export const EMPTY_BENCHMARKS: Benchmarks = { test_data: false };

export function comparisons(layer: CompiledLayer, field: PopupField, data: Benchmarks = EMPTY_BENCHMARKS): Benchmark[] {
  const source = data[layer.source];
  return source && typeof source === "object" ? source[field.benchmark_field ?? field.field] ?? [] : [];
}
function formatted(row: Benchmark, field: PopupField): string {
  return row.display || formatValue(row.value, field.benchmark_format ?? field.format);
}
function detail(row: Benchmark, field: PopupField): string {
  const format = field.benchmark_format ?? field.format;
  const moe = row.moe == null ? "" : ` ± ${format === "percent" ? `${(row.moe * 100).toFixed(1)} pp` : formatValue(row.moe, format)} (90% MOE)`;
  return `${row.label} ${formatted(row, field)}${moe} · ${row.period} · ${row.source}${row.note ? ` · ${row.note}` : ""}`;
}
export function benchmarkHtml(layer: CompiledLayer, field: PopupField, data: Benchmarks = EMPTY_BENCHMARKS, all = false): string {
  const rows = comparisons(layer, field, data);
  if (!rows.length) return "";
  const priority = [["austin_pd_area", "austin_city"], ["texas"], ["us"], ["peer_cities", "texas_cities_100k"]];
  const chosen = priority.flatMap((ids) => { const found = ids.map((id) => rows.find((r) => r.geography === id)).find(Boolean); return found ? [found] : []; });
  const shown = chosen.length ? chosen : rows.slice(0, 4);
  const test = data.test_data ? "Test data · " : "";
  if (all) return `<span class="benchmark-details">${escapeHtml(test)}${rows.map((r) => `<span>${escapeHtml(detail(r, field))}</span>`).join("")}</span>`;
  return `<small class="benchmark-line" title="${escapeHtml(test + rows.map((r) => detail(r, field)).join("; "))}">Compared with: ${escapeHtml(test + shown.map((r) => `${r.label} ${formatted(r, field)}`).join(" · "))}</small>`;
}
