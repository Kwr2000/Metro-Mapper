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
from statistics import median

import yaml

from .inputs import SCORE_INPUTS, assert_no_demographics
from .paths import paths
from .privacy import check_properties

COUNTY_FIPS = {"Travis":"48453", "Williamson":"48491", "Hays":"48209"}
FLAG_ORDER = ("new", "lot", "condo", "size", "type", "cal")
NO_RANGE = ("no_value", "no_building", "partial")
HOME_INPUTS = tuple(field for field in SCORE_INPUTS["value_range"] if field not in {"cbsa","year","quarter","index_sa"})
# P2-08's explicit core-file scope excludes inputs.py. Keep its native-column
# declaration here, shared with the adapter, and run the same demographic guard.
HMDA_INPUTS = ("activity_year", "county_code", "census_tract", "action_taken", "loan_purpose",
               "lien_status", "derived_dwelling_category", "total_units", "property_value")
HMDA_THRESHOLDS = {"min_loans":30, "min_homes":30, "median_ratio_min":.90, "median_ratio_max":1.10,
                   "ratio_min":.80, "ratio_max":1.20, "min_share_within_20":.75}
HMDA_NOTE = ("Compared with what 2025 home buyers' lenders recorded as the property value, "
    "this checks tract medians of single-family appraisal-based centres against HMDA purchase-loan "
    "property values, adjusted to the same FHFA quarter. HMDA values are midpoints of $10,000 bands. "
    "Sold homes are newer and larger on average than all homes, so this is an area-level check, "
    "not a test of any one home. No sale prices or applicant characteristics are used.")
FLAG_TEXT = {
    "new":"Built in the last two years or held as builder inventory",
    "lot":"Lot larger than one acre",
    "condo":"Condominium",
    "size":"Living area outside the 5th–95th percentile of similar homes",
    "type":"Mobile home, two-to-four units or rural home; the study covers single-family homes",
    "cal":"Neighbourhood adjustment from home-purchase loans",
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
                "large_lot_acres","size_percentiles","size_min_group","hood_min_group","calibration"}
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
    cal = cfg["calibration"]
    if (not isinstance(cal,dict) or set(cal) != {"enabled","fit_year","test_year","n0","clamps"}
        or type(cal["enabled"]) is not bool or type(cal["fit_year"]) is not int
        or type(cal["test_year"]) is not int or cal["test_year"] != cal["fit_year"]-1
        or cal["n0"] != 30 or cal["clamps"] != [.8,1.25]):
        raise ValueError("value range: invalid calibration config")
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


def value_range(market_value, county_fips, range_pct, factor, levels, k=1):
    if range_pct is None or market_value is None or market_value == 0:
        return {"low":None,"mid":None,"high":None}
    if range_pct not in (10,20) or decimal(market_value) < 0 or decimal(factor) <= 0 or decimal(k) <= 0 or county_fips not in levels or decimal(levels[county_fips]) <= 0:
        raise ValueError("value range: invalid reference-formula input")
    mid = round_thousand(decimal(market_value)/decimal(levels[county_fips])*decimal(factor)*decimal(k))
    width = decimal(range_pct)/100
    return {"low":round_thousand(Decimal(mid)*(1-width)),"mid":mid,"high":round_thousand(Decimal(mid)*(1+width))}


def annotation(home, limits, cfg, k=1):
    codes = flags(home,limits,cfg)
    pct = None if codes and codes[0] in NO_RANGE else int(100*decimal(cfg["wide_width"] if codes else cfg["base_width"]))
    if pct is not None and abs(decimal(k)-1) >= Decimal(".10"):codes.append("cal")
    return pct, ",".join(codes) or None


def validate_annotation(home, pct, codes, limits, cfg):
    if (pct,codes) != annotation(home,limits,cfg):
        raise ValueError("value range: width and flags differ from recomputation")


