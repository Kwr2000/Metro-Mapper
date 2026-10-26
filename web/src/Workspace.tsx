import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chooseColour } from "./colour";
import { LayerPanel } from "./LayerPanel";
import { MapView } from "./MapView";
import { FiltersPanel } from "./FiltersPanel";
import { CompareTable, CompareTray } from "./ComparePanel";
import { ShortlistPanel } from "./ShortlistPanel";
import { addCompare, areaLayer, areaName, blockGroupLayers, featuresFor, featureId, filterLayers, interiorPoint, matchAreas } from "./areas";
import { normalizeLayerVariants, switchLayerVariant } from "./layer-variants";
import { asOfLabel, initialVisible, showsTestData, type Registry } from "./registry";
import { readLocal, readShortlist, storageAvailable, writeLocal, type SavedArea } from "./store";
import { encodeView, readView, registryView, type Camera, type ViewState } from "./view-state";
import { EMPTY_BENCHMARKS, type Benchmarks } from "./benchmarks";
import { useLayerData } from "./use-layer-data";

function initialView(registry: Registry, benchmarks: Benchmarks): ViewState {
  const shared = readView(window.location.hash);
  if (shared) return registryView(shared, registry, benchmarks);
  const saved = readLocal<unknown>("visible", null);
  const known = new Set(registry.layers.map((l) => l.id));
  const visible = Array.isArray(saved) ? saved.filter((id) => typeof id === "string" && known.has(id)) :
    [...initialVisible(registry)].filter((id) => !registry.layers.find((l) => l.id === id)?.demographic);
  const raw: ViewState = { camera: readLocal<Camera>("camera", { center: registry.basemap.center as [number, number], zoom: registry.basemap.zoom }),
    visible, variants: {}, filters: {}, compare: [], colour: {} };
  return registryView(readView(encodeView(raw))!, registry, benchmarks);
}

