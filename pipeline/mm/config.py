"""Typed access to files in config/."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from .paths import paths


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdapterBudget(_Strict):
    per_day: int | None = None
    per_month: int | None = None
    min_interval_seconds: float = 0.0
    max_minutes: float | None = None  # wall-clock limit for one run of this adapter


class Budgets(_Strict):
    adapters: dict[str, AdapterBudget]


class AppConfig(_Strict):
    site_title: str
    basemap_style_url: str
    basemap_attribution: str
    center: list[float]
    zoom: float
    study_bbox: list[float]  # [west, south, east, north]
    counties: dict[str, str]  # 5-digit FIPS -> name


def _load_yaml(path: Path) -> Any:
    with path.open() as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def _cached(name: str, root: str) -> Any:
    return _load_yaml(Path(root) / "config" / name)


def load(name: str) -> Any:
    return _cached(name, str(paths().root))


def budgets() -> Budgets:
    return Budgets.model_validate(load("budgets.yaml"))


def app_config() -> AppConfig:
    return AppConfig.model_validate(load("app.yaml"))


def live_gates() -> dict[str, str]:
    """adapter id -> reason it must not run live yet (config/live_gates.yaml)."""
    p = paths().config / "live_gates.yaml"
    data = load("live_gates.yaml") if p.is_file() else {}
    return dict((data or {}).get("gated") or {})


def clear_cache() -> None:
    _cached.cache_clear()
