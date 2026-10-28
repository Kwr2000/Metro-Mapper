"""Offline non-demographic area percentiles; personal weights never enter the pipeline."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import json
import math
import os

from shapely.geometry import shape
from shapely.strtree import STRtree

from .inputs import SCORE_INPUTS, assert_no_demographics
from .paths import paths
from . import adapter, canonical, runlog
from .adapter import RunContext
from .budget import CallBudget

# These are the only value-bearing fields read. Geography, dates and district geometry
# are needed solely for joins/provenance; no registry layer values are consulted.
FIELDS = ("rate_part1", "overall_score", "flood_share_1pct", "walk_basket", "bike_basket",
          "walk_grocery", "walk_park", "transit_per_hour")
MINUTES = {3,4,5,6}  # walk/bike minute fields
CAP_NOTE = "More than 60 minutes"
CAPPED = -1  # published raw marker: more than 60 minutes
CAP_RANK = 61
SOURCES = ("areas", "dps_agency", "schools", "fema_nfhl", "access")
FIXTURE_TIME = datetime(2026,10,28,tzinfo=timezone.utc)
FACTORS = (
    ("safety", "Safety", "dps_agency", [0], "lower", "Texas Department of Public Safety, Crime in Texas",
     ["Part I reports per 1,000 residents"], ["per 1,000"], "Agency-wide rate: one number per police agency, not a street-level measure. APD's finer layer is not mixed in."),
    ("schools", "Schools", "schools", [1], "higher", "Texas Education Agency; U.S. Census Bureau district boundaries",
     ["District overall score"], ["points"], "District containing the block group's interior point. District rating only; campuses vary and this does not assign an attendance zone."),
    ("flood", "Flood", "fema_nfhl", [2], "lower", "FEMA National Flood Hazard Layer",
     ["1% annual-chance flood-zone area"], ["share"], "Area share, not a prediction for a home. FEMA map versions vary; retrieval dates are labelled as such."),
    ("daily", "Walk/bike to daily needs", "access", [3,4], "lower", "OpenStreetMap via Geofabrik; Metro Mapper access calculations (ODbL 1.0)",
     ["Walking daily-needs basket", "Cycling daily-needs basket"], ["minutes","minutes"], "Mean of the walking and cycling percentiles. Both measurements are required; missing values are not replaced."),
    ("grocery_parks", "Grocery and parks", "access", [5,6], "lower", "OpenStreetMap via Geofabrik; Metro Mapper access calculations (ODbL 1.0)",
     ["Walk to grocery", "Walk to park"], ["minutes","minutes"], "Mean of the grocery and park walking percentiles. Both measurements are required."),
    ("transit", "Transit", "access", [7], "higher", "CapMetro GTFS via data.texas.gov; Metro Mapper access calculations",
     ["Morning departures"], ["trips per hour"], "CapMetro only. An observed zero outside service is zero, not missing; other transit agencies are not included."),
)


def source_records(source):
    if source not in SOURCES:raise ValueError("area score: unapproved source")
    target = canonical.path_for("area_feature",source)
    if target.is_file():
        def stream():
            with gzip.open(target,"rt",encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():yield json.loads(line)
        return stream(),False
    # A frozen fixture date must match the existing 2025 DPS report and 2026 GTFS
    # fixtures. A January date asks DPS for its older report. Never call fetch/runner.
    ad = adapter.load(source)
    ctx = RunContext("fixture",FIXTURE_TIME,CallBudget.for_adapter(source,FIXTURE_TIME),adapter.adapter_dir(source))
    queue = deque(ad.plan(ctx));rows = []
    while queue:
        raw = adapter.read_fixture(source,queue.popleft())
        queue.extendleft(reversed(ad.follow_up(raw,ctx)))
        rows.extend(ad.normalize(raw))
    return iter(r.model_dump(mode="json") for r in ad.finalize(rows)),True


def whole(value):
    """Nearest whole percentile, halves upward, independent of binary float ties."""
    return math.floor(value+Fraction(1,2))


def percentiles(values, *, lower=False):
    """Mid-distribution rank: 100 * (less + tied/2) / n; all ties and n=1 give 50."""
    found = defaultdict(list)
    for identity,value in values.items():
        if value is None:continue
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError("area score: invalid numeric input")
        found[value].append(identity)
    n = sum(len(ids) for ids in found.values())
    result = {identity:None for identity in values};less = 0
    for value,ids in sorted(found.items()):
        rank = Fraction(100*(2*less+len(ids)),2*n)
        if lower:rank = 100-rank
        for identity in ids:result[identity] = whole(rank)
        less += len(ids)
    return result


def district_values(areas, districts):
    ordered = sorted(districts, key=lambda r:r["feature_id"])
    if len({r["feature_id"] for r in ordered})!=len(ordered):raise ValueError("area score: duplicate district")
    geometries = [shape(r["geometry"]) for r in ordered]
    if any(g.is_empty or not g.is_valid or g.geom_type not in ("Polygon","MultiPolygon") for g in geometries):
        raise ValueError("area score: invalid district boundary")
    tree = STRtree(geometries)
    result = {}
    for area in areas:
        geometry = shape(area["geometry"])
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon","MultiPolygon"):
            raise ValueError("area score: invalid area boundary")
        point = geometry.representative_point()
        hits = sorted(tree.query(point,predicate="covered_by"),key=lambda i:ordered[i]["feature_id"])
        result[area["feature_id"]] = ordered[hits[0]]["properties"].get("overall_score") if hits else None
    return result


def build(records, *, fixtures=(), dates=None):
    assert_no_demographics("area_score",SCORE_INPUTS["area_score"])
    if set(SCORE_INPUTS["area_score"]) != set(FIELDS)|{FIELDS[i]+"_note" for i in MINUTES}:raise ValueError("area score: unregistered input")
    if set(records) != set(SOURCES):
        raise ValueError("area score: unexpected source")
    areas = sorted((r for r in records["areas"] if r["dataset"] == "block_group"),key=lambda r:r["feature_id"])
    ids = [r["feature_id"] for r in areas]
    if not ids or len(set(ids)) != len(ids):raise ValueError("area score: missing or duplicate base areas")
    columns = [{identity:None for identity in ids} for _ in FIELDS]
    districts = [r for r in records["schools"] if r["dataset"] == "district"]
    columns[1].update(district_values(areas,districts))
    for source,indices in (("dps_agency",[0]),("fema_nfhl",[2]),("access",[3,4,5,6,7])):
        seen = set()
        for record in records[source]:
            if record["dataset"] != "block_group":continue
            identity = record["feature_id"]
            if identity not in columns[0]:continue
            if identity in seen:raise ValueError("area score: duplicate source area")
            seen.add(identity)
            for index in indices:
                value = record["properties"].get(FIELDS[index])
                # Access caps routes at 60 minutes: "More than 60 minutes" is a measured worst
                # value, not missing (review 2026-10-28). Published raw as CAPPED; ranked as 61.
                if value is None and index in MINUTES and record["properties"].get(FIELDS[index]+"_note") == CAP_NOTE:
                    value = CAPPED
                columns[index][identity] = value
    ranked = [percentiles({k:(CAP_RANK if i in MINUTES and v == CAPPED else v) for k,v in column.items()},lower=i!=1 and i!=7)
              for i,column in enumerate(columns)]
    rows = {}
    for identity in ids:
        scores = []
        for _,_,_,indices,_,_,_,_,_ in FACTORS:
            parts = [ranked[i][identity] for i in indices]
            scores.append(None if any(p is None for p in parts) else whole(Fraction(sum(parts),len(parts))))
        rows[identity] = scores+[column[identity] for column in columns]
    fixture_set = set(fixtures);factors = []
    dates = dates or {}
    for identity,label,source,indices,better,credit,labels,units,note in FACTORS:
        factors.append({"id":identity,"label":label,"source":credit,"field":[FIELDS[i] for i in indices],
            "raw_indices":[6+i for i in indices],"measure_labels":labels,"units":units,
            "better":better,"as_of":dates.get(source,"Date not available"),"note":note,
            "test_data":source in fixture_set or "areas" in fixture_set})
    return {"v":1,"test_data":bool(fixture_set),"factors":factors,"rows":rows,
        "percentile_note":"Mid-rank percentiles relative to block groups in Travis, Williamson and Hays counties; 100 is the better direction, not absolute quality.",
        "method":"100 × (number below + half the tied group) / number measured; flip lower-is-better inputs, round half upward. Composite factors average both rounded component percentiles and round half upward. Walk/bike times over 60 minutes are measured as 'more than 60 minutes' and rank as the slowest, tied."}


def publish():
    """Read only approved stored sources, else their labelled fixtures. Atomic output."""
    records = {};fixtures = [];dates = {}
    logs = [r for r in runlog.read_all() if r.mode=="live"]
    for source in SOURCES:
        stream,fixture = source_records(source)
        # Filter datasets before accessing properties; unrelated campus/benchmark records
        # and every unlisted numeric field remain outside the calculation.
        dataset = "district" if source=="schools" else "block_group"
        rows = [r for r in stream if r["dataset"]==dataset]
        records[source] = rows
        if fixture:fixtures.append(source)
        observed = sorted({r["source_as_of"] for r in rows if r.get("source_as_of")})
        last = runlog.last_success(source,logs)
        if source=="schools":
            periods = sorted({str(r["properties"]["ratings_year"]) for r in rows if r["properties"].get("ratings_year")})
            dates[source] = ", ".join(periods)+" ratings" if periods else "Rating date not available"
        elif observed:dates[source] = ", ".join(observed)
        elif not fixture and last:dates[source] = "Retrieved "+last.finished_at.date().isoformat()
        else:dates[source] = "Synthetic fixture snapshot "+FIXTURE_TIME.date().isoformat()
    document = build(records,fixtures=fixtures,dates=dates)
    payload = json.dumps(document,sort_keys=True,separators=(",",":"),allow_nan=False).encode()+b"\n"
    if len(payload)>=1_000_000:raise ValueError("area score: output must be under 1 MB")
    target = paths().web_public/"data/area_score.json";target.parent.mkdir(parents=True,exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    try:
        temporary.write_bytes(payload);os.replace(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"area score: {len(document['rows'])} block groups, {len(payload)} bytes, test_data={document['test_data']}")
    return document
