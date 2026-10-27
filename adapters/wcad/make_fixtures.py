"""Tiny native Socrata arrays: string cells only, null/empty cells omitted."""
from copy import deepcopy
import json
from pathlib import Path


def property_row(pid, **overrides):
    row = {"propertyid": f"{pid}.000000", "quickrefid": f"R{pid}", "propertytypecode": "R",
        "neighborhoodcode": "TEST-HOOD", "neighborhooddesc": "Synthetic neighborhood",
        "totalpropmktvalue": "435394.000000", "totallandmktvalue": "100000.000000",
        "totalimpmktvalue": "335394.000000", "totalsqftlivingarea": "2000.000000",
        "streetnumber": "1008", "streetdirectional": "S", "streetname": "TEST", "streetsuffix": "ST",
        "city": "Round Rock", "zip": "78664", "datadate": "2026-10-21T02:00:32.620"}
    row.update(overrides)
    return {key: value for key, value in row.items() if value is not None and value != ""}


def source_rows():
    props = [property_row(1001), property_row(1002, totalsqftlivingarea="1200.000000", condobuilding="02", condounit="0201"),
        property_row(1003, totalsqftlivingarea="1400.000000", city=None),
        property_row(1004, totalsqftlivingarea="900.000000"), property_row(1005, totalsqftlivingarea="2200.000000"),
        property_row(1006, totalsqftlivingarea="0.000000"), property_row(1007),
        property_row(1008, quickrefid="M1008", propertytypecode="M"),
        property_row(1009, datadate="2026-10-22T03:15:00.000")]
    props.insert(1, deepcopy(props[0]))
    improvement = [{"propertyid": f"{pid}.000000", "fsptb": code, "vtsgimp_impvalue": value} for pid, code, value in [
        (1001,"A3","999999.000000"), (1001,"A1","100000.000000"), (1001,"A9","200000.000000"),
        (1002,"A8","100000.000000"), (1003,"E1","100000.000000"), (1004,"A5","100000.000000"),
        (1005,"B2","100000.000000"), (1006,"O1","100000.000000"), (1007,"A7","100000.000000"), (1008,"M1","100000.000000")]]
    segments = [{"propertyid": f"{pid}.000000", "fsegtype": code, "farea": area, "factyear": year} for pid, code, area, year in [
        (1001,"MA","1500.000000","1998.000000"), (1001,"MA2","500.000000","2005.000000"),
        (1002,"MA","1200.000000","2001.000000"), (1003,"MA","1400.000000","1980.000000"),
        (1004,"MA","900.000000","2010.000000"), (1005,"MA","2200.000000","1975.000000")]]
    land = [{"propertyid":"1001.000000","acres":"0.000000","sqft":"6534.000000"},
        {"propertyid":"1002.000000"}, {"propertyid":"1003.000000","acres":"6.891000","sqft":"999.000000"},
        {"propertyid":"1004.000000","acres":"0.000000","sqft":"0.000000"}, {"propertyid":"1005.000000","sqft":"4356.000000"}]
    return {"property":props, "improvement":improvement, "segment":segments, "land":land}


def main():
    folder = Path(__file__).parent/'fixtures';folder.mkdir(exist_ok=True)
    for kind, rows in source_rows().items():
        count_field = "count_propertyid" if kind == "land" else "count"
        for suffix, body in [("count",[{count_field:str(len(rows))}]), ("p0",rows)]:
            (folder/f'{kind}_{suffix}.json').write_text(json.dumps({"status":200,"body":body},indent=2)+'\n')


if __name__ == '__main__':
    main()
