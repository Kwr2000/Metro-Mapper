# Hays CAD 2026 property facts

Annual canonical-only adapter for the monthly Property Data Export as of October 19, 2026.
Uses the fixed URL and native headers in `adapter.py`; no source calls during development.
Values describe January 1, 2026; `certified` records the October 19 export correction date.
The source has no sale prices. These are appraisal values, not sale prices or estimates.
The certified Orion export lacks improvements/segments and is deliberately not used.

One budgeted request streams the outer ZIP to a temporary directory under `data/raw`.
Each nested ZIP gets a seekable temporary file, without extracting its members; both levels
are removed before `fetch` returns, including on error. A normal run is one call; returned
HTTP/parse failures suppress the runner's automatic download retry. No raw retention or recording.

All six file kinds must appear exactly once, identified by header rather than numeric member
names. Exactly one CSV per nested ZIP. Headers use Latin-1 and CSV quoting; the four allowed
column lists are `COLUMNS` in `adapter.py`. The byte-level CSV projector buffers and decodes
only selected cells, while traversing discarded cells solely for delimiters/quote structure.
It never materializes `LegalDesc`, free-text `Situs`, prior values, taxing units, lease numbers
or any other unselected cell. Owner/sales streams close immediately after one header read;
no TextIOWrapper, data iteration, row counting or decoding is done on them. Private compressed
archive bytes necessarily pass through temporary ZIP storage, which is deleted, never retained.

Improvements choose the highest-valued mapped `StateCode|Type`; ties keep file order. Missing
values rank below observed zero. Skips use the highest-valued overall improvement's pair or
`(blank)|(blank)` for no improvement. Personal-property `M1` remains unmapped. Hays does not
separate condos/townhomes from its `A`/`A1` residential single-family category; no condo label
is inferred. Main area includes every case-sensitive `Type` starting `MA`, including `MAENCL`,
across the property's segments; it is a check value, not a substituted living area. Year is
from the largest measured main segment (first tie; its missing/zero year stays null). Floors
count main-segment rows. Blank numeric cells stay missing; invalid, negative or nonfinite
numbers fail. Money and living area round to whole units, main sums to six decimals, lots to
four; observed zero money/MA is preserved, rounded-zero living area/lot size is null.
Land uses summed positive acres, else summed positive square feet / 43,560, else LegalAcres.

Common canonical names match TCAD/WCAD, with `hays_property_id` and `quickrefid` also stored.
Identity is the QuickRefID's exact digit suffix, retaining any leading zeros; it is independent
of the internal PropertyID. Unsupported fields are null. In particular `partial_owner: null`
is the shared schema's required name, not a Hays owner-file field. This exact null key is the
only expected exception to a privacy grep for owner keys. Geometry is EMPTY; no layer or
parcel geometry join is added.

Repeated PropertyIDs compare all selected original string cells before trimming. An identical
repeat is kept once; any selected difference permanently excludes that ID, counted once in
`conflicting_ids`. `repeated_rows` counts all extra rows, including conflicting ones. Counts
reconcile rows = distinct IDs + repeats and distinct IDs = kept + code skips + invalid QuickRefs
+ conflicting IDs. Duplicate kept QuickRef suffixes fail rather than silently merge.

The count-only `run_summary` reports rows for the four read files. Owner/sales counts are null
because their rows are never read; their keys confirm header discovery. It includes category
and skip counts, duplicates/conflicts, invalid QuickRefs, living/MA/year/lot counts and shares,
optional live-only local Hays parcel matches, processing runtime and Linux process peak RSS.
No property IDs, addresses, source values or private exception text are logged. Runtime stops
at finalization; also inspect total workflow runtime, serialization peak and compressed file
size in Claude's first live check. Parcel coverage is report-only; fixtures never read live
canonical parcels. Annual cadence is declared here; automatic due scheduling remains manifest
based pending P2-05, as for TCAD/WCAD.

Production volume gates: property rows within 2% of 134,553, kept 82,000–100,000. Tiny fixtures
bypass only volume; both modes enforce ≥95% single-family living-area coverage and ≥95% of
comparable living/MA values within one square foot. Empty denominators report null, never 100%.
The runner preserves prior canonical data on failure. Live use stays gated pending Claude.

`make_fixtures.py` rebuilds the small JSON parsed-response fixture from synthetic native CSV
cells in six numeric nested ZIPs. Tests independently transcribe the four allowlists, build
real ZIPs, guard private streams after the header and forbidden-cell decoding, exercise quoted
Latin-1 and multiline CSV, and scan mock-live canonical files/run logs for canaries. All tests
block source networking. Run `make test` from the repository root.

Claude's live check: rows property 134,553 (134,552 distinct), improvement 103,491, segment
419,776 and land 130,100; owner/sales header presence only. Check kept 82k–100k and categories,
≥95% single-family living coverage (~98%), ≥95% MA agreement (~97.9%), year/lot coverage,
parcel match (~99%, report only), five property-search browser checks, canonical size,
processing/full runtime and peak memory, and stored-field privacy (including no legal fields).
