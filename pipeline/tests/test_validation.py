"""P1-09: the refresh validation report and the monthly refresh's keep-or-roll-back rule."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mm import adapter, canonical, inputs, layers_due, publish, refresh, runlog, validation
from mm.adapter import RunContext
from mm.budget import CallBudget
from mm.schemas import IngestionRun

ROOT = Path(__file__).resolve().parents[2]


def _check(rep, check_id):
    return next(c for c in rep["checks"] if c["id"] == check_id)


@pytest.fixture
def fake_only(fake_live):
    """Only the fake live layer: the real layers have no published files in these tests."""
    for p in (fake_live / "layers").glob("*.yaml"):
        if p.name != "fake_layer.yaml":
            p.unlink()
    return fake_live


@pytest.fixture
def no_stored_publish(monkeypatch):
    """Refresh tests use only the fake adapter; skip republishing every real adapter's fixtures."""
    monkeypatch.setattr(refresh, "_publish_stored", lambda: None)


def test_spearman_ranks_and_ties():
    assert validation.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1)
    assert validation.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1)
    assert validation.spearman([1, 1, 2, 3], [5, 5, 6, 7]) == pytest.approx(1)
    assert validation.spearman([1, 1, 1], [1, 2, 3]) is None
    assert validation.spearman([1, 2], [1, 2]) is None


def test_hex_smoothing_keeps_a_smooth_gradient_in_order():
    from shapely.geometry import box

    x0, y0 = validation.to_projected(-97.75, 30.30)
    size = 2500
    feats, values = [], {}
    for i in range(5):
        for j in range(5):
            g = f"bg{i}{j}"
            feats.append((g, box(x0 + i * size, y0 + j * size, x0 + (i + 1) * size, y0 + (j + 1) * size)))
            values[g] = float(i * 5 + j)
    w = validation.hex_weights(feats)
    smoothed = validation.hex_smoothed(w, values)
    assert set(smoothed) == set(values)
    keys = sorted(values)
    assert validation.spearman([values[k] for k in keys], [smoothed[k] for k in keys]) > 0.8
    # A missing value is skipped, never treated as zero.
    del values["bg00"]
    assert "bg00" not in validation.hex_smoothed(w, values)


def test_ranked_attributes_skip_demographics_and_read_style_fields(repo):
    got = {(layer.id, fld) for layer, fld in validation.ranked_attributes()}
    assert ("flood_share", "flood_share_1pct") in got
    assert not any(layer_id.startswith("acs_") for layer_id, _ in got)
    assert ("apd_part1_rate", "rate_part1") in got


def test_validate_live_layer_passes_and_sets_baseline(fake_only):
    from mm import runner

    assert runner.run("fake_live", mode="live").status == "success"
    rep = validation.build()
    assert rep["passed"]
    assert _check(rep, "layers")["status"] == "pass"
    assert rep["baseline"]["fake_layer"] == 3
    row = next(r for r in rep["layers"] if r["id"] == "fake_layer")
    assert row["features"] == 3 and not row["test_data"]


def test_layer_below_half_of_last_month_fails_hard(fake_only, monkeypatch):
    from mm import runner

    runner.run("fake_live", mode="live")
    validation.write({**validation.build(), "baseline": {"fake_layer": 10}})
    rep = validation.build()
    assert not rep["passed"]
    assert any("below half" in i for i in _check(rep, "layers")["items"])
    assert rep["baseline"]["fake_layer"] == 10  # a failed refresh keeps last month's count


def test_missing_attribution_fails_hard(fake_only):
    from mm import runner

    p = fake_only / "layers" / "fake_layer.yaml"
    p.write_text(p.read_text().replace("attribution: test", "attribution: ' '"))
    runner.run("fake_live", mode="live")
    rep = validation.build()
    assert not rep["passed"]
    assert "fake_layer: no source attribution" in _check(rep, "layers")["items"]


def test_personal_field_in_published_file_fails_hard(fake_only):
    from mm import runner
    from mm.paths import paths

    runner.run("fake_live", mode="live")
    p = paths().published_layers / "fake_layer.geojson"
    doc = json.loads(p.read_text())
    doc["features"][0]["properties"]["owner_name"] = "x"
    p.write_text(json.dumps(doc))
    rep = validation.build()
    assert not rep["passed"]
    assert _check(rep, "privacy")["status"] == "fail"


def test_demographic_score_input_fails_hard(repo, monkeypatch):
    field = sorted(inputs.demographic_fields())[0]
    monkeypatch.setitem(inputs.SCORE_INPUTS, "value_for_money", [field])
    rep = validation.build()
    assert _check(rep, "demographics")["status"] == "fail"
    assert not rep["passed"]


def test_test_data_is_soft_only(repo):
    from mm import runner

    runner.run("demo_points", mode="fixture")
    rep = validation.build()
    site = _check(rep, "site_state")
    assert site["kind"] == "soft" and site["status"] == "warn"
    assert "demo_landmarks: test data" in site["items"]


