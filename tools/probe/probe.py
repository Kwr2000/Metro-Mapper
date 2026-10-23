"""Metro Mapper source probe (Phase 0).

Checks, from wherever it runs (normally a GitHub Actions runner), that each candidate
source can be reached unattended, and reports sizes, dates and record counts.

Polite by design:
- one small request per check (HEAD, a byte range, a count query, or a page fetch);
- no bulk downloads: zip archives are inspected by reading only their directory
  (the last bytes of the file) and, at most, one small member;
- never prints personal data: only counts, sizes, dates, column names and status.

Standard library only. Usage:  python tools/probe/probe.py [--only id1,id2] > summary.md
CENSUS_API_KEY is read from the environment if set and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from typing import Callable

UA = "metro-mapper-probe/0.1 (+https://github.com/Kwr2000/metro-mapper)"
TIMEOUT = 60
BBOX = (-98.30, 29.75, -97.25, 30.91)  # Travis + Williamson + Hays, roughly


# ---------------------------------------------------------------- HTTP helpers

def _req(url: str, method: str = "GET", headers: dict | None = None,
         max_bytes: int | None = None) -> tuple[int, dict, bytes, str]:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            body = b"" if method == "HEAD" else (
                resp.read(max_bytes) if max_bytes else resp.read())
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body, resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read(2000), url


def head(url: str) -> tuple[int, dict, str]:
    status, hdrs, _, final = _req(url, "HEAD")
    if status in (403, 405, 501):  # some servers refuse HEAD; ask for one byte instead
        status, hdrs, _, final = _req(url, headers={"Range": "bytes=0-0"})
    return status, hdrs, final


def get_json(url: str):
    status, hdrs, body, _ = _req(url)
    ctype = hdrs.get("content-type", "")
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    try:
        return json.loads(body)
    except ValueError:
        raise RuntimeError(f"not JSON (content-type {ctype!r}, starts {body[:60]!r})")


def size_of(hdrs: dict) -> int | None:
    if "content-range" in hdrs:
        m = re.search(r"/(\d+)$", hdrs["content-range"])
        if m:
            return int(m.group(1))
    if "content-length" in hdrs:
        return int(hdrs["content-length"])
    return None


def mb(n: int | None) -> str:
    return "?" if n is None else f"{n / 1e6:,.1f} MB"


def range_get(url: str, start: int, end: int) -> bytes:
    status, _, body, _ = _req(url, headers={"Range": f"bytes={start}-{end}"})
    if status != 206:
        raise RuntimeError(f"range request answered HTTP {status} (no byte ranges)")
    return body


# ---------------------------------------------------------------- zip directory reader

@dataclass
class ZipMember:
    name: str
    comp: int
    uncomp: int
    method: int
    offset: int


def zip_members(url: str) -> tuple[int, str, list[ZipMember], str]:
    """List a remote zip's members by reading only its central directory."""
    status, hdrs, final = head(url)
    size = size_of(hdrs)
    if not size:  # e.g. a redirect to a chunked response: ask the final URL for one byte
        status, hdrs, _, final = _req(final, headers={"Range": "bytes=0-0"}, max_bytes=1)
        size = size_of(hdrs)
    if not size:
        raise RuntimeError(f"HTTP {status}, no size reported")
    tail_len = min(size, 1 << 20)
    tail = range_get(final, size - tail_len, size - 1)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise RuntimeError("end of central directory not found in last 1 MB")
    n, cd_size, cd_off = struct.unpack("<HII", tail[eocd + 10:eocd + 20])
    if cd_off == 0xFFFFFFFF or n == 0xFFFF:  # zip64
        loc = tail.rfind(b"PK\x06\x07")
        z64_off = struct.unpack("<Q", tail[loc + 8:loc + 16])[0]
        rec = tail[z64_off - (size - tail_len):]
        n, cd_size, cd_off = struct.unpack("<QQQ", rec[32:56])
    p = cd_off - (size - tail_len)
    if p < 0:
        tail = range_get(final, cd_off, size - 1)
        p = 0
    members = []
    for _ in range(n):
        (method, comp, uncomp, nl, el, cl, lho) = (
            struct.unpack("<H", tail[p + 10:p + 12])[0],
            *struct.unpack("<II", tail[p + 20:p + 28]),
            *struct.unpack("<HHH", tail[p + 28:p + 34]),
            struct.unpack("<I", tail[p + 42:p + 46])[0],
        )
        name = tail[p + 46:p + 46 + nl].decode("utf-8", "replace")
        extra = tail[p + 46 + nl:p + 46 + nl + el]
        q = 0
        while q + 4 <= len(extra):  # zip64 extended sizes
            hid, ln = struct.unpack("<HH", extra[q:q + 4])
            if hid == 1:
                vals, o = extra[q + 4:q + 4 + ln], 0
                if uncomp == 0xFFFFFFFF:
                    uncomp = struct.unpack("<Q", vals[o:o + 8])[0]; o += 8
                if comp == 0xFFFFFFFF:
                    comp = struct.unpack("<Q", vals[o:o + 8])[0]; o += 8
                if lho == 0xFFFFFFFF:
                    lho = struct.unpack("<Q", vals[o:o + 8])[0]
            q += 4 + ln
        members.append(ZipMember(name, comp, uncomp, method, lho))
        p += 46 + nl + el + cl
    return size, hdrs.get("last-modified", "?"), members, final


