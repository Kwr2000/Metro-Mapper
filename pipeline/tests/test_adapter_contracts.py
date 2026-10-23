"""Contract test for every adapter in adapters/: run it against its recorded fixtures
and require valid canonical records. A source that changes shape fails here once its
fixture is updated, before bad data is written."""

from datetime import datetime, timezone

import pytest

from mm import adapter as adapter_mod
from mm import runner
from mm.budget import CallBudget
from mm.schemas import ENTITY_MODELS

ADAPTERS = adapter_mod.available()


@pytest.mark.parametrize("adapter_id", ADAPTERS)
def test_adapter_runs_on_fixtures(repo, adapter_id):
    ad = adapter_mod.load(adapter_id)
    ctx = adapter_mod.RunContext(mode="fixture", now=datetime.now(timezone.utc),
                                 budget=CallBudget.for_adapter(adapter_id),
                                 adapter_dir=adapter_mod.adapter_dir(adapter_id))
    requests = ad.plan(ctx)
    assert requests, "plan() returned no requests"
    for req in requests:
        assert (adapter_mod.adapter_dir(adapter_id) / "fixtures" / f"{req.key}.json").is_file(), \
            f"no fixture for request {req.key}"
    run = runner.run(adapter_id, mode="fixture")
    assert run.status == "success", run.errors
    assert run.rows_out > 0
    assert run.calls_made == 0  # fixture mode never touches the network
    assert run.schema_hash


@pytest.mark.parametrize("adapter_id", ADAPTERS)
def test_adapter_declares_known_entity(adapter_id):
    ad = adapter_mod.load(adapter_id)
    assert ad.entity in ENTITY_MODELS
    assert ad.cadence


def test_loader_rejects_mismatched_id(repo):
    d = repo / "adapters" / "wrong_name"
    d.mkdir()
    (d / "adapter.py").write_text((repo / "adapters/demo_points/adapter.py").read_text())
    with pytest.raises(ValueError, match="folder is 'wrong_name'"):
        adapter_mod.load("wrong_name")
