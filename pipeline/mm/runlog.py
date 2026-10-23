"""The ingestion_run log: one JSON line per adapter run, append-only."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from .paths import paths
from .schemas import IngestionRun


def append(run: IngestionRun) -> None:
    p = paths().run_log if run.mode == "live" else paths().fixture_run_log
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(run.model_dump_json() + "\n")


def read_all() -> list[IngestionRun]:
    runs = []
    for p in (paths().run_log, paths().fixture_run_log):
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if line.strip():
                runs.append(IngestionRun.model_validate_json(line))
    return sorted(runs, key=lambda r: r.started_at)


def for_adapter(adapter: str, runs: Iterable[IngestionRun] | None = None) -> list[IngestionRun]:
    runs = read_all() if runs is None else runs
    return sorted((r for r in runs if r.adapter == adapter), key=lambda r: r.started_at)


def last_success(adapter: str, runs: Iterable[IngestionRun] | None = None) -> IngestionRun | None:
    ok = [r for r in for_adapter(adapter, runs) if r.status == "success"]
    return ok[-1] if ok else None


def live_calls_since(adapter: str, since: datetime, runs: Iterable[IngestionRun] | None = None) -> int:
    """Calls made against the real source since `since` (fixture runs cost nothing)."""
    return sum(
        r.calls_made
        for r in for_adapter(adapter, runs)
        if r.mode == "live" and r.started_at >= since
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