def zip_member_head(url: str, m: ZipMember, max_comp: int = 200_000) -> bytes:
    """Read and inflate the first part of one member (small members: all of it)."""
    lh = range_get(url, m.offset, m.offset + 29)
    nl, el = struct.unpack("<HH", lh[26:30])
    start = m.offset + 30 + nl + el
    data = range_get(url, start, start + min(m.comp, max_comp) - 1)
    if m.method == 0:
        return data
    d = zlib.decompressobj(-15)
    return d.decompress(data, 2_000_000)


# ---------------------------------------------------------------- checks

@dataclass
class Result:
    id: str
    ok: bool
    detail: str
    ms: int = 0


CHECKS: list[tuple[str, str, Callable[[], str]]] = []


def check(cid: str, label: str):
    def deco(fn):
        CHECKS.append((cid, label, fn))
        return fn
    return deco


def arcgis_count(layer_url: str, where: str = "1=1", bbox: tuple | None = None) -> int:
    params = {"where": where, "returnCountOnly": "true", "f": "json"}
    if bbox:
        params.update({"geometry": ",".join(map(str, bbox)), "geometryType": "esriGeometryEnvelope",
                       "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"})
    j = get_json(layer_url + "/query?" + urllib.parse.urlencode(params))
    if "count" not in j:
        raise RuntimeError(f"no count: {str(j)[:150]}")
    return j["count"]


def socrata(domain: str, dataset: str, soql: str):
    return get_json(f"https://{domain}/resource/{dataset}.json?" + urllib.parse.urlencode({"$query": soql}))


# --- Appraisal rolls

@check("tcad_page", "TCAD public information page lists the certified export")
def _():
    status, _, body, _ = _req("https://traviscad.org/publicinformation")
    links = re.findall(rb'href="([^"]*largefiles/[^"]*\.zip)"', body)
    certs = [l.decode() for l in links if b"Certified" in l or b"certified" in l]
    return f"HTTP {status}; {len(links)} export links; certified: {', '.join(c.rsplit('/', 1)[-1] for c in certs[:3])}"


@check("tcad_export", "TCAD 2026 certified appraisal export (zip directory only)")
def _():
    url = "https://traviscad.org/wp-content/largefiles/2026%20Certified%20Appraisal%20Export%20Supp%200_07182026.zip"
    size, lm, members, _ = zip_members(url)
    names = {m.name: m.uncomp for m in members}
    return (f"{mb(size)}, last-modified {lm}; {len(members)} files; PROP.TXT {mb(names.get('PROP.TXT'))}, "
            f"IMP_DET.TXT {mb(names.get('IMP_DET.TXT'))} uncompressed")


