"""The canonical store: validated records of each adapter's last good live run.

One gzipped NDJSON file per adapter (data/canonical/<entity>/<adapter>.ndjson.gz),
written deterministically (sorted, fixed gzip header time) so an unchanged refresh
makes no git diff. `mm publish` republishes from here without any network call.
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

from pydantic import BaseModel

from .paths import paths
from .schemas import ENTITY_MODELS


def path_for(entity: str, adapter_id: str) -> Path:
    return paths().canonical / entity / f"{adapter_id}.ndjson.gz"


def write(entity: str, adapter_id: str, records: list[BaseModel]) -> Path:
    out = path_for(entity, adapter_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = sorted(r.model_dump_json() for r in records)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("\n".join(lines) + ("\n" if lines else "")).encode())
    out.write_bytes(buf.getvalue())
    return out


def read(entity: str, adapter_id: str) -> list[BaseModel] | None:
    p = path_for(entity, adapter_id)
    if not p.is_file():
        return None
    model = ENTITY_MODELS[entity]
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [model.model_validate(json.loads(line)) for line in f if line.strip()]
