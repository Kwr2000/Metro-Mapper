# WCAD 2026 certified property facts

Canonical records for P2-05 only, with the same common field names as TCAD. No layer, core or
web change. Credit: Williamson Central Appraisal District, open-data portal, 2026 certified
datasets. No license stated; the owner's public-government-data rule is recorded in SOURCES.
Annual cadence, approved budget exactly 40/day with two seconds between calls, first live use
gated. No key and no new dependencies. Development and tests use synthetic fixtures only.

The request builder and transport validator accept exactly these dataset/select pairs:

| Kind | Dataset | Selected cells |
|---|---|---|
| property | ai3c-c9pf | The 20 property columns listed in the task and `COLUMNS` |
| improvement | 2huh-jk3y | propertyid, fsptb, vtsgimp_impvalue |
| segment | xs93-mfpk | propertyid, fsegtype, farea, factyear |
| land | bens-i2m7 | propertyid, sum(faclandsize) AS acres, sum(fsftlandsize) AS sqft |

Every request has the specified 2026 filter; segments additionally restrict to MA/MA2/MA3/MA4.
Each count is followed by ordered 100,000-row pages until a short page (including an empty
last page when the count is an exact multiple). Property/improvement/segment use propertyid
plus :id to break ties; grouped land uses propertyid alone. Count requests select count(*),
or count(distinct propertyid) for land (native response cell count_propertyid). Land page
requests also group by propertyid. The observed source row counts require 18 total calls.
Tiny fixtures use eight calls; a smaller-page test exercises full, short and empty pages.
Fetched rows must match the count exactly; missing/out-of-order/oversized pages fail closed.

There is no owner, assessment, exemption, sale/history, appeal, agent, permit or property-
characteristic dataset query. Legal descriptions, comments, DBA, generic address, mh fields,
cap or sale cells are never selected. Independent tests check every generated request's ID,
select, filter, group and ordering, and reject forged requests before transport. Unselected
extra response fields are ignored at the selection boundary, even in count responses. A
canary/guard test proves they are never accessed or copied into records, files or logs.
Raw retention and recording are off. Failed transport/API/JSON errors contain no source text.

Portal cells must be strings, with nulls omitted. Decimal numbers (including integer IDs and
years with .000000) are parsed explicitly; nonnumeric, nonfinite, negative or nonintegral ID/
count/year cells fail. Missing numeric cells remain missing. Duplicate property rows must be
identical across every selected cell, including datadate; extra unselected cells do not affect
that comparison. Only the first identical row is used and repeated_rows is reported. Grouped
land repeats, conflicting quickrefids or malformed kept R IDs fail too.

Improvement classification uses the highest-valued mapped code, with first-row ties. Missing
improvement values rank below known values (including an observed zero); all-missing ties also
keep the first. Skipped properties use the highest-valued overall code or "no improvement";
a blank code is counted as "(blank)". M1 remains unmapped and skipped even when the property
has a measured main area, following the owner's personal-property mobile-home decision.

All four main-area codes contribute to ma_area. Year comes from the largest measured segment,
with first-row ties and no fallback when that segment has no year. Floors count segment rows,
including rows whose area is missing. Observed zero MA area remains zero; no measured segments
means null. Living area rounds to whole square feet; zero/missing rounds to null. Money rounds
to whole dollars, MA sums to six decimals, lot acreage to four. Rounded acreage of zero is
null, never an invented minimum. Missing lot data is expected for about 70% of homes.

Address parts are trimmed and joined in TCAD order. Suffix directional joins the suffix; unit
number takes precedence over condo unit. Building and neighborhood descriptions remain separate
facts. Unsupported TCAD fields are present as null, including the required partial_owner key
(which is never a queried WCAD owner column). A stored-field scan must allow that exact null
key while excluding owner identities, mail, exemption and legal fields/values. certified is the latest available property
datadate date, including skipped properties; no datadate anywhere fails. Value/source-as-of is
2026-01-01, independent of the portal refresh date. No 2025 value or estimated sale price.

Only the two production volume checks (319,443 distinct IDs ±2%; 215,000–255,000 kept) are
bypassed in fixture mode. Count equality, numeric/ID validation and both 97% quality checks
apply to fixtures too. Living-area coverage uses the combined single-family/condo cohort;
MA agreement compares the stored sums within one square foot. Empty denominators are null.
The run summary includes each denominator, counts, category/skip distributions and coverage.

Normalization aggregates selected pages, then clears their mutable payload lists to keep
memory bounded instead of retaining per-improvement/segment models. In live mode only, the
optional P2-01 local file is streamed for exact Williamson ID matching. This reports coverage,
without joining geometry or gating on the match. Fixture mode never reads live parcels.
Runtime and Linux peak memory are measured at finalization; Claude should also inspect full
job/serialization resources and canonical size. tools/live_summary.py includes the audit.
Annual automatic refresh remains manifest-driven until later publication work.

Regenerate: `python adapters/wcad/make_fixtures.py`.
Test: `python -m pytest pipeline/tests/test_wcad.py` (all synthetic inputs are tiny).