@check("wcad_socrata_parcels", "WCAD open data: parcel polygons (count + 1 geometry)")
def _():
    n = socrata("data.wcad.org", "an3x-cnmw", "SELECT count(*) AS n")[0]["n"]
    status, _, body, _ = _req("https://data.wcad.org/resource/an3x-cnmw.geojson?" +
                              urllib.parse.urlencode({"$select": "parcelid,geometry", "$limit": "1"}))
    gtype = json.loads(body)["features"][0]["geometry"]["type"] if status == 200 else f"HTTP {status}"
    return f"{int(n):,} parcels; GeoJSON geometry {gtype}"


@check("wcad_socrata_property", "WCAD open data: certified property table (2026 rows, living area filled)")
def _():
    r = socrata("data.wcad.org", "ai3c-c9pf",
                "SELECT count(*) AS n, count(totalsqftlivingarea) AS la WHERE tax_year = '2026'")[0]
    return f"{int(r['n']):,} rows for 2026, living area present on {int(r['la']):,}"


@check("wcad_roll_sharepoint", "WCAD 2026 certified roll download (SharePoint link, unattended?)")
def _():
    url = ("https://williamsoncad.sharepoint.com/:u:/s/OperationsInfo/"
           "IQBJmdRcyJKnQI28Z7qxxJYrASLIJSlpY0tHdOPHi9DZc3c?e=MbvQlH&download=1")
    status, hdrs, body, final = _req(url, headers={"Range": "bytes=0-3"}, max_bytes=4)
    kind = "zip" if body[:2] == b"PK" else hdrs.get("content-type", "?")
    if status not in (200, 206):
        raise RuntimeError(f"HTTP {status} (not downloadable unattended); content-type {kind}")
    return f"HTTP {status}; first bytes look like: {kind}; size {mb(size_of(hdrs))}; final host {urllib.parse.urlparse(final).netloc}"


@check("hays_page", "Hays CAD data downloads page: newest monthly export link")
def _():
    status, _, body, _ = _req("https://hayscad.com/data-downloads/")
    links = re.findall(rb'href="(https://hayscad\.com/wp-content/uploads/[^"]*PROPERTY-DATA-EXPORT[^"]*\.zip)"', body)
    newest = links[0].decode() if links else "none found"
    return f"HTTP {status}; {len(links)} property-data export links; first listed: {newest.rsplit('/', 1)[-1]}"


@check("hays_export", "Hays CAD monthly export as of 2026-10-19 (zip directory only)")
def _():
    url = "https://hayscad.com/wp-content/uploads/2026/10/2026-PROPERTY-DATA-EXPORT-FILES-AS-OF-10-19-2026.zip"
    size, lm, members, _ = zip_members(url)
    return f"{mb(size)}, last-modified {lm}; members: " + ", ".join(
        re.sub(r".*FILE-([A-Z]+)-.*", r"\1", m.name) for m in members)


@check("comptroller_pvs", "Comptroller 2024 property value study page (Travis, category A)")
def _():
    status, _, body, _ = _req("https://comptroller.texas.gov/auto-data/PT2/ratio-study/2024/2270000001A.php")
    m = re.search(rb"SINGLE-FAMILY RESIDENCES.{0,400}", body, re.S)
    cells = re.findall(rb">\s*([\d.,]+)\s*<", m.group(0)) if m else []
    return f"HTTP {status}; category A cells: {[c.decode() for c in cells[:7]]}"


# --- Parcel shapes

for _fips, _name in (("48453", "travis"), ("48491", "williamson"), ("48209", "hays")):
    def _mk(fips=_fips, name=_name):
        @check(f"stratmap_{name}", f"TxGIO StratMap 2026 parcels, {name.title()} (zip directory only)")
        def _():
            url = ("https://tnris-data-warehouse.s3.us-east-1.amazonaws.com/LCD/collection/"
                   f"stratmap-2026-land-parcels/items/shp/stratmap-2026-land-parcels_{fips}_shp.zip")
            size, lm, members, _ = zip_members(url)
            shx = next((m for m in members if m.name.endswith(".shx")), None)
            n = (shx.uncomp - 100) // 8 if shx else None
            return f"{mb(size)}, last-modified {lm}; ~{n:,} parcels (from .shx)"
    _mk()


