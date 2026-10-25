"""Canonical schemas: the contract between adapters, the registry and the site.

Adapters emit canonical records only. The site reads only the compiled registry
and published layer files. Source field names never cross these seams. TypeScript
types for the site are generated from the JSON Schema of the models in
EXPORTED_MODELS (`mm schema`, then `npm run gen:types` in web/).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SLUG_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"

Refresh = Literal["daily", "weekly", "monthly", "annual", "as_revised", "manual"]

# How long after the expected refresh a source counts as stale, in hours.
FRESHNESS_HOURS: dict[str, float | None] = {
    "daily": 48,
    "weekly": 24 * 9,
    "monthly": 24 * 35,
    "annual": 24 * 400,
    "as_revised": None,  # never stale on a clock; checked against the source's own date
    "manual": None,
}


class Strict(BaseModel):
    # Defaults count as required in the exported schema: the compiled registry
    # always contains every field, so generated TypeScript types need no `?`.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


# --------------------------------------------------------------------------
# Layer manifests (exported)
# --------------------------------------------------------------------------


class LegendItem(Strict):
    label: str
    color: str
    outline: str | None = Field(None, description="Swatch border colour, e.g. for a hollow 'not rated' symbol")


class LayerStyle(Strict):
    """A MapLibre layer style. `paint`/`layout` are passed to MapLibre as-is."""

    type: Literal["circle", "line", "fill", "fill-extrusion", "symbol", "heatmap", "raster"]
    paint: dict[str, Any] = Field(default_factory=dict)
    layout: dict[str, Any] = Field(default_factory=dict)
    minzoom: float | None = None
    maxzoom: float | None = None


class PopupField(Strict):
    field: str
    label: str
    format: Literal["text", "number", "currency", "date", "percent", "link"] = "text"
    moe_field: str | None = None
    reliability_field: str | None = None
    annotation_field: str | None = None
    # A text property shown instead of the formatted value when set (e.g. "$250,000 or
    # more" for a Census top-coded median, whose stored number is only used for colour).
    display_field: str | None = None
    # Notes that only sometimes apply: leave the row out when empty instead of showing
    # "Not available" (which would read as missing data).
    hide_if_empty: bool = False


class LayerVariant(Strict):
    """Layers sharing a family are one choice in the panel with a scale toggle."""

    family: str = Field(pattern=SLUG_PATTERN)
    key: str
    label: str


class LayerManifest(Strict):
    id: str = Field(pattern=SLUG_PATTERN)
    title: str
    group: str
    description: str = ""
    source: str = Field(pattern=SLUG_PATTERN, description="Adapter id that produces this layer")
    geometry: Literal["point", "line", "polygon", "raster", "none"]
    join: Literal["parcel", "point", "block_group", "tract", "zip", "jurisdiction", "precinct", "none"]
    publish: Literal["geojson", "pmtiles", "none"]
    style: LayerStyle | None = None
    popup: list[PopupField] = Field(default_factory=list)
    popup_title: str | None = None
    hover: list[PopupField] = Field(default_factory=list)
    variant: LayerVariant | None = None
    data_bundle: str | None = Field(None, pattern=SLUG_PATTERN,
                                    description="Layers that share one published data file")
    legend: list[LegendItem] = Field(default_factory=list)
    dataset: str | None = Field(None, description="Which of the source's datasets; None = all")
    where: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Equality filters on feature properties"
    )
    as_of_field: str | None = None
    coverage: str
    refresh: Refresh
    attribution: str
    license: str = ""
    disclaimer: str = Field("", description="The publisher's own disclaimer, shown with the layer")
    demographic: bool = Field(
        False,
        description="Census demographics: map layer and filter only, never a score or model input "
                    "(AGENTS.md rule 4). Every field of a demographic layer is a demographic field.",
    )
    default_visible: bool = False
    order: int = 100

    @model_validator(mode="after")
    def _style_matches_geometry(self) -> "LayerManifest":
        if self.publish == "none" or self.geometry == "none":
            return self
        if self.style is None:
            raise ValueError("a published map layer needs a style")
        allowed = {
            "point": {"circle", "symbol", "heatmap"},
            "line": {"line", "symbol"},
            "polygon": {"fill", "line", "fill-extrusion", "symbol"},
            "raster": {"raster"},
        }[self.geometry]
        if self.style.type not in allowed:
            raise ValueError(
                f"style type '{self.style.type}' does not fit geometry '{self.geometry}' "
                f"(allowed: {sorted(allowed)})"
            )
        return self

    def fields(self) -> set[str]:
        """Every feature property this layer shows."""
        out: set[str] = set()
        for f in [*self.popup, *self.hover]:
            out.update(x for x in (f.field, f.moe_field, f.reliability_field, f.annotation_field,
                                   f.display_field) if x)
        if self.as_of_field:
            out.add(self.as_of_field)
        return out


# --------------------------------------------------------------------------
# Compiled registry (exported) - the only thing the site reads about layers
# --------------------------------------------------------------------------

Freshness = Literal["fresh", "stale", "never_run", "failing", "not_scheduled", "fixture_only"]


class CompiledLayer(LayerManifest):
    data_url: str | None
    as_of: str | None = Field(description="ISO date the data describes, or the last successful run")
    last_success: str | None
    freshness: Freshness


class BasemapConfig(Strict):
    style_url: str
    attribution: str
    center: list[float] = Field(min_length=2, max_length=2, description="[lon, lat]")
    zoom: float


class Registry(Strict):
    version: int = 1
    site_title: str
    compiled_at: str
    basemap: BasemapConfig
    groups: list[str]
    layers: list[CompiledLayer]


# --------------------------------------------------------------------------
# Run log and health (exported)
# --------------------------------------------------------------------------

RunStatus = Literal["success", "partial", "failed", "skipped"]


class IngestionRun(Strict):
    run_id: str
    adapter: str
    mode: Literal["live", "fixture"]
    started_at: datetime
    finished_at: datetime
    status: RunStatus
    planned_calls: int = 0
    calls_made: int = 0
    rows_out: int = 0
    schema_hash: str | None = None
    source_as_of: date | None = None
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AdapterHealth(Strict):
    adapter: str
    cadence: str
    last_run: datetime | None
    last_status: RunStatus | None
    last_success: datetime | None
    freshness: Freshness
    calls_today: int
    calls_this_month: int
    budget_per_day: int | None
    budget_per_month: int | None
    last_errors: list[str]
    schema_hash: str | None
    schema_changed: bool


class HealthReport(Strict):
    generated_at: datetime
    adapters: list[AdapterHealth]
    recent_runs: list[IngestionRun]


# --------------------------------------------------------------------------
# Canonical entities emitted by adapters (not exported)
# --------------------------------------------------------------------------


class AreaFeature(Strict):
    """One map feature: a polygon, line or point with display properties."""

    dataset: str = Field(pattern=SLUG_PATTERN, description="A source can emit several datasets; layers pick one")
    feature_id: str
    geometry: dict[str, Any] = Field(description="GeoJSON geometry, WGS84")
    properties: dict[str, Any] = Field(default_factory=dict)
    source_as_of: date | None = None


ENTITY_MODELS: dict[str, type[BaseModel]] = {
    "area_feature": AreaFeature,
}

# Models whose JSON Schema is exported for TypeScript generation.
EXPORTED_MODELS: dict[str, type[BaseModel]] = {
    "registry": Registry,
    "health": HealthReport,
}
