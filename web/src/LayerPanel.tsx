import { asOfLabel, freshnessLabel, type Registry } from "./registry";
import { contextGroups, PEOPLE, PEOPLE_NOTE } from "./areas";

export function LayerPanel({
  registry,
  visible,
  onToggle,
  onSwitchVariant,
  choices,
}: {
  registry: Registry;
  visible: ReadonlySet<string>;
  onToggle: (id: string) => void;
  onSwitchVariant: (group: string, key: string) => void;
  choices: Record<string, string>;
}) {
  return (
    <aside className="panel" aria-label="Layers">
      <h2 className="panel-title">Layers</h2>
      {registry.layers.length === 0 && <p className="muted">No layers yet.</p>}
      {contextGroups(registry, registry.layers.filter((l) => l.publish !== "none")).map(([group, allLayers]) => {
        const variants = [...new Map(allLayers.filter((l) => l.variant).map((l) => [l.variant!.key, l.variant!])).values()];
        const registryGroup = allLayers[0].group;
        const active = allLayers.find((l) => l.variant && visible.has(l.id))?.variant?.key ?? choices[registryGroup] ?? variants[0]?.key;
        const layers = allLayers.filter((l) => !l.variant || l.variant.key === active);
        return (
          <details key={group} className="group" open={group !== PEOPLE}>
            <summary className="group-title">{group}</summary>
            {group === PEOPLE && <p className="small muted">{PEOPLE_NOTE}</p>}
            {variants.length > 1 && (
              <div className="area-scale" role="group" aria-label={`${group} geography`}>
                {variants.map((v) => (
                  <button key={v.key} aria-pressed={v.key === active} onClick={() => {
                    onSwitchVariant(registryGroup, v.key);
                  }}>{v.label}</button>
                ))}
              </div>
            )}
            <ul>
              {layers.map((l) => {
                const disabled = !l.data_url;
                return (
                  <li key={l.id} className="layer-row" data-layer-id={l.id}>
                    <label className={disabled ? "disabled" : ""}>
                      <input type="checkbox" checked={visible.has(l.id)} disabled={disabled} onChange={() => onToggle(l.id)} />
                      <span className="layer-title">{l.title}</span>
                    </label>
                    <div className="layer-meta">
                      <span className={`badge badge-${l.freshness}`}>{freshnessLabel(l)}</span>
                      <span className="muted">{asOfLabel(l)}</span>
                    </div>
                    {visible.has(l.id) && l.legend.length > 0 && (
                      <ul className="layer-legend" aria-label={`${l.title} legend`}>
                        {l.legend.map((li) => (
                          <li key={li.label}>
                            <span className={`swatch swatch-${l.style?.type}`} style={{ background: li.color, ...(li.outline ? { boxShadow: `inset 0 0 0 2px ${li.outline}` } : {}) }} aria-hidden="true" />
                            <span>{li.label}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {visible.has(l.id) && l.description && <p className="layer-desc small muted">{l.description}</p>}
                    <div className="layer-attrib muted">Source: {l.attribution}</div>
                  </li>
                );
              })}
            </ul>
          </details>
        );
      })}
    </aside>
  );
}
