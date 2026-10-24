import { useCallback, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import { loadJSON, type CompiledLayer } from "./registry";
import type { LayerData } from "./areas";

/** One local publication per bundle, shared by map, filters and comparison. */
export function useLayerData() {
  const [data, setData] = useState<LayerData>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const requests = useRef(new Map<string, Promise<void>>());
  const ensure = useCallback((layer: CompiledLayer) => {
    const url = layer.data_url; if (!url || requests.current.has(url)) return;
    // Publication paths only: a registry entry cannot cause an external data request.
    if (!/^data\/layers\/[a-z0-9_]+\.geojson$/.test(url)) {
      setErrors((old) => ({ ...old, [url]: "Unsupported publication path" })); return;
    }
    requests.current.set(url, loadJSON<FeatureCollection>(url).then((doc) => {
      if (doc.type !== "FeatureCollection" || !Array.isArray(doc.features)) throw new Error("Invalid publication");
      setData((old) => ({ ...old, [url]: doc }));
    }).catch(() => { setErrors((old) => ({ ...old, [url]: "Data could not load. Reload the page to retry." })); }));
  }, []);
  return { data, errors, ensure };
}
