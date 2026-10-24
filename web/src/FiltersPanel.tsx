import type { Registry } from "./registry";
import { asOfLabel } from "./registry";
import { contextGroups, filterLayers, observedRange, PEOPLE, PEOPLE_NOTE, type Filters, type LayerData, type Range } from "./areas";

export function FiltersPanel({ registry, data, errors, filters, missing, onChange }: {
  registry: Registry; data: LayerData; errors: Record<string, string>; filters: Filters;
  missing: Record<string, number>; onChange: (filters: Filters) => void;
}) {
  return <section aria-label="Filters"><h2>Filters</h2><p className="muted small">Choose ranges to highlight matching areas. Missing values do not match.</p>
    <button onClick={() => onChange({})} disabled={!Object.keys(filters).length}>Clear filters</button>
    {contextGroups(registry, filterLayers(registry)).map(([group, layers]) => <details key={group} open={group !== PEOPLE} className="filter-group">
      <summary>{group}</summary>{group === PEOPLE && <p className="small muted">{PEOPLE_NOTE}</p>}
      {layers.map((layer) => {
        const active = filters[layer.id], observed = observedRange(layer, data), factor = layer.popup[0].format === "percent" ? 100 : 1;
        const bounds = observed ? { min: observed.min! * factor, max: observed.max! * factor } : null;
        const selected = active && bounds ? { min: (active.min ?? observed!.min!) * factor, max: (active.max ?? observed!.max!) * factor } : null;
        const change = (edge: "min" | "max", value: string) => {
          const next: Range = { min: active?.min ?? observed?.min ?? null, max: active?.max ?? observed?.max ?? null };
          next[edge] = value === "" ? null : Number(value) / factor;
          if (next.min !== null && next.max !== null && next.min > next.max) next[edge === "min" ? "max" : "min"] = next[edge];
          onChange({ ...filters, [layer.id]: next });
        };
        return <div className="filter-row" key={layer.id} data-filter-id={layer.id}>
          <label><input type="checkbox" checked={!!active} onChange={(e) => {
            const next = { ...filters }; if (e.target.checked) next[layer.id] = { min: null, max: null }; else delete next[layer.id]; onChange(next);
          }} />{layer.popup[0].label}</label>
          <p className="small muted">{asOfLabel(layer)} · {layer.attribution}</p>
          {active && <>
            {layer.data_url && errors[layer.data_url] ? <p role="alert">{errors[layer.data_url]}</p> : !data[layer.data_url!] ? <p>Loading filter data…</p> : !bounds ? <p>No numeric values available.</p> : <>
              <div className="range-pair" role="group" aria-label={`${layer.popup[0].label} range`}>
                {(["min", "max"] as const).map((edge) => <label key={edge}>{edge === "min" ? "Minimum" : "Maximum"}{factor === 100 ? " (%)" : ""}
                  <input type="number" step="any" aria-label={`${layer.popup[0].label} ${edge}`} value={selected![edge]} onChange={(e) => change(edge, e.target.value)} />
                </label>)}
              </div>
              <div className="range-track">{(["min", "max"] as const).map((edge) => <input key={edge} type="range"
                aria-label={`${layer.popup[0].label} ${edge} slider`} min={Math.min(bounds.min, selected!.min)} max={Math.max(bounds.max, selected!.max)}
                step={bounds.max === bounds.min ? 1 : (bounds.max - bounds.min) / 1000} value={selected![edge]} onChange={(e) => change(edge, e.target.value)} />)}</div>
            </>}
            {data[layer.data_url!] && missing[layer.id] !== undefined && <p className="small">{missing[layer.id].toLocaleString()} areas have no value for this filter.</p>}
          </>}
        </div>;
      })}
    </details>)}
  </section>;
}
