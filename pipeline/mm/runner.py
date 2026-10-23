"""Runs one adapter end to end:

plan -> fetch (or fixture) -> normalize -> validate -> empty-layer guard
     -> canonical store (live) -> publish layers -> ingestion_run log
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import traceback
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from . import adapter as adapter_mod
from . import canonical, config, layer_guard, publish, runlog
from .budget import BudgetExceeded, CallBudget
from .paths import paths
from .schemas import ENTITY_MODELS, IngestionRun

MAX_FAIL_STREAK = 3


class Terminated(BaseException):
    """Raised by the SIGTERM handler (cli) so the run log still records calls made."""


def progress(msg: str) -> None:
    """One line to the job log so a long live run is never silent. Counts only."""
    print(msg, file=sys.stderr, flush=True)


def schema_hash(records: list[BaseModel]) -> str | None:
    if not records:
        return None
    keys: set[str] = set()
    for r in records:
        d = r.model_dump()
        keys.update(d.keys())
        props = d.get("properties")
        if isinstance(props, dict):
            keys.update(f"properties.{k}" for k in props)
    digest = hashlib.sha256((type(records[0]).__name__ + "|" + ",".join(sorted(keys))).encode())
    return digest.hexdigest()[:12]


def _write_raw(adapter_id: str, run_id: str, now: datetime, raws: list[adapter_mod.RawPayload]) -> Path | None:
    """Raw responses of a live run, for debugging. data/raw is gitignored."""
    if not raws:
        return None
    d = paths().raw / adapter_id / now.strftime("%Y-%m")
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{run_id}.ndjson.gz"
    with gzip.open(out, "wt", encoding="utf-8") as f:
        for raw in raws:
            f.write(json.dumps({
                "request": {"key": raw.request.key, "params": raw.request.params},
                "status": raw.status,
                "fetched_at": (raw.fetched_at or now).isoformat(),
                "body": raw.body,
            }, sort_keys=True, default=str) + "\n")
    return out


def run(adapter_id: str, mode: Literal["live", "fixture"] = "fixture",
        now: datetime | None = None) -> IngestionRun:
    now = now or runlog.utcnow()
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    errors: list[str] = []
    notes: list[str] = []
    planned = calls = 0
    records: list[BaseModel] = []
    raws: list[adapter_mod.RawPayload] = []
    status = "success"
    source_as_of = None
    interrupted: BaseException | None = None

    if mode == "live" and adapter_id in config.live_gates():
        reason = config.live_gates()[adapter_id]
        run_ = IngestionRun(run_id=run_id, adapter=adapter_id, mode="live", started_at=now,
                            finished_at=now, status="skipped",
                            notes=[f"live ingestion gated (config/live_gates.yaml): {reason}"])
        runlog.append(run_)
        return run_
    try:
        ad = adapter_mod.load(adapter_id)
        budget = CallBudget.for_adapter(adapter_id, now)
        if mode == "fixture":
            # Fixtures spend no calls and are never limited by live spend; keep configured
            # caps so plans stay bounded the same way as live.
            b = config.budgets().adapters.get(adapter_id)
            limits = [v for v in ((b.per_day, b.per_month) if b else ()) if v is not None]
            budget.remaining = min(limits, default=None)
        ctx = adapter_mod.RunContext(mode=mode, now=now, budget=budget,
                                     adapter_dir=adapter_mod.adapter_dir(adapter_id))
        queue = deque(ad.plan(ctx))
        fail_streak = 0
        planned = len(queue)

        while queue:
            req = queue.popleft()
            if mode == "fixture":
                raw = adapter_mod.read_fixture(adapter_id, req)
            else:
                if budget.out_of_time():
                    errors.append(f"{adapter_id}: time limit of {budget.max_minutes} min reached; "
                                  f"{len(queue) + 1} requests left for the next run")
                    status = "partial"
                    break
                try:
                    budget.spend()
                except BudgetExceeded as e:
                    errors.append(f"{e}; {len(queue) + 1} requests not made")
                    status = "partial"
                    break
                calls += 1
                if calls % 10 == 0:
                    progress(f"{adapter_id}: {calls} calls, {len(queue)} queued, "
                             f"{budget.elapsed() / 60:.1f} min")
                try:
                    raw = ad.fetch(req, ctx)
                    fail_streak = 0
                except Exception as e:  # one failed call does not sink the run
                    errors.append(f"{req.key}: {type(e).__name__}: {e}")
                    status = "partial"
                    fail_streak += 1
                    if fail_streak >= MAX_FAIL_STREAK:  # e.g. rate-limited: stop, don't hammer
                        errors.append(f"{adapter_id}: {fail_streak} failures in a row; stopped, "
                                      f"{len(queue)} requests left for the next run")
                        break
                    continue
            raws.append(raw)
            extra = ad.follow_up(raw, ctx)
            planned += len(extra)
            queue.extendleft(reversed(extra))  # depth-first: finish a page run before the next

        if mode == "live" and ad.retain_raw:
            _write_raw(adapter_id, run_id, now, raws)
        model = ENTITY_MODELS[ad.entity]
        for raw in raws:
            for rec in ad.normalize(raw):
                if not isinstance(rec, model):
                    raise TypeError(f"{adapter_id} emitted {type(rec).__name__}, expected {model.__name__}")
                records.append(rec)
        records = [model.model_validate(r.model_dump()) for r in ad.finalize(records)]  # re-validate
        for r in records:
            if not isinstance(r, model):
                raise TypeError(f"{adapter_id}.finalize emitted {type(r).__name__}, expected {model.__name__}")

        source_as_of = ad.source_as_of(raws)
        if planned and not raws:
            status = "failed"
        if mode == "live" and status == "partial":
            # Never publish an incomplete layer over a complete one.
            errors.append(f"{adapter_id}: incomplete run; nothing published")
        elif status != "failed":
            held = layer_guard.drops(adapter_id, records) if mode == "live" else []
            if held:
                status = "failed"
                msg = layer_guard.held_message(held)
                errors.append(msg)
                print(f"::warning title={adapter_id} layer kept::{msg}", file=sys.stderr)
            else:
                written = publish.publish_for_adapter(
                    adapter_id, ad.entity, records, mode=mode, source_as_of=source_as_of,
                    keep_stale_flag=False)
                if mode == "live":
                    canonical.write(ad.entity, adapter_id, records)
                notes.extend(f"published {p}" for p in written)
    except (ValidationError, Exception) as e:  # noqa: BLE001 - logged, never swallowed silently
        status = "failed"
        errors.append(f"{type(e).__name__}: {e}")
        errors.append(traceback.format_exc(limit=3))
    except (KeyboardInterrupt, Terminated) as e:
        status = "failed"
        errors.append(f"interrupted ({type(e).__name__}); {calls} calls made before stopping")
        interrupted = e

    run_ = IngestionRun(
        run_id=run_id,
        adapter=adapter_id,
        mode=mode,
        started_at=now,
        finished_at=runlog.utcnow(),
        status=status,
        planned_calls=planned,
        calls_made=calls,
        rows_out=len(records),
        schema_hash=schema_hash(records),
        source_as_of=source_as_of,
        errors=errors,
        notes=notes,
    )
    runlog.append(run_)
    if layer_guard.is_held(run_):
        layer_guard.mark_stale(adapter_id, layer_guard.stale_info(adapter_id) or {})
    if interrupted is not None:
        raise interrupted
    return run_
