"""Offline area medians from the homes publication; no new source or inferred locations."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN
import json
import os
import re
from statistics import median

from . import values
from .inputs import SCORE_INPUTS, assert_no_demographics
from .paths import paths

INPUTS = ("category", "market_value", "living_area", "block_group", "range_pct", "id", "factor", "levels", "published", "calibration", "county", "tract", "k")
METHOD = ("Median appraisal-based centre per sq ft of single-family homes with a range and living area; "
          "at least ten located homes per 2020 Census block group. Homes without a block-group location "
          "are excluded; no location is inferred. These are appraisal-based centres, not sale prices. "
          "Sources: county appraisal districts, Texas Comptroller study and FHFA purchase-only metro HPI. "
          "Whole dollars use nearest-even rounding after the ordinary median.")


def build(meta, documents, calibration=None):
    assert_no_demographics("area_price", SCORE_INPUTS["area_price"])
    if set(SCORE_INPUTS["area_price"]) != set(INPUTS):raise ValueError("area price: unregistered input")
    model = meta.get("value_range") or {}
    calibrated=model.get("calibration",{}).get("used") is True
    if calibrated and calibration is None:raise ValueError("area price: accepted calibration is unavailable")
    dates = sorted({d for c in meta["counties"].values() for d in c.get("value_as_of",[])})
    as_of = f"CAD value dates: {', '.join(dates) or 'Not available'}; FHFA: {model.get('hpi',{}).get('as_of','Not available')}; Comptroller study: {model.get('study_year','Not available')}"
    if calibrated:as_of+=f"; HMDA fitting year: {calibration['fit_year']}; held-out year: {calibration['test_year']}"
    test = bool(meta["test_data"] or model.get("test_data"))
    if calibrated:test=test or bool(calibration.get("test_data"))
    groups = defaultdict(list)
    if model.get("published") is True:
        seen = set()
        for doc in documents:
            test = test or doc["test_data"]
            if doc["v"] != 1 or len(set(doc["fields"])) != len(doc["fields"]):raise ValueError("area price: invalid shard")
            indices = {field:doc["fields"].index(field) for field in INPUTS[:6]}
            for row in doc["rows"]:
                # Select only the registered cells; never copy the full property record.
                p = {field:row[i] for field,i in indices.items()}
                identity=p["id"]
                if identity in seen:raise ValueError("area price: duplicate home")
                seen.add(identity)
                group=p["block_group"];area=p["living_area"]
                if p["category"]!="single_family" or p["range_pct"] is None or group is None or area is None:continue
                if not isinstance(group,str) or not re.fullmatch(r"(?:48453|48491|48209)[0-9]{7}",group):raise ValueError("area price: invalid geography")
                if values.decimal(area)<=0:continue
                fips=identity.split(":")[0]
                k=values.factor_for(group[:11],fips,calibration) if calibrated else 1
                centre=values.value_range(p["market_value"],fips,p["range_pct"],model["hpi"]["factor"],model["levels"],k)["mid"]
                if centre is not None:groups[group].append(Decimal(centre)/values.decimal(area))
    rows={group:[len(psf),int(median(psf).quantize(Decimal(1),rounding=ROUND_HALF_EVEN))]
          for group,psf in sorted(groups.items()) if len(psf)>=10}
    method=METHOD+(" Accepted tract or county calibration uses FFIEC HMDA home-purchase loans." if calibrated else "")
    if model.get("published") is not True:method+=" Area prices are unavailable while value ranges are unpublished."
    return {"v":1,"test_data":test,"as_of":as_of,"method":method,"rows":rows}


def publish():
    folder=paths().web_public/"data/homes"
    meta=json.loads((folder/"meta.json").read_text())
    active=meta.get("value_range",{}).get("calibration",{}).get("used") is True
    calibration=json.loads((folder/"calibration.json").read_text()) if active else None
    def documents():
        for file in sorted((folder/"addr").glob("*.json")):yield json.loads(file.read_text())
    document=build(meta,documents(),calibration)
    payload=(json.dumps(document,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    if len(payload)>=100_000:raise ValueError("area price: output must be under 100 KB")
    target=folder.parent/"area_price.json";temporary=target.with_suffix(".json.tmp")
    try:
        temporary.write_bytes(payload);os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    print(f"area price: {len(document['rows'])} block groups, {len(payload)} bytes, test_data={document['test_data']}")
    return document
