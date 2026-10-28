# HMDA tract check

One annual CSV request through the budgeted runner, restricted to 2025 purchase originations
in the three study counties. The API returns a wide file. A streaming byte scanner retains
only the nine columns declared in `mm.values.HMDA_INPUTS`; other cells are never buffered as
fields or decoded. The response is reduced to tract aggregates before `fetch` returns.
Raw retention and recording are disabled. Logs contain counts only; errors contain no cells.

`make_fixtures.py` rebuilds the synthetic native-column CSV fixture: 30 measured loans per
county plus explicit filter/invalid-value cases. Like the CAD adapters, fixture mode skips
only the production scale checks (30,323 ±5% source rows and ≥250 tracts with ≥30 loans).
Every county, column, filter, aggregation and privacy check still applies. Tests generate a
production-sized synthetic CSV in memory to verify the full live thresholds without calling
the source. Fixture records never authorize publishing a value range.

Publisher verification and terms are in `docs/SOURCES.md`; first live use remains gated.
