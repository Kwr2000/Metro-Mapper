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


@check("tcad_layout", "TCAD export: member names, record lengths and terminators (lengths only, no cell contents)")
def _():
    from collections import Counter
    url = "https://traviscad.org/wp-content/largefiles/2026%20Certified%20Appraisal%20Export%20Supp%200_07182026.zip"
    size, lm, members, final = zip_members(url)
    out = [f"final host {urllib.parse.urlparse(final).netloc}"]
    wanted = {"TOTALS.TXT": 2491, "ABS_SUBD.TXT": 50, "IMP_INFO.TXT": 114, "IMP_DET.TXT": 622, "PROP.TXT": 9922}
    spans = {"IMP_INFO.TXT": (12, 16), "IMP_DET.TXT": (12, 16), "PROP.TXT": (17, 22)}
    for name, expect in wanted.items():
        match = [m for m in members if m.name.rsplit("/", 1)[-1].upper() == name]
        if len(match) != 1:
            out.append(f"{name}: {len(match)} matches {[m.name for m in match]}")
            continue
        m = match[0]
        head_bytes = zip_member_head(url, m, 1_000_000)
        lines = head_bytes.split(b"\n")[:-1]
        lens = Counter(len(l.removesuffix(b"\r")) for l in lines)
        crlf = sum(l.endswith(b"\r") for l in lines)
        est = m.uncomp / (expect + 2)
        text = f"{name}: uncompressed {m.uncomp:,} B (~{est:,.0f} lines if {expect}+CRLF); head {len(lines)} lines, lengths {dict(lens.most_common(3))}, CRLF {crlf}/{len(lines)}"
        if name in spans:
            a, b = spans[name]
            text += f", year cells {dict(Counter(l[a:b].decode('latin-1').strip() for l in lines).most_common(3))}"
        if name == "PROP.TXT":
            text += f", sup_num cells {dict(Counter(l[22:34].decode('latin-1').strip() for l in lines).most_common(2))}"
        if name == "TOTALS.TXT":
            for l in lines:
                if l[12:17].decode("latin-1").strip() == "03":
                    text += f", county row: num_real_mobile {l[282:294].decode('latin-1').strip()} sup_num {l[808:820].decode('latin-1').strip()}"
        out.append(text)
    # The adapter's own GET: same headers, first 1 MiB only.
    req = urllib.request.Request(url, headers={"User-Agent": "metro-mapper/0.1 (+https://github.com/Kwr2000/metro-mapper)", "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            first = resp.read(1 << 20)
            out.append(f"adapter-style GET: HTTP {resp.status}, content-length {resp.headers.get('Content-Length')}, type {resp.headers.get('Content-Type')}, first bytes {first[:4]!r}")
    except Exception as e:
        out.append(f"adapter-style GET failed: {type(e).__name__} {str(e)[:100]}")
    return "; ".join(out)


@check("tcad_small_members", "TCAD export: whole ABS_SUBD and IMP_INFO content checks (counts only)")
def _():
    from collections import Counter
    url = "https://traviscad.org/wp-content/largefiles/2026%20Certified%20Appraisal%20Export%20Supp%200_07182026.zip"
    size, lm, members, final = zip_members(url)
    def whole(name):
        m = next(m for m in members if m.name.rsplit("/", 1)[-1].upper() == name)
        lh = range_get(final, m.offset, m.offset + 29)
        nl, el = struct.unpack("<HH", lh[26:30])
        start = m.offset + 30 + nl + el
        data = range_get(final, start, start + m.comp - 1)
        raw = data if m.method == 0 else zlib.decompress(data, -15)
        return [l.removesuffix(b"\r") for l in raw.split(b"\n") if l], m
    out = []
    lines, m = whole("ABS_SUBD.TXT")
    codes, descs = Counter(), {}
    for l in lines:
        c = l[0:10].decode("latin-1").strip(); d = l[10:50].decode("latin-1").strip()
        codes[c] += 1; descs.setdefault(c, set()).add(d)
    dup = [c for c, n in codes.items() if n > 1]
    conflict = [c for c in dup if len(descs[c]) > 1]
    out.append(f"ABS_SUBD {len(lines):,} rows, {len(codes):,} codes, blank codes {codes.get('', 0)}, duplicate codes {len(dup)}, "
               f"duplicates with different descriptions {len(conflict)} (e.g. {conflict[:3]}), blank descriptions {sum(1 for c in descs if '' in descs[c])}")
    lines, m = whole("IMP_INFO.TXT")
    keys, types, years, bad_ids = Counter(), Counter(), Counter(), 0
    for l in lines:
        pid, yr, iid, typ = (l[0:12].decode("latin-1").strip(), l[12:16].decode("latin-1").strip(),
                             l[16:28].decode("latin-1").strip(), l[28:38].decode("latin-1").strip())
        keys[(pid, iid)] += 1; types[typ] += 1; years[yr] += 1
        bad_ids += not (pid.isdigit() and iid.isdigit())
    out.append(f"IMP_INFO {len(lines):,} rows, duplicate (prop,imprv) keys {sum(1 for n in keys.values() if n > 1)}, blank type codes {types.get('', 0)}, "
               f"non-numeric ids {bad_ids}, years {dict(years)}, top types {dict(types.most_common(6))}")
    return "; ".join(out)


@check("tcad_shapes", "TCAD export: cell shapes in samples of PROP and IMP_DET (shapes and counts only)")
def _():
    from collections import Counter
    url = "https://traviscad.org/wp-content/largefiles/2026%20Certified%20Appraisal%20Export%20Supp%200_07182026.zip"
    size, lm, members, final = zip_members(url)
    def member(name):
        return next(m for m in members if m.name.rsplit("/", 1)[-1].upper() == name)
    def sample(name, max_comp):
        m = member(name)
        lh = range_get(final, m.offset, m.offset + 29)
        nl, el = struct.unpack("<HH", lh[26:30])
        start = m.offset + 30 + nl + el
        data = range_get(final, start, start + min(m.comp, max_comp) - 1)
        raw = zlib.decompressobj(-15).decompress(data)
        return [l.removesuffix(b"\r") for l in raw.split(b"\n")[:-1]]
    def shape(v):
        v = v.strip()
        return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", v)) or "(blank)"
    cell = lambda l, a, b: l[a - 1:b].decode("latin-1")
    out = []
    # IMP_INFO keys, to look for orphan segments in the IMP_DET sample.
    m = member("IMP_INFO.TXT")
    lh = range_get(final, m.offset, m.offset + 29)
    nl, el = struct.unpack("<HH", lh[26:30])
    start = m.offset + 30 + nl + el
    info = zlib.decompress(range_get(final, start, start + m.comp - 1), -15).split(b"\n")
    keys = {(l[0:12], l[16:28]) for l in info if l.strip()}
    det = sample("IMP_DET.TXT", 6_000_000)
    orphans = sum((l[0:12], l[16:28]) not in keys for l in det)
    fields = {"year": (13, 16), "yr_built": (86, 89), "area": (94, 108)}
    parts = [f"IMP_DET sample {len(det):,} rows, orphan segments {orphans}, lengths {dict(Counter(len(l) for l in det).most_common(2))}"]
    for k, (a, b) in fields.items():
        parts.append(f"{k} shapes {dict(Counter(shape(cell(l, a, b)) for l in det).most_common(4))}")
    parts.append(f"segment codes {dict(Counter(cell(l, 41, 50).strip() for l in det).most_common(14))}")
    out.append("; ".join(parts))
    prop = sample("PROP.TXT", 6_000_000)
    pf = {"prop_type": (13, 17), "val_yr": (18, 22), "sup_num": (23, 34), "partial_owner": (679, 679), "udi": (680, 691),
          "land_hstd": (1796, 1810), "land_non": (1811, 1825), "imprv_hstd": (1826, 1840), "imprv_non": (1841, 1855),
          "deed_dt": (2034, 2058), "land_acres": (2772, 2791), "market": (4214, 4227), "situs_num": (4460, 4474)}
    parts = [f"PROP sample {len(prop):,} rows, lengths {dict(Counter(len(l) for l in prop).most_common(2))}"]
    for k, (a, b) in pf.items():
        parts.append(f"{k} shapes {dict(Counter(shape(cell(l, a, b)) for l in prop).most_common(4))}")
    parts.append(f"prop types {dict(Counter(cell(l, 13, 17).strip() for l in prop).most_common(6))}")
    parts.append(f"imprv state {dict(Counter(cell(l, 2732, 2741).strip() for l in prop).most_common(12))}")
    parts.append(f"land state {dict(Counter(cell(l, 2742, 2751).strip() for l in prop).most_common(6))}")
    out.append("; ".join(parts))
    return " || ".join(out)


@check("tcad_dups", "TCAD PROP.TXT: repeated property IDs in the first part of the file (codes and counts only)")
def _():
    from collections import Counter
    url = "https://traviscad.org/wp-content/largefiles/2026%20Certified%20Appraisal%20Export%20Supp%200_07182026.zip"
    size, lm, members, final = zip_members(url)
    m = next(m for m in members if m.name.rsplit("/", 1)[-1].upper() == "PROP.TXT")
    lh = range_get(final, m.offset, m.offset + 29)
    nl, el = struct.unpack("<HH", lh[26:30])
    start = m.offset + 30 + nl + el
    data = range_get(final, start, start + 40_000_000 - 1)
    raw = zlib.decompressobj(-15).decompress(data)
    lines = [l.removesuffix(b"\r") for l in raw.split(b"\n")[:-1]]
    cell = lambda l, a, b: l[a - 1:b].decode("latin-1").strip()
    fields = {"prop_type": (13, 17), "val_yr": (18, 22), "sup_num": (23, 34), "geo_id": (547, 596), "imprv_state": (2732, 2741),
              "land_state": (2742, 2751), "market": (4214, 4227), "hood": (1686, 1695), "situs_num": (4460, 4474),
              "situs_street": (1050, 1099), "deed": (2034, 2058), "land_acres": (2772, 2791), "abs": (1676, 1685)}
    byid = {}
    for i, l in enumerate(lines):
        byid.setdefault(cell(l, 1, 12), []).append(i)
    dups = {k: v for k, v in byid.items() if len(v) > 1}
    differ, types, states, gaps = Counter(), Counter(), Counter(), Counter()
    for k, idx in dups.items():
        rows = [lines[i] for i in idx]
        for f, (a, b) in fields.items():
            if len({cell(r, a, b) for r in rows}) > 1:
                differ[f] += 1
        types[tuple(cell(r, 13, 17) for r in rows)] += 1
        states[tuple(cell(r, 2732, 2741) or cell(r, 2742, 2751) for r in rows)] += 1
        gaps[idx[1] - idx[0] if len(idx) > 1 else 0] += 1
    return (f"first {len(lines):,} rows, {len(byid):,} distinct IDs, repeated IDs {len(dups)}, max repeats {max((len(v) for v in dups.values()), default=1)}; "
            f"fields that differ between repeats {dict(differ)}; type pairs {dict(types.most_common(5))}; state pairs {dict(states.most_common(6))}; "
            f"row gaps {dict(gaps.most_common(4))}")


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


# --- Service metadata for task specs (layer ids and field names only)

def _fields(layer_url: str) -> str:
    j = get_json(layer_url + "?f=json")
    if "error" in j:
        raise RuntimeError(str(j["error"])[:150])
    return (f"'{j.get('name')}' max {j.get('maxRecordCount')}; fields: "
            + ", ".join(f"{f['name']}:{f['type'].replace('esriFieldType', '')}" for f in j.get("fields", [])))


@check("meta_tigerweb_layers", "TIGERweb Census2020 layer list")
def _():
    j = get_json("https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer?f=json")
    return "; ".join(f"{l['id']}={l['name']}" for l in j.get("layers", []))


@check("meta_tigerweb_bg_fields", "TIGERweb Census2020 block-group fields")
def _():
    return _fields("https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/tigerWMS_Census2020/MapServer/8")


@check("meta_austin_npa_fields", "City of Austin neighborhood planning areas: fields")
def _():
    base = "https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/PLANNINGCADASTRE_neighborhood_planning_areas/FeatureServer"
    lid = get_json(base + "?f=json")["layers"][0]["id"]
    return _fields(f"{base}/{lid}")


@check("meta_wcad_subdivision_cols", "WCAD subdivisions: columns")
def _():
    status, _, body, _ = _req("https://data.wcad.org/api/views/em3v-vwsk.json")
    v = json.loads(body)
    return ", ".join(f"{c['fieldName']}:{c['dataTypeName']}" for c in v.get("columns", []))


@check("meta_nfhl_zone_fields", "FEMA NFHL flood hazard zones: fields")
def _():
    return _fields("https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28")


TXUCR_XLSX = ("https://txucr.nibrs.com/Report/DownloadReportExcel?offenses=&startdate=Jan%20-%202025"
              "&enddate=Dec%20-%202025&reportId={rid}")
TIGER_CURRENT = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer"


@check("dps_txucr_agency_xlsx", "DPS UCR portal: 2025 index crime by agency (XLSX, 50k-100k report)")
def _():
    import re

    url = TXUCR_XLSX.format(rid=613)
    page = "https://txucr.nibrs.com/Report/TexasCITReport"

    def show(status, body):
        kind = "xlsx" if body[:4] == b"PK\x03\x04" else "not a zip"
        text = body.decode("utf-8", "replace") if kind != "xlsx" else ""
        title = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
        snippet = re.sub(r"<[^>]+>|\s+", " ", text)[:160]
        return f"HTTP {status}, {len(body):,} bytes, {kind}" + (
            f", title {title.group(1).strip()[:80]!r}, text {snippet!r}" if kind != "xlsx" else "")

    out = []
    # The page itself, then the download with a conventional crawler-style user agent that
    # still names this project (ASP.NET sites sometimes fail on unrecognised agents).
    compat = f"Mozilla/5.0 (compatible; {UA})"
    for label, u, agent in (("page, project UA", page, UA), ("page, compatible UA", page, compat),
                            ("xlsx, compatible UA", url, compat)):
        status, _, body, _ = _req(u, headers={"User-Agent": agent, "Accept": "*/*"})
        out.append(f"{label}: " + show(status, body if u == url else body[:4000]))
        time.sleep(2)
    return "; ".join(out)


@check("tiger_current_places", "TIGERweb Current: incorporated places in the study area")
def _():
    layers = get_json(TIGER_CURRENT + "?f=json")["layers"]
    hits = [l for l in layers if l["name"].strip().lower() == "incorporated places"]
    if len(hits) != 1:
        return "layers named Incorporated Places: " + ", ".join(str(l["id"]) for l in hits)
    lid = hits[0]["id"]
    n = arcgis_count(f"{TIGER_CURRENT}/{lid}", bbox=BBOX)
    return f"layer {lid}; {n} places intersect the study bbox; fields: " + _fields(f"{TIGER_CURRENT}/{lid}")[:300]


TLC_ELECTIONS = ("https://data.capitol.texas.gov/dataset/35b16aee-0bb0-4866-b1ec-859f1f044241/resource/"
                 "e1cd6332-6a7a-4c78-ad2a-852268f6c7a2/download/2024-general-vtds-election-data.zip")
TLC_VTDS = ("https://data.capitol.texas.gov/dataset/4d8298d0-d176-4c19-b174-42837027b73e/resource/"
            "906f47e4-4e39-4156-b1bd-4969be0b2780/download/vtds_24pg.zip")


@check("tlc_elections", "Texas Legislative Council: 2024 general VTD election data and VTD shapes (HEAD)")
def _():
    out = []
    for label, url in (("election data", TLC_ELECTIONS), ("VTD shapes", TLC_VTDS)):
        status, hdrs, final = head(url)
        out.append(f"{label}: HTTP {status}, {mb(size_of(hdrs))}, Last-Modified {hdrs.get('last-modified', '?')}")
    return "; ".join(out)


# Benchmarks (P1-11): one ACS request for every comparison geography via the ucgid predicate.
PEERS = {"0668000": "San Jose", "1235000": "Jacksonville", "4827000": "Fort Worth", "3918000": "Columbus",
         "1836003": "Indianapolis", "3712000": "Charlotte", "0667000": "San Francisco", "5363000": "Seattle",
         "0820000": "Denver", "4819000": "Dallas", "4865000": "San Antonio", "0666000": "San Diego",
         "4752006": "Nashville", "1150000": "Washington", "4055000": "Oklahoma City"}


@check("census_ucgid_benchmarks", "Census ACS 2024 5-year: comparison geographies in one ucgid request")
def _():
    key = os.environ.get("CENSUS_API_KEY", "")
    ids = ["0100000US", "0400000US48", "0500000US48453", "0500000US48491", "0500000US48209",
           "310M700US12420", "310M600US12420", "1600000US4805000", *("1600000US" + g for g in PEERS)]
    out = []
    url = ("https://api.census.gov/data/2024/acs/acs5?get=NAME,B01003_001E,B19013_001E&ucgid="
           + ",".join(ids) + (f"&key={key}" if key else ""))
    status, _, body, _ = _req(url)
    if status != 200:
        return f"HTTP {status}: {body[:200].decode('utf-8', 'replace')}"
    rows = json.loads(body)
    out.append(f"{len(rows) - 1} of {len(ids)} geographies returned")
    for name, pop, income, ucgid in ((r[0], r[1], r[2], r[-1]) for r in rows[1:]):
        out.append(f"{ucgid} {name}: pop {pop}, median income {income}")
    return "; ".join(out)



@check("fbi_national", "FBI Crime Data API (documented, api.usa.gov): 2025 national violent and property")
def _():
    key = os.environ.get("FBI_API_KEY", "")
    if not key:
        return "FBI_API_KEY not set"
    out = []
    for code in ("V", "P"):
        url = (f"https://api.usa.gov/crime/fbi/cde/summarized/national/{code}"
               f"?from=01-2025&to=12-2025&type=rates&API_KEY={key}")
        status, _, body, _ = _req(url)
        if status != 200:
            out.append(f"{code}: HTTP {status}")  # never print the body: it could echo the key
            continue
        j = json.loads(body)
        actual = sum((j.get("offenses", {}).get("actuals", {}).get("United States Offenses") or {}).values())
        pops = list((j.get("populations", {}).get("participated_population", {}).get("United States") or {}).values())
        rate = actual / (sum(pops) / len(pops)) * 1000 if pops else None
        out.append(f"{code}: {len(pops)} months, offenses {actual:,}, per 1,000 {rate:.2f}, "
                   f"top keys {sorted(j)[:6]}")
        time.sleep(2)
    return "; ".join(out)


@check("fbi_arson", "FBI Crime Data API: does the national property series (P) include arson?")
def _():
    key = os.environ.get("FBI_API_KEY", "")
    if not key:
        return "FBI_API_KEY not set"
    totals, out = {}, []
    for code in ("P", "BUR", "LAR", "MVT", "ARS"):
        url = (f"https://api.usa.gov/crime/fbi/cde/summarized/national/{code}"
               f"?from=01-2025&to=12-2025&API_KEY={key}")
        status, _, body, _ = _req(url)
        if status != 200:
            out.append(f"{code}: HTTP {status}")  # never print the body: it could echo the key
            continue
        j = json.loads(body)
        totals[code] = sum((j.get("offenses", {}).get("actuals", {}).get("United States Offenses") or {}).values())
        out.append(f"{code}: {totals[code]:,}")
        time.sleep(2)
    if {"P", "BUR", "LAR", "MVT"} <= totals.keys():
        three = totals["BUR"] + totals["LAR"] + totals["MVT"]
        out.append(f"BUR+LAR+MVT = {three:,}; P - that = {totals['P'] - three:,}"
                   + (f"; ARS = {totals['ARS']:,}" if "ARS" in totals else ""))
    return "; ".join(out)


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
