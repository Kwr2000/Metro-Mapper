"""The source-adapter contract and adapter discovery.

An adapter lives in adapters/<id>/adapter.py and exposes `ADAPTER = <class>`.
It turns one external source into canonical records (mm.schemas.ENTITY_MODELS).

    plan(ctx)       -> the requests for this run (within budget)
    fetch(req, ctx) -> one live call, returning the raw payload verbatim
    normalize(raw)  -> canonical records only; never source field names
    source_as_of()  -> the date the data describes, when the source says

The runner, not the adapter, handles fixtures, budgets, validation, publishing and
the run log. In fixture mode `fetch` is never called: the runner reads
adapters/<id>/fixtures/<request.key>.json instead.
"""

from __future__ import annotations

import importlib.util
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

from .budget import CallBudget
from .paths import paths
from .schemas import ENTITY_MODELS, SLUG_PATTERN

_SLUG = re.compile(SLUG_PATTERN)
_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")

USER_AGENT = "metro-mapper/0.1 (+https://github.com/Kwr2000/metro-mapper)"


@dataclass(frozen=True)
class Request:
    """One planned call. `key` names its fixture file."""

    key: str
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _KEY.match(self.key):
            raise ValueError(f"request key {self.key!r} must match {_KEY.pattern}")


@dataclass(frozen=True)
class RawPayload:
    request: Request
    body: Any
    status: int = 200
    fetched_at: datetime | None = None


@dataclass
class RunContext:
    mode: Literal["live", "fixture"]
    now: datetime
    budget: CallBudget
    adapter_dir: Path


class SourceAdapter(ABC):
    id: ClassVar[str]
    entity: ClassVar[str]
    cadence: ClassVar[str]  # human-readable schedule, or "manual"
    user_agent: ClassVar[str] = USER_AGENT
    # Keep raw live responses under data/raw (gitignored). Off by default: raw files from
    # appraisal districts carry owner names and addresses.
    retain_raw: ClassVar[bool] = False
    # Seconds to wait before the one retry of a failed live request (None = runner default).
    # Some servers drop connections when asked again too soon; give those a longer pause.
    retry_wait_seconds: ClassVar[float | None] = None
    # `mm record` may save live responses as fixtures only when the response holds no
    # personal data. Off by default: write synthetic fixtures with native field names.
    recordable: ClassVar[bool] = False

    @abstractmethod
    def plan(self, ctx: RunContext) -> list[Request]: ...

    @abstractmethod
    def fetch(self, req: Request, ctx: RunContext) -> RawPayload: ...

    @abstractmethod
    def normalize(self, raw: RawPayload) -> Iterable[BaseModel]: ...

    def source_as_of(self, raws: list[RawPayload]) -> date | None:
        return None

    def finalize(self, records: list[BaseModel]) -> list[BaseModel]:
        """Combine records from all of a run's responses (e.g. name block groups from
        several sources' polygons). Called once, after every response is normalized.
        Must emit this adapter's entity; the runner validates the result."""
        return records

    def follow_up(self, raw: RawPayload, ctx: RunContext) -> list[Request]:
        """Extra requests prompted by a response (e.g. the next page).
        The runner queues them right after the current request, within budget."""
        return []


def adapter_dir(adapter_id: str) -> Path:
    return paths().adapters / adapter_id


def available() -> list[str]:
    root = paths().adapters
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "adapter.py").is_file())


def load(adapter_id: str) -> SourceAdapter:
    if not _SLUG.match(adapter_id):
        raise ValueError(f"bad adapter id {adapter_id!r}")
    path = adapter_dir(adapter_id) / "adapter.py"
    if not path.is_file():
        raise FileNotFoundError(f"no adapter at {path}")
    spec = importlib.util.spec_from_file_location(f"mm_adapters.{adapter_id}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, "ADAPTER", None)
    if cls is None or not isinstance(cls, type) or not issubclass(cls, SourceAdapter):
        raise TypeError(f"{path} must define ADAPTER = <SourceAdapter subclass>")
    if cls.id != adapter_id:
        raise ValueError(f"{path}: ADAPTER.id is {cls.id!r}, folder is {adapter_id!r}")
    if cls.entity not in ENTITY_MODELS:
        raise ValueError(f"{adapter_id}: unknown entity {cls.entity!r}")
    return cls()


def read_fixture(adapter_id: str, req: Request) -> RawPayload:
    p = adapter_dir(adapter_id) / "fixtures" / f"{req.key}.json"
    if not p.is_file():
        raise FileNotFoundError(f"missing fixture {p}")
    doc = json.loads(p.read_text())
    return RawPayload(request=req, body=doc.get("body"), status=doc.get("status", 200))
