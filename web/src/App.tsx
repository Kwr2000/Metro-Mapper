import { useEffect, useState } from "react";
import { AboutPage, Footer, HealthPage, SourcesPage } from "./pages";
import { MethodologyPage } from "./MethodologyPage";
import { EMPTY_BENCHMARKS, type Benchmarks } from "./benchmarks";
import { Workspace } from "./Workspace";
import { loadJSON, type Registry } from "./registry";

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
  const [registry, setRegistry] = useState<Registry | null>(null), [error, setError] = useState<string | null>(null);
  const [benchmarks, setBenchmarks] = useState<Benchmarks>(EMPTY_BENCHMARKS);
  useEffect(() => { Promise.all([loadJSON<Registry>("registry.json"), loadJSON<Benchmarks>("benchmarks.json").catch(() => EMPTY_BENCHMARKS)])
    .then(([reg, bench]) => { setRegistry(reg); setBenchmarks(bench); }, (e) => setError(String(e))); }, []);
  const nav = (href: string, label: string) => <a href={href} aria-current={route === href ? "page" : undefined}>{label}</a>;
  const mapPage = !["#/sources", "#/health", "#/about", "#/methodology"].includes(route);
  return <div className="app">
    <header className="topbar"><a className="brand" href="#/">{registry?.site_title ?? "Metro Mapper"}</a>
      <nav aria-label="Pages">{nav("#/", "Map")}{nav("#/sources", "Sources")}{nav("#/methodology", "Methodology")}{nav("#/health", "Health")}{nav("#/about", "About")}</nav>
    </header>
    {registry && <Workspace registry={registry} benchmarks={benchmarks} active={mapPage} />}
    {mapPage && !registry && <main className="page">{error ? <p className="error">The layer list couldn't load ({error}).</p> : <p>Loading…</p>}</main>}
    {route === "#/sources" && <SourcesPage registry={registry} error={error} />}
    {route === "#/health" && <HealthPage />}
    {route === "#/about" && <AboutPage />}
    {route === "#/methodology" && <MethodologyPage />}
    <Footer />
  </div>;
}
