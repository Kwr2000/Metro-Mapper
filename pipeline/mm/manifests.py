"""Load and validate layer manifests (one YAML file each in layers/)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from .paths import paths
from .schemas import LayerManifest


class ManifestError(ValueError):
    pass


def _load_dir(folder: Path, model: type[BaseModel]) -> list:
    if not folder.exists():
        return []
    items = []
    for f in sorted(folder.glob("*.yaml")):
        try:
            doc = yaml.safe_load(f.read_text()) or {}
            item = model.model_validate(doc)
        except (ValidationError, yaml.YAMLError) as e:
            raise ManifestError(f"{f.relative_to(paths().root)}: {e}") from e
        if item.id != f.stem:
            raise ManifestError(f"{f.name}: id '{item.id}' must match the file name '{f.stem}'")
        items.append(item)
    return items


def load_layers() -> list[LayerManifest]:
    layers = _load_dir(paths().layers, LayerManifest)
    bundles: dict[str, tuple] = {}
    variants: set[tuple] = set()
    for layer in layers:
        if layer.data_bundle:
            scope = (layer.source, layer.dataset, layer.geometry, layer.publish,
                     tuple(sorted(layer.where.items())))
            if layer.data_bundle in bundles and bundles[layer.data_bundle] != scope:
                raise ManifestError(f"{layer.id}: shared data bundle has inconsistent feature selection")
            bundles[layer.data_bundle] = scope
        if layer.variant:
            key = (layer.group, layer.variant.family, layer.variant.key)
            if key in variants:
                raise ManifestError(f"{layer.id}: duplicate layer variant")
            variants.add(key)
    ids = {layer.id for layer in layers}
    for bundle in bundles:
        if bundle in ids:
            raise ManifestError(f"data bundle '{bundle}' has the same name as a layer id")
    return layers
