"""Which map-layer adapters are due a live refresh, and a summary of what ran.

For the monthly refresh workflow (P1-09), which runs on the 3rd of each month. An adapter
is due when a layer it feeds has a weekly, monthly or annual `refresh` and its last
successful live run is at least MIN_AGE old, or it has never run live. MIN_AGE sits a few
days under the interval so a month-to-month run (28 to 31 days apart) is never skipped,
while a manual run in the last 25 days still waits for the next month. Manual layers and
gated adapters are excluded.

    mm layers-due                      # adapter ids, one per line
    mm layers-due --summary-since T    # Markdown table of live runs since T (UTC ISO time)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from . import adapter as adapter_mod
from . import config, runlog
from .manifests import load_layers

INTERVAL = {"weekly": timedelta(days=7), "monthly": timedelta(days=30), "annual": timedelta(days=365)}
MIN_AGE = {timedelta(days=7): timedelta(days=6), timedelta(days=30): timedelta(days=25),
           timedelta(days=365): timedelta(days=350)}


def layer_adapters() -> dict[str, timedelta]:
    """adapter id -> shortest layer refresh interval (gated adapters excluded)."""
    out: dict[str, timedelta] = {}
    gated = config.live_gates()
    available = set(adapter_mod.available())
    for layer in load_layers():
        iv = INTERVAL.get(layer.refresh)
        if iv is None or layer.source not in available:
            continue
        out[layer.source] = min(iv, out.get(layer.source, iv))
    return dict(sorted((k, v) for k, v in out.items() if k not in gated))


def due(now: datetime | None = None, force: bool = False) -> list[tuple[str, str]]:
    """(adapter id, reason) for each adapter due now (all of them with force)."""
    now = now or runlog.utcnow()
    if force:
        return [(a, "forced") for a in layer_adapters()]
    runs = runlog.read_all()
    result = []
    for adapter_id, iv in layer_adapters().items():
        ok = [r for r in runlog.for_adapter(adapter_id, runs) if r.mode == "live" and r.status == "success"]
        if not ok:
            result.append((adapter_id, "never succeeded live"))
        elif now - ok[-1].finished_at >= MIN_AGE[iv]:
            result.append((adapter_id, f"last live success {ok[-1].finished_at:%Y-%m-%d}"))
    return result


def summary(since: datetime) -> str:
    runs = [r for r in runlog.read_all() if r.mode == "live" and r.started_at >= since
            and r.adapter in layer_adapters()]
    lines = ["| adapter | status | features | source as of | calls | seconds |", "|---|---|---|---|---|---|"]
    for r in runs:
        secs = int((r.finished_at - r.started_at).total_seconds())
        lines.append(f"| {r.adapter} | {r.status} | {r.rows_out} | {r.source_as_of or '—'} | "
                     f"{r.calls_made} | {secs} |" + (f" {r.errors[0][:120]}" if r.errors else ""))
    if not runs:
        lines.append("| (none ran) | | | | | |")
    return "\n".join(lines)


def main(summary_since: str | None, force: bool = False) -> int:
    if summary_since:
        print(summary(datetime.fromisoformat(summary_since)))
        return 0
    for adapter_id, reason in due(force=force):
        print(f"{adapter_id}: {reason}", file=sys.stderr)
        print(adapter_id)
    return 0
