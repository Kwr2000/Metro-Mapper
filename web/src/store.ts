// Browser-only conveniences (AGENTS.md: personal state lives only in the browser).
// localStorage can be missing or throw (private windows, blocked storage); every
// read and write is guarded, and the site works without it.
const PREFIX = "metro-mapper:";

export function readLocal<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeLocal(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch { /* storage unavailable: keep working in memory */ }
}
