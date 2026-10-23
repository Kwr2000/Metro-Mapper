"""Keep a good map layer when a live refresh comes back empty or sharply smaller.

A live run is compared, layer by layer, with what is currently published. If a layer
that had features would be replaced by none, or by fewer than MIN_RATIO of them (when
it had at least MIN_PREVIOUS), the run publishes nothing and does not touch the
canonical copy: the previous data stays on the map, the run is logged as failed with a
HELD_MARKER error (a warning in Actions), the registry shows the layer as "stale", and
the published file carries `stale: true` until a good refresh replaces it.

A real, accepted drop is let through for one manual run with
`MM_ACCEPT_LAYER_DROP=<adapter id> mm run --adapter <id> --mode live`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from pydantic import BaseModel

from . import runlog
from .manifests import load_layers
from .paths import paths
from .schemas import AreaFeature, IngestionRun

MIN_RATIO = 0.5
MIN_PREVIOUS = 20
HELD_MARKER = "held previous data"
ACCEPT_ENV = "MM_ACCEPT_LAYER_DROP"


@dataclass(frozen=True)
class Drop:
    layer_id: str
    previous: int
    new: int

    def describe(self) -> str:
        return f"{self.layer_id} {self.previous} -> {self.new} features"


def _published(layer) -> dict | None:
    from .publish import published_path

    p = published_path(layer)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def drops(adapter_id: str, records: list[BaseModel]) -> list[Drop]:
    """Layers of this adapter that the new records would empty or sharply shrink."""
    from .publish import selected

    if os.environ.get(ACCEPT_ENV) == adapter_id:
        return []
    out = []
    for layer in load_layers():
        if layer.source != adapter_id or layer.publish != "geojson":
            continue
        prev_doc = _published(layer)
        if not prev_doc or prev_doc.get("test_data"):
            continue  # nothing live to protect (missing or fixture data)
        prev = len(prev_doc.get("features") or [])
        if prev == 0:
            continue  # an empty layer stays a valid empty layer
        new = sum(1 for r in records if isinstance(r, AreaFeature) and selected(layer, r))
        if new == 0 or (prev >= MIN_PREVIOUS and new < MIN_RATIO * prev):
            out.append(Drop(layer.id, prev, new))
    return out


def held_message(found: list[Drop]) -> str:
    return (f"{HELD_MARKER}: " + "; ".join(d.describe() for d in found)
            + f" (below {MIN_RATIO:.0%} of previous or empty); layer kept and marked stale")


def is_held(run: IngestionRun) -> bool:
    return run.status == "failed" and any(e.startswith(HELD_MARKER) for e in run.errors)


def stale_info(adapter_id: str) -> dict | None:
    """Published-file stale fields if this adapter's latest live runs were held, else None."""
    live = [r for r in runlog.for_adapter(adapter_id) if r.mode == "live"]
    streak = []
    for r in reversed(live):
        if not is_held(r):
            break
        streak.append(r)
    if not streak:
        return None
    reason = next(e for e in streak[0].errors if e.startswith(HELD_MARKER))
    return {"stale": True, "stale_reason": reason, "stale_since": streak[-1].started_at.isoformat()}


def mark_stale(adapter_id: str, info: dict) -> None:
    """Flag this adapter's published layers as stale, keeping their features."""
    for layer in load_layers():
        if layer.source != adapter_id or layer.publish != "geojson":
            continue
        from .publish import published_path

        doc = _published(layer)
        if doc is None:
            continue
        doc.update(info)
        published_path(layer).write_text(json.dumps(doc, separators=(",", ":")))
