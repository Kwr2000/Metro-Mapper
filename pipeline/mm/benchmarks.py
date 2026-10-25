"""Validated, non-spatial source comparisons, published independently of map features."""
from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from .paths import paths
from .privacy import check_properties
from .schemas import AreaFeature

GEOGRAPHIES = ("us", "texas", "austin_metro", "austin_city", "travis", "williamson", "hays",
               "peer_cities", "austin_pd_area", "texas_cities_100k", "three_county")
EMPTY = {"type": "GeometryCollection", "geometries": []}


class Benchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    geography: str
    label: str
    value: float
    moe: float | None
    period: str
    source: str
    note: str | None
    display: str | None = None  # Capped Census medians must remain ranges.

    @field_validator("value", "moe", mode="before")
    @classmethod
    def finite_number(cls, v):
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
            raise ValueError("benchmark must be a finite number")
        return v

    @field_validator("moe")
    @classmethod
    def nonnegative_moe(cls, v):
        if v is not None and v < 0:
            raise ValueError("benchmark MOE must be nonnegative")
        return v

    @field_validator("geography")
    @classmethod
    def known_geography(cls, v):
        if v not in GEOGRAPHIES:
            raise ValueError("unknown benchmark geography")
        return v


def record(field, geography, label, value, period, source, *, moe=None, note=None, display=None, as_of=None):
    props = Benchmark(field=field, geography=geography, label=label, value=value, moe=moe,
                      period=period, source=source, note=note, display=display).model_dump()
    return AreaFeature(dataset="benchmark", feature_id=f"{field}|{geography}", geometry=EMPTY,
                       properties=props, source_as_of=as_of)


def validate(records):
    out, seen = [], set()
    for r in records:
        if not isinstance(r, AreaFeature) or r.dataset != "benchmark":
            continue
        check_properties("benchmark", r.properties)
        props = Benchmark.model_validate(r.properties).model_dump()
        check_properties("benchmark field", [props["field"]])
        if r.geometry != EMPTY or r.feature_id != f"{props['field']}|{props['geography']}" or r.feature_id in seen:
            raise ValueError("invalid/duplicate non-spatial benchmark identity")
        seen.add(r.feature_id)
        out.append(props)
    return out


def publish(adapter_id, records, mode):
    """Per-producer safe publications keep independent runs and fixture/live provenance."""
    from . import adapter
    props = validate(records)
    target = getattr(adapter.load(adapter_id), "benchmark_source", adapter_id) if adapter_id in adapter.available() else adapter_id
    folder = paths().web_public / "data" / "benchmarks"
    folder.mkdir(parents=True, exist_ok=True)
    producer = {"source": target, "test_data": mode == "fixture", "records": props}
    cached = {p.stem: json.loads(p.read_text()) for p in folder.glob("*.json") if p.stem != adapter_id}
    cached[adapter_id] = producer
    document, fixture, seen = {}, False, set()
    for name, item in sorted(cached.items()):
        for row in item["records"]:
            check_properties("benchmark", row)
            p = Benchmark.model_validate(row).model_dump()
            identity = (item["source"], p["field"], p["geography"])
            if identity in seen:
                raise ValueError("duplicate benchmark across producers")
            seen.add(identity)
            document.setdefault(item["source"], {}).setdefault(p["field"], []).append(p)
            fixture |= item["test_data"]
    for fields in document.values():
        for rows in fields.values():
            rows.sort(key=lambda p: GEOGRAPHIES.index(p["geography"]))
    document["test_data"] = fixture
    payload = json.dumps(document, allow_nan=False, separators=(",", ":"))
    (folder / f"{adapter_id}.json").write_text(json.dumps(producer, allow_nan=False))
    (paths().web_public / "benchmarks.json").write_text(payload)
