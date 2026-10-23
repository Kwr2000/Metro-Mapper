import { formatValue } from "./registry";
import type { PopupField } from "./generated/registry";

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

/** Source links are opt-in via manifests and allow only absolute HTTP(S). */
export function popupValueHtml(value: unknown, format: string): string {
  if (format === "link" && typeof value === "string") {
    try {
      const url = new URL(value);
      if (["http:", "https:"].includes(url.protocol) && !url.username && !url.password) {
        return `<a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">Open source page</a>`;
      }
    } catch { /* Display malformed URLs as ordinary escaped text. */ }
  }
  return escapeHtml(formatValue(value, format));
}

/** Manifest-defined estimates keep their uncertainty, including missing MOEs. */
export function popupFieldHtml(field: PopupField, properties: Record<string, unknown> | null): string {
  const display = field.display_field ? properties?.[field.display_field] : undefined;
  let value = typeof display === "string" && display ? escapeHtml(display) : popupValueHtml(properties?.[field.field], field.format ?? "text");
  if (field.moe_field) {
    const moe = properties?.[field.moe_field];
    value += `<small>${typeof moe === "number" ? `± ${escapeHtml(field.format === "percent" ? `${(moe * 100).toFixed(1)} pp` : formatValue(moe, field.format))} (90% MOE)` : "MOE unavailable (90%)"}</small>`;
  }
  if (field.reliability_field) {
    const reliability = properties?.[field.reliability_field];
    if (reliability !== "MOE ≤30% of estimate") value += `<small class="${reliability === "low reliability" ? "reliability-low" : "muted"}">${escapeHtml(String(reliability ?? "Reliability unknown"))}</small>`;
  }
  if (field.annotation_field && properties?.[field.annotation_field]) value += `<small>${escapeHtml(String(properties[field.annotation_field]))}</small>`;
  return value;
}

/** Keep the close control outside the scroll body; the same markup serves all popups. */
export function popupContent(html: string): string {
  return `<button type="button" class="popup-close" aria-label="Close popup">×</button><div class="popup-scroll">${html}</div>`;
}

export function bindPopupClose(element: HTMLElement | undefined, close: () => void): () => void {
  if (!element) return () => {};
  const button = element.querySelector<HTMLButtonElement>(".popup-close");
  const escape = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
  const click = (event: MouseEvent) => { event.stopPropagation(); close(); };
  button?.addEventListener("click", click);
  document.addEventListener("keydown", escape);
  return () => { button?.removeEventListener("click", click); document.removeEventListener("keydown", escape); };
}