def hood_stats(homes, factor, levels, *, cfg=None, limits=None, calibration=None, annotations=None):
    cfg = settings() if cfg is None else cfg
    limits = size_bounds(homes,cfg) if limits is None else limits
    groups = defaultdict(list)
    for i,home in enumerate(homes):
        pct,_ = annotation(home,limits,cfg) if annotations is None else annotations[i]
        area = home.get("living_area")
        if pct is None or area is None or area <= 0 or not home.get("hood_cd"):continue
        category = home["category"] if home["category"] in {"single_family","condo"} else "other"
        mid = value_range(home["market_value"],COUNTY_FIPS[home["county"]],pct,factor,levels,factor_for(home.get("tract"),COUNTY_FIPS[home["county"]],calibration) if calibration else 1)["mid"]
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
    # Builder inventory on January 1 is mostly lots or unfinished houses with no building value
    # (Travis: 10,411 of 13,043 on 2026-10-27), so it is left out of the coverage check.
    built = [(home,pct) for home,(pct,_) in zip(homes,annotations) if home["category"] != "builder_inventory"]
    built_with_range = sum(pct is not None for _,pct in built)
    if not test_data and built_with_range*100 < len(built)*97:
        raise ValueError(f"value range: county range coverage below 97 percent (builder inventory excluded) - {homes[0]['county']} {built_with_range} of {len(built)}")
    if not test_data and covered*100 < sf*90:
        raise ValueError(f"value range: hood statistics coverage below 90 percent - {homes[0]['county']} {covered} of {sf}")
    summary = {"homes":len(homes),"with_range":has_range,"coverage_homes":len(built),"coverage_with_range":built_with_range,"range_share":has_range/len(homes) if homes else None,
        "by_range_pct":{p:counts[p] for p in ("10","20","none")},
        "by_flag":{p:flag_counts[p] for p in (*FLAG_ORDER,*NO_RANGE)},
        "single_family_with_range":sf,"hood_stats_covered":covered,"hood_stats_coverage":covered/sf if sf else None}
    return annotations,stats,summary


def hmda_adjustment(records, year):
    """Move the HMDA year's values to the latest SA quarter, using all four quarters."""
    rows = {}
    for record in records:
        r = record.model_dump(mode="json") if hasattr(record,"model_dump") else record
        if r["dataset"] != "hpi":continue
        p = r["properties"]
        if str(p["cbsa"]) != "12420" or type(p["year"]) is not int or type(p["quarter"]) is not int or not 1 <= p["quarter"] <= 4:
            raise ValueError("Invalid Austin HPI period for HMDA adjustment.")
        serial = p["year"]*4+p["quarter"]-1
        if serial in rows or decimal(p["index_sa"]) <= 0:
            raise ValueError("Duplicate or nonpositive HPI quarter for HMDA adjustment.")
        rows[serial] = decimal(p["index_sa"])
    quarters = [year*4+i for i in range(4)]
    if not set(quarters) <= rows.keys():
        raise ValueError("The HMDA year's four HPI quarters are unavailable.")
    latest = max(rows)
    if latest < quarters[-1]:
        raise ValueError("The latest HPI quarter precedes the HMDA year.")
    base = sum(rows[q] for q in quarters)/4
    return {"factor":float(rows[latest]/base), "base_quarters":[quarter_label(q) for q in quarters],
            "base_index":float(base), "latest_quarter":quarter_label(latest),
            "latest_index":float(rows[latest]), "as_of":quarter_end(latest).isoformat(),
            "source":"FHFA House Price Index (purchase-only)", "seasonally_adjusted":True}


