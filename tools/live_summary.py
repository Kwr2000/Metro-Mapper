"""Summarize one adapter's latest live run and the layers it published, for review.

Prints Markdown: run status, calls, errors, and per layer the feature count, as-of date,
null counts per property, value counts for low-cardinality text properties and
min/median/max for numbers. Reads only local files (no network). Published files have
already passed the personal-data guard, so nothing personal can appear here.

Usage: python tools/live_summary.py <adapter id>
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter

from mm import canonical, runlog
from mm.manifests import load_layers
from mm.publish import published_path


def main(adapter_id: str) -> int:
    runs = [r for r in runlog.for_adapter(adapter_id) if r.mode == "live"]
    out = [f"# Live run: `{adapter_id}`", ""]
    if not runs:
        out.append("No live run recorded.")
        print("\n".join(out))
        return 0
    r = runs[-1]
    out += [f"- status **{r.status}**, calls {r.calls_made}/{r.planned_calls}, rows {r.rows_out}, "
            f"source as of {r.source_as_of or '—'}, {int((r.finished_at - r.started_at).total_seconds())} s"]
    out += [f"- note: {n}" for n in r.notes]
    out += [f"- error: {e.splitlines()[0][:300]}" for e in r.errors if e.strip()]
    if adapter_id in {"apd", "access", "dps_agency", "elections", "parcels", "tcad", "wcad", "hays_cad"} and r.status == "success":
        for record in canonical.read("area_feature", adapter_id) or []:
            if record.dataset == "run_summary" and record.source_as_of == r.source_as_of:
                out += [f"- note: {key}={value}" for key, value in record.properties.items()]
    for layer in load_layers():
        if layer.source != adapter_id:
            continue
        p = published_path(layer)
        out += ["", f"## Layer `{layer.id}`"]
        if not p.is_file():
            out.append("Not published.")
            continue
        doc = json.loads(p.read_text())
        feats = doc.get("features") or []
        out.append(f"{len(feats):,} features; test_data={doc.get('test_data')}; "
                   f"source_as_of={doc.get('source_as_of')}; stale={doc.get('stale', False)}")
        if adapter_id == "schools" and r.status == "success" and not doc.get("test_data"):
            if layer.dataset == "district":
                out.append(f"- note: districts kept={len(feats)}")
            elif layer.dataset == "campus":
                props = [feature.get("properties") or {} for feature in feats]
                matched = sum(row.get("campus_number") is not None for row in props)
                rating_rows = sum(row.get("rating_note") != "No TEA rating found for this campus" for row in props)
                rated = sum(row.get("overall_rating") in {"A", "B", "C", "D", "F"} for row in props)
                not_rated = sum(row.get("overall_rating") == "Not Rated" for row in props)
                out.append(f"- note: campuses={len(props)}; matched={matched}; rating rows={rating_rows}; "
                           f"rated={rated}; not rated={not_rated}; unmatched={len(props) - matched}")
        values: dict[str, list] = {}
        for f in feats:
            for k, v in (f.get("properties") or {}).items():
                values.setdefault(k, []).append(v)
        out += ["", "| property | nulls | summary |", "|---|---|---|"]
        for k, vs in sorted(values.items()):
            nulls = sum(v is None or v == "" for v in vs)
            present = [v for v in vs if v is not None and v != ""]
            nums = [v for v in present if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if nums and len(nums) == len(present):
                summary = f"min {min(nums):,} · median {statistics.median(nums):,} · max {max(nums):,}"
            else:
                counts = Counter(str(v) for v in present)
                if len(counts) <= 12:
                    summary = " · ".join(f"{v} ({n:,})" for v, n in counts.most_common())
                else:
                    summary = f"{len(counts):,} distinct; top: " + " · ".join(
                        f"{v} ({n:,})" for v, n in counts.most_common(5))
            out.append(f"| {k} | {nulls:,} | {summary.replace('|', '/')} |")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
