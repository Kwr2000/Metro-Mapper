// Browser-only conveniences (AGENTS.md: personal state lives only in the browser).
// localStorage can be missing or throw (private windows, blocked storage); every
// read and write is guarded, and the site works without it.
const PREFIX = "metro-mapper:";
const session = new Map<string, unknown>();
const pending = new Set<string>();

export function readLocal<T>(key: string, fallback: T): T {
  if (pending.has(key)) return session.get(key) as T;
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return (session.has(key) ? session.get(key) : fallback) as T;
  }
}

export function writeLocal(key: string, value: unknown): boolean {
  session.set(key, value);
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
    pending.delete(key);
    return true;
  } catch { pending.add(key); return false; }
}

export function storageAvailable(): boolean {
  try { window.localStorage.setItem(PREFIX + "check", "1"); window.localStorage.removeItem(PREFIX + "check"); return true; }
  catch { return false; }
}
export type SavedArea = { id: string; name: string; note: string };
export function readShortlist(): SavedArea[] {
  const value = readLocal<unknown>("shortlist", []);
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is SavedArea => v && /^\d{12}$/.test(v.id) && typeof v.name === "string" && typeof v.note === "string");
}

/** Asking prices never enter view state, query strings, fetch URLs or shared links. */
export function readAskingPrice(id: string): string {
  const value=readLocal<unknown>("asking:"+id,"");
  return typeof value==="string" && /^\d*(?:\.\d{0,2})?$/.test(value) ? value : "";
}
export function writeAskingPrice(id: string, value: string): boolean {
  return writeLocal("asking:"+id,/^\d*(?:\.\d{0,2})?$/.test(value) ? value : "");
}
