# HMDA tract calibration and check

Two annual CSV requests through the existing budgeted runner, for 2025 and 2024 purchase
originations in the three study counties. The budget remains 6/day. Each wide response is
scanned as bytes: only the nine columns in `mm.values.HMDA_INPUTS` are buffered/decoded.
Only tract aggregates and a count-only summary leave `fetch`; no raw CSV or loan rows are
retained or recordable. The aggregate identity is `<year>:<tract>` so the years cannot collide.

`make_fixtures.py` rebuilds both small native-column synthetic CSV fixtures. Fixture mode
skips only scale checks: 2025 source rows 30,323 ±5%, 2024 source rows 32,641 ±5%, and at
least 250 tracts with 30 loans in each year. County, schema, filter and privacy checks apply
to both. Tests serve full-sized synthetic streams in memory, without contacting the source.

The latest year alone fits the factors; the preceding year is held out for selection. If
that check fails, the original range and its P2-08 check apply. Fixtures cannot authorize
publishing ranges. Terms, source counts and verification are recorded in `docs/SOURCES.md`;
Claude performs the first two-year live check after review.
