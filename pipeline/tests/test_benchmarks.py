"""Synthetic same-source comparisons and their separate, privacy-checked publication."""
import copy
import importlib.util
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import ValidationError

from mm import adapter, benchmarks, canonical, cli, config, layers_due, publish, runner
from mm.adapter import RawPayload, RunContext
from mm.budget import CallBudget
from mm.paths import paths
from mm.privacy import PrivacyError
from mm.schemas import AreaFeature

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def load(name):
    spec = importlib.util.spec_from_file_location(name + "_benchmarks_test", ROOT / "adapters" / name / "adapter.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def normalized(name, repo, module=None):
    mod = module or load(name)
    ad = mod.ADAPTER()
    context = RunContext("fixture", NOW, CallBudget.for_adapter(name, NOW), repo / "adapters" / name)
    raws = [adapter.read_fixture(name, req) for req in ad.plan(context)]
    return ad, [r for raw in raws for r in ad.normalize(raw)], raws


def emitted(name, repo):
    ad, records, _ = normalized(name, repo)
    return ad.finalize(records)


def indexed(records):
    return {(r.properties["field"], r.properties["geography"]): r.properties for r in records if r.dataset == "benchmark"}


def sample(**kwargs):
    return benchmarks.record("measure", "texas", "Texas", 10, "2025", "Synthetic", **kwargs)


@pytest.mark.parametrize("value", [True, "12", float("nan"), float("inf")])
def test_benchmark_requires_finite_numeric_value(value):
    with pytest.raises(ValidationError):
        benchmarks.record("measure", "texas", "Texas", value, "2025", "Synthetic")


def test_validation_identity_geometry_duplicate_privacy(repo):
    valid = sample()
    assert benchmarks.validate([valid])[0]["value"] == 10
    for change in ({"feature_id": "wrong"}, {"geometry": {"type": "Point", "coordinates": [0, 0]}}):
        with pytest.raises(ValueError):
            benchmarks.validate([valid.model_copy(update=change)])
    with pytest.raises(ValueError): benchmarks.validate([valid, valid])
    with pytest.raises(ValidationError): sample(moe=-1)
    with pytest.raises(ValidationError): benchmarks.record("x", "unlisted", "Bad", 1, "2025", "Synthetic")
    private = valid.model_copy(deep=True); private.properties["owner_name"] = "Never publish"
    with pytest.raises(PrivacyError): benchmarks.validate([private])
    private = benchmarks.record("owner_name", "texas", "Bad", 1, "2025", "Synthetic")
    with pytest.raises(PrivacyError): benchmarks.validate([private])


def test_publisher_order_flags_routing_replaces_old_and_no_map_features(repo):
    records = [sample(), benchmarks.record("measure", "us", "US", 9, "2025", "Synthetic")]
    publish.publish_for_adapter("demo_points", "area_feature", records, mode="fixture")
    doc = json.loads((paths().web_public / "benchmarks.json").read_text())
    assert doc["test_data"] is True
    assert [r["geography"] for r in doc["demo_points"]["measure"]] == ["us", "texas"]
    for layer in __import__('mm.manifests', fromlist=['load_layers']).load_layers():
        if layer.source == "demo_points":
            assert json.loads(publish.published_path(layer).read_text())["features"] == []
    publish.publish_for_adapter("demo_points", "area_feature", [], mode="live")
    assert json.loads((paths().web_public / "benchmarks.json").read_text()) == {"test_data": False}
    fbi = emitted("fbi_national", repo)
    publish.publish_for_adapter("fbi_national", "area_feature", fbi, mode="live")
    doc = json.loads((paths().web_public / "benchmarks.json").read_text())
    assert "dps_agency" in doc and "fbi_national" not in doc and doc["test_data"] is False
    assert all(not publish.selected(layer, fbi[0]) for layer in __import__('mm.manifests', fromlist=['load_layers']).load_layers())


def test_acs_metric_reuse_caps_peer_mean_and_all_twelve_rule(repo):
    mod = load("acs")
    ad, recs, _ = normalized("acs", repo, mod)
    result = indexed(ad.finalize(recs))
    assert len(result) == 21 * 8
    us = [r for r in recs if r.properties.get("scale") == "benchmark" and r.properties["geoid"] == "0100000US"]
    cells = {k:v for r in us for k,v in r.properties["cells"].items()}
    spec = mod.metrics.METRICS["under_18_share"]
    value, moe, *_ = mod.measure(cells, spec[2], spec[3], spec[1])
    assert result["under_18_share", "us"]["value"] == value
    assert result["under_18_share", "us"]["moe"] == moe
    assert result["median_household_income", "peer_cities"]["value"] == 102500
    assert result["median_household_income", "peer_cities"]["moe"] is None
    assert "Average of 12" in result["median_household_income", "peer_cities"]["note"]
    changed = copy.deepcopy(recs)
    for rec in changed:
        if rec.properties.get("scale") != "benchmark": continue
        if rec.properties["geoid"] == "0100000US" and mod.CELL_IDS["B19013_001"] in rec.properties["cells"]:
            rec.properties["cells"][mod.CELL_IDS["B19013_001"]].update(estimate=250000, estimate_annotation="250,000+", moe_annotation="***")
        if rec.properties["geoid"] == next(iter(mod.PEER_IDS)) and mod.CELL_IDS["B19013_001"] in rec.properties["cells"]:
            rec.properties["cells"][mod.CELL_IDS["B19013_001"]]["estimate"] = None
    changed = indexed(ad.finalize(changed))
    assert changed["median_household_income", "us"]["display"] == "$250,000 or more"
    assert ("median_household_income", "peer_cities") not in changed
    assert ("under_18_share", "peer_cities") in changed


def test_acs_peer_population_warning_not_failure(repo, capsys):
    mod = load("acs"); ad, recs, _ = normalized("acs", repo, mod)
    for r in recs:
        if r.properties.get("scale") == "benchmark" and r.properties["geoid"] in mod.PEER_IDS:
            cell = r.properties["cells"].get(mod.CELL_IDS["B01003_001"])
            if cell: cell["estimate"] = 500000
    ad.finalize(recs)
    assert "peer population outside range" in capsys.readouterr().err


def test_apd_combined_raw_rates_use_eligible_population_and_all_area_density(repo):
    output = emitted("apd", repo); ix = indexed(output)
    inside = [r.properties for r in output if r.dataset == "block_group" and r.properties["safety_note"] != "Not available (outside Austin PD)"]
    eligible = [p for p in inside if p["population_2020"] >= 100]
    expected = sum(p["violent"] + p["property"] for p in eligible) / sum(p["population_2020"] for p in eligible) * 1000
    assert ix["rate_part1", "austin_pd_area"]["value"] == round(expected, 1)
    assert set(p["geography"] for p in ix.values()) == {"austin_pd_area"}


def test_dps_texas_633_and_lettered_ori_combined_rate(repo):
    mod = load("dps_agency"); ad, recs, raws = normalized("dps_agency", repo, mod)
    ix = indexed(ad.finalize(recs))
    assert ix["rate_part1", "texas"]["value"] == 28
    assert ix["rate_violent", "texas"]["value"] == 10
    raw = next(r for r in raws if r.request.key == "dps_615")
    all_rows = mod.table_rows(raw.body, ad.year, include_all=True)
    assert "TXDPD0000" in {r["ori"] for r in all_rows}
    expected = round(sum(r["part1"] for r in all_rows) / sum(r["agency_population"] for r in all_rows) * 1000, 1)
    assert ix["rate_part1", "texas_cities_100k"]["value"] == expected
    rates = copy.deepcopy(next(r for r in raws if r.request.key == "dps_633").body)
    rates["sheets"]["Rates"].pop()
    with pytest.raises(ValueError, match="633"): mod.texas_rates(rates, 2025)
    rates["sheets"]["Rates"][1][2] = "unexpected"
    with pytest.raises(ValueError, match="633"): mod.texas_rates(rates, 2025)


def test_fbi_annual_counts_over_mean_population_and_v_plus_p(repo):
    ad, recs, _ = normalized("fbi_national", repo)
    by_kind = {r.feature_id: r for r in recs}
    by_kind["V"].properties.update(count=12000, population=4000000)
    by_kind["P"].properties.update(count=60000, population=3000000)
    by_kind["ARS"].properties.update(count=3000, population=2500000)
    ix = indexed(ad.finalize(recs))
    assert ix["rate_violent", "us"]["value"] == 3
    # Summarized P includes arson, which DPS Part I excludes: (60,000 - 3,000) / 3,000,000 = 19.
    assert ix["rate_part1", "us"]["value"] == 22
    assert "not FBI estimates" in ix["rate_part1", "us"]["note"]
    assert "arson removed" in ix["rate_part1", "us"]["note"]


def test_fbi_arson_must_be_part_of_the_property_series(repo):
    ad, recs, _ = normalized("fbi_national", repo)
    by_kind = {r.feature_id: r for r in recs}
    by_kind["ARS"].properties.update(count=by_kind["P"].properties["count"] + 1)
    with pytest.raises(ValueError, match="arson"): ad.finalize(recs)
    with pytest.raises(ValueError, match="V, P and ARS"): ad.finalize([r for r in recs if r.feature_id != "ARS"])


def test_fbi_month_completeness_dates_and_missing_key_no_secret_in_logs(repo, monkeypatch):
    mod = load("fbi_national"); ad, recs, raws = normalized("fbi_national", repo, mod)
    monkeypatch.delenv("FBI_API_KEY", raising=False)
    context = RunContext("live", NOW, CallBudget.for_adapter("fbi_national", NOW), repo / "adapters/fbi_national")
    with pytest.raises(RuntimeError, match="FBI_API_KEY is required"): ad.plan(context)
    with pytest.raises(RuntimeError, match="FBI_API_KEY is required"): ad.fetch(raws[0].request, context)
    bad = copy.deepcopy(raws[0].body); bad["offenses"]["actuals"]["United States Offenses"].pop("01-2025")
    with pytest.raises(ValueError, match="twelve months"): list(ad.normalize(RawPayload(raws[0].request, bad)))
    token = "synthetic-secret-never-publish"; monkeypatch.setenv("FBI_API_KEY", token)
    reqs = ad.plan(context)
    assert token not in repr(reqs)
    def broken(request, **kwargs):
        assert "API_KEY=" + token in request.full_url
        raise OSError(request.full_url)
    monkeypatch.setattr("urllib.request.urlopen", broken)
    with pytest.raises(RuntimeError) as error: ad.fetch(reqs[0], context)
    assert token not in str(error.value)
    monkeypatch.setenv("MM_LIVE_CHECK", "fbi_national"); monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    run = runner.run("fbi_national", "live", now=NOW)
    assert run.status == "failed" and token not in run.model_dump_json()


def test_school_campus_and_district_are_separate_statewide_rated_aggregates(repo):
    mod = load("schools"); ad, recs, _ = normalized("schools", repo, mod)
    ix = indexed(ad.finalize(recs))
    for dataset, key in (("campus", "school_rating_input"), ("district", "school_district_rating_input")):
        rated = [r.properties for r in recs if r.dataset == key and r.properties["overall_rating"] in {"A","B","C","D","F"}]
        scores = [p["overall_score"] for p in rated if p["overall_score"] is not None]
        assert ix[dataset + "_overall_score", "texas"]["value"] == pytest.approx(sum(scores)/len(scores))
        assert ix[dataset + "_overall_rating", "texas"]["value"] == pytest.approx(sum(p["overall_rating"] in {"A","B"} for p in rated)/len(rated))


def test_access_population_median_and_election_statewide_totals(repo):
    output = indexed(emitted("access", repo))
    assert len(output) == 9
    assert all(p["geography"] == "three_county" for p in output.values())
    assert output["walk_grocery", "three_county"]["value"] == 3
    ix = indexed(emitted("elections", repo))
    assert len(ix) == 8
    assert ix["pres_2024_dem_share", "texas"]["value"] == round((124+100)/(254+300),3)
    assert ix["turnout_2024", "texas"]["value"] == round((404+500)/(650+1000),3)


def test_approved_budgets_gate_and_annual_schedule_secrets_workflows(repo):
    budgets = config.budgets().adapters
    assert budgets["acs"].per_day == 40 and budgets["dps_agency"].per_day == 10
    assert budgets["fbi_national"].per_day == 4 and budgets["fbi_national"].min_interval_seconds == 2
    assert layers_due.layer_adapters()["fbi_national"].days == 365
    # Ungated after its first live check (run 40249786937, 2026-10-26).
    (paths().config / "live_gates.yaml").write_text((ROOT / "config/live_gates.yaml").read_text()); config.clear_cache()
    assert "fbi_national" not in config.live_gates()
    assert "fbi_national" in layers_due.layer_adapters()
    for file in ("live-run.yml", "refresh.yml"):
        assert "FBI_API_KEY: ${{ secrets.FBI_API_KEY }}" in (ROOT / ".github/workflows" / file).read_text()


def test_fbi_mocked_live_uses_transport_key_and_publishes_no_credentials(repo, monkeypatch):
    token = "synthetic-fbi-transport-key"
    monkeypatch.setenv("FBI_API_KEY", token)
    monkeypatch.setattr("mm.budget.time.sleep", lambda _: None)
    responses = {}
    ad, recs, raws = normalized("fbi_national", repo)
    for raw in raws: responses[raw.request.params["kind"]] = raw.body
    seen = []
    class Response(BytesIO):
        status = 200
    def response(req, **kwargs):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(req.full_url)
        assert parse_qs(parsed.query)["API_KEY"] == [token]
        seen.append(parsed.path.rsplit("/",1)[-1])
        return Response(json.dumps(responses[seen[-1]]).encode())
    monkeypatch.setattr("urllib.request.urlopen", response)
    run = runner.run("fbi_national", "live", now=NOW)
    assert run.status == "success" and seen == ["V", "P", "ARS"] and run.calls_made == 3, run.errors
    assert token not in run.model_dump_json()
    doc = json.loads((paths().web_public / "benchmarks.json").read_text())
    assert not doc["test_data"] and "us" == doc["dps_agency"]["rate_part1"][0]["geography"]
    assert token not in json.dumps(doc)
    assert not paths().raw.exists()


def test_mm_publish_rebuilds_benchmarks_from_stored_records_without_source_calls(repo):
    recs = [sample()]
    canonical.write("area_feature", "apd", recs)
    # Other adapters use fixtures; the source transport is disabled by the global fixture.
    assert cli._cmd_publish(type("Args", (), {})()) == 0
    doc = json.loads((paths().web_public / "benchmarks.json").read_text())
    assert doc["apd"]["measure"][0]["value"] == 10
    assert doc["test_data"]  # Other benchmark producers came from fixtures.
