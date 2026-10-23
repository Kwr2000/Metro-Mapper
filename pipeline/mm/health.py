"""Build web/public/health.json from the run log and budgets."""

from __future__ import annotations

from datetime import datetime

from . import adapter as adapter_mod
from . import config, runlog
from .budget import spent
from .manifests import load_layers
from .paths import paths
from .registry import freshness
from .schemas import AdapterHealth, HealthReport

_ORDER = ["daily", "weekly", "monthly", "annual", "as_revised", "manual"]


def build(now: datetime | None = None, write: bool = True) -> HealthReport:
    now = now or runlog.utcnow()
    all_runs = runlog.read_all()
    budgets = config.budgets().adapters
    refresh_by_adapter: dict[str, str] = {}
    for l in load_layers():
        # an adapter feeding several layers is held to its most frequent refresh
        cur = refresh_by_adapter.get(l.source)
        if cur is None or _ORDER.index(l.refresh) < _ORDER.index(cur):
            refresh_by_adapter[l.source] = l.refresh

    out: list[AdapterHealth] = []
    for adapter_id in adapter_mod.available():
        cadence = adapter_mod.load(adapter_id).cadence
        runs = runlog.for_adapter(adapter_id, all_runs)
        fresh, last_ok = freshness(refresh_by_adapter.get(adapter_id, "manual"), runs, now)
        last = runs[-1] if runs else None
        hashes = [r.schema_hash for r in runs if r.status == "success" and r.schema_hash]
        today, month = spent(adapter_id, now)
        b = budgets.get(adapter_id)
        out.append(AdapterHealth(
            adapter=adapter_id,
            cadence=cadence,
            last_run=last.started_at if last else None,
            last_status=last.status if last else None,
            last_success=last_ok.finished_at if last_ok else None,
            freshness=fresh,
            calls_today=today,
            calls_this_month=month,
            budget_per_day=b.per_day if b else None,
            budget_per_month=b.per_month if b else None,
            last_errors=[e for e in (last.errors if last else []) if "\n" not in e][:5],
            schema_hash=hashes[-1] if hashes else None,
            schema_changed=len(hashes) >= 2 and hashes[-1] != hashes[-2],
        ))

    report = HealthReport(
        generated_at=now,
        adapters=out,
        recent_runs=[r for r in all_runs if r.mode == "live"][-25:][::-1],
    )
    if write:
        p = paths().health_json
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(report.model_dump_json(indent=2))
    return report
