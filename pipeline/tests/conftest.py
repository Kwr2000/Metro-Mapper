"""Every test runs against a temporary copy of the repo's config, adapters and layers,
so tests never read or write real data."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    for name in ("config", "adapters", "layers"):
        shutil.copytree(REPO / name, tmp_path / name)
    # Core tests use their own demo adapter, so the repo's real adapters can change freely.
    demo = Path(__file__).parent / "demo"
    shutil.copytree(demo / "demo_points", tmp_path / "adapters" / "demo_points", dirs_exist_ok=True)
    shutil.copy(demo / "demo_landmarks.yaml", tmp_path / "layers" / "demo_landmarks.yaml")
    budgets = tmp_path / "config" / "budgets.yaml"
    if "demo_points" not in budgets.read_text():
        budgets.write_text(budgets.read_text().rstrip() + "\n  demo_points: {per_day: 1}\n")
    (tmp_path / "web" / "public").mkdir(parents=True)
    # The live gate has its own test, so the copied repo starts with nothing gated.
    (tmp_path / "config" / "live_gates.yaml").write_text("gated: {}\n")
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    from mm import config

    config.clear_cache()
    yield tmp_path
    config.clear_cache()


FAKE_LIVE_ADAPTER = '''
import os
from mm.adapter import RawPayload, Request, SourceAdapter
from mm.schemas import AreaFeature

class FakeLive(SourceAdapter):
    id = "fake_live"
    entity = "area_feature"
    cadence = "monthly"
    retain_raw = True
    def plan(self, ctx):
        return [Request(key=f"page_{i}") for i in range(int(os.environ.get("FAKE_PAGES", "3")))]
    def fetch(self, req, ctx):
        if os.environ.get("FAKE_FAIL") == req.key:
            raise RuntimeError("source down")
        return RawPayload(request=req, body={"x": -97.74, "y": 30.27, "k": req.key}, fetched_at=ctx.now)
    def normalize(self, raw):
        yield AreaFeature(dataset="fake", feature_id=raw.body["k"],
                          geometry={"type": "Point", "coordinates": [raw.body["x"], raw.body["y"]]},
                          properties={"k": raw.body["k"]})

ADAPTER = FakeLive
'''

FAKE_LAYER = """
id: fake_layer
title: Fake layer
group: Test
source: fake_live
geometry: point
join: point
publish: geojson
style: {type: circle, paint: {circle-radius: 4}}
popup: [{field: k, label: K}]
coverage: test
refresh: monthly
attribution: test
"""


@pytest.fixture()
def fake_live(repo, monkeypatch):
    d = repo / "adapters" / "fake_live"
    (d / "fixtures").mkdir(parents=True)
    (d / "adapter.py").write_text(FAKE_LIVE_ADAPTER)
    for i in range(3):
        (d / "fixtures" / f"page_{i}.json").write_text(
            '{"status": 200, "body": {"x": -97.74, "y": 30.27, "k": "page_%d"}}' % i)
    (repo / "layers" / "fake_layer.yaml").write_text(FAKE_LAYER)
    budgets = (repo / "config" / "budgets.yaml").read_text()
    budgets += "  fake_live:\n    per_day: 4\n"
    (repo / "config" / "budgets.yaml").write_text(budgets)
    monkeypatch.setattr("mm.budget.time.sleep", lambda s: None)
    from mm import config

    config.clear_cache()
    return repo


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Tests never call live sources (AGENTS.md rule 7). Any real request fails loudly."""
    import socket
    import urllib.request

    def blocked(*a, **k):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


# Tests that each rebuild the full fixture set. CI skips them (`-m "not slow"`);
# `make test` and Claude's pre-merge local run include them. Add ids here as they appear.
SLOW_TESTS: set[str] = set()


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid.split("tests/", 1)[-1] in SLOW_TESTS:
            item.add_marker(pytest.mark.slow)
