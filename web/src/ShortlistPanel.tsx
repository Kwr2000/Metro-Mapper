import type { SavedArea } from "./store";

export function ShortlistPanel({ saved, persistent, onChange, onFly, onCompare }: {
  saved: SavedArea[]; persistent: boolean; onChange: (saved: SavedArea[]) => void;
  onFly: (id: string) => void; onCompare: () => void;
}) {
  return <section aria-label="Shortlist"><h2>Shortlist</h2>
    <p className="small muted">Private to this browser. Notes and saved areas are never included in shared links.</p>
    {!persistent && <p role="status">Storage is unavailable. Your shortlist works for this session but won't be kept after you leave.</p>}
    {!saved.length ? <p>No saved areas. Click an area on the map to save it.</p> : <>
      <button onClick={onCompare}>Compare shortlist (first 4)</button>
      <ul className="saved-list">{saved.map((item) => <li key={item.id}>
        <button className="text-button" onClick={() => onFly(item.id)}>{item.name}</button>
        <label className="small">Private note for {item.name}<textarea value={item.note} onChange={(e) => onChange(saved.map((s) => s.id === item.id ? { ...s, note: e.target.value } : s))} /></label>
        <button disabled={!item.note} onClick={() => onChange(saved.map((s) => s.id === item.id ? { ...s, note: "" } : s))}>Delete note</button>{" "}
        <button onClick={() => onChange(saved.filter((s) => s.id !== item.id))}>Remove saved area</button>
      </li>)}</ul>
    </>}
  </section>;
}
