import { useEffect, useRef } from "react";
import maplibregl, { type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { asOfLabel, buildMapLayers, drawable, freshnessLabel, sourceFor, type CompiledLayer, type Registry } from "./registry";
import { buildPolygonIndexIdle, type PolygonIndex } from "./map-polygons";
import { bindPopupClose, escapeHtml as esc, popupContent, popupFieldHtml } from "./popup";

// If the basemap can't load, keep the data layers usable on a plain background.
const FALLBACK_STYLE: StyleSpecification = { version: 8, sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef0f2" } }] };

async function resolveBasemap(url: string): Promise<StyleSpecification | string> {
  try { const res = await fetch(url); if (!res.ok) throw new Error(String(res.status)); return url; }
  catch { return FALLBACK_STYLE; }
}

/** One layer's section of a popup: values, then source, as-of and freshness. */
export function featureHtml(meta: CompiledLayer, properties: Record<string, unknown> | null, fields = meta.popup): string {
  const rows = fields.map((p) => `<tr><th>${esc(p.label)}</th><td>${popupFieldHtml(p, properties)}</td></tr>`).join("");
  return `<section class="inspection-layer"><div class="popup-title">${esc(meta.popup_title ?? meta.title)}</div>` +
    `<table>${rows}</table>` +
    `<div class="popup-foot">Source: ${esc(meta.attribution)} · ${esc(asOfLabel(meta))} · ${esc(freshnessLabel(meta))}</div>` +
    (meta.disclaimer ? `<div class="popup-foot">${esc(meta.disclaimer)}</div>` : "") + `</section>`;
}

export interface MapViewProps {
  registry: Registry;
  visible: ReadonlySet<string>;
  camera: { center: [number, number]; zoom: number } | null;
  onCameraChange?: (camera: { center: [number, number]; zoom: number }) => void;
}

export function MapView(props: MapViewProps) {
  const { registry, visible } = props;
  const el = useRef<HTMLDivElement>(null), mapRef = useRef<maplibregl.Map | null>(null);
  const latest = useRef(props); latest.current = props;
  const refresh = useRef<(() => void) | null>(null);

  useEffect(() => {
    let cancelled = false, map: maplibregl.Map | null = null;
    const indexes = new Map<string, PolygonIndex>(), indexing = new Set<string>(), failed = new Set<string>();
    const compiled = buildMapLayers(registry, latest.current.visible);
    const metas = new Map(drawable(registry).map((l) => [l.id, l]));
    const polygonMetas = drawable(registry).filter((l) => l.geometry === "polygon");
    let inspection: maplibregl.Popup | null = null, inspectPoint: maplibregl.LngLat | null = null;
    let clicked: { meta: CompiledLayer; properties: Record<string, unknown> | null } | null = null;
    let unbind: (() => void) | undefined;
    const layerIsVisible = (l: CompiledLayer) => latest.current.visible.has(l.id) &&
      (l.style?.minzoom == null || map!.getZoom() >= l.style.minzoom) &&
      (l.style?.maxzoom == null || map!.getZoom() < l.style.maxzoom);

    function renderInspection() {
      if (!map || !inspection || !inspectPoint) return;
      const seen = new Set<string>(), point = [inspectPoint.lng, inspectPoint.lat];
      let html = "", pending = 0, unavailable = 0;
      if (clicked && clicked.meta.geometry !== "polygon" && layerIsVisible(clicked.meta)) html += featureHtml(clicked.meta, clicked.properties);
      for (const meta of polygonMetas.filter(layerIsVisible)) {
        const id = sourceFor(meta), index = indexes.get(id);
        if (seen.has(meta.id)) continue; seen.add(meta.id);
        if (!index) { if (failed.has(id)) unavailable++; else pending++; continue; }
        for (const feature of index.query(point).features) html += featureHtml(meta, feature.properties as Record<string, unknown>);
      }
      if (!html) html = `<p>Nothing from the visible layers here.</p>`;
      if (pending) html += `<p class="muted">${pending} visible layer(s) still loading.</p>`;
      if (unavailable) html += `<p class="muted">${unavailable} visible layer(s) unavailable.</p>`;
      unbind?.();
      inspection.setHTML(popupContent(`<div class="popup map-inspection" data-testid="map-inspection"><h3>What's here?</h3>${html}</div>`));
      unbind = bindPopupClose(inspection.getElement?.(), () => inspection?.remove());
    }
    function indexSources() {
      if (!map || cancelled) return;
      for (const meta of polygonMetas) {
        const id = sourceFor(meta);
        if (indexes.has(id) || indexing.has(id) || failed.has(id) || !map.getSource(id) || !map.isSourceLoaded(id)) continue;
        indexing.add(id);
        // getData reads MapLibre's already-loaded GeoJSON; it never fetches the URL again.
        (map.getSource(id) as GeoJSONSource).getData().then((data) => buildPolygonIndexIdle(data, () => cancelled))
          .then((index) => { if (!cancelled && index) { indexes.set(id, index); renderInspection(); } })
          .catch(() => { if (!cancelled) { failed.add(id); renderInspection(); } });
      }
    }
    refresh.current = () => { indexSources(); renderInspection(); };

    (async () => {
      const style = await resolveBasemap(registry.basemap.style_url);
      if (cancelled || !el.current) return;
      const initial = latest.current.camera;
      map = new maplibregl.Map({
        container: el.current, style,
        center: initial?.center ?? (registry.basemap.center as [number, number]),
        zoom: initial?.zoom ?? registry.basemap.zoom,
        attributionControl: { compact: true, customAttribution: typeof style === "string" ? undefined : registry.basemap.attribution },
      });
      mapRef.current = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("moveend", () => {
        if (!map || cancelled) return;
        const c = map.getCenter();
        latest.current.onCameraChange?.({ center: [+c.lng.toFixed(5), +c.lat.toFixed(5)], zoom: +map.getZoom().toFixed(2) });
      });
      map.on("error", (event) => {
        const id = (event as { sourceId?: unknown }).sourceId;
        if (typeof id === "string") { failed.add(id); renderInspection(); }
        console.error(event.error);
      });
      map.on("load", () => {
        if (!map || cancelled) return;
        for (const [id, src] of Object.entries(compiled.sources)) map.addSource(id, src);
        for (const layer of compiled.layers) {
          layer.layout.visibility = latest.current.visible.has(layer.metadata.mmLayer) ? "visible" : "none";
          map.addLayer(layer as maplibregl.LayerSpecification);
        }
        map.on("click", (event) => {
          if (!map) return;
          if (inspection?.isOpen()) { inspection.remove(); return; }
          const hits = map.queryRenderedFeatures(event.point, { layers: compiled.layers.map((l) => l.id) });
          const point = hits.find((f) => metas.get((f.layer.metadata as { mmLayer: string }).mmLayer)?.geometry !== "polygon");
          clicked = point ? { meta: metas.get((point.layer.metadata as { mmLayer: string }).mmLayer)!, properties: point.properties } : null;
          inspectPoint = event.lngLat;
          inspection = new maplibregl.Popup({ closeButton: false, closeOnClick: false, maxWidth: "380px", className: "inspection-popup" })
            .setLngLat(event.lngLat);
          renderInspection(); inspection.addTo(map);
          inspection.on("close", () => { unbind?.(); unbind = undefined; inspection = null; inspectPoint = null; clicked = null; });
        });
        map.on("sourcedata", indexSources); map.on("idle", indexSources); indexSources();
        el.current?.setAttribute("data-map-ready", "true");
      });
    })();
    const observer = new ResizeObserver(() => map?.resize());
    if (el.current) observer.observe(el.current);
    return () => {
      cancelled = true; unbind?.(); observer.disconnect(); inspection?.remove();
      el.current?.removeAttribute("data-map-ready");
      map?.remove(); mapRef.current = null; refresh.current = null;
    };
  }, [registry]);

  useEffect(() => {
    const map = mapRef.current; if (!map) return;
    for (const layer of buildMapLayers(registry, visible).layers) if (map.getLayer(layer.id))
      map.setLayoutProperty(layer.id, "visibility", visible.has(layer.metadata.mmLayer) ? "visible" : "none");
    refresh.current?.();
  }, [visible, registry]);

  return <div ref={el} className="map" data-testid="map" role="region" aria-label="Map" />;
}
