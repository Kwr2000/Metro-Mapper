from datetime import datetime, timedelta, timezone

from mm import layers_due, runlog
from mm.schemas import IngestionRun

NOW = datetime(2026, 11, 3, 9, 15, tzinfo=timezone.utc)


def _run(adapter, mode, status, ago):
    t = NOW - ago
    runlog.append(IngestionRun(run_id=f"{adapter}-{ago}", adapter=adapter, mode=mode, started_at=t,
                               finished_at=t, status=status, rows_out=12))


def test_manual_layers_are_never_due(fake_live):
    got = layers_due.layer_adapters()
    assert "demo_points" not in got
    assert got["fake_live"] == timedelta(days=30)


def test_due_uses_live_successes_only(fake_live):
    _run("fake_live", "fixture", "success", timedelta(hours=1))
    assert dict(layers_due.due(NOW))["fake_live"] == "never succeeded live"
    _run("fake_live", "live", "success", timedelta(days=10))
    assert "fake_live" not in dict(layers_due.due(NOW))
    _run("fake_live", "live", "success", timedelta(days=31))  # older run does not matter
    assert "fake_live" not in dict(layers_due.due(NOW))
    assert dict(layers_due.due(NOW + timedelta(days=25)))["fake_live"].startswith("last live success")
    assert set(dict(layers_due.due(NOW, force=True))) == set(layers_due.layer_adapters())


def test_summary_lists_live_layer_runs(fake_live):
    _run("fake_live", "live", "success", timedelta(minutes=5))
    table = layers_due.summary(NOW - timedelta(hours=1))
    assert "| fake_live | success | 12 |" in table