def hmda_check(tract_centres, records, hpi_records, *, test_data=False, year=2025):
    """Aggregate-only check; failure hides ranges and leaves property facts publishable.

    Our tract median and the median ratio use the ordinary median (mean of the two
    middle values for even groups). HMDA's stored percentiles follow its adapter's
    nearest-rank contract. Decimal comparisons include every specified boundary.
    """
    assert_no_demographics("hmda_validation", (*HMDA_INPUTS, *SCORE_INPUTS["value_range"], "tract", "loans", "median_value"))
    result = {"passed":False, "tracts":0, "median_ratio":None, "share_within_20":None,
              "per_county":{county:{"tracts":0,"median_ratio":None,"share_within_20":None,
                  "warning":"No eligible comparison is available."} for county in COUNTY_FIPS},
              "hmda_year":year, "hmda_loans":0, "hmda_tracts":0,
              "source":f"FFIEC Home Mortgage Disclosure Act data, {year}", "source_as_of":f"{year}-12-31",
              "test_data":test_data, "adjustment":None, "thresholds":dict(HMDA_THRESHOLDS),
              "note":HMDA_NOTE.replace("2025",str(year)), "reasons":[]}
    rows = {}
    for record in records:
        r = record.model_dump(mode="json") if hasattr(record,"model_dump") else record
        if r["dataset"] != "hmda_tract":continue
        p = r["properties"]
        if p["year"] != year:continue
        tract = p["tract"]
        if (not isinstance(tract,str) or len(tract) != 11 or not tract.isascii() or not tract.isdigit()
            or tract[:5] not in COUNTY_FIPS.values() or r["feature_id"] not in {tract,f"{year}:{tract}"} or tract in rows
            or p["county"] != next(c for c,fips in COUNTY_FIPS.items() if fips == tract[:5])
            or type(p["loans"]) is not int or p["loans"] < 1
            or decimal(p["median_value"]) <= 0):
            result["reasons"].append("HMDA tract aggregates are invalid or duplicated.")
            return result
        rows[tract] = p
    result.update(hmda_loans=sum(p["loans"] for p in rows.values()),hmda_tracts=len(rows))
    try:
        adjustment = hmda_adjustment(hpi_records,year)
    except ValueError:
        result["reasons"].append("The HMDA FHFA time adjustment is unavailable.")
        return result
    result["adjustment"] = adjustment
    # Use the exact quotient for thresholds; serialize a float only in the report.
    factor = decimal(adjustment["latest_index"])/decimal(adjustment["base_index"])
    ratios = []; counties = defaultdict(list)
    for tract,p in sorted(rows.items()):
        ours = tract_centres.get(tract,[])
        if p["loans"] < 30 or len(ours) < 30:continue
        ratio = median([decimal(value) for value in ours])/(decimal(p["median_value"])*factor)
        ratios.append(ratio);counties[p["county"]].append(ratio)

    def figures(observations):
        within = sum(Decimal("0.80") <= value <= Decimal("1.20") for value in observations)
        return {"tracts":len(observations), "median_ratio":float(median(observations)) if observations else None,
                "share_within_20":within/len(observations) if observations else None,
                "share_within_10":sum(Decimal(".90") <= v <= Decimal("1.10") for v in observations)/len(observations) if observations else None,
                "median_abs_log_error":float(median([abs(v.ln()) for v in observations])) if observations else None}

    result.update(figures(ratios))
    for county in COUNTY_FIPS:
        observations = counties[county]
        result["per_county"][county] = {**figures(observations), "warning":
            "No tracts meet both minimum counts." if not observations else
            "County median ratio is outside 0.90–1.10." if not Decimal(".90") <= median(observations) <= Decimal("1.10") else None}
    if not ratios:
        result["reasons"].append("No overlapping tracts have at least 30 loans and 30 single-family homes with a range.")
    else:
        if not Decimal(".90") <= median(ratios) <= Decimal("1.10"):
            result["reasons"].append("Median tract ratio is outside 0.90–1.10.")
        if sum(Decimal(".80") <= r <= Decimal("1.20") for r in ratios)*4 < len(ratios)*3:
            result["reasons"].append("Fewer than 75% of tract ratios are within 0.80–1.20.")
    result["passed"] = not result["reasons"]
    check_properties("HMDA validation",result)
    return result


