"""Appraisal-based value range reference arithmetic and comparable-home statistics.

P2-07 must port value_range using decimal arithmetic and nearest-even $1,000 rounding,
including exact $500 ties. Low/high use the already rounded centre. Shared synthetic
vectors live in data/value_range_cases.json. No sale-price data or demographic inputs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import math

import yaml

from .inputs import SCORE_INPUTS, assert_no_demographics
from .paths import paths
from .privacy import check_properties

COUNTY_FIPS = {"Travis":"48453", "Williamson":"48491", "Hays":"48209"}
FLAG_ORDER = ("new", "lot", "condo", "size", "type")
NO_RANGE = ("no_value", "no_building", "partial")
HOME_INPUTS = tuple(field for field in SCORE_INPUTS["value_range"] if field not in {"cbsa","year","quarter","index_sa"})
FLAG_TEXT = {
    "new":"Built in the last two years or held as builder inventory",
    "lot":"Lot larger than one acre",
    "condo":"Condominium",
    "size":"Living area outside the 5th–95th percentile of similar homes",
    "type":"Mobile home, two-to-four units or rural home; the study covers single-family homes",
    "no_value":"Market value is missing or zero",
    "no_building":"Improvement value is zero",
    "partial":"TCAD partial-ownership record",
}
METHOD = ("Appraisal-based value range: divide the 2026 CAD market value by the county's 2024 "
    "Comptroller category A median appraisal level, then multiply by the latest seasonally adjusted "
    "FHFA purchase-only Austin metro HPI divided by the mean of the quarter before and the quarter "
    "of the value date. Round the centre to $1,000; apply ±10%, or ±20% for the listed flags, then "
    "round both endpoints to $1,000. The study placed about three in four single-family sales "
    "within 10% of the appraisal. Missing characteristics are not imputed.")
YEAR_NOTE = "Year-over-year appraisal changes are not available: the stored CAD exports contain 2026 values only."


def decimal(value):
    if isinstance(value, bool) or not isinstance(value, (int,float,str,Decimal)):
        raise ValueError("value range: invalid numeric input")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("value range: invalid numeric input") from None
    if not result.is_finite():
        raise ValueError("value range: nonfinite numeric input")
    return result


def settings():
    with (paths().config/"value_range.yaml").open() as handle:
        cfg = yaml.safe_load(handle)
    required = {"published","study","levels","within_10pct","base_width","wide_width","new_years",
                "large_lot_acres","size_percentiles","size_min_group","hood_min_group"}
    if not isinstance(cfg,dict) or set(cfg) != required or not isinstance(cfg["published"],bool) or not isinstance(cfg["study"],str):
        raise ValueError("value range: invalid config fields")
    if set(cfg["levels"]) != set(COUNTY_FIPS.values()) or set(cfg["within_10pct"]) != set(COUNTY_FIPS.values()):
        raise ValueError("value range: invalid county config")
    if any(decimal(v) <= 0 for v in cfg["levels"].values()) or any(not 0 <= decimal(v) <= 1 for v in cfg["within_10pct"].values()):
        raise ValueError("value range: invalid study levels or coverage")
    if not 0 < decimal(cfg["base_width"]) <= decimal(cfg["wide_width"]) < 1 or decimal(cfg["large_lot_acres"]) < 0:
        raise ValueError("value range: invalid width or lot threshold")
    if any(isinstance(cfg[k],bool) or not isinstance(cfg[k],int) or cfg[k] < 1 for k in ("size_min_group","hood_min_group")) or type(cfg["new_years"]) is not int or cfg["new_years"] < 0:
        raise ValueError("value range: invalid group size or year threshold")
    if len(cfg["size_percentiles"]) != 2 or not 0 < cfg["size_percentiles"][0] < cfg["size_percentiles"][1] <= 100:
        raise ValueError("value range: invalid percentiles")
    for key in ("base_width","wide_width"):
        if decimal(cfg[key])*100 != (decimal(cfg[key])*100).to_integral_value():
            raise ValueError("value range: widths must be whole percentages")
    return cfg


def quarter_end(serial):
    year, index = divmod(serial,4)
    if index == 3:return date(year,12,31)
    return date(year,index*3+4,1)-timedelta(days=1)


def quarter_label(serial):
    return f"{serial//4}Q{serial%4+1}"


def hpi_factor(records, value_date):
    rows = {}
    for record in records:
        r = record.model_dump(mode="json") if hasattr(record,"model_dump") else record
        if r["dataset"] != "hpi":continue
        p = r["properties"]
        if str(p["cbsa"]) != "12420" or type(p["year"]) is not int or type(p["quarter"]) is not int or not 1900 <= p["year"] <= 2200 or not 1 <= p["quarter"] <= 4:
            raise ValueError("value range: invalid Austin HPI period")
        serial = p["year"]*4+p["quarter"]-1
        if serial in rows or decimal(p["index_sa"]) <= 0:
            raise ValueError("value range: duplicate HPI quarter or nonpositive index")
        rows[serial] = decimal(p["index_sa"])
    if not rows:
        raise ValueError("value range: missing latest HPI quarter")
    day = date.fromisoformat(value_date) if isinstance(value_date,str) else value_date
    current = day.year*4+(day.month-1)//3
    base = (current-1,current)
    if not set(base) <= rows.keys():
        raise ValueError("value range: missing base HPI quarter")
    ordered = sorted(rows)
    if ordered != list(range(ordered[0],ordered[-1]+1)):
        raise ValueError("value range: HPI quarters have gaps")
    latest = ordered[-1]
    base_index = sum(rows[q] for q in base)/2
    factor = rows[latest]/base_index
    if not Decimal("0.8") <= factor <= Decimal("1.2"):
        raise ValueError("value range: HPI factor outside 0.80 to 1.20")
    return {"factor":float(factor), "base_quarters":[quarter_label(q) for q in base], "base_index":float(base_index),
            "latest_quarter":quarter_label(latest), "latest_index":float(rows[latest]), "as_of":quarter_end(latest).isoformat()}


def percentile(ordered, percent):
    if not ordered:return None
    return ordered[max(0,math.ceil(len(ordered)*percent/100)-1)]


def size_bounds(homes, cfg=None):
    cfg = settings() if cfg is None else cfg
    local, county = defaultdict(list), defaultdict(list)
    for home in homes:
        area = home.get("living_area")
        if area is None or area <= 0:continue
        key = (home["county"],home["category"])
        county[key].append(area)
        if home.get("hood_cd"):
            local[(*key,home["hood_cd"])].append(area)
    bounds = {}
    for key, areas in county.items():
        ordered = sorted(areas)
        bounds[(*key,None)] = tuple(percentile(ordered,p) for p in cfg["size_percentiles"])
    for key, areas in local.items():
        if len(areas) >= cfg["size_min_group"]:
            bounds[key] = tuple(percentile(sorted(areas),p) for p in cfg["size_percentiles"])
    return bounds


def flags(home, size_limits, cfg=None):
    cfg = settings() if cfg is None else cfg
    value = home.get("market_value")
    if value is None or value == 0:return ["no_value"]
    if home.get("improvement_value") == 0:return ["no_building"]
    if home["county"] == "Travis" and home.get("partial_owner") is True:return ["partial"]
    result = []
    year = home.get("year_built")
    if home["category"] == "builder_inventory" or year is not None and year >= home["value_year"]-cfg["new_years"]:result.append("new")
    acres = home.get("land_acres")
    if acres is not None and acres > cfg["large_lot_acres"]:result.append("lot")
    if home["category"] == "condo":result.append("condo")
    key = (home["county"],home["category"])
    limits = size_limits.get((*key,home.get("hood_cd")),size_limits.get((*key,None)))
    area = home.get("living_area")
    if area is not None and area > 0 and limits is not None and (area < limits[0] or area > limits[1]):result.append("size")
    if home["category"] in {"mobile_home","two_to_four_units","rural_home"}:result.append("type")
    return result


def round_thousand(value):
    return int(value.quantize(Decimal("1E3"), rounding=ROUND_HALF_EVEN))


def value_range(market_value, county_fips, range_pct, factor, levels):
    if range_pct is None or market_value is None or market_value == 0:
        return {"low":None,"mid":None,"high":None}
    if range_pct not in (10,20) or decimal(market_value) < 0 or decimal(factor) <= 0 or county_fips not in levels or decimal(levels[county_fips]) <= 0:
        raise ValueError("value range: invalid reference-formula input")
    mid = round_thousand(decimal(market_value)/decimal(levels[county_fips])*decimal(factor))
    width = decimal(range_pct)/100
    return {"low":round_thousand(Decimal(mid)*(1-width)),"mid":mid,"high":round_thousand(Decimal(mid)*(1+width))}


def annotation(home, limits, cfg):
    codes = flags(home,limits,cfg)
    pct = None if codes and codes[0] in NO_RANGE else int(100*decimal(cfg["wide_width"] if codes else cfg["base_width"]))
    return pct, ",".join(codes) or None


def validate_annotation(home, pct, codes, limits, cfg):
    if (pct,codes) != annotation(home,limits,cfg):
        raise ValueError("value range: width and flags differ from recomputation")


def hood_stats(homes, factor, levels, *, cfg=None, limits=None):
    cfg = settings() if cfg is None else cfg
    limits = size_bounds(homes,cfg) if limits is None else limits
    groups = defaultdict(list)
    for home in homes:
        pct,_ = annotation(home,limits,cfg)
        area = home.get("living_area")
        if pct is None or area is None or area <= 0 or not home.get("hood_cd"):continue
        category = home["category"] if home["category"] in {"single_family","condo"} else "other"
        mid = value_range(home["market_value"],COUNTY_FIPS[home["county"]],pct,factor,levels)["mid"]
        groups[(home["county"],home["hood_cd"],category)].append(Decimal(mid)/decimal(area))
    output = []
    for (county,code,category), prices in sorted(groups.items()):
        if len(prices) < cfg["hood_min_group"]:continue
        ordered = sorted(prices)
        output.append({"county":county,"hood_cd":code,"category":category,"n":len(prices),
            **{f"p{p}":int(percentile(ordered,p).quantize(Decimal(1),rounding=ROUND_HALF_EVEN)) for p in (10,25,50,75,90)}})
    return output


def prepare(homes, factor, cfg, *, test_data):
    """One county at a time; return widths/flags, statistics and count-only quality audit."""
    limits = size_bounds(homes,cfg)
    annotations = [annotation(home,limits,cfg) for home in homes]
    for home,(pct,codes) in zip(homes,annotations):validate_annotation(home,pct,codes,limits,cfg)
    stats = hood_stats(homes,factor,cfg["levels"],cfg=cfg,limits=limits)
    covered_groups = {(s["county"],s["hood_cd"],s["category"]) for s in stats}
    counts = Counter(); flag_counts = Counter(); sf = covered = 0
    for home,(pct,codes) in zip(homes,annotations):
        counts["none" if pct is None else str(pct)] += 1
        flag_counts.update(codes.split(",") if codes else [])
        if home["category"] == "single_family" and pct is not None:
            sf += 1
            covered += (home["county"],home.get("hood_cd"),"single_family") in covered_groups and (home.get("living_area") or 0) > 0
    has_range = len(homes)-counts["none"]
    if not test_data and has_range*100 < len(homes)*97:
        raise ValueError(f"value range: county range coverage below 97 percent - {homes[0]['county']} {has_range} of {len(homes)}")
    if not test_data and covered*100 < sf*90:
        raise ValueError(f"value range: hood statistics coverage below 90 percent - {homes[0]['county']} {covered} of {sf}")
    summary = {"homes":len(homes),"with_range":has_range,"range_share":has_range/len(homes) if homes else None,
        "by_range_pct":{p:counts[p] for p in ("10","20","none")},
        "by_flag":{p:flag_counts[p] for p in (*FLAG_ORDER,*NO_RANGE)},
        "single_family_with_range":sf,"hood_stats_covered":covered,"hood_stats_coverage":covered/sf if sf else None}
    return annotations,stats,summary


def metadata(cfg, hpi, test_data, counties):
    assert_no_demographics("value_range",SCORE_INPUTS["value_range"])
    result = {"published":cfg["published"],"test_data":test_data,"label":"Appraisal-based value range",
        "method":METHOD,"study":cfg["study"],"study_year":2024,"levels":cfg["levels"],"within_10pct":cfg["within_10pct"],
        "hpi":{**hpi,"source":"FHFA House Price Index (purchase-only)","cbsa":"12420","seasonally_adjusted":True},
        "widths":{"base":cfg["base_width"],"wide":cfg["wide_width"]},"flags":FLAG_TEXT,
        "year_over_year_note":YEAR_NOTE,
        "rules":{k:cfg[k] for k in ("new_years","large_lot_acres","size_percentiles","size_min_group","hood_min_group")},
        "size_note":"Size percentiles use the same category, county and appraisal neighbourhood with at least 20 measured homes; otherwise the same category county-wide. Percentiles use nearest rank; homes on the percentile edges are not flagged.",
        "hood_stats_note":"Neighbourhood statistics require at least ten homes with living area and a range; single-family and condo groups are separate, with other categories grouped together. Prices per square foot use the rounded centre.",
        "counties":counties}
    check_properties("value range metadata",result)
    return result
