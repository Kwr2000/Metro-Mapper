"""Ground rules enforced by tests: nothing about people is published (rule 5),
demographics never feed a score or model (rule 4), and app code never names a
specific layer (seams)."""

import json
import re
from pathlib import Path

import pytest

from conftest import REPO
from mm import inputs, privacy, runner
from mm.publish import publish_for_adapter
from mm.schemas import AreaFeature


@pytest.mark.parametrize("key", ["owner_name", "py_owner_name", "mail_addr1", "MAIL_ZIP", "hs_exempt",
                                 "ov65_exempt", "dv1_exempt", "confidential_flag", "agent_name",
                                 "mortgage_co", "PrevOwnerName", "party_name", "buyer_id", "address",
                                 "NAME_CARE", "homestead_cap"])
def test_personal_field_names_are_refused(key):
    assert privacy.personal_keys([key]) == [key]


@pytest.mark.parametrize("key", ["situs_address", "situs_city", "market_value", "geoid", "name",
                                 "owner_occupied_share", "owner_occupied_share_moe", "agency",
                                 "median_household_income", "flood_share_1pct"])
def test_ordinary_fields_are_allowed(key):
    assert privacy.personal_keys([key]) == []


def test_publish_refuses_personal_fields(repo):
    rec = AreaFeature(dataset="landmarks", feature_id="x",
                      geometry={"type": "Point", "coordinates": [-97.7, 30.3]},
                      properties={"name": "A", "kind": "park", "owner_name": "Someone"})
    with pytest.raises(privacy.PrivacyError, match="owner_name"):
        publish_for_adapter("demo_points", "area_feature", [rec])


def test_fixture_build_publishes_no_personal_fields(repo):
    from mm import adapter as adapter_mod

    for a in adapter_mod.available():
        assert runner.run(a, mode="fixture").status == "success"
    for p in (repo / "web/public/data/layers").glob("*.geojson"):
        keys = set()
        for f in json.loads(p.read_text())["features"]:
            keys |= set(f["properties"])
        assert privacy.personal_keys(keys) == [], p.name


DEMO_LAYER = """
id: demo_people
title: Demo people layer
group: People
source: demo_points
geometry: point
join: point
publish: geojson
style: {type: circle}
popup:
  - {field: median_household_income, label: Income, moe_field: median_household_income_moe}
coverage: test
refresh: annual
attribution: test
demographic: true
"""


def test_demographic_fields_cannot_be_score_inputs(repo, monkeypatch):
    (repo / "layers/demo_people.yaml").write_text(DEMO_LAYER)
    assert {"median_household_income", "median_household_income_moe"} <= inputs.demographic_fields()
    with pytest.raises(inputs.DemographicInputError, match="median_household_income"):
        inputs.assert_no_demographics("value_for_money", ["flood_share_1pct", "median_household_income"])
    inputs.assert_no_demographics("value_for_money", ["flood_share_1pct"])


def test_declared_score_inputs_contain_no_demographics(repo):
    for score_id, fields in inputs.SCORE_INPUTS.items():
        inputs.assert_no_demographics(score_id, fields)


def test_web_code_never_names_a_layer():
    """Adding a layer must need only a manifest; the site reads the registry."""
    ids = [p.stem for p in (REPO / "layers").glob("*.yaml")]
    src = REPO / "web" / "src"
    if not src.exists():
        pytest.skip("no web/src yet")
    offenders = []
    for f in src.rglob("*.ts*"):
        if "__tests__" in f.parts or f.name.endswith(".d.ts") or "generated" in f.parts:
            continue
        text = f.read_text()
        offenders += [f"{f.relative_to(REPO)}: {i}" for i in ids if re.search(rf"\b{re.escape(i)}\b", text)]
    assert not offenders, offenders
