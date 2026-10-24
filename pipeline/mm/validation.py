"""Validation report for each refresh (P1-09; targets in docs/PLAN.md).

Checks what is about to be published (web/public/data/layers, built from data/canonical
and any fresh live runs) and writes `data/validation/validation.json` plus a readable
`data/validation/report.md`. **Hard** checks decide whether a refresh may publish;
**soft** checks are reported only.

Hard: every published layer has a source, an as-of date and at least half of last
month's features; no demographic field feeds a score; no personal fields are published;
APD block-group counts reconcile with APD's own total. Soft: block-group rankings are
stable against H3 resolution-8 hexagons (Spearman >= 0.8); refresh runs succeeded; no
layer shows test data or is stale.

    mm validate            # print the report; writes nothing
    mm refresh --mode live # run due adapters, validate, keep or roll back (refresh.py)
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Literal

from . import canonical, inputs, privacy, registry, runlog
from .manifests import load_layers
from .paths import paths
from .publish import file_id, published_path
from .schemas import LayerManifest

MIN_RATIO = 0.5
SPEARMAN_TARGET = 0.8
H3_RESOLUTION = 8

Status = Literal["pass", "fail", "warn", "skipped"]


@dataclass
class Check:
    id: str
    title: str
    kind: Literal["hard", "soft"]
    status: Status
    detail: str
    items: list[str] = field(default_factory=list)


@dataclass
class LayerCount:
    id: str
    source: str
    features: int | None
    previous: int | None
    as_of: str | None
    test_data: bool
    stale: bool


def validation_dir():
    return paths().data / "validation"


def report_path():
    return validation_dir() / "validation.json"


def previous_report() -> dict | None:
    try:
        return json.loads(report_path().read_text())
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=1)
def _transformers():
    from pyproj import Transformer

    fwd = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    back = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    return fwd, back


def to_projected(lon: float, lat: float) -> tuple[float, float]:
    return _transformers()[0].transform(lon, lat)


def to_wgs84_point(x: float, y: float) -> tuple[float, float]:
    return _transformers()[1].transform(x, y)


def project(geom):
    from shapely.ops import transform

    return transform(_transformers()[0].transform, geom)


def _doc(layer: LayerManifest) -> dict | None:
    p = published_path(layer)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- hard checks


def check_layers(baseline: dict[str, int], reg) -> tuple[Check, list[LayerCount]]:
    compiled = {l.id: l for l in reg.layers}
    counts: list[LayerCount] = []
    problems: list[str] = []
    for layer in load_layers():
        if layer.publish == "none":
            continue
        c = compiled[layer.id]
        doc = _doc(layer)
        n = len(doc.get("features") or []) if doc else None
        prev = baseline.get(layer.id)
        test = bool(doc and doc.get("test_data"))
        lc = LayerCount(layer.id, layer.source, n, prev, c.as_of, test, bool(doc and doc.get("stale")))
        counts.append(lc)
        if doc is None:
            problems.append(f"{layer.id}: no published file")
            continue
        if not layer.attribution.strip():
            problems.append(f"{layer.id}: no source attribution")
        if not c.as_of:
            problems.append(f"{layer.id}: no as-of date")
        if test:
            continue  # test data is reported by a soft check; it has no live count to keep
        if prev and n is not None and n < MIN_RATIO * prev:
            problems.append(f"{layer.id}: {n:,} features, below half of last month's {prev:,}")
    n_live = sum(1 for c in counts if not c.test_data and c.features is not None)
    return (Check("layers", "Every layer has a source, an as-of date and at least half of last "
                  "month's features", "hard", "fail" if problems else "pass",
                  f"{len(counts)} layers ({n_live} live)" if not problems else
                  f"{len(problems)} problem(s)", problems), counts)


def check_demographics() -> Check:
    bad = []
    for score_id, fields in inputs.SCORE_INPUTS.items():
        try:
            inputs.assert_no_demographics(score_id, fields)
        except inputs.DemographicInputError as e:
            bad.append(str(e))
    n = len(inputs.SCORE_INPUTS)
    return Check("demographics", "No demographic field feeds any score, ranking or value input",
                 "hard", "fail" if bad else "pass",
                 f"{n} score(s) declared" + ("" if n else " (none until Phase 2)"), bad)


def check_privacy() -> Check:
    bad = []
    files = 0
    for p in sorted(paths().published_layers.glob("*.geojson")):
        try:
            doc = json.loads(p.read_text())
        except (OSError, ValueError):
            bad.append(f"{p.name}: unreadable")
            continue
        files += 1
        keys = set()
        for f in doc.get("features") or []:
            keys.update((f.get("properties") or {}).keys())
        if found := privacy.personal_keys(keys):
            bad.append(f"{p.name}: {found}")
    return Check("privacy", "No personal fields in published files", "hard",
                 "fail" if bad else "pass", f"{files} published files scanned", bad)


APD_TOTAL = "reports in period"
APD_UNLOCATED = "without block group"
APD_OUTSIDE = "reports in block groups outside APD area"


def check_apd() -> Check:
    title = "APD block-group counts add up to APD's total for the same period"
    recs = canonical.read("area_feature", "apd")
    layer = next((l for l in load_layers() if l.source == "apd" and l.publish == "geojson"), None)
    doc = _doc(layer) if layer else None
    if not recs or doc is None or doc.get("test_data"):
        return Check("apd_reconcile", title, "hard", "skipped", "no live APD data")
    summary = [r for r in recs if r.dataset == "run_summary"]
    if len(summary) != 1:
        return Check("apd_reconcile", title, "hard", "fail", f"{len(summary)} APD run summaries stored")
    s = summary[0].properties
    if APD_OUTSIDE not in s:
        return Check("apd_reconcile", title, "hard", "skipped",
                     "stored APD summary predates this check; it runs from the next APD refresh")
    published = sum((f.get("properties") or {}).get("total") or 0 for f in doc.get("features") or [])
    expected = s[APD_TOTAL] - s[APD_UNLOCATED] - s[APD_OUTSIDE]
    ok = published == expected
    return Check("apd_reconcile", title, "hard", "pass" if ok else "fail",
                 f"block groups in APD area {published:,}; APD total {s[APD_TOTAL]:,} less "
                 f"{s[APD_UNLOCATED]:,} without a block group and {s[APD_OUTSIDE]:,} in block "
                 f"groups outside the APD area = {expected:,}")


# ---------------------------------------------------------------- soft checks


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return None if va == 0 or vb == 0 else cov / (va * vb)


def _style_fields(node) -> list[str]:
    """Property names read by ["get", name] in a style expression, in order."""
    if isinstance(node, list):
        if len(node) == 2 and node[0] == "get" and isinstance(node[1], str):
            return [node[1]]
        return [f for x in node for f in _style_fields(x)]
    if isinstance(node, dict):
        return [f for x in node.values() for f in _style_fields(x)]
    return []


def ranked_attributes() -> list[tuple[LayerManifest, str]]:
    """(layer, field) for each non-demographic block-group layer that colours the map by a
    property: the property its style reads. Each (file, field) pair is checked once."""
    out, seen = [], set()
    for layer in load_layers():
        if layer.demographic or layer.join != "block_group" or layer.publish != "geojson":
            continue
        fields = _style_fields(layer.style.paint if layer.style else {})
        if fields and (file_id(layer), fields[0]) not in seen:
            seen.add((file_id(layer), fields[0]))
            out.append((layer, fields[0]))
    return out


@dataclass
class HexWeights:
    """Overlap areas between block groups and the H3 hexagons that cover them."""

    geoids: list[str]
    bg_area: dict[int, list[tuple[int, float]]]  # bg index -> [(hex index, overlap area)]
    hex_area: dict[int, list[tuple[int, float]]]  # hex index -> [(bg index, overlap area)]


def hex_weights(features: list[tuple[str, object]]) -> HexWeights:
    """`features` is (geoid, polygon in EPSG:5070)."""
    import h3
    from shapely.geometry import Polygon
    from shapely.strtree import STRtree

    geoms = [g for _, g in features]
    minx = min(g.bounds[0] for g in geoms)
    miny = min(g.bounds[1] for g in geoms)
    maxx = max(g.bounds[2] for g in geoms)
    maxy = max(g.bounds[3] for g in geoms)
    corners = [to_wgs84_point(x, y) for x, y in ((minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy))]
    w, e = min(c[0] for c in corners), max(c[0] for c in corners)
    s, n = min(c[1] for c in corners), max(c[1] for c in corners)
    cells = set(h3.polygon_to_cells(h3.LatLngPoly([(s, w), (s, e), (n, e), (n, w)]), H3_RESOLUTION))
    cells = {nb for c in cells for nb in h3.grid_disk(c, 1)}  # cover the edges too
    hexes = [Polygon([to_projected(lon, lat) for lat, lon in h3.cell_to_boundary(c)]) for c in sorted(cells)]
    tree = STRtree(hexes)
    bg_area: dict[int, list[tuple[int, float]]] = {}
    hex_area: dict[int, list[tuple[int, float]]] = {}
    for i, g in enumerate(geoms):
        for j in tree.query(g, predicate="intersects"):
            a = g.intersection(hexes[j]).area
            if a > 0:
                bg_area.setdefault(i, []).append((int(j), a))
                hex_area.setdefault(int(j), []).append((i, a))
    return HexWeights([g for g, _ in features], bg_area, hex_area)


def hex_smoothed(w: HexWeights, values: dict[str, float]) -> dict[str, float]:
    """Each hexagon takes the overlap-weighted mean of its block groups' values; each block
    group then takes the overlap-weighted mean of its hexagons. Missing values are skipped."""
    idx = {g: i for i, g in enumerate(w.geoids)}
    vals = {idx[g]: v for g, v in values.items() if g in idx}
    hex_val = {}
    for j, parts in w.hex_area.items():
        num = sum(a * vals[i] for i, a in parts if i in vals)
        den = sum(a for i, a in parts if i in vals)
        if den:
            hex_val[j] = num / den
    out = {}
    for i in vals:
        parts = [(j, a) for j, a in w.bg_area.get(i, []) if j in hex_val]
        den = sum(a for _, a in parts)
        if den:
            out[w.geoids[i]] = sum(a * hex_val[j] for j, a in parts) / den
    return out


def check_h3_stability() -> Check:
    title = f"Block-group rankings match H3 res-{H3_RESOLUTION} hexagons (Spearman ≥ {SPEARMAN_TARGET})"
    try:
        import h3  # noqa: F401
    except ImportError:
        return Check("h3_stability", title, "soft", "skipped", "h3 is not installed")
    from shapely.geometry import shape

    weights: dict[tuple[str, ...], HexWeights] = {}
    items, low, done = [], 0, 0
    for layer, fld in ranked_attributes():
        doc = _doc(layer)
        if not doc or doc.get("test_data"):
            continue
        feats = [f for f in doc.get("features") or [] if f.get("geometry")]
        key = tuple(sorted(str(f.get("id")) for f in feats))
        if len(key) < 3:
            continue
        if key not in weights:
            polys = [(str(f.get("id")), project(shape(f["geometry"]))) for f in feats]
            weights[key] = hex_weights([(g, p) for g, p in polys if not p.is_empty and p.area > 0])
        values = {}
        for f in feats:
            v = (f.get("properties") or {}).get(fld)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                values[str(f.get("id"))] = float(v)
        smoothed = hex_smoothed(weights[key], values)
        pairs = [(values[g], smoothed[g]) for g in values if g in smoothed]
        rho = spearman([a for a, _ in pairs], [b for _, b in pairs])
        if rho is None:
            continue
        done += 1
        low += rho < SPEARMAN_TARGET
        items.append(f"{fld} ({layer.source}, {len(pairs):,} areas): {rho:.2f}"
                     + ("  ← below target" if rho < SPEARMAN_TARGET else ""))
    if not done:
        return Check("h3_stability", title, "soft", "skipped", "no live block-group attributes yet")
    return Check("h3_stability", title, "soft", "warn" if low else "pass",
                 f"{done - low} of {done} attributes at or above target", items)


def check_runs(results: list[dict] | None) -> Check:
    title = "Due adapters refreshed successfully"
    if results is None:
        return Check("runs", title, "soft", "skipped", "validation only; no refresh ran")
    if not results:
        return Check("runs", title, "soft", "pass", "nothing was due this month")
    bad = [f"{r['adapter']}: {r['status']} — previous data kept" + (f" ({r['error']})" if r.get("error") else "")
           for r in results if r["status"] != "success"]
    return Check("runs", title, "soft", "warn" if bad else "pass",
                 f"{len(results) - len(bad)} of {len(results)} succeeded", bad)


def check_site_state(counts: list[LayerCount], reg) -> Check:
    fresh = {l.id: l.freshness for l in reg.layers}
    items = [f"{c.id}: test data" for c in counts if c.test_data]
    items += [f"{c.id}: marked stale (a refresh was held)" for c in counts if c.stale]
    items += [f"{c.id}: {fresh[c.id]}" for c in counts
              if not c.test_data and not c.stale and fresh.get(c.id) in ("stale", "failing")]
    return Check("site_state", "No layer shows test data or is out of date", "soft",
                 "warn" if items else "pass", f"{len(items)} layer(s) to look at" if items else "all live and current",
                 items)


LATER = [
    ("hmda", "Tract appraisal-based values vs HMDA property values (Phase 2+)"),
    ("zip_medians", "ZIP medians vs Redfin/Zillow (Phase 2+)"),
]


# ---------------------------------------------------------------- report


def build(now: datetime | None = None, results: list[dict] | None = None) -> dict:
    now = now or runlog.utcnow()
    prev = previous_report() or {}
    baseline = dict(prev.get("baseline") or {})
    reg = registry.compile_registry(now=now, write=False)
    layer_check, counts = check_layers(baseline, reg)
    checks = [layer_check, check_demographics(), check_privacy(), check_apd(),
              check_h3_stability(), check_runs(results), check_site_state(counts, reg)]
    checks += [Check(i, t, "soft", "skipped", "not applicable yet") for i, t in LATER]
    passed = not any(c.kind == "hard" and c.status == "fail" for c in checks)
    new_baseline = dict(baseline)
    if passed:
        for c in counts:
            if c.features is not None and not c.test_data:
                new_baseline[c.id] = c.features
    return {
        "generated_at": now.isoformat(),
        "passed": passed,
        "published": None,  # set by refresh: whether this refresh's new data went live
        "checks": [asdict(c) for c in checks],
        "layers": [asdict(c) for c in counts],
        "runs": results,
        # Feature counts of what is live, for next month's comparison. A failed refresh
        # keeps the previous month's numbers, because the previous month stays live.
        "baseline": dict(sorted(new_baseline.items())),
    }


ICON = {"pass": "✅ pass", "fail": "❌ FAIL", "warn": "⚠️ check", "skipped": "— skipped"}


def markdown(rep: dict) -> str:
    when = rep["generated_at"][:16].replace("T", " ") + " UTC"
    head = "passed" if rep["passed"] else "**FAILED — the previous month's data stays live**"
    out = [f"# Validation report — {when}", "", f"Hard checks {head}."]
    if rep.get("published") is not None:
        out.append("New data published." if rep["published"] else "No new data published.")
    for kind in ("hard", "soft"):
        out += ["", f"## {kind.capitalize()} checks", "", "| check | result | detail |", "|---|---|---|"]
        for c in (c for c in rep["checks"] if c["kind"] == kind):
            out.append(f"| {c['title']} | {ICON[c['status']]} | {c['detail']} |".replace("\n", " "))
        for c in (c for c in rep["checks"] if c["kind"] == kind and c["items"]):
            out += ["", f"**{c['title']}**", ""] + [f"- {i}" for i in c["items"][:40]]
    if rep.get("runs"):
        out += ["", "## Refresh runs", "", "| adapter | why | status | features | calls |", "|---|---|---|---|---|"]
        for r in rep["runs"]:
            out.append(f"| {r['adapter']} | {r['reason']} | {r['status']} | {r['rows']:,} | {r['calls']} |")
    out += ["", "## Layers", "", "| layer | features | last month | as of | note |", "|---|---|---|---|---|"]
    for c in rep["layers"]:
        note = "test data" if c["test_data"] else ("stale" if c["stale"] else "")
        f = "—" if c["features"] is None else f"{c['features']:,}"
        p = "—" if c["previous"] is None else f"{c['previous']:,}"
        out.append(f"| {c['id']} | {f} | {p} | {c['as_of'] or '—'} | {note} |")
    return "\n".join(out) + "\n"


def write(rep: dict) -> None:
    d = validation_dir()
    d.mkdir(parents=True, exist_ok=True)
    report_path().write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n")
    (d / "report.md").write_text(markdown(rep))


def main(write_files: bool = False) -> int:
    rep = build()
    print(markdown(rep))
    if write_files:
        write(rep)
    return 0 if rep["passed"] else 1
