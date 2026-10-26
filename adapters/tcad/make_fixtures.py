"""Generate tiny synthetic stripped responses, using the publisher's native cell names."""
import json
from pathlib import Path


def property_row(pid, state="A1"):
    return {
        "prop_id": pid, "prop_type_cd": "R", "prop_val_yr": "02026", "sup_num": "000000000000",
        "geo_id": "TEST-GEO-"+pid, "partial_owner": "F", "udi_group": "000000000000",
        "situs_street_prefx": "S", "situs_street": "8TH", "situs_street_suffix": "ST",
        "situs_city": "", "situs_zip": "78704", "abs_subdv_cd": "TEST01", "hood_cd": "TEST-HOOD",
        "deed_dt": "02-03-2020", "imprv_state_cd": state, "land_state_cd": "C1",
        "land_acres": .1435, "market_value": "00000000500000", "situs_num": "1008", "situs_unit": "",
        "land_value": 200000, "improvement_value": 300000, "abs_subdv_desc": "THE GROVE AT TEST CREEK",
        "living_area": 2000, "adu_area": None, "hvac_area": 2000, "year_built": 1998,
        "floors": 2, "dwelling_count": 1, "has_adu": False,
    }


def main():
    a, b = property_row("000000000123"), property_row("000000000456", "A4")
    b.update(partial_owner="T", udi_group="000000000007", living_area=1500, hvac_area=1500,
             adu_area=400, has_adu=True, deed_dt="", situs_num="1010", year_built=2005, floors=1)
    body = {"properties": [a,b], "summary": {"records_read": 4, "real_mobile": 3,
            "skipped_by_state": {"B1": 1, "J1": 1}, "totals_num_real_mobile": 3}}
    (Path(__file__).parent/'fixtures/tcad_2026.json').write_text(json.dumps({"status": 200, "body": body}, indent=2)+'\n')


if __name__ == '__main__':
    main()
