"""Repo layout. Every path the pipeline touches is defined here.

Set MM_ROOT to point the pipeline at a different checkout (tests do this
with a temporary copy so they never touch real data).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_root() -> Path:
    env = os.environ.get("MM_ROOT")
    if env:
        return Path(env).resolve()
    # pipeline/mm/paths.py -> repo root is two levels above pipeline/
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def adapters(self) -> Path:
        return self.root / "adapters"

    @property
    def layers(self) -> Path:
        return self.root / "layers"

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        """Raw responses of live runs. Gitignored: raw source files may hold personal data."""
        return self.data / "raw"

    @property
    def canonical(self) -> Path:
        """Validated canonical records of the last good live run (committed)."""
        return self.data / "canonical"

    @property
    def run_log(self) -> Path:
        return self.data / "runs" / "ingestion_runs.jsonl"

    @property
    def fixture_run_log(self) -> Path:
        """Fixture-mode runs (CI, local dev). Not committed; never count as fresh data."""
        return self.data / "runs" / "fixture_runs.jsonl"

    @property
    def web_public(self) -> Path:
        return self.root / "web" / "public"

    @property
    def published_layers(self) -> Path:
        return self.web_public / "data" / "layers"

    @property
    def registry_json(self) -> Path:
        return self.web_public / "registry.json"

    @property
    def health_json(self) -> Path:
        return self.web_public / "health.json"

    @property
    def schemas(self) -> Path:
        return self.root / "schemas"


def paths() -> Paths:
    return Paths(_default_root())
