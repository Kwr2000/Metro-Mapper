# TCAD 2026 property facts

Canonical records only: no map manifest or web change. One annual certified-export request
(`tcad_2026`), budget 2/day, 45-minute limit. First live use is gated. Attribution: Travis
Central Appraisal District, 2026 Certified Appraisal Export, Supplement 0, 2026-07-18;
no license stated (owner's government-data publication approval, docs/SOURCES.md).

The ZIP is streamed in 1 MiB chunks to `data/raw/tcad-*/download.zip`. Only TOTALS.TXT,
ABS_SUBD.TXT, IMP_INFO.TXT, IMP_DET.TXT and PROP.TXT are opened, in that order, directly inside
the ZIP. Nothing is extracted. zip64 is supported. Temporary storage is deleted before fetch
returns, on both success and failure; raw retention and recording are disabled. A failed
payload suppresses an automatic second large download. Errors contain no source cell text.

`RANGES` in adapter.py is the complete 1-based inclusive allowlist. Fixed-width bytes pass
through a line buffer; only those cells are sliced and decoded as Latin-1. Owner identity,
mail, confidential, exemption, qualification, mortgage and cap cells are never sliced or
decoded. Improvement descriptions/IDs that are not needed are not read either. The two land
and two improvement value components exist only locally while summing; the compact response,
fixtures and canonical records contain only their sums. A test guards every slice independently
against the spec, plants canaries in the forbidden cells and proves they never leave ingestion.
`partial_owner` is the **explicitly required property-share boolean**, not an owner identity;
its name and its count do contain the word "owner". Do not mistake them for owner-name fields
when performing the live stored-data scan. This task does not change the core privacy guard.

There is no extracted text or segment list in memory: improvement accumulators retain living
area, HVAC area, floor bitset and the largest floor's year; these collapse to per-property facts
before PROP streams once. Equal-size floor or dwelling ties use first source order. Floors are
1ST–5TH, 1/2 and ADDL; FBSMT/RSBLW add living area but do not increment floor count or supply a
floor year. Positive living area determines coverage/dwelling count; missing/zero living area
is null. ADU/garage-apartment improvements set has_adu even if area is missing. Only living
area is rounded to whole square feet; ADU/HVAC sums retain the source's six-decimal precision.
HVAC comparison uses the stored sums, with tolerance 2% of living area. Missing HVAC values
are excluded from that comparison and the denominator is reported; an empty denominator is
null, never 100%. Missing monetary components make their sum null, never an invented zero.

Compact fixtures retain native source names (e.g. prop_type_cd, situs_street_prefx, deed_dt)
plus explicitly derived sums/areas. Normalize accepts only this stripped vocabulary and emits
the task's exact canonical fields, with EMPTY geometry. All records describe 2026-01-01 market
values; certified date is separately 2026-07-18. No 2025 values, bedrooms/bathrooms, assessed or
capped values. Blank situs pieces are null; display joins number/prefix/street/suffix/unit/city/ZIP.
Subdivision casing follows P1-02c title/small-word handling, retaining TCAD's own plat qualifiers.

Checks fail closed: exact record lengths, 2026/zero supplement, R+M vs county TOTALS within 2%,
living coverage and HVAC agreement ≥97%, deadline. Fixtures bypass only the production kept
volume of 330,000–430,000. Duplicate PROP/improvement keys, conflicting subdivision codes,
missing segment-improvement links, malformed numeric/date cells and mixed improvement years
fail rather than guess. CRLF and LF line endings (or a final line without a terminator) are
accepted; lengths are measured after removing the terminator. ABS_SUBD/TOTALS also enforce their
publisher-verified 50/2,491 byte lengths. In live mode the optional parcel match streams local
canonical P2-01 records, restricts to Travis, normalizes numeric ID padding and reports the
match share; it never joins a point into this task or gates on that share. Fixture mode does
not read live canonical parcels.

The run_summary is count-only and `tools/live_summary.py tcad` includes it. Runtime includes
download/parse/normalization/local matching; peak memory is the Linux process high-water mark
at finalization. Core validation/serialization occur afterward: Claude should also check full
job resources and compressed canonical size. As with parcels, annual cadence is declared here;
automatic refresh is manifest-driven and will include this canonical-only source in later work.

Regenerate compact synthetic fixtures: `python adapters/tcad/make_fixtures.py`.
Tests: `python -m pytest pipeline/tests/test_tcad.py` (all fixtures are tiny, none need `slow`).
