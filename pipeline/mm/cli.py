"""Command line: `mm <command>`. Run `mm --help` for the list."""

from __future__ import annotations

import argparse
import json
import sys

from . import adapter as adapter_mod
from . import canonical, config, health, homes, registry, runlog, runner
from .budget import BudgetExceeded, CallBudget
from .manifests import ManifestError


def _cmd_run(a: argparse.Namespace) -> int:
    ids = adapter_mod.available() if a.adapter == "all" else [a.adapter]
    worst = 0
    for adapter_id in ids:
        run = runner.run(adapter_id, mode=a.mode)
        print(f"{adapter_id}: {run.status} ({run.mode}) rows={run.rows_out} "
              f"calls={run.calls_made}/{run.planned_calls}")
        for e in run.errors:
            print("  error:", e.splitlines()[0])
        if run.status == "failed":
            worst = 1
    return worst


def _cmd_record(a: argparse.Namespace) -> int:
    """Live-fetch an adapter's planned requests and save them as fixtures (opt-in only)."""
    if a.adapter in config.live_gates():
        print(f"{a.adapter}: live calls gated (config/live_gates.yaml)", file=sys.stderr)
        return 2
    ad = adapter_mod.load(a.adapter)
    if not ad.recordable:
        print(f"{a.adapter}: recording is off for this adapter; write synthetic fixtures with "
              "native field names instead", file=sys.stderr)
        return 2
    now = runlog.utcnow()
    budget = CallBudget.for_adapter(a.adapter, now)
    ctx = adapter_mod.RunContext(mode="live", now=now, budget=budget,
                                 adapter_dir=adapter_mod.adapter_dir(a.adapter))
    reqs = ad.plan(ctx)[: a.max_calls]
    fixtures = adapter_mod.adapter_dir(a.adapter) / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    calls = 0
    errors: list[str] = []
    for req in reqs:
        try:
            budget.spend()
        except BudgetExceeded as e:
            errors.append(str(e))
            break
        calls += 1
        raw = ad.fetch(req, ctx)
        doc = {"request": {"key": req.key, "params": req.params}, "status": raw.status, "body": raw.body}
        (fixtures / f"{req.key}.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        print(f"recorded {req.key} (HTTP {raw.status})")
    from .schemas import IngestionRun
    runlog.append(IngestionRun(
        run_id=now.strftime("%Y%m%dT%H%M%SZ") + "-record", adapter=a.adapter, mode="live",
        started_at=now, finished_at=runlog.utcnow(), status="skipped" if not calls else "success",
        planned_calls=len(reqs), calls_made=calls, errors=errors, notes=["fixture recording"],
    ))
    return 0 if not errors else 1


def _cmd_compile(a: argparse.Namespace) -> int:
    reg = registry.compile_registry()
    print(f"registry: {len(reg.layers)} layers, groups={reg.groups}")
    return 0


def _cmd_health(a: argparse.Namespace) -> int:
    rep = health.build()
    for h in rep.adapters:
        print(f"{h.adapter}: {h.freshness} last={h.last_status} today={h.calls_today} month={h.calls_this_month}")
    return 0


def _cmd_schema(a: argparse.Namespace) -> int:
    for p in registry.export_schemas():
        print("wrote", p)
    return 0


def _cmd_layers_due(a: argparse.Namespace) -> int:
    from . import layers_due

    return layers_due.main(a.summary_since, a.force)


def _cmd_validate(a: argparse.Namespace) -> int:
    from . import validation

    return validation.main(write_files=a.write)


def _cmd_refresh(a: argparse.Namespace) -> int:
    from . import refresh

    return refresh.main(mode=a.mode, dry_run=a.dry_run, report=a.report)


def _copy_validation() -> None:
    """The last refresh's validation report is served with the site (no network)."""
    from .paths import paths

    src = paths().data / "validation" / "validation.json"
    if src.is_file():
        dst = paths().web_public / "validation.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())


def _cmd_publish(a: argparse.Namespace) -> int:
    """Publish from stored live data (data/canonical); adapters that have never run live
    publish their fixtures, labeled Test data. No network calls. Used by the Pages build."""
    from .publish import publish_for_adapter

    worst = 0
    live_runs = [r for r in runlog.read_all() if r.mode == "live"]
    for adapter_id in adapter_mod.available():
        ad = adapter_mod.load(adapter_id)
        recs = canonical.read(ad.entity, adapter_id)
        if recs is not None:
            last = runlog.last_success(adapter_id, live_runs)
            as_of = last.source_as_of if last else None
            for p in publish_for_adapter(adapter_id, ad.entity, recs, mode="live", source_as_of=as_of):
                print(f"{adapter_id}: republished {p} from stored live data")
            continue
        run = runner.run(adapter_id, mode="fixture")
        print(f"{adapter_id}: no stored live data; published fixtures (labeled Test data)")
        if run.status == "failed":
            worst = 1
            for e in run.errors:
                print("  error:", e.splitlines()[0])
    homes.publish()
    from . import area_price
    area_price.publish()
    from . import area_score
    area_score.publish()
    _cmd_compile(a)
    _cmd_health(a)
    _copy_validation()
    return worst


def _cmd_build(a: argparse.Namespace) -> int:
    """Everything the site needs, from fixtures only: what CI runs."""
    rc = _cmd_run(argparse.Namespace(adapter="all", mode="fixture"))
    _cmd_compile(a)
    _cmd_health(a)
    return rc


def _install_signal_handlers() -> None:
    import signal

    def _terminated(signum, frame):  # noqa: ARG001
        raise runner.Terminated(f"signal {signum}")
    signal.signal(signal.SIGTERM, _terminated)


def main(argv: list[str] | None = None) -> int:
    _install_signal_handlers()
    p = argparse.ArgumentParser(prog="mm", description="Metro Mapper pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run one adapter (or 'all')")
    r.add_argument("--adapter", required=True)
    r.add_argument("--mode", choices=["live", "fixture"], default="fixture")
    r.set_defaults(fn=_cmd_run)

    rec = sub.add_parser("record", help="live-fetch planned requests and save them as fixtures (opt-in)")
    rec.add_argument("--adapter", required=True)
    rec.add_argument("--max-calls", type=int, default=5)
    rec.set_defaults(fn=_cmd_record)

    sub.add_parser("compile", help="compile layers/ into registry.json").set_defaults(fn=_cmd_compile)
    sub.add_parser("health", help="write health.json from the run log").set_defaults(fn=_cmd_health)
    sub.add_parser("schema", help="export JSON Schemas for TypeScript generation").set_defaults(fn=_cmd_schema)

    ld = sub.add_parser("layers-due", help="map-layer adapters due a live refresh (one id per line)")
    ld.add_argument("--force", action="store_true", help="list every layer adapter, due or not")
    ld.add_argument("--summary-since", help="instead, print a table of live layer runs since this UTC time")
    ld.set_defaults(fn=_cmd_layers_due)

    v = sub.add_parser("validate", help="validation report on what is published (hard checks decide the exit code)")
    v.add_argument("--write", action="store_true", help="also write data/validation/")
    v.set_defaults(fn=_cmd_validate)

    rf = sub.add_parser("refresh", help="monthly refresh: run due adapters, validate, keep or roll back")
    rf.add_argument("--mode", choices=["live", "fixture"], default="live")
    rf.add_argument("--dry-run", action="store_true", help="list what is due and validate; no source calls, no writes")
    rf.add_argument("--report", help="also write the Markdown report to this file")
    rf.set_defaults(fn=_cmd_refresh)

    sub.add_parser("publish", help="publish from stored live data (fixtures where none); no network").set_defaults(fn=_cmd_publish)
    sub.add_parser("build", help="run all adapters on fixtures, compile, health").set_defaults(fn=_cmd_build)

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except ManifestError as e:
        print(f"manifest error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
