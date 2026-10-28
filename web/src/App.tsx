import { useEffect, useRef, useState } from "react";
import { AboutPage, Footer, HealthPage, SourcesPage } from "./pages";
import { MethodologyPage } from "./MethodologyPage";
import { EMPTY_BENCHMARKS, type Benchmarks } from "./benchmarks";
import { HomePage } from "./homes/HomePage";
import type { Home } from "./homes/data";
import { Workspace } from "./Workspace";
import { loadJSON, type Registry } from "./registry";
import type { ViewState } from "./view-state";

function useHashRoute(): string {
  const [route, setRoute] = useState(() => window.location.hash || "#/");
  useEffect(() => {
    const on = () => setRoute(window.location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function App() {
  const hash = useHashRoute(), route = hash.split("?")[0];
  const batchPage=route==="#/home" && new URLSearchParams(hash.split("?")[1]??"").get("tab")==="many";
  const mapSnapshot=useRef<ViewState|null>(null);
  const [homeMapTarget,setHomeMapTarget]=useState<Home|null>(null);
  const showHomeOnMap=(home:Home)=>{setHomeMapTarget({...home});window.location.hash="#/";};
  const [registry, setRegistry] = useState<Registry | null>(null), [error, setError] = useState<string | null>(null);
  const [benchmarks, setBenchmarks] = useState<Benchmarks>(EMPTY_BENCHMARKS);
  useEffect(() => { Promise.all([loadJSON<Registry>("registry.json"), loadJSON<Benchmarks>("benchmarks.json").catch(() => EMPTY_BENCHMARKS)])
    .then(([reg, bench]) => { setRegistry(reg); setBenchmarks(bench); }, (e) => setError(String(e))); }, []);
  const nav = (href: string, label: string) => <a href={href} aria-current={route === href ? "page" : undefined}>{label}</a>;
  const [visitedMap,setVisitedMap]=useState(false);
  const mapPage = !["#/sources", "#/health", "#/about", "#/methodology", "#/home"].includes(route);
  useEffect(()=>{if(mapPage)setVisitedMap(true);},[mapPage]);
  return <div className="app">
    <header className="topbar"><a className="brand" href="#/">{registry?.site_title ?? "Metro Mapper"}</a>
      <nav aria-label="Pages">{nav("#/", "Map")}{nav("#/home", "Check a home")}{nav("#/sources", "Sources")}{nav("#/methodology", "Methodology")}{nav("#/health", "Health")}{nav("#/about", "About")}</nav>
    </header>
    {registry && (mapPage || visitedMap) && !batchPage && <Workspace registry={registry} benchmarks={benchmarks} active={mapPage} homeTarget={homeMapTarget} initialSnapshot={mapSnapshot.current} onSnapshot={view=>{mapSnapshot.current=view;}} />}
    {mapPage && !registry && <main className="page">{error ? <p className="error">The layer list couldn't load ({error}).</p> : <p>Loading…</p>}</main>}
    {route === "#/home" && <HomePage hash={hash} registry={registry} onShowMap={showHomeOnMap} />}
    {route === "#/sources" && <SourcesPage registry={registry} error={error} />}
    {route === "#/health" && <HealthPage />}
    {route === "#/about" && <AboutPage />}
    {route === "#/methodology" && <MethodologyPage />}
    <Footer />
  </div>;
}
