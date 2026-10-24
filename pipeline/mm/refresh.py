"""The monthly refresh (P1-09), run by .github/workflows/refresh.yml.

1. Publish what is stored (last month's data) so every layer has a file to compare.
2. Run each due adapter live (layers_due: monthly and annual layers, gated adapters
   excluded), each within its own approved budget in config/budgets.yaml.
3. Validate (validation.py). If a hard check fails, put data/canonical back exactly as it
   was before the refresh, so nothing new is published and last month stays live. The run
   log always keeps the calls made, so they count against the budgets.
4. Write data/validation/validation.json and report.md. The workflow commits them with
   the run log (a commit every month keeps the schedule alive under GitHub's 60-day rule).

    mm refresh --mode live      # what the workflow runs
    mm refresh --dry-run        # list what is due and validate; no source calls, no writes
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import layers_due, runner, validation
from .paths import paths


def _snapshot() -> dict[Path, bytes]:
    root = paths().canonical
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} if root.exists() else {}


def _restore(snap: dict[Path, bytes]) -> None:
    root = paths().canonical
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file() and p not in snap:
                p.unlink()
    for p, data in snap.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def _publish_stored() -> None:
    from .cli import _cmd_publish
    import argparse

    _cmd_publish(argparse.Namespace())


def refresh(mode: str = "live", dry_run: bool = False) -> dict:
    due = layers_due.due()
    print("due: " + (", ".join(f"{a} ({why})" for a, why in due) or "nothing"), file=sys.stderr)
    _publish_stored()
    if dry_run:
        rep = validation.build(results=[{"adapter": a, "reason": why, "status": "dry run",
                                         "rows": 0, "calls": 0} for a, why in due])
        rep["published"] = False
        return rep

    before = _snapshot()
    results = []
    for adapter_id, why in due:
        run = runner.run(adapter_id, mode=mode)
        err = next((e.splitlines()[0][:200] for e in run.errors if e.strip()), None)
        results.append({"adapter": adapter_id, "reason": why, "status": run.status,
                        "rows": run.rows_out, "calls": run.calls_made, "run_id": run.run_id,
                        "error": err})
        print(f"{adapter_id}: {run.status} rows={run.rows_out} calls={run.calls_made}", file=sys.stderr)

    rep = validation.build(results=results)
    changed = _snapshot() != before
    if not rep["passed"]:
        _restore(before)
        _publish_stored()  # put the previous month's files back for anything local
        changed = False
    rep["published"] = changed
    validation.write(rep)
    return rep


def main(mode: str, dry_run: bool, report: str | None = None) -> int:
    rep = refresh(mode=mode, dry_run=dry_run)
    text = validation.markdown(rep)
    print(text)
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        Path(report).write_text(text)
    if not rep["passed"]:
        print("::error title=Validation failed::Hard checks failed; the previous month's data "
              "stays live. See data/validation/report.md.", file=sys.stderr)
        return 1
    return 0

