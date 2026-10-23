"""Demo adapter that proves the seams. Delete it, together with
layers/demo_landmarks.yaml, once real layers exist.

It reads a bundled file of three public landmarks and emits area_feature records.
It makes no network calls in any mode.
"""

from __future__ import annotations

import json
from datetime import date

from mm.adapter import RawPayload, Request, RunContext, SourceAdapter
from mm.schemas import AreaFeature


class DemoPoints(SourceAdapter):
    id = "demo_points"
    entity = "area_feature"
    cadence = "manual"

    def plan(self, ctx: RunContext) -> list[Request]:
        return [Request(key="landmarks")]

    def fetch(self, req: Request, ctx: RunContext) -> RawPayload:
        # "Live" for this adapter is the bundled file: there is no remote source.
        doc = json.loads((ctx.adapter_dir / "fixtures" / f"{req.key}.json").read_text())
        return RawPayload(request=req, body=doc["body"], fetched_at=ctx.now)

    def normalize(self, raw: RawPayload):
        for row in raw.body["places"]:
            yield AreaFeature(
                dataset="landmarks",
                feature_id=row["slug"],
                geometry={"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                properties={"name": row["name"], "kind": row["kind"], "county": row["county"]},
                source_as_of=date.fromisoformat(raw.body["as_of"]),
            )

    def source_as_of(self, raws: list[RawPayload]) -> date | None:
        return date.fromisoformat(raws[0].body["as_of"]) if raws else None


ADAPTER = DemoPoints
