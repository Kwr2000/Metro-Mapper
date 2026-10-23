"""An empty or sharply smaller live refresh must not replace a good map layer."""

import json

import pytest

from mm import canonical, layer_guard, registry, runner


@pytest.fixture()
def pages(fake_live, monkeypatch):
    b = fake_live / "config/budgets.yaml"
    b.write_text(b.read_text().replace("per_day: 4", "per_day: 1000"))
    from mm import config
    config.clear_cache()
    monkeypatch.setattr(layer_guard, "MIN_PREVIOUS", 4)
    return fake_live


def _layer(repo):
    return json.loads((repo / "web/public/data/layers/fake_layer.geojson").read_text())


def _fresh():
    reg = registry.compile_registry(write=False)
    return next(l for l in reg.layers if l.id == "fake_layer").freshness


@pytest.mark.parametrize("second_pages", [0, 2])
def test_empty_or_sharply_smaller_refresh_keeps_layer_and_marks_stale(pages, monkeypatch, second_pages):
    monkeypatch.setenv("FAKE_PAGES", "6")
    assert runner.run("fake_live", mode="live").status == "success"
    assert len(_layer(pages)["features"]) == 6
    stored = canonical.path_for("area_feature", "fake_live").read_bytes()

    monkeypatch.setenv("FAKE_PAGES", str(second_pages))
    run = runner.run("fake_live", mode="live")
    assert run.status == "failed" and layer_guard.is_held(run)
    assert any("fake_layer 6 -> " in e for e in run.errors)
    doc = _layer(pages)
    assert len(doc["features"]) == 6  # previous data kept
    assert doc["stale"] is True and doc["stale_reason"].startswith(layer_guard.HELD_MARKER)
    assert canonical.path_for("area_feature", "fake_live").read_bytes() == stored
    assert _fresh() == "stale"

    monkeypatch.setenv("FAKE_PAGES", "5")
    assert runner.run("fake_live", mode="live").status == "success"
    doc = _layer(pages)
    assert len(doc["features"]) == 5 and "stale" not in doc
    assert _fresh() == "fresh"


def test_accepted_drop_and_tiny_layers(pages, monkeypatch):
    monkeypatch.setenv("FAKE_PAGES", "6")
    runner.run("fake_live", mode="live")
    monkeypatch.setenv("FAKE_PAGES", "1")
    monkeypatch.setenv(layer_guard.ACCEPT_ENV, "fake_live")
    assert runner.run("fake_live", mode="live").status == "success"
    monkeypatch.delenv(layer_guard.ACCEPT_ENV)
    monkeypatch.setenv("FAKE_PAGES", "0")
    assert runner.run("fake_live", mode="live").status == "failed"  # 1 -> 0 is still held
