# FHFA purchase-only Austin HPI

One fixed, budgeted request for `hpi_po_metro.txt`. Native TSV header is exactly
`cbsa`, `metro_name`, `yr`, `qtr`, `index_nsa`, `index_sa` (tab-separated);
metro names are quoted and can contain commas. Only CBSA 12420 is kept. Other
metros' unavailable numeric cells are not parsed. No raw retention or recording.

Checks: positive finite indexes, integer valid years/quarters, no repeated or
missing quarters, at least 140 Austin rows, 2025Q4 and 2026Q1 base quarters present,
and the latest completed quarter no more than nine calendar months before the
live run. Returned failures stop without an automatic second download. Canonical
`hpi` records use the latest quarter-end as `source_as_of`; no map file is added.
The `publish: none` manifest registers monthly refresh; the exact approved budget
is 2/day, with first live use gated.

The fixture has 142 **synthetic** consecutive Austin quarters and one ignored
metro, all in native TSV form inside the fixture body. Only the three reference
SA indexes and latest NSA number come from the task spec. `make_fixtures.py` is
reproducible and makes no source calls. Fixture validation uses the fixed
2026-10-27 verification date so builds do not depend on the clock (including the
homes publisher's fixed-date fixture runner). Live mode always uses its run date.

Claude's live check: confirm 142 Austin quarters through 2026Q2, positive indexes
and native header, latest SA 681.16 / NSA 693.01, base mean (680.77 + 656.56)/2 =
668.665 and factor 1.0186864872544548. Public domain U.S. government data; credit
FHFA House Price Index (purchase-only). The source verification/probe is recorded
in SOURCES; Codex develops only on synthetic fixtures.

`config/value_range.yaml` keeps `published: false` pending P2-08. The production
publisher additionally requires ≥97% range coverage and ≥90% single-family
hood-stat coverage per real CAD county. These checks remain strict even when HPI
comes from a fixture. A fixture CAD county alone bypasses those two production
coverage checks: its tiny independent fixtures cannot form ten-home hood groups
and intentionally include exclusion records. Arithmetic, annotations, size,
privacy and all existing homes checks still apply.