def _apd_module():
    spec = importlib.util.spec_from_file_location("apd_for_validation", ROOT / "adapters/apd/adapter.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _store_apd_live(now):
    apd = _apd_module()
    ctx = RunContext("fixture", now, CallBudget.for_adapter("apd", now), adapter.adapter_dir("apd"))
    ad = apd.APDReports()
    raws = [adapter.read_fixture("apd", r) for r in ad.plan(ctx)]
    records = ad.finalize([rec for raw in raws for rec in ad.normalize(raw)])
    canonical.write("area_feature", "apd", records)
    publish.publish_for_adapter("apd", "area_feature", records, mode="live")
    return records


def test_apd_counts_reconcile_with_apd_total(repo):
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    records = _store_apd_live(now)
    summary = next(r for r in records if r.dataset == "run_summary").properties
    assert validation.APD_OUTSIDE in summary
    check = validation.check_apd()
    assert check.status == "pass", check.detail

    # A changed total no longer reconciles: hard failure.
    for r in records:
        if r.dataset == "run_summary":
            r.properties[validation.APD_TOTAL] += 1
    canonical.write("area_feature", "apd", records)
    assert validation.check_apd().status == "fail"


def test_apd_check_waits_for_a_summary_with_the_new_count(repo):
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    records = _store_apd_live(now)
    for r in records:
        if r.dataset == "run_summary":
            del r.properties[validation.APD_OUTSIDE]
    canonical.write("area_feature", "apd", records)
    assert validation.check_apd().status == "skipped"


def test_refresh_publishes_when_hard_checks_pass(fake_only, no_stored_publish):
    rep = refresh.refresh(mode="live")
    assert rep["passed"] and rep["published"]
    assert [r["adapter"] for r in rep["runs"]] == ["fake_live"]
    assert canonical.read("area_feature", "fake_live")
    saved = json.loads(validation.report_path().read_text())
    assert saved["baseline"]["fake_layer"] == 3
    assert (validation.validation_dir() / "report.md").read_text().startswith("# Validation report")


def test_refresh_rolls_back_on_hard_failure(fake_only, no_stored_publish, monkeypatch):
    refresh.refresh(mode="live")
    path = canonical.path_for("area_feature", "fake_live")
    before = path.read_bytes()
    calls_before = len([r for r in runlog.read_all() if r.mode == "live"])

    monkeypatch.setenv("FAKE_PAGES", "2")  # different data this month
    monkeypatch.setattr(layers_due, "due", lambda: [("fake_live", "test")])
    monkeypatch.setattr(validation, "check_privacy", lambda: validation.Check(
        "privacy", "No personal fields", "hard", "fail", "planted"))
    assert refresh.main(mode="live", dry_run=False) == 1
    assert path.read_bytes() == before  # last month's data stays
    saved = json.loads(validation.report_path().read_text())
    assert not saved["passed"] and saved["published"] is False
    assert saved["baseline"]["fake_layer"] == 3
    # The calls made still count against the budget.
    assert len([r for r in runlog.read_all() if r.mode == "live"]) == calls_before + 1


def test_refresh_removes_new_canonical_files_on_failure(fake_only, no_stored_publish, monkeypatch):
    monkeypatch.setattr(validation, "check_privacy", lambda: validation.Check(
        "privacy", "No personal fields", "hard", "fail", "planted"))
    rep = refresh.refresh(mode="live")
    assert not rep["passed"]
    assert canonical.read("area_feature", "fake_live") is None


def test_dry_run_makes_no_live_calls_and_writes_nothing(fake_only, no_stored_publish):
    rep = refresh.refresh(mode="live", dry_run=True)
    assert [r["status"] for r in rep["runs"]] == ["dry run"]
    assert not [r for r in runlog.read_all() if r.mode == "live"]
    assert not validation.report_path().exists()


def _live_success(adapter_id, when):
    runlog.append(IngestionRun(run_id=f"{adapter_id}-{when:%Y%m%d}", adapter=adapter_id, mode="live",
                               started_at=when, finished_at=when, status="success", rows_out=3))


def test_monthly_refresh_never_skips_february(fake_live):
    feb = datetime(2027, 2, 3, 9, 20, tzinfo=timezone.utc)
    _live_success("fake_live", feb)
    assert "fake_live" in dict(layers_due.due(datetime(2027, 3, 3, 9, 15, tzinfo=timezone.utc)))


def test_a_recent_manual_run_waits_for_next_month(fake_live):
    _live_success("fake_live", datetime(2026, 10, 24, tzinfo=timezone.utc))
    assert "fake_live" not in dict(layers_due.due(datetime(2026, 11, 3, 9, 15, tzinfo=timezone.utc)))
    assert "fake_live" in dict(layers_due.due(datetime(2026, 12, 3, 9, 15, tzinfo=timezone.utc)))


def test_annual_layers_are_due_about_a_year_later(repo):
    _live_success("acs", datetime(2026, 10, 24, tzinfo=timezone.utc))
    assert layers_due.layer_adapters()["acs"] == timedelta(days=365)
    assert "acs" not in dict(layers_due.due(datetime(2027, 10, 3, 9, 15, tzinfo=timezone.utc)))
    assert "acs" in dict(layers_due.due(datetime(2027, 11, 3, 9, 15, tzinfo=timezone.utc)))


def test_publish_serves_the_last_validation_report(fake_only):
    from mm.cli import _copy_validation
    from mm.paths import paths

    validation.write(validation.build())
    _copy_validation()
    assert "checks" in json.loads((paths().web_public / "validation.json").read_text())