@check("travis_county_tcad_layer", "Travis County GIS: TCAD parcels layer (count)")
def _():
    n = arcgis_count("https://gis.traviscountytx.gov/server1/rest/services/Boundaries_and_Jurisdictions/TCAD_public/MapServer/0")
    return f"{n:,} parcels; max 2,000 per page"


@check("hays_county_parcels", "Hays County GIS: parcels layer (count)")
def _():
    base = "https://services5.arcgis.com/bVphnK8rPe5MHUSr/arcgis/rest/services/Hays_County_Parcels/FeatureServer"
    j = get_json(base + "?f=json")
    lid = j["layers"][0]["id"]
    return f"layer '{j['layers'][0]['name']}': {arcgis_count(f'{base}/{lid}'):,} features"


# --- Schools

@check("tea_campus_csv", "TEA 2026 campus accountability CSV (first 4 KB only)")
def _():
    url = ("https://rptsvr1.tea.texas.gov/cgi/sas/broker/?_service=marykay&_program=perfrept.perfmast.sas"
           "&_debug=0&ccyy=2026&dsname=RATE&sumlev=C&key=RATE&key=D1&key=D2&key=D3&key=FLAG&key=GRD"
           "&key=PAIR&datafmt=C&prgopt=reports/acct/dd/dd_get_data.sas")
    status, hdrs, body, _ = _req(url, max_bytes=4096)
    first = body.split(b"\n", 1)[0][:120].decode("latin1")
    return f"HTTP {status}; content-type {hdrs.get('content-type')}; header starts: {first}"


@check("aisd_zones", "AISD 2026-27 zones (Reassignments FeatureServer, elementary layer count)")
def _():
    return f"{arcgis_count('https://services2.arcgis.com/5HXFPHsCivNoDso0/arcgis/rest/services/Reassignments/FeatureServer/9'):,} elementary zones"


@check("hays_cisd_zones", "Hays CISD zones (PASA School Finder, elementary layer count)")
def _():
    return f"{arcgis_count('https://services8.arcgis.com/dRr2IyKONDHB1yz8/arcgis/rest/services/Hays_School_Finder/FeatureServer/2'):,} elementary zones"


# --- Safety

@check("apd_crime", "APD crime reports (aggregate count, last full month)")
def _():
    r = socrata("data.austintexas.gov", "fdj4-gpfu",
                "SELECT count(*) AS n, count(census_block_group) AS bg "
                "WHERE rep_date >= '2026-09-01' AND rep_date < '2026-10-01'")[0]
    return f"Sept 2026: {int(r['n']):,} reports, {int(r['bg']):,} with a block group"


@check("dps_crime_in_texas", "Texas DPS Crime in Texas 2025 report (HEAD)")
def _():
    status, hdrs, _ = head("https://www.dps.texas.gov/sites/default/files/documents/crimereports/25/2025cit.pdf")
    return f"HTTP {status}; {mb(size_of(hdrs))}; last-modified {hdrs.get('last-modified', '?')}"


# --- Access, flood, demographics

@check("capmetro_gtfs", "CapMetro GTFS on data.texas.gov (zip directory + feed_info.txt)")
def _():
    size, lm, members, final = zip_members("https://data.texas.gov/download/r4v4-vz24/application%2Fzip")
    fi = next((m for m in members if m.name.endswith("feed_info.txt")), None)
    info = zip_member_head(final, fi).decode("utf-8", "replace").splitlines()[:2] if fi else ["no feed_info.txt"]
    return f"{mb(size)}; {len(members)} files; feed_info: {' / '.join(info)}"


@check("geofabrik_texas", "Geofabrik Texas OSM extract (HEAD)")
def _():
    status, hdrs, _ = head("https://download.geofabrik.de/north-america/us/texas-latest.osm.pbf")
    return f"HTTP {status}; {mb(size_of(hdrs))}; last-modified {hdrs.get('last-modified', '?')}"


@check("fema_nfhl", "FEMA NFHL flood hazard zones in the study area (count)")
def _():
    n = arcgis_count("https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28", bbox=BBOX)
    return f"{n:,} flood hazard polygons intersect the three-county box"


