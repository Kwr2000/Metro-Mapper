"""Ground rule 4 (AGENTS.md): demographics are context and filters, never inputs.

Every score, ranking, value model or "value for money" measure declares the feature
properties it reads here. Tests (and `assert_no_demographics` at runtime) fail if any
of them is a field of a layer marked `demographic: true`.
"""

from __future__ import annotations

from collections.abc import Iterable

# score/model id -> every home/HPI feature property read by the model.
SCORE_INPUTS: dict[str, list[str]] = {
    "area_score": ["rate_part1", "overall_score", "flood_share_1pct", "walk_basket", "bike_basket",
                   "walk_grocery", "walk_park", "transit_per_hour",
                   # access notes: only to recognise "More than 60 minutes" (a measured value)
                   "walk_basket_note", "bike_basket_note", "walk_grocery_note", "walk_park_note"],
    "value_range": ["county", "category", "hood_cd", "market_value", "improvement_value", "value_year",
                    "year_built", "land_acres", "living_area", "partial_owner", "cbsa", "year", "quarter", "index_sa"],
}


class DemographicInputError(ValueError):
    pass


def demographic_fields() -> set[str]:
    from .manifests import load_layers

    out: set[str] = set()
    for layer in load_layers():
        if layer.demographic:
            out |= layer.fields()
    # Geography identifiers and dates are shared by every layer and are not demographics.
    return out - {"geoid", "geography", "name", "name_source", "vintage", "period_end", "county"}


def assert_no_demographics(score_id: str, fields: Iterable[str]) -> None:
    bad = sorted(set(fields) & demographic_fields())
    if bad:
        raise DemographicInputError(
            f"{score_id} reads demographic fields {bad}; demographics may not feed any score "
            f"or model (AGENTS.md rule 4)")