export function Workspace({ registry, active, benchmarks = EMPTY_BENCHMARKS }: { registry: Registry; active: boolean; benchmarks?: Benchmarks }) {
  const [view, setView] = useState<ViewState>(() => initialView(registry, benchmarks));
  const visible = useMemo(() => normalizeLayerVariants(registry, new Set(view.visible)), [registry, view.visible]);
  const [pane, setPane] = useState("Layers"), [expanded, setExpanded] = useState(true);
  const [selected, setSelected] = useState<string | null>(null), [message, setMessage] = useState("");
  const [compareOpen, setCompareOpen] = useState(false);
  const [saved, setSaved] = useState<SavedArea[]>(readShortlist), [persistent, setPersistent] = useState(storageAvailable);
  const [share, setShare] = useState(false);
  const tools = useRef<HTMLElement>(null), [bottomInset, setBottomInset] = useState(0);
  const { data, errors, ensure } = useLayerData();
  const base = areaLayer(registry);
  const areas = useMemo(() => base ? featuresFor(base, data) : [], [base, data]);
  const filterable = useMemo(() => filterLayers(registry), [registry]);
  const result = useMemo(() => matchAreas(areas, filterable, view.filters, data), [areas, filterable, view.filters, data]);
  const activeFilters = filterable.filter((l) => view.filters[l.id]);
  const filterReady = activeFilters.every((l) => l.data_url && data[l.data_url]);
  const filterFailed = activeFilters.some((l) => l.data_url && errors[l.data_url]);
  const update = useCallback((patch: Partial<ViewState>) => setView((old) => ({ ...old, ...patch })), []);

  useEffect(() => {
    const element = tools.current; if (!element || typeof ResizeObserver === "undefined") return;
    const measure = () => setBottomInset(window.innerWidth <= 760 ? element.getBoundingClientRect().height + 16 : 0);
    const observer = new ResizeObserver(measure); observer.observe(element); measure();
    window.addEventListener("resize", measure);
    return () => { observer.disconnect(); window.removeEventListener("resize", measure); };
  }, []);

  useEffect(() => {
    if (base) ensure(base);
    for (const layer of registry.layers) if (visible.has(layer.id) || view.filters[layer.id] ||
        (compareOpen && blockGroupLayers(registry).includes(layer))) ensure(layer);
  }, [base, registry, visible, view.filters, compareOpen, ensure]);

  useEffect(() => {
    const restore = () => { const shared = readView(window.location.hash); if (shared) setView(registryView(shared, registry, benchmarks)); };
    window.addEventListener("hashchange", restore);
    return () => window.removeEventListener("hashchange", restore);
  }, [registry, benchmarks]);
  useEffect(() => {
    if (active) window.history.replaceState(null, "", encodeView({ ...view, visible: [...visible] }));
  }, [active, view, visible]);

  const onCameraChange = useCallback((camera: Camera) => { update({ camera }); writeLocal("camera", camera); }, [update]);
  const changeVisible = (next: Set<string>) => { update({ visible: [...next] }); writeLocal("visible", [...next]); };
  const toggle = (id: string) => { const next = new Set(visible); if (next.has(id)) next.delete(id); else next.add(id); changeVisible(next); };
  const compare = (id: string) => { const next = addCompare(view.compare, id); update({ compare: next.ids }); setMessage(next.message); };
  const save = (id: string) => {
    if (saved.some((s) => s.id === id)) { setMessage("Already saved in your shortlist."); return; }
    const area = areas.find((f) => featureId(f) === id); if (!area) return;
    const next = [...saved, { id, name: areaName(area), note: "" }];
    setSaved(next); setPersistent(writeLocal("shortlist", next)); setMessage("Area saved. Add a private note in Shortlist.");
  };
  const fly = (id: string) => {
    const area = areas.find((f) => featureId(f) === id), point = area ? interiorPoint(area) : null;
    if (!point) { setMessage("This area is not available in the loaded boundaries."); return; }
    update({ camera: { center: point, zoom: Math.max(12, view.camera?.zoom ?? 12) } });
    setSelected(id); setExpanded(false);
  };
  const chosen = areas.find((f) => featureId(f) === selected);
  const count = areas.length ? `${result.matches.size.toLocaleString()} of ${areas.length.toLocaleString()} areas match` : "Loading areas…";

  return <div className="workspace-shell" hidden={!active}>
    <div className="workspace-toolbar"><strong aria-live="polite" data-testid="match-count">{filterFailed ? "Filter data unavailable" : activeFilters.length && !filterReady ? "Loading filters…" : count}</strong>
      <button onClick={() => setShare(!share)}>Share view</button></div>
    {share && <label className="share-link small">View link (no notes or shortlist)<input aria-label="View link" readOnly value={new URL(encodeView({ ...view, visible: [...visible] }), window.location.href).href} onFocus={(e) => e.target.select()} /></label>}
    <div className="workspace">
      <aside ref={tools} className={`workbench ${expanded ? "expanded" : "collapsed"}`} aria-label="Area tools">
        <nav className="tool-tabs" aria-label="Area tools tabs">{["Layers", "Filters", "Compare", "Shortlist"].map((name) =>
          <button key={name} aria-pressed={pane === name && expanded} onClick={() => { setExpanded(pane === name ? !expanded : true); setPane(name); }}>{name}{name === "Compare" && view.compare.length ? ` (${view.compare.length})` : ""}</button>)}</nav>
        <div className="tool-body">
          <div hidden={pane !== "Layers"}><LayerPanel colour={view.colour} benchmarks={benchmarks} onColour={(layer, geo) => update({ colour: chooseColour(registry, view.colour, layer, geo) })} registry={registry} visible={visible} onToggle={toggle} choices={view.variants}
            onSwitchVariant={(group, key) => { update({ visible: [...switchLayerVariant(registry, visible, group, key)], variants: { ...view.variants, [group]: key } }); }} /></div>
          <div hidden={pane !== "Filters"}><FiltersPanel registry={registry} filters={view.filters} data={data} errors={errors} missing={result.missing} onChange={(filters) => update({ filters })} /></div>
          <div hidden={pane !== "Compare"}><CompareTray areas={areas} ids={view.compare} onRemove={(id) => update({ compare: view.compare.filter((x) => x !== id) })} onOpen={() => setCompareOpen(true)} />
            <div className="area-picker"><label>Choose area<select aria-label="Choose area" value={selected ?? ""} onChange={(e) => setSelected(e.target.value || null)}>
              <option value="">Select an area</option>{areas.map((f) => <option key={featureId(f)} value={featureId(f)}>{areaName(f)} · {featureId(f)}</option>)}
            </select></label><button disabled={!selected} onClick={() => selected && compare(selected)}>Add selected area to compare</button>
              <button disabled={!selected} onClick={() => selected && save(selected)}>Save selected area</button></div>
          </div>
          <div hidden={pane !== "Shortlist"}><ShortlistPanel saved={saved} persistent={persistent} onChange={(next) => { setSaved(next); setPersistent(writeLocal("shortlist", next)); }}
            onFly={fly} onCompare={() => { update({ compare: saved.slice(0, 4).map((s) => s.id) }); setPane("Compare"); setExpanded(true); }} /></div>
          {message && !chosen && <p className="action-message" role="status">{message}</p>}
        </div>
      </aside>
      <div className="map-wrap">
        {(benchmarks.test_data || showsTestData(registry, new Set([...visible, ...Object.keys(view.filters)]))) && <div className="test-banner" data-testid="test-banner" role="status">Test data: some displayed values are made-up samples, not real data.</div>}
        {base?.data_url && errors[base.data_url] && <p className="map-error" role="alert">{errors[base.data_url]}</p>}
        <MapView colour={view.colour} benchmarks={benchmarks} registry={registry} visible={visible} camera={view.camera} onCameraChange={onCameraChange} data={data}
          bottomInset={bottomInset} areas={areas} matches={activeFilters.length && filterReady ? result.matches : null} onSelectArea={(id) => {
            setSelected(id); setMessage("");
            // On a phone the tools sheet covers the lower map: fold it so the popup is visible.
            if (window.matchMedia?.("(max-width: 760px)").matches) setExpanded(false);
          }} />
        {chosen && <section className="selected-area" aria-label="Selected area"><button className="close-selection" aria-label="Close selected area" onClick={() => setSelected(null)}>×</button>
          <div className="selected-head"><strong>{areaName(chosen)}</strong>
            <span className="small muted" title={`Source: ${base?.attribution ?? ""}`}>{featureId(chosen)} · {base && asOfLabel(base)}</span></div>
          <div className="selected-actions"><button onClick={() => compare(featureId(chosen))}>Add to compare</button><button onClick={() => save(featureId(chosen))}>Save area</button></div>
          {message && <p className="small" role="status">{message}</p>}
        </section>}
      </div>
    </div>
    {compareOpen && <CompareTable benchmarks={benchmarks} registry={registry} areas={areas} ids={view.compare} data={data} errors={errors} onClose={() => setCompareOpen(false)} />}
  </div>;
}
