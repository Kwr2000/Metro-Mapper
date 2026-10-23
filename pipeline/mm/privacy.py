"""Ground rule 5 (AGENTS.md): nothing about people is published.

Adapters strip owner names, mailing addresses, exemption flags and similar fields at
ingest. This module is the second line of defence: publishing refuses any feature
property whose name looks personal. Property (situs) addresses are allowed; they
describe the property, not a person.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

FORBIDDEN = re.compile(
    r"owner|mail|(^|_)addr(ess)?(_|$|\d)|exempt|confidential|agent|mortgage|deed_num|deed_book|"
    r"buyer|seller|grantor|grantee|party_?name|name_?care|in_care|taxpayer|phone|email|"
    r"(^|_)ov65|(^|_)dv\d|disab|veteran|homestead",
    re.IGNORECASE,
)
ALLOWED_PREFIXES = ("situs",)
# Area-level statistics whose names contain a forbidden word (e.g. ACS owner-occupancy).
ALLOWED = re.compile(r"^owner_occupied", re.IGNORECASE)


class PrivacyError(ValueError):
    pass


def personal_keys(keys: Iterable[str]) -> list[str]:
    """Property names that look like personal data."""
    return sorted({k for k in keys
                   if FORBIDDEN.search(k) and not k.lower().startswith(ALLOWED_PREFIXES)
                   and not ALLOWED.search(k)})


def check_properties(where: str, keys: Iterable[str]) -> None:
    bad = personal_keys(keys)
    if bad:
        raise PrivacyError(f"{where}: refusing to publish personal fields {bad} (AGENTS.md rule 5)")
