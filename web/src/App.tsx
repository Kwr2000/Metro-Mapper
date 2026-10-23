import { useCallback, useEffect, useState } from "react";
import { LayerPanel } from "./LayerPanel";
import { MapView } from "./MapView";
import { normalizeLayerVariants, switchLayerVariant } from "./layer-variants";
import { AboutPage, Footer, HealthPage, SourcesPage } from "./pages";
import { initialVisible, loadJSON, showsTestData, type Registry } from "./registry";
import { readLocal, writeLocal } from "./store";

type Camera = { center: [number, number]; zoom: number };

function useHashRoute(): string {
  const [route, setRoute] = useState(() => window.location.hash || "#/");
  useEffect(() => {
    const on = () => setRoute(window.location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route.split("?")[0];
}

export function App() {
  const route = useHashRoute();
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState<Set<string>>(new Set());
  const [camera, setCamera] = useState<Camera | null>(() => readLocal<Camera | null>("camera", null));
  const [pane, setPane] = useState<"map" | "layers">("map");

  useEffect(() => {
    loadJSON<Registry>("registry.json").then((r) => {
      const known = new Set(r.layers.map((l) => l.id));
      const saved = readLocal<string[] | null>("visible", null)?.filter((id) => known.has(id));
      setVisible(normalizeLayerVariants(r, saved ? new Set(saved) : initialVisible(r)));
      setRegistry(r);
    }, (e) => setError(String(e)));
  }, []);

  const update = useCallback((next: Set<string>) => { setVisible(next); writeLocal("visible", [...next]); }, []);
  const toggle = useCallback((id: string) => {
    const next = new Set(visible);
    if (next.has(id)) next.delete(id); else next.add(id);
    update(next);
  }, [visible, update]);
  const onCamera = useCallback((c: Camera) => { setCamera(c); writeLocal("camera", c); }, []);

  const nav = (href: string, label: string) => (
    <a href={href} aria-current={route === href ? "page" : undefined}>{label}</a>
  );
  let body;
  if (route === "#/sources") body = <SourcesPage registry={registry} error={error} />;
  else if (route === "#/health") body = <HealthPage />;
  else if (route === "#/about") body = <AboutPage />;
  else if (error) body = <main className="page"><p className="error">The map's layer list couldn't load ({error}).</p></main>;
  else if (!registry) body = <main className="page"><p className="muted">Loading…</p></main>;
  else body = (
    <>
      <nav className="workspace-tabs" aria-label="Workspace views">
        <button aria-pressed={pane === "map"} onClick={() => setPane("map")}>Map</button>
        <button aria-pressed={pane === "layers"} onClick={() => setPane("layers")}>Layers</button>
      </nav>
      <div className={`workspace pane-${pane}`}>
        <LayerPanel registry={registry} visible={visible} onToggle={toggle}
          onSwitchVariant={(group, key) => update(switchLayerVariant(registry, visible, group, key))} />
        <div className="map-wrap">
          {showsTestData(registry, visible) && (
            <div className="test-banner" role="status" data-testid="test-banner">
              Test data: some visible layers show made-up sample data, not real data.
            </div>
          )}
          <MapView registry={registry} visible={visible} camera={camera} onCameraChange={onCamera} />
        </div>
      </div>
    </>
  );

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">{registry?.site_title ?? "Metro Mapper"}</a>
        <nav aria-label="Pages">
          {nav("#/", "Map")}
          {nav("#/sources", "Sources")}
          {nav("#/health", "Health")}
          {nav("#/about", "About")}
        </nav>
      </header>
      {body}
      <Footer />
    </div>
  );
}
