"""Compile layers/*.yaml into web/public/registry.json.

The site builds its layer list, toggles, legends, popups, attribution and as-of
badges from this file alone. Checks performed here:
  - every manifest validates against its schema, and ids match file names
  - ids are unique; every layer's source is an existing adapter
  - as_of and freshness come from the run log, never from the manifest
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import adapter as adapter_mod
from . import config, layer_guard, runlog
from .manifests import ManifestError, load_layers
from .paths import paths
from .publish import data_url, published_exists
from .schemas import (
    FRESHNESS_HOURS,
    BasemapConfig,
    CompiledLayer,
    Freshness,
    IngestionRun,
    LayerManifest,
    Registry,
)


def freshness(refresh: str, runs: list[IngestionRun], now: datetime) -> tuple[Freshness, IngestionRun | None]:
    """Only live runs make data fresh. Fixture runs give 'fixture_only' so the site
    never presents test data as current."""
    live = [r for r in runs if r.mode == "live" and r.status != "skipped"]
    if not live:
        fx = [r for r in runs if r.status == "success"]
        return ("fixture_only", fx[-1]) if fx else ("never_run", None)
    # Partial runs (budget or time limit reached) publish nothing, so only successes count.
    ok = [r for r in live if r.status == "success"]
    last_ok = ok[-1] if ok else None
    if last_ok is None:
        return "failing", None
    hours = FRESHNESS_HOURS.get(refresh)
    if hours is None:
        return "not_scheduled", last_ok
    if now - last_ok.finished_at > timedelta(hours=hours):
        return "stale", last_ok
    if live[-1].status == "failed":
        # A held refresh kept the previous data on the map: show it as stale, not failing.
        return ("stale" if layer_guard.is_held(live[-1]) else "failing"), last_ok
    return "fresh", last_ok


def compile_registry(now: datetime | None = None, write: bool = True) -> Registry:
    now = now or runlog.utcnow()
    layers = load_layers()

    seen: set[str] = set()
    for it in layers:
        if it.id in seen:
            raise ManifestError(f"duplicate layer id '{it.id}'")
        seen.add(it.id)

    known_adapters = set(adapter_mod.available())
    for layer in layers:
        if layer.source not in known_adapters:
            raise ManifestError(
                f"layer '{layer.id}': source adapter '{layer.source}' not found in adapters/"
            )

    all_runs = runlog.read_all()
    compiled: list[CompiledLayer] = []
    for layer in sorted(layers, key=lambda l: (l.order, l.id)):
        runs = runlog.for_adapter(layer.source, all_runs)
        fresh, last_ok = freshness(layer.refresh, runs, now)
        as_of = None
        if last_ok is not None:
            as_of = (last_ok.source_as_of or last_ok.finished_at.date()).isoformat()
        url = data_url(layer.id, layer.publish) if published_exists(layer.id, layer.publish) else None
        compiled.append(CompiledLayer(
            **layer.model_dump(),
            data_url=url,
            as_of=as_of,
            last_success=last_ok.finished_at.isoformat() if last_ok else None,
            freshness=fresh,
        ))

    app = config.app_config()
    groups: list[str] = []
    for l in compiled:
        if l.group not in groups:
            groups.append(l.group)

    reg = Registry(
        site_title=app.site_title,
        compiled_at=now.isoformat(),
        basemap=BasemapConfig(
            style_url=app.basemap_style_url,
            attribution=app.basemap_attribution,
            center=app.center,
            zoom=app.zoom,
        ),
        groups=groups,
        layers=compiled,
    )
    if write:
        out = paths().registry_json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(reg.model_dump_json(indent=2))
    return reg


def layer_by_id(layer_id: str) -> LayerManifest:
    for l in load_layers():
        if l.id == layer_id:
            return l
    raise KeyError(layer_id)


def export_schemas() -> list[str]:
    from .schemas import EXPORTED_MODELS

    out_dir = paths().schemas
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in EXPORTED_MODELS.items():
        p = out_dir / f"{name}.schema.json"
        p.write_text(json.dumps(model.model_json_schema(mode="serialization"), indent=2, sort_keys=True) + "\n")
        written.append(str(p.relative_to(paths().root)))
    return written