def ranges_published(configured, validation, test_data, hmda_live):
    return configured is True and validation.get("passed") is True and not test_data and hmda_live is True


def factor_for(tract, county_fips, calibration):
    if not calibration:return 1
    # A home's county remains authoritative; foreign/missing tracts use its county factor.
    if isinstance(tract,str) and tract.startswith(county_fips) and tract in calibration["tract"]:
        return calibration["tract"][tract]
    return calibration["county"].get(county_fips,1)


def fit_calibration(tract_centres, records, hpi_records, cfg):
    """Only the specified latest year can cross this fitting boundary.

    The preceding year's loan counts and values are deliberately never read here.
    Geography and aggregate fields are guarded alongside the existing nine-column list.
    """
    assert_no_demographics("range_calibration", (*HMDA_INPUTS,*SCORE_INPUTS["value_range"],"tract","loans","median_value"))
    year=cfg["fit_year"]
    output={"v":1,"fit_year":year,"test_year":cfg["test_year"],
            "county":{fips:1 for fips in COUNTY_FIPS.values()},"tract":{}}
    rows=[]
    for record in records:
        # Filter before serialization too: held-out model objects never cross this boundary.
        dataset=record.dataset if hasattr(record,"model_dump") else record["dataset"]
        properties=record.properties if hasattr(record,"model_dump") else record["properties"]
        if dataset=="hmda_tract" and properties["year"]==year:
            rows.append(record.model_dump(mode="json") if hasattr(record,"model_dump") else record)
    # Reuse strict aggregate validation, even if none meet the comparison minimums.
    audit=hmda_check(tract_centres,rows,hpi_records,year=year)
    if audit["adjustment"] is None or any("invalid" in reason for reason in audit["reasons"]):
        return output
    adj=audit["adjustment"]
    time_factor=decimal(adj["latest_index"])/decimal(adj["base_index"])
    raw={};county=defaultdict(list)
    for r in rows:
        p=r["properties"];tract=p["tract"];ours=tract_centres.get(tract,[])
        if len(ours)<30 or p["loans"]<10:continue
        ratio=decimal(p["median_value"])*time_factor/median([decimal(v) for v in ours])
        raw[tract]=(ratio,p["loans"])
        if p["loans"]>=30:county[tract[:5]].append(ratio)
    output["county"].update({c:float(median(ratios)) for c,ratios in sorted(county.items())})
    for tract,(ratio,n) in sorted(raw.items()):
        base=decimal(output["county"][tract[:5]])
        shrunk=base*(ratio/base)**(Decimal(n)/Decimal(n+cfg["n0"]))
        output["tract"][tract]=float(min(decimal(cfg["clamps"][1]),max(decimal(cfg["clamps"][0]),shrunk)))
    return output


def holdout_passed(calibrated, baseline):
    reasons=list(calibrated["reasons"])
    if calibrated.get("share_within_10") is None or baseline.get("share_within_10") is None:
        reasons.append("The held-out year has no eligible comparison.")
    elif calibrated["tracts"]!=baseline["tracts"] or calibrated["share_within_10"]<baseline["share_within_10"]:
        reasons.append("Held-out share within ±10% is lower than without calibration.")
    return not reasons,reasons