@check("tigerweb_bg", "TIGERweb 2020 block groups for the three counties (count)")
def _():
    n = arcgis_count("https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer/8",
                     where="STATE='48' AND COUNTY IN ('453','491','209')")
    return f"{n:,} block groups"


@check("acs_keyless", "Census ACS 2024 5-year, county level, no key")
def _():
    j = get_json("https://api.census.gov/data/2024/acs/acs5?get=NAME,B01003_001E&for=county:453,491,209&in=state:48")
    return f"JSON with {len(j) - 1} counties"


@check("acs_blockgroup_key", "Census ACS 2024 5-year, block groups in Hays, with key if set")
def _():
    key = os.environ.get("CENSUS_API_KEY", "")
    q = {"get": "B01003_001E", "for": "block group:*", "in": "state:48 county:209"}
    if key:
        q["key"] = key
    try:
        j = get_json("https://api.census.gov/data/2024/acs/acs5?" + urllib.parse.urlencode(q))
        return f"key {'set' if key else 'NOT set'}; JSON with {len(j) - 1} block groups"
    except RuntimeError as e:
        raise RuntimeError(f"key {'set' if key else 'NOT set'}; {e}")


@check("hmda_2025", "HMDA 2025 data browser: home-purchase originations, three counties")
def _():
    q = {"years": "2025", "counties": "48453,48491,48209", "actions_taken": "1", "loan_purposes": "1"}
    j = get_json("https://ffiec.cfpb.gov/v2/data-browser-api/view/aggregations?" + urllib.parse.urlencode(q))
    aggs = j.get("aggregations", [])
    return f"{sum(a.get('count', 0) for a in aggs):,} loans across {len(aggs)} groups"


# --- Checks-only sources and names

@check("redfin_zip_tracker", "Redfin Data Center ZIP market tracker (HEAD)")
def _():
    status, hdrs, _ = head("https://redfin-public-data.s3.us-west-2.amazonaws.com/redfin_market_tracker/zip_code_market_tracker.tsv000.gz")
    return f"HTTP {status}; {mb(size_of(hdrs))}; last-modified {hdrs.get('last-modified', '?')}"


@check("zillow_zhvi_zip", "Zillow ZHVI by ZIP (HEAD)")
def _():
    status, hdrs, _ = head("https://files.zillowstatic.com/research/public_csvs/zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv")
    return f"HTTP {status}; {mb(size_of(hdrs))}; last-modified {hdrs.get('last-modified', '?')}"


@check("austin_neighborhoods", "City of Austin neighborhood planning areas (count)")
def _():
    base = "https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/PLANNINGCADASTRE_neighborhood_planning_areas/FeatureServer"
    j = get_json(base + "?f=json")
    lid = j["layers"][0]["id"]
    return f"{arcgis_count(f'{base}/{lid}'):,} areas"


@check("wcad_subdivisions", "WCAD open data: subdivision polygons (count)")
def _():
    return f"{int(socrata('data.wcad.org', 'em3v-vwsk', 'SELECT count(*) AS n')[0]['n']):,} subdivisions"


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated check ids")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s}
    results: list[tuple[str, str, Result]] = []
    for cid, label, fn in CHECKS:
        if only and cid not in only:
            continue
        t0 = time.monotonic()
        try:
            res = Result(cid, True, fn())
        except Exception as e:  # report and continue: a probe never stops at the first failure
            res = Result(cid, False, f"{type(e).__name__}: {e}"[:300])
        res.ms = int((time.monotonic() - t0) * 1000)
        results.append((cid, label, res))
        time.sleep(1)  # be gentle; most checks hit different hosts anyway
    ok = sum(r.ok for *_, r in results)
    print(f"# Metro Mapper source probe\n\n{ok}/{len(results)} checks OK, "
          f"run {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n")
    print("| check | ok | time | result |\n|---|---|---|---|")
    for cid, label, r in results:
        detail = r.detail.replace("|", "/").replace("\n", " ")
        print(f"| `{cid}` {label} | {'yes' if r.ok else '**no**'} | {r.ms / 1000:.1f}s | {detail} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
