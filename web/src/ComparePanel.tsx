import { useEffect, useRef } from "react";
import type { PolygonFeature } from "./map-polygons";
import { buildPolygonIndex } from "./map-polygons";
import { areaName, blockGroupLayers, contextGroups, featuresFor, featureId, interiorPoint, PEOPLE, PEOPLE_NOTE, type LayerData } from "./areas";
import { asOfLabel, freshnessLabel, type Registry } from "./registry";
import { popupFieldHtml } from "./popup";

export function CompareTray({ areas, ids, onRemove, onOpen }: { areas: PolygonFeature[]; ids: string[]; onRemove: (id: string) => void; onOpen: () => void }) {
  return <section aria-label="Compare tray"><h2>Compare areas <small>({ids.length}/4)</small></h2>
    <p className="small muted">Side by side, in the order you choose. No scores or rankings.</p>
    {!ids.length && <p>Click an area on the map and choose Add to compare.</p>}
    <ol className="compare-list">{ids.map((id) => <li key={id}><span>{areas.find((f) => featureId(f) === id) ? areaName(areas.find((f) => featureId(f) === id)!) : id}</span>
      <button aria-label={`Remove ${id} from compare`} onClick={() => onRemove(id)}>Remove</button></li>)}</ol>
    <button disabled={!ids.length} onClick={onOpen}>Compare</button>
  </section>;
}

export function CompareTable({ registry, areas, ids, data, errors, onClose }: {
  registry: Registry; areas: PolygonFeature[]; ids: string[]; data: LayerData; errors: Record<string, string>; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = dialog.current!;
    if (el.showModal) el.showModal(); else el.setAttribute("open", "");
    return () => { el.close?.(); };
  }, []);
  const names = ids.map((id) => { const area = areas.find((a) => featureId(a) === id); return area ? areaName(area) : id; });
  const jurisdictions = registry.layers.filter((l) => l.join === "jurisdiction" && l.geometry === "polygon" && l.data_url && data[l.data_url]);
  return <dialog ref={dialog} className="compare-dialog" aria-label="Area comparison" onCancel={onClose}>
    <div className="dialog-heading"><h2>Area comparison</h2><button onClick={onClose} autoFocus>Close comparison</button></div>
    <p>Values are context, with their sources and dates. No sorting or combined score.</p>
    {contextGroups(registry, blockGroupLayers(registry)).map(([group, layers]) => <section key={group} className="comparison-group">
      <h3>{group}</h3>{group === PEOPLE && <p>{PEOPLE_NOTE}</p>}
      {layers.map((layer) => {
        const byId = new Map(featuresFor(layer, data).map((f) => [featureId(f), f.properties]));
        const loading = layer.data_url && !data[layer.data_url] && !errors[layer.data_url];
        return <section className="comparison-layer" key={layer.id}><h4>{layer.popup_title ?? layer.title}</h4>
          <p className="small muted">Source: {layer.attribution} · {asOfLabel(layer)} · {freshnessLabel(layer)}</p>
          {layer.disclaimer && <p className="small muted">{layer.disclaimer}</p>}
          {loading && <p role="status">Loading…</p>}{layer.data_url && errors[layer.data_url] && <p role="alert">{errors[layer.data_url]}</p>}
          <table className="comparison-table"><thead><tr><th scope="col">Measure</th>{names.map((name, i) => <th scope="col" key={ids[i]}>{name}</th>)}</tr></thead>
            <tbody>{layer.popup.map((field) => <tr key={field.field}><th scope="row">{field.label}</th>{ids.map((id, i) => <td key={id} data-area={names[i]}
              dangerouslySetInnerHTML={{ __html: popupFieldHtml(field, byId.get(id) ?? null) }} />)}</tr>)}</tbody></table>
        </section>;
      })}
    </section>)}
    <section><h3>Districts at each area's interior point</h3>
      <p className="small muted">Only loaded jurisdiction layers are checked. This does not assign a campus or attendance zone.</p>
      {!jurisdictions.length && <p>Load a jurisdiction layer to see its name and source link here.</p>}
      {jurisdictions.map((layer) => {
        const index = buildPolygonIndex(data[layer.data_url!]);
        const fields = layer.popup.filter((f) => f.field === "name" || f.format === "link");
        return <section key={layer.id}><h4>{layer.title}</h4><p className="small muted">Source: {layer.attribution} · {asOfLabel(layer)} · {freshnessLabel(layer)}</p>
          {ids.map((id, i) => {
            const area = areas.find((a) => featureId(a) === id), point = area ? interiorPoint(area) : null;
            const found = point ? index.query(point).features : [];
            return <div key={id}><strong>{names[i]}</strong>{found.length ? found.map((feature, j) => <p key={j}>{fields.map((field) =>
              <span className="district-value" key={field.field} dangerouslySetInnerHTML={{ __html: popupFieldHtml(field, feature.properties) }} />)}</p>) : <p>Not available</p>}</div>;
          })}</section>;
      })}
    </section>
  </dialog>;
}
