"""Rebuild the small synthetic native-column CSV fixture. No network or loan data."""
import csv
from io import StringIO
import json
from pathlib import Path

from mm.values import HMDA_INPUTS


def native_text():
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HMDA_INPUTS, lineterminator="\r\n")
    writer.writeheader()
    rows = []
    for county, base in (("48453",305000),("48491",355000),("48209",255000)):
        for i in range(30):
            rows.append(dict(zip(HMDA_INPUTS, ("2025",county,county+"000100","1","1","1",
                "Single Family (1-4 Units):Site-Built","1",str(base+i*10000)))))
    writer.writerows(rows)
    for field, value in (("action_taken","3"),("loan_purpose","2"),("lien_status","2"),
        ("derived_dwelling_category","Single Family (1-4 Units):Manufactured"),("total_units","2"),
        ("property_value","Exempt"),("property_value","NA"),("property_value",""),
        ("property_value","305000.0"),("census_tract","NA")):
        writer.writerow({**rows[0],field:value})
    return output.getvalue()


if __name__ == "__main__":
    target = Path(__file__).parent/"fixtures/purchase_2025.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({"status":200,"body":native_text()},indent=2)+"\n")
