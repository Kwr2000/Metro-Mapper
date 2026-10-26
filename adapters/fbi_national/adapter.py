"""Reported national FBI counts, never estimates or peer-city comparisons."""
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date, timezone

from mm.adapter import RawPayload, Request, SourceAdapter
from mm.benchmarks import record as benchmark
from mm.schemas import AreaFeature

API = "https://api.usa.gov/crime/fbi/cde/summarized/national/"
EMPTY = {"type": "GeometryCollection", "geometries": []}
NOTE = "Reported offenses (not FBI estimates); about 97% of the US population covered"


def monthly(series, year, population=False):
    if not isinstance(series, dict):
        raise ValueError("FBI monthly series missing")
    parsed = {}
    for key, value in series.items():
        month = None
        for fmt in ("%m-%Y", "%Y-%m", "%m/%Y"):
            try:
                day = datetime.strptime(key, fmt)
                if day.year == year:
                    month = day.month
                break
            except (ValueError, TypeError):
                pass
        if month is None or month in parsed or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("invalid FBI monthly values/dates")
        if value < 0 or (population and value <= 0) or (not population and value != int(value)):
            raise ValueError("invalid FBI count/population")
        parsed[month] = value
    if set(parsed) != set(range(1, 13)):
        raise ValueError("FBI needs all twelve months")
    return list(parsed.values())


class FBINational(SourceAdapter):
    id = "fbi_national"
    entity = "area_feature"
    cadence = "annual"
    benchmark_source = "dps_agency"

    def plan(self, ctx):
        now = ctx.now.astimezone(timezone.utc)
        self.year = now.year - (1 if now.month >= 7 else 2)
        if ctx.mode == "live" and not os.environ.get("FBI_API_KEY"):
            raise RuntimeError("FBI_API_KEY is required")
        return [Request(kind.lower(), {"url": API + kind, "kind": kind,
                "query": {"from": f"01-{self.year}", "to": f"12-{self.year}"}}) for kind in ("V", "P", "ARS")]

    def fetch(self, req, ctx):
        key = os.environ.get("FBI_API_KEY")
        if not key:
            raise RuntimeError("FBI_API_KEY is required")
        try:
            query = {**req.params["query"], "API_KEY": key}
            request = urllib.request.Request(req.params["url"] + "?" + urllib.parse.urlencode(query),
                                             headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(request, timeout=90) as response:
                body = json.load(response) if response.status == 200 else None
                return RawPayload(req, body, status=response.status)
        except urllib.error.HTTPError as exc:
            return RawPayload(req, None, status=exc.code)
        except Exception:
            raise RuntimeError("FBI transport failed; URL and response withheld") from None

    def normalize(self, raw):
        if raw.status != 200:
            raise ValueError(f"FBI HTTP {raw.status}; response withheld")
        try:
            counts = monthly(raw.body["offenses"]["actuals"]["United States Offenses"], self.year)
            populations = monthly(raw.body["populations"]["participated_population"]["United States"], self.year, True)
        except (KeyError, TypeError):
            raise ValueError("FBI response fields missing; response withheld") from None
        yield AreaFeature(dataset="national_input", feature_id=raw.request.params["kind"], geometry=EMPTY,
            properties={"count": sum(counts), "population": sum(populations) / 12})

    def finalize(self, records):
        rows = {r.feature_id: r.properties for r in records}
        if set(rows) != {"V", "P", "ARS"} or len(records) != 3:
            raise ValueError("FBI needs exactly V, P and ARS annual series")
        if not 0 <= rows["ARS"]["count"] <= rows["P"]["count"]:
            raise ValueError("FBI arson count must be part of the property series")
        # Summarized P includes arson (probe 2026-10-25: P = burglary + larceny + motor vehicle
        # theft + arson, exactly). DPS Part I excludes arson, so take it out of P.
        rates = {"V": rows["V"]["count"] / rows["V"]["population"] * 1000,
                 "P": (rows["P"]["count"] - rows["ARS"]["count"]) / rows["P"]["population"] * 1000}
        as_of = date(self.year, 12, 31)
        return [benchmark("rate_violent", "us", "US", round(rates["V"], 1), str(self.year), "FBI Crime Data API", note=NOTE, as_of=as_of),
                benchmark("rate_part1", "us", "US", round(rates["V"] + rates["P"], 1), str(self.year), "FBI Crime Data API",
                    note=NOTE + "; violent + burglary, larceny and motor vehicle theft (arson removed from the property series)", as_of=as_of)]

    def source_as_of(self, raws):
        return date(self.year, 12, 31)


ADAPTER = FBINational
