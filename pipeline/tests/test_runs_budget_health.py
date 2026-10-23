import gzip
from datetime import timedelta

import pytest

from mm import canonical, cli, health, registry, runlog, runner
from mm.budget import BudgetExceeded, CallBudget


def test_fixture_runs_stay_out_of_the_committed_log(repo):
    runner.run("demo_points", mode="fixture")
    assert not (repo / "data/runs/ingestion_runs.jsonl").exists()
    assert (repo / "data/runs/fixture_runs.jsonl").exists()


def test_live_run_logs_canonical_and_raw(fake_live):
    run = runner.run("fake_live", mode="live")
    assert run.status == "success" and run.calls_made == 3
    assert (fake_live / "data/runs/ingestion_runs.jsonl").exists()
    raw_files = list((fake_live / "data/raw/fake_live").rglob("*.ndjson.gz"))
    assert len(raw_files) == 1 and len(gzip.open(raw_files[0], "rt").read().splitlines()) == 3
    stored = canonical.read("area_feature", "fake_live")
    assert [r.feature_id for r in stored] == ["page_0", "page_1", "page_2"]
    reg = registry.compile_registry()
    assert next(l for l in reg.layers if l.id == "fake_layer").freshness == "fresh"


def test_canonical_is_deterministic(fake_live):
    runner.run("fake_live", mode="live")
    first = canonical.path_for("area_feature", "fake_live").read_bytes()
    canonical.write("area_feature", "fake_live", canonical.read("area_feature", "fake_live"))
    assert canonical.path_for("area_feature", "fake_live").read_bytes() == first


def test_budget_fails_closed_and_partial_runs_publish_nothing(fake_live):
    # per_day is 4: the first run spends 3, the second gets 1 call then stops
    runner.run("fake_live", mode="live")
    second = runner.run("fake_live", mode="live")
    assert second.status == "partial" and second.calls_made == 1
    assert any("budget exhausted" in e for e in second.errors)
    assert any("nothing published" in e for e in second.errors)
    assert len(canonical.read("area_feature", "fake_live")) == 3  # first run's data kept
    assert runner.run("fake_live", mode="live").calls_made == 0


def test_adapter_without_budget_cannot_run_live(fake_live):
    b = fake_live / "config/budgets.yaml"
    b.write_text(b.read_text().replace("  fake_live:\n    per_day: 4\n", ""))
    from mm import config
    config.clear_cache()
    run = runner.run("fake_live", mode="live")
    assert run.calls_made == 0 and run.status == "failed"


def test_live_gate_skips(fake_live):
    (fake_live / "config/live_gates.yaml").write_text("gated:\n  fake_live: not probed yet\n")
    from mm import config
    config.clear_cache()
    run = runner.run("fake_live", mode="live")
    assert run.status == "skipped" and run.calls_made == 0


def test_first_live_check_bypasses_gate_for_that_adapter_only(fake_live, monkeypatch):
    (fake_live / "config/live_gates.yaml").write_text("gated:\n  fake_live: not checked yet\n")
    from mm import config
    config.clear_cache()
    monkeypatch.setenv("MM_LIVE_CHECK", "other_adapter")
    assert runner.run("fake_live", mode="live").status == "skipped"
    monkeypatch.setenv("MM_LIVE_CHECK", "fake_live")
    run = runner.run("fake_live", mode="live")
    assert run.status == "success" and run.calls_made == 3
    assert any("first live check" in n for n in run.notes)


def test_budget_object_raises():
    b = CallBudget(adapter="x", per_day=1, per_month=None, min_interval_seconds=0, remaining=1)
    b.spend()
    with pytest.raises(BudgetExceeded):
        b.spend()


def test_stale_after_cadence_window(fake_live):
    runner.run("fake_live", mode="live")
    later = runlog.utcnow() + timedelta(days=40)
    reg = registry.compile_registry(now=later)
    assert next(l for l in reg.layers if l.id == "fake_layer").freshness == "stale"


def test_health_reports_calls_and_schema(fake_live):
    runner.run("fake_live", mode="live")
    rep = health.build()
    h = next(a for a in rep.adapters if a.adapter == "fake_live")
    assert h.calls_today == 3 and h.budget_per_day == 4
    assert h.freshness == "fresh" and h.schema_hash and not h.schema_changed
    assert (fake_live / "web/public/health.json").exists()


def test_publish_uses_stored_live_data_without_network(fake_live):
    import json

    runner.run("fake_live", mode="live")
    (fake_live / "web/public/data/layers/fake_layer.geojson").unlink()
    assert cli.main(["publish"]) == 0
    doc = json.loads((fake_live / "web/public/data/layers/fake_layer.geojson").read_text())
    assert doc["test_data"] is False and len(doc["features"]) == 3
    demo = json.loads((fake_live / "web/public/data/layers/demo_landmarks.geojson").read_text())
    assert demo["test_data"] is True  # never ran live: fixtures, labeled


def test_finalize_combines_records_across_responses(fake_live):
    p = fake_live / "adapters/fake_live/adapter.py"
    p.write_text(p.read_text().replace("ADAPTER = FakeLive", """
    def finalize(self, records):
        n = len(records)
        return [r.model_copy(update={"properties": {**r.properties, "of": n}}) for r in records]

ADAPTER = FakeLive""".replace("\n    def", "\n    def")))
    import json
    run = runner.run("fake_live", mode="fixture")
    assert run.status == "success", run.errors
    doc = json.loads((fake_live / "web/public/data/layers/fake_layer.geojson").read_text())
    assert {f["properties"]["of"] for f in doc["features"]} == {3}


def test_fixture_files_are_labeled_test_data_even_after_live_runs(fake_live):
    """A fixture build must never inherit 'Current' from a committed live run."""
    assert runner.run("fake_live", mode="live").status == "success"
    assert runner.run("fake_live", mode="fixture").status == "success"
    layer = next(l for l in registry.compile_registry().layers if l.id == "fake_layer")
    assert layer.freshness == "fixture_only"
    assert cli.main(["publish"]) == 0  # republish stored live data
    layer = next(l for l in registry.compile_registry().layers if l.id == "fake_layer")
    assert layer.freshness == "fresh"


def test_failed_request_is_retried_once_within_budget(fake_live, monkeypatch):
    monkeypatch.setattr("mm.runner.time.sleep", lambda s: None)
    b = fake_live / "config/budgets.yaml"
    b.write_text(b.read_text().replace("per_day: 4", "per_day: 10"))
    from mm import config
    config.clear_cache()
    p = fake_live / "adapters/fake_live/adapter.py"
    p.write_text(p.read_text().replace(
        'if os.environ.get("FAKE_FAIL") == req.key:',
        'if os.environ.get("FAKE_FAIL") == req.key and not getattr(self, "_failed", False):\n'
        '            self._failed = os.environ.get("FAKE_FAIL_ONCE") == "1"'))
    monkeypatch.setenv("FAKE_FAIL", "page_1")
    monkeypatch.setenv("FAKE_FAIL_ONCE", "1")
    run = runner.run("fake_live", mode="live")
    assert run.status == "success" and run.calls_made == 4  # 3 pages + 1 retry
    assert any("retried" in n for n in run.notes)
    monkeypatch.setenv("FAKE_FAIL_ONCE", "0")  # fails every time: one retry, then partial
    run = runner.run("fake_live", mode="live")
    assert run.status == "partial" and run.calls_made == 4
