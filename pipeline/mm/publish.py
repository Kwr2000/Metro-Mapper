"""Publishers turn canonical records into the files the site loads.

GeoJSON is implemented. PMTiles is added when the first layer needs it; manifests
can already name it.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from . import layer_guard
from .manifests import load_layers
from .paths import paths
from .privacy import check_properties
from .schemas import AreaFeature, LayerManifest


def selected(layer: LayerManifest, r: AreaFeature) -> bool:
    if layer.dataset is not None and r.dataset != layer.dataset:
        return False
    return all(r.properties.get(k) == v for k, v in layer.where.items())


def file_id(layer: LayerManifest) -> str:
    """Layers that share a `data_bundle` share one published file, named after the bundle."""
    return layer.data_bundle or layer.id


def published_path(layer: LayerManifest) -> Path:
    return paths().published_layers / f"{file_id(layer)}.geojson"


def _geojson(layer: LayerManifest, records: list[BaseModel]) -> dict:
    feats = []
    dates: list[date] = []
    keys: set[str] = set()
    for r in records:
        if isinstance(r, AreaFeature) and selected(layer, r):
            if r.source_as_of:
                dates.append(r.source_as_of)
            keys.update(r.properties)
            feats.append({
                "type": "Feature",
                "id": r.feature_id,
                "geometry": r.geometry,
                "properties": {"feature_id": r.feature_id, **r.properties},
            })
    check_properties(f"layer {layer.id}", keys)
    feats.sort(key=lambda f: str(f["id"]))
    return {"type": "FeatureCollection", "features": feats,
            "source_as_of": min(dates).isoformat() if dates else None}


def _json_default(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def publish_for_adapter(adapter_id: str, entity: str, records: list[BaseModel],
                        mode: str = "fixture", source_as_of: date | None = None,
                        keep_stale_flag: bool = True) -> list[str]:
    """`keep_stale_flag=False` is for a fresh live run publishing its own new data."""
    written: list[str] = []
    done: set[str] = set()
    for layer in load_layers():
        if layer.source != adapter_id or layer.publish == "none":
            continue
        if file_id(layer) in done:
            continue  # a shared bundle file is written once
        done.add(file_id(layer))
        if layer.publish != "geojson":
            raise NotImplementedError(f"layer {layer.id}: publisher '{layer.publish}' is not built yet")
        if entity != "area_feature":
            raise ValueError(f"layer {layer.id}: geojson publishing needs area_feature records")
        out = published_path(layer)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc = _geojson(layer, records)
        doc["test_data"] = mode == "fixture"
        if source_as_of is not None:
            doc["source_as_of"] = source_as_of.isoformat()
        if keep_stale_flag and mode == "live" and (stale := layer_guard.stale_info(adapter_id)):
            doc.update(stale)  # the last refresh was held; keep showing this data as stale
        out.write_text(json.dumps(doc, default=_json_default, separators=(",", ":")))
        written.append(str(out.relative_to(paths().root)))
    return written


def data_url(layer_id: str, publish_kind: str) -> str | None:
    if publish_kind == "geojson":
        return f"data/layers/{layer_id}.geojson"
    if publish_kind == "pmtiles":
        return f"data/layers/{layer_id}.pmtiles"
    return None


def published_exists(layer_id: str, publish_kind: str) -> bool:
    url = data_url(layer_id, publish_kind)
    return bool(url) and (paths().web_public / Path(url)).is_file()