def calibrate(tract_centres, tract_markets, records, hpi_records, hpi, cfg, *, test_data=False):
    """Fit on the latest year; select exclusively on the preceding year; fail back safely."""
    records=list(records);cal=cfg["calibration"];fit_year=cal["fit_year"];test_year=cal["test_year"]
    fit_result=hmda_check(tract_centres,records,hpi_records,test_data=test_data,year=fit_year)
    candidate=fit_calibration(tract_centres,records,hpi_records,cal)
    adjusted={tract:[value_range(v,tract[:5],10,hpi["factor"],cfg["levels"],factor_for(tract,tract[:5],candidate))["mid"] for v in markets]
              for tract,markets in tract_markets.items()}
    baseline=hmda_check(tract_centres,records,hpi_records,test_data=test_data,year=test_year)
    held_out=hmda_check(adjusted,records,hpi_records,test_data=test_data,year=test_year)
    fitted_result=hmda_check(adjusted,records,hpi_records,test_data=test_data,year=fit_year)
    fit_result["label"]=f"Fitting-year result, {fit_year}, uncalibrated"
    fitted_result["label"]=f"Fitting-year result, {fit_year}, calibrated"
    baseline["label"]=f"Held-out result, {test_year}, uncalibrated"
    held_out["label"]=f"Held-out result, {test_year}, calibrated"
    passed,reasons=holdout_passed(held_out,baseline)
    # Invalid fit aggregates must never be made usable by a favourable test year.
    if fit_result["adjustment"] is None or any("invalid" in r for r in fit_result["reasons"]) or not fit_result["hmda_tracts"]:
        passed=False;reasons.append("Latest-year fitting data are unavailable or invalid.")
    if not candidate["tract"]:
        passed=False;reasons.append("No latest-year tract meets the fitting minimums.")
    used=cal["enabled"] and passed
    effective=candidate if used else {**candidate,"county":{c:1 for c in COUNTY_FIPS.values()},"tract":{}}
    result={**(held_out if used else fit_result),"calibration_requested":cal["enabled"],"calibration_used":used,
            "fit_year_result":fit_result,"fit_year_calibrated":fitted_result,"holdout":{"test_year":test_year,"passed":passed,
                "uncalibrated":baseline,"calibrated":held_out,"reasons":reasons},
            "fallback_reason":None if used else "; ".join(reasons) if cal["enabled"] else "Calibration is disabled."}
    info={**cal,"used":used,"test_data":test_data,"fitted_tracts":len(candidate["tract"]),
          "tracts_with_factor":len(effective["tract"]),"county_factors":effective["county"],
          "method":"Latest-year tract loan medians relative to uncalibrated single-family centres; shrink toward the county by n/(n+30), then clamp tract factors to 0.80–1.25. The preceding year is used only for validation."}
    check_properties("calibration validation",result)
    return effective,result,info


def metadata(cfg, hpi, test_data, counties, *, validation=None, hmda_live=False):
    assert_no_demographics("value_range",SCORE_INPUTS["value_range"])
    validation = validation if validation is not None else {"passed":False,"reasons":["HMDA validation is unavailable."]}
    result = {"published":ranges_published(cfg["published"],validation,test_data,hmda_live),"test_data":test_data,"label":"Appraisal-based value range",
        "method":METHOD+(" Multiply by the held-out-validated neighbourhood or county factor before rounding." if validation.get("calibration_used") else ""),"study":cfg["study"],"study_year":2024,"levels":cfg["levels"],"within_10pct":cfg["within_10pct"],
        "hpi":{**hpi,"source":"FHFA House Price Index (purchase-only)","cbsa":"12420","seasonally_adjusted":True},
        "widths":{"base":cfg["base_width"],"wide":cfg["wide_width"]},"flags":FLAG_TEXT,
        "year_over_year_note":YEAR_NOTE,
        "rules":{k:cfg[k] for k in ("new_years","large_lot_acres","size_percentiles","size_min_group","hood_min_group")},
        "size_note":"Size percentiles use the same category, county and appraisal neighbourhood with at least 20 measured homes; otherwise the same category county-wide. Percentiles use nearest rank; homes on the percentile edges are not flagged.",
        "hood_stats_note":"Neighbourhood statistics require at least ten homes with living area and a range; single-family and condo groups are separate, with other categories grouped together. Prices per square foot use the rounded centre.",
        "counties":counties, "validation":validation}
    check_properties("value range metadata",result)
    return result
