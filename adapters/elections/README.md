# TLC election context

Two budgeted annual downloads supply 2020 and 2024 presidential returns and registration/
turnout on TLC's **2024 precincts**. The CC BY source, dates and file URLs are recorded in
`docs/SOURCES.md`; the budget and pyshp approval are in `docs/DECISIONS.md`. Live use stays
gated for Claude's first check. No block-group, tract or address join is made.

Both ZIPs stream in 1 MiB chunks to ignored temporary folders under `data/raw/`. Read only
four election CSV members and the SHP/SHX/DBF/PRJ components. CSVs are streamed directly from
the archive; unused fields and non-presidential/out-of-county rows are discarded immediately.
Only `vtdkey`, `TotalVR`, `TotalTO` survive VRTO parsing. `SpanishSurnamePercent` and `TotalPop`
never reach retained response bodies, records, fixtures, logs or published data. The downloaded
archive and extracted components are deleted on success and every error before fetch returns.
Raw retention and fixture recording remain disabled. Large-file errors return a failed payload
so the runner does not download a large archive twice. The same 15-minute deadline covers
streaming, parsing and finalization.

Read the shape CRS from `.prj`, repair invalid polygon parts with `make_valid`, and reproject
to WGS84. As in the areas adapter, simplify in EPSG:5070 at 5 m, then round WGS84 coordinates
to six decimals. Fail if the rounded geometry is invalid. Join only by numeric TLC VTD key,
which is stored as canonical text. VTD labels retain their original leading zeros.

A return row is unique per election, precinct, party and candidate; multiple differently
named write-ins count toward Other. Exactly one Democratic and one Republican candidate row
is required for each precinct/year, including zero-vote rows. Missing rows never become zeros.
Shares and margin use all presidential votes as denominator; compute the margin before
rounding, then round final ratios to three decimals using Python's nearest-even rule.

Suppression applies independently to each election. Below 50 presidential votes, that year's
counts and shares/margin are null; candidate names, registration and valid turnout remain.
Ballots exceeding registration suppress turnout, including when registration is zero.
Year-prefixed notes distinguish which election has each issue. The source-as-of date is the
2024 general-election date, 2024-11-05, with TLC's re-tabulation explained in `source_note`.

All schema, count, join, duplicate, geometry and suppression checks apply to tiny fixtures.
Only live mode enforces the production scale (553 ± 30) and 2024 D/R totals within 1% of the
spec's verified values. Tests separately exercise those guards, including a full-size synthetic
run. Fixtures are six invented precincts with native headers and fields, never observations.
Regenerate with `python adapters/elections/make_fixtures.py`; manifests with `make_layers.py`.

Both layers share one `elections_precinct` data file and set `demographic: true`, so they
appear under People (context only) and cannot feed scores/rankings. A separate, non-spatial
canonical `run_summary` keeps whole-region counts before suppression, county counts, turnout,
small-precinct counts, runtime and peak memory. It is printed as a count-only note and shown
by `tools/live_summary.py elections`; it is excluded from the published precinct bundle.
