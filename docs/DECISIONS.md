# Decisions

Design decisions and the owner's approvals, newest first. Each entry says what was decided,
why, and (for approvals) that the owner approved it in writing.

## 2026-10-27 — P2-05 homes lookup reviewed and merged (Claude, chat)

- PR #116 reviewed against the spec: built only from canonical files, fixed public columns, no
  owner or demographic fields, counts reconcile with each run summary, staging then atomic swap.
  `mm publish` on the real files: 190.6 MB in `homes/` (limit 200 MB), 662 address shards
  (largest 1.95 MB), 6,048 map cells, about 2.5 minutes. Pages deploy at `d58bc0e` took 4.5 minutes.
- One fix before merging: TCAD stores numbered streets without the ordinal ("E 17 ST"), which
  listings write "E 17th St"; 8,634 Travis homes are on such streets. A bare number that is the
  whole street name before a suffix now becomes an ordinal on both sides; six real-shape vectors added.
- Checked 20 listing-style addresses (all three counties, condo units with "UNIT" and "#",
  "County Road 221", duplexes): each finds the right home(s) with the spot-checked living area and
  year built. Round-trip misses: Travis 3,084 of 377,311, Williamson 1,007 of 235,581, Hays 440 of 89,687.
- The 200 MB size limit leaves little room (about 5%); revisit before adding fields or counties.

## 2026-10-27 — P2-05 homes lookup implementation choices (Codex)

- Publish only from the four local canonical files, with pure fixture adapter execution for
  missing files (never fetch, write canonical data or spend calls). A county is Test data if
  either its CAD records or the parcel input is from fixtures; a mixed shard/grid file is Test
  data if any of its rows is. All three county flags roll up to `meta.json`. Real production
  placement gates apply only to counties with both live inputs: the existing independent
  adapter fixtures intentionally have different parcel IDs and cannot meet those gates.
  Count reconciliation, identity, privacy, round-trip and size checks still apply to fixtures.
- Keep the source situs display and parts in the harmonized intermediate record. Export exactly
  the spec's 23 compact address columns (number/unit/ZIP are strings; numeric measures stay
  numeric; missing cells are null). `address_key`, `prop_id`, situs parts and `tract` are
  intermediate fields, not extra compact columns. Preserve observed zero numeric measures;
  reject invalid/negative/nonfinite numbers rather than turn missing values into zero.
  Copy parcel coordinates/block group/tract only on an exact canonical feature-ID match.
- Use explicit unit markers before implicit trailing units, retain compound house numbers and
  separate house-letter tokens, and do not confuse numbered highways with house letters or
  five-digit explicit units with ZIPs. Commas delimit the locality while allowing a comma
  before a unit marker. Unpunctuated CAD city tails use a fixed list of localities and spelling
  variants found in the stored CAD inputs; no location source or network lookup is added.
  Directionals remain positional, suffix conversion is terminal, and unknown/ambiguous forms
  remain visible in count-only round-trip misses. Shared JSON vectors are explicitly synthetic.
- Shard names strip directional prefix, suffix and postdirection before taking alphanumeric
  street-name characters. Pad short/empty names with `0`; an oversized two-character base
  splits once on the third character (`0` if absent). Meta maps each base to its shard IDs,
  without `.json`; grid rows reference those actual shard IDs. Rows sort by street key,
  natural numeric house number, natural unit, then ID. Grid envelopes contain v/test_data/rows;
  callers check the clicked cell plus its eight neighbours before the 30 m nearest-point test.
- Keep neighbourhood descriptions once per county/code; if a code has multiple descriptions,
  use the lexicographically smallest observed spelling for deterministic output. Dates remain
  source dates (no build timestamp). Count-only metrics include all/unplaced categories and
  numbered-home round-trip misses. Do not publish private source fields or join demographics;
  the existing privacy guard checks the fixed public property columns.
- Stage and validate the entire homes tree, then replace it on the same filesystem, restoring
  the previous tree if installation fails. Failures leave the previous homes build in place;
  Pages stops before deployment on a publish error. Limits use uncompressed UTF-8 JSON bytes:
  split bases above 2,000,000 bytes and require the whole tree below 200,000,000 bytes. All
  generated homes/layer files stay ignored and uncommitted. Core integration is one call from
  `mm publish`, after adapters and before registry compilation; no adapter or web code changes.

- Full stored-data publish (network blocked) passed in 159.288 s, peak RSS 3,520 MiB:
  710,480 homes, 649,478 placed, 61,002 unplaced; 190,599,658 uncompressed bytes, 664 shards,
  largest ME.json 1,953,427 bytes and 6,048 grid cells. Travis/Williamson/Hays homes and
  placement counts exactly match the spec. Numbered-home round-trip misses: Travis
  3,084/377,311 (99.18% found), Williamson 1,007/235,581 (99.57%), Hays 440/89,687 (99.51%).
  All production gates pass. Remaining ambiguous/malformed display forms are reported as
  misses, never removed from the home rows. The 53,645 unplaced Travis condos stay unplaced;
  P2-05b's source decision is unchanged. A separate read-back audit of every written row
  and grid entry found zero coordinate, grid, sorting or shard-routing mismatches.

## 2026-10-27 — P2-04 Hays CAD reviewed, merged and live-checked; ungated; WCAD spot check (Claude, chat)

- PR #113 reviewed against the spec (files found by header; owner and sales files never read past
  the header; byte-level CSV reader decodes only allowlisted cells; canaries). One real-shape fix
  before merging: exempt state codes carry a statute suffix (`XE-11.182`), which the code pattern
  rejected; it now accepts `[A-Z0-9][A-Z0-9.-]{0,15}`. `make test` 983 pipeline + 51 web; CI
  green; merged.
- First live check, run 40575881166: 1 call, 22 s, peak 435 MB, 4.1 MB stored. Property rows
  134,553 (one repeated ID with conflicting rows, skipped); kept 90,157 (single family 79,493,
  mobile home 4,560, rural 4,519, two-to-four 936, builder inventory 649); 58 non-`R` IDs skipped.
  Living area 99.7% of single family; agrees with the `MA*` sum for 97.9%; year built 91.0%; lot
  size 60.6%; 98.4% matched to P2-01's Hays parcels. No owner, mailing, exemption or legal fields
  stored. Ungated.
- Hays spot check on esearch.hayscad.com (2026, "Total Main Area"): R163194 1,636 / 2020;
  R94307 2,763 (1,811 + 952 upstairs) / 1999; R97005 1,984 / 2000; R155475 1,374 / 2018;
  R17475 3,576 (its first improvement; Hays shows no year built, stored null). All match.
- WCAD spot check on search.wcad.org: R417015 1,379 / 2003; R098495 1,397 / 1985; R560055
  condo 2,344 / 2018; R041212 duplex 2,540 (2 × 1,270) / 1984; R009556 rural 3,740 / 1983.
  All match the stored living area and year built.

## 2026-10-27 — P2-04 Hays CAD implementation choices (Codex)

- Existing written Phase 2 approval (2026-10-25) covers Hays CAD 2/day and annual refresh.
  Add exactly `{per_day: 2}` and keep the first-live-check gate; no new budget, source,
  dependency, core/web change or map layer. Use the task's monthly export, not Orion certified.
- Count only the four read CSVs. Owner/sales `rows_by_file` values are null (header discovered),
  since even counting their rows would violate the header-only requirement. Numeric nested
  members are identified solely by headers. Decode only allowlisted cells, parsing discarded
  cells solely to recognize CSV structure; compressed nested archives use temporary seekable
  files under the download folder and are deleted even on parse failure.
- Improvement ties keep first file order; missing value ranks below observed zero. Code skips
  use the highest overall improvement's `StateCode|Type`; absent improvement is
  `(blank)|(blank)`. Count invalid QuickRefs separately. Compare duplicate rows' selected
  original strings exactly, before trimming; all extra rows increment `repeated_rows`, and
  `conflicting_ids` counts distinct permanently excluded IDs, including later identical repeats.
  Duplicate kept QuickRef digit suffixes fail closed. Preserve the suffix's exact digits,
  including any leading zeros; internal numeric PropertyID remains a separate integer.
- Sum all case-sensitive MA-prefixed segment areas across a property. Floors count their rows;
  largest measured segment's year wins, first tie, with no fallback if that year is missing/0.
  Missing numeric cells stay null; nonnumeric, negative and nonfinite selected quantities fail.
  Round money/living to whole units, MA sums to six decimals, acreage to four; zero or
  rounded-zero living/lot values are null, observed zero money/MA stays zero. Lot precedence
  is based on positive source sums before rounding; never invent a minimum lot size.
- Apply both 95% quality gates in fixture and live modes; bypass only production volumes on
  tiny fixtures. Empty denominators report null. Keep TCAD/WCAD common field names, including
  required `partial_owner: null`, the sole expected exception to an owner-key privacy grep.
  Hays A/A1 residential codes do not separate condos/townhomes, so no condo label is inferred.
- Optional parcel matching is live-only, local and report-only, using exact Hays IDs; fixtures
  never consult live canonical parcels. Summary runtime stops at finalization and peak memory
  is Linux process RSS; Claude must also check full job/serialization resources and file size.
  Annual adapter cadence is declared; automatic scheduling remains manifest-driven pending
  later publication work, consistent with TCAD/WCAD. No source calls made in development.

## 2026-10-27 — P2-03 WCAD reviewed, merged and live-checked; ungated (Claude, chat)

- PR #110 reviewed against the spec (select allowlist, four datasets only, canaries, native string
  shapes, paging and count checks); one real-shape fix before merging: the portal names an
  unaliased distinct count `count_distinct_propertyid`, so the land count now uses
  `AS count_propertyid`. `make test` 903 pipeline + 51 web; CI green; merged.
- First live check, run 40559703311: 18 calls, 113 s, peak 986 MB, 9.6 MB stored. Property rows
  323,073 / 319,443 distinct (3,630 identical repeats); kept 236,087 (single family 208,788,
  condo 12,169, rural 5,836, mobile home 4,978, two-to-four 2,337, builder inventory 1,979),
  exactly as the spec's county-wide check. Living area 99.94% of single family and condo; agrees
  with the main-area sum for 99.62%; year built 97.1%; lot size 31.8%. 99.2% of kept IDs match
  P2-01's Williamson parcels (condos included, unlike Travis). No owner, mailing, exemption or
  legal fields stored ("homestead" appears only in neighborhood and street names). Ungated.

## 2026-10-26 — P2-03 WCAD implementation choices (Codex)

- The existing Phase 2 approval covers WCAD 40/day and annual refresh. Add exactly
  `{per_day: 40, min_interval_seconds: 2}`, keep first live use gated, and add no layer,
  core/web change or dependency. Values/source-as-of are 2026-01-01; `certified` is the latest
  available property datadate date, including skipped properties. No datadate anywhere fails.
- Use native count cells `count` and, for count(distinct propertyid), `count_propertyid`.
  Page until short, including an empty last page for exact multiples. Validate the complete
  request against the fixed dataset/select/filter/order/group builder before transport.
  Ignore unselected response cells, then aggregate and clear payload lists during normalize
  to avoid keeping one canonical model per source segment/improvement.
- Duplicate comparison uses the exact selected string cells and omitted-key shape before
  trimming; every selected difference fails. Missing improvement values rank below observed
  values, including zero; first-row ties remain first. M1 remains unmapped and skipped;
  no classification is inferred from living area, consistent with the owner's decision.
- Missing source values stay null. Round money/living area to whole units, main-area sums to
  six decimals and lot acreage to four; a rounded lot/living value of zero is null. Floors
  count main-segment rows; year comes from the largest measured segment with first-row ties,
  and stays null if that segment's year is missing/zero. A missing main-area sum is null;
  an observed sum of zero is preserved. Numeric cells must be finite and nonnegative.
- The living-area gate uses the combined single-family/condo cohort; MA agreement uses stored
  values within one square foot. Empty denominators are reported as null, never 100%.
  Tiny fixtures bypass only the two production volume checks; all other checks apply.
- Keep all common TCAD field names, including `partial_owner: null`; this required null key
  is not a WCAD owner column and is the only intended owner-key exception in the live scan.
- Only live mode consults the optional local P2-01 file, matching exact Williamson quickref
  strings and reporting coverage without geometry or a match gate. Fixture mode never reads
  real canonical parcels. Runtime/memory stop at finalization; inspect full job resources and
  serialized file size in the live check. Automatic refresh remains manifest-driven pending
  later publication work, as with TCAD and parcels.

## 2026-10-26 — Owner decision: mobile homes; P2-03 spec (Claude, chat)

- **Owner decision:** TCAD's 11,744 `MH` mobile-home records stay skipped, now with the real count
  known (re-confirmed in writing). WCAD's personal-property mobile homes (`M1`) are skipped the same way.
- P2-03 (WCAD) spec written after checking the open-data portal in the browser (SOURCES, WCAD).

## 2026-10-27 — TCAD spot check on TCAD's property pages (Claude, chat)

- Five properties from live run 40425025647 checked by hand on travis.prodigycad.com (2026,
  Certified). Stored `living_area` equals TCAD's own "Main Area" and `year_built` equals the
  1st-floor segment's year for all five: 287194 (A1, 1,498 sq ft, 1999), 554861 (A1, 1,032,
  1997), 233087 (A4 townhome, 1,226 = 926 + 300, 1973), 264771 (B2, 2,379 = 1,719 + 660,
  1976), 355999 (E1, 1,285 = 1,073 + 212, 1983; land 6.8910 acres; its 140 sq ft "Sketch
  Only" segment is correctly left out). The HVAC segment equals Main Area on all five.

## 2026-10-27 — Parcels re-run without `acres` (Claude)

- Run 40425928158 (4 calls, 111 s, 1.76 GB; file 12.6 MB): Travis 386,240, Williamson 286,776, Hays
  120,445 kept (793,461), 159 points outside a block group, as before. Properties are now exactly
  county, prop_id, geo_id, block_group, tract, parcel_as_of; no `acres`. A case-insensitive search found
  no owner, mail, care, legal, exempt or acres. Merged with the owner's 2026-10-26 decision implemented.

## 2026-10-27 — P2-02 TCAD first live check passed; ungated (Claude)

- Run 40425025647 (the fourth attempt; the first three failed on real-data shapes and stored nothing,
  see the 2026-10-26 entry and #100, #101, #105): 1 call, 66 s of processing, peak memory 1.76 GB,
  stored file 19.2 MB compressed (338 MB as text). 493,324 rows read; **384,236 properties kept**
  (limit 330,000–430,000): single family 290,624, condo 54,675, builder inventory 13,043, two to
  four units 10,939, rural home 6,854, mobile home (A2) 6,006, other residential 2,095.
- Real/mobile count 453,705 vs TOTALS 453,779 (−0.02%): TOTALS counts mobile homes coded `MH`, so the
  check now counts R + M + MH. Living area on 99.67% of single-family and condo properties (limit
  97%); living area agrees with the HVAC area within 2% for 98.92% of 333,357 (limit 97%); 78
  partial-owner repeat rows merged; 19 partial-owner records kept.
- Share of kept IDs found among P2-01's Travis parcels: 85.0% overall; 99.9% of single-family
  (290,424 of 290,624) but only about 2% of condos (1,030 of 54,675), because the parcel file has no
  polygon per condo unit. P2-05 needs another way to place condos (the master lot or situs).
- **Correction for the owner:** mobile homes coded `MH` are **11,744 records (2.4% of properties)**,
  not "about 130" (an extrapolation from the first third of the file, where they are rare). They stay
  skipped for now; the owner should re-confirm that decision with the real number.
- Stored data: exactly the spec's properties, geometry empty, one `run_summary`. A case-insensitive
  search found no owner, mailing, exemption, mortgage or cap fields; the words "owner", "homestead",
  "confidence" and "mortgage" appear only in the `partial_owner` flag and in street and subdivision
  names. Five properties for the browser spot check are listed in STATUS. Ungated; gate test updated.

## 2026-10-26 — Owner decisions after the P1-12 / P2-02 review

- **Owner decision (premise corrected 2026-10-27: the real `MH` count is 11,744, not about 130):** TCAD mobile homes coded `MH` (about 130 records, usually on rented land) stay
  skipped; mobile homes recorded as real property (state code A2) are kept. The spec's R and M
  rule is unchanged.
- **Owner decision:** leave the live workflow's 30-minute job limit as is (TCAD is allowed 45);
  raise it only if a run is cut off.
- **Owner decision:** drop `acres` from the parcel record. Williamson's `GIS_AREA` is 0 for every
  parcel and Hays's totals twice the county; lot size comes from the appraisal districts (TCAD
  `land_acres`, and the Williamson and Hays tasks). The parcels adapter no longer reads `GIS_AREA`
  or `GIS_AREA_U` (rows are `[prop_id, geo_id, lon, lat]`; test added that bad area values are
  ignored). The stored file keeps `acres` until `parcels` is re-run after 00:00 UTC on 2026-10-27.

## 2026-10-26 — Fresh-clone verification; TCAD daily-budget hold (Codex)

- The requested PRs were already merged when this session started: #98 at `c9311d1`, #99 at
  `dcf644c`, followed by TCAD fixes #100/#101. Verified both original PR heads had green CI;
  no second merge or source run was needed to establish that state. Current full tests pass
  (831 pipeline, 51 web, schemas/types/build); local fixture e2e passes at both requested sizes.
- Pages deployment 40266966217 succeeded at `e1b4190`. Current main differs only in docs and
  the probe script, so the app/manifests/canonical inputs match that deployment. Direct
  github.io access is blocked by the environment; rebuilt those inputs locally without source
  calls and checked crime vs Texas 21.6/1,000, grocery walk vs three-county 32 minutes, campus
  score vs Texas 81.033, bachelor's share vs Texas 33.8%, and election margin vs Texas 13.7
  points. All five headers/legends/popup classes passed at 1440×900 and 390×844; all 4,767
  features matched an independent classification and MapLibre paint evaluation. The ACS
  MOE rule moved 375 estimates to the middle class. All 42 demographic comparisons have
  neutral palettes/wording; both directional mutations were rejected for every such manifest.
- Rechecked TCAD's exact byte allowlist, independent slice guard, forbidden-cell canaries,
  ZIP member restrictions and native fixed-width formats against the spec, including the
  already-merged blank-type and partial-owner-repeat regressions. No core/web changes made.
- Committed run log contains the two failed TCAD calls on 2026-10-26 (40265353275 and
  40266259475). The runner confirms 0 calls remaining; no successful canonical TCAD file
  exists, so live quality/resource numbers and five stored-property examples are unavailable.
  Keep the gate. No source calls/probes were made in this session. Next eligible first check:
  00:00 UTC on 2026-10-27 (19:00 America/Chicago on October 26), using the existing budget.

## 2026-10-26 — P1-12 colour by comparison reviewed, merged and checked (Claude)

- PR #98: every Rules/Tests/Other item checked. The schema validator rejects any `compare` on a
  `demographic: true` layer unless `direction` is `neutral`; all 44 ACS and election layers are
  demographic and neutral, and only the crime, access and school layers (15) are directional.
  `make test` (759 pipeline, 51 web) and the e2e at both sizes pass; CI green; merged.
- Live-data check on a local build of the deployed site (`mm publish` + `vite build` on the
  committed data, because the agent sandbox cannot reach github.io): the five layers' legends,
  headers, colours and popup class labels agree with an independent classification of every area,
  including the margin-of-error middle class (ACS) and grey for missing areas. No score, rank or
  filter uses the classes. Two cosmetic header nits are in STATUS.

## 2026-10-26 — P2-02 TCAD reviewed and merged; first live check fixes (Claude)

- PR #99 reviewed against the spec: the parser slices only the listed byte ranges (a test fails on
  any other slice and on any whole-line decode), canaries sit in the owner, mailing, confidential,
  exemption and qualify-year ranges and in unused members, record lengths 9,922/114/622/50/2,491,
  CRLF, 4 implied decimals, zero-padded IDs and MM-DD-YYYY dates match the spec; 828 tests; merged.
- The fixtures missed two real shapes, found by live runs and counts-only probes (the agent cannot
  call the source itself): (1) one `IMP_INFO` row has a blank `imprv_type_cd` (run 40265353275 failed
  in 4 s) — it is now a dwelling improvement, as the spec's rule says (#100); (2) `PROP.TXT` repeats
  a property on adjacent rows when `partial_owner` is T with the same `udi_group` (run 40266259475
  failed in 33 s) — the first row is kept and the rest are counted as `repeated_rows`, and any
  other repeat still fails (#101). The adapter now reports its own static failure message (never
  source text) so a failed check says which check failed.
- Probes (40265498631, 40265585555, 40265679662, 40266384937, 40266455000, 40266597630): layout
  and lengths match the spec; no orphan segments; cell shapes as expected; about 84% of rows would
  be kept (about 380,000 properties); mobile homes are coded `MH`.
- Both of 2026-10-26's two `tcad` calls are used. Run again after 00:00 UTC on 2026-10-27.

## 2026-10-25 — P1-12 comparison display choices (Codex)

- The comparison's MOE rule reads `moe_field` from the existing popup row matching
  `compare.field`; no duplicate manifest setting is needed. It includes both endpoints of
  the area's interval, ignores a null MOE, and does not combine the benchmark's MOE.
- Election lead wording follows the existing canonical convention: a percent-formatted
  `*_margin` field with comparison unit `pts` is a Republican-positive margin. This selects
  the specified Democratic/Republican shift labels without naming a layer ID in app code.
- A variant family's choice is stored under each member's layer ID in the existing version-1
  share-link format. Changing either variant updates the family; an unavailable geography
  falls back to Values for that member. Selecting a geography in Values mode enters
  Compared with; pressing Compared with again keeps the current geography.
- Palettes, cut points and legend wording follow the task. The middle legend adds the
  specified margin-of-error note whenever the matching popup row declares an MOE field.
  Comparison classes remain display-only; filter and comparison-table calculations are unchanged.

## 2026-10-25 — P2-02 TCAD implementation choices (Codex)

- The Phase 2 owner approval already covers TCAD 2/day and annual refresh. Add exactly
  `{per_day: 2, max_minutes: 45}`, keep first live use gated, and add no layer or core/web code.
  Source-as-of is 2026-01-01 (the value date); certified date is separately 2026-07-18.
- Decode only the allowlisted fixed-width cells as Latin-1, never a whole line. Also enforce
  the verified ABS_SUBD/TOTALS record lengths (50/2,491), accept CRLF/LF/final unterminated
  records, and reject duplicate property/improvement keys, conflicting subdivision names,
  missing improvement links and mixed improvement years rather than guess.
- Floor count and year selection use the seven floor codes; FBSMT/RSBLW contribute living
  area only. Ties use first source order. A positive living sum determines a dwelling and
  coverage; no area yields null. An ADU improvement sets has_adu even without a measured
  area. Missing monetary components make the sum null, never an invented zero.
- The 97% living-area check uses the combined single-family/condo cohort. HVAC agreement
  compares the stored sums within 2% of living area. Only living_area is rounded to whole
  square feet as specified; ADU/HVAC sums retain six-decimal source precision. A zero comparison
  denominator is reported as null (never 100%); the count denominators are included.
- Subdivision names follow P1-02c title/small-word casing but preserve the source's plat
  qualifiers, since these are property facts. Situs display joins the supplied address
  pieces in number/prefix/street/suffix/unit/city/ZIP order, omitting blanks.
- Only live mode consults the optional local P2-01 canonical file (streamed, Travis only,
  numeric ID padding normalized). Fixture mode never consults real parcel data. Only the
  production kept-volume check is bypassed for tiny fixtures; all other quality checks apply.
- `partial_owner` is the explicitly required property-share boolean, and its audit count is
  also required. These two names contain “owner”; the live privacy scan should allow these
  exact safe fields and find no owner identities, mail or exemption fields/values. No change
  is made to the core publication privacy guard; this task is canonical-only for P2-05.
- Run-summary runtime/memory stop at finalization, as in P2-01; Claude must also inspect
  complete job runtime, memory and serialization size. Annual cadence is declared by the
  adapter; automated refresh remains manifest-driven pending later publication work.

## 2026-10-26 — Owner approvals: P1-12 and P2-02 scope

- **Owner approval:** P1-12 colours demographic (ACS) and election layers by comparison too,
  with neutral colours and "lower/higher than" wording only, never better/worse
  (`docs/tasks/P1-12-colour-by-comparison.md`, rule 2).
- **Owner decision:** P2-02 covers TCAD 2026 values only; no 2025 values for now.

## 2026-10-26 — P1-11 comparisons reviewed, merged and live-checked (Claude)

- PR #82 reviewed against the spec (705 pipeline + 41 web tests, e2e at 1440×900 and 390×844, CI
  green) and merged. The owner's budget approvals for P1-11 are recorded once, in the
  "Owner approvals: P1-11 budgets; Phase 2 plan" entry (a duplicate by Codex was removed).
- Live runs (one at a time, inside budgets; `access` and `elections` waited for the next UTC day
  because their daily calls were used up on 2026-10-25): dps_agency 40232299790 (Texas 21.6 /
  3.4; Texas cities over 100,000 25.3 / 4.1), acs 40232390317 (income US 80,734, Texas 78,476,
  Austin 93,658; 21 measures × 8 geographies), apd 40232586636 (32.7 / 3.7 per 1,000; density
  102), schools 40232775313 (campus mean 81.0, 59.5% A or B; district 80.0, 55.7%), access
  40248194811 (walk to grocery 32 min, bike 10; walking basket median over 60 min so no
  reference; transit 0 trips/hour), elections 40249589136 (2024 Democratic 42.4%, Republican
  56.1%, turnout 61.3%; 2020 46.5% / 52.0% / 67.0%), fbi_national 40249786937 (see its entry).
  Existing records were unchanged by each run except the newer OSM date and three values in
  access. Nothing was edited by hand.
- Combined `benchmarks.json`: 7 sources, 199 records, not test data, no personal fields.

## 2026-10-26 — P2-01 parcels first live check passed; ungated (Claude)

- Run 40250516420: 4 calls, 116 s runtime (limit 30 min), peak memory 1.8 GB, stored file
  13.9 MB compressed (244 MB as text; limit 100 MB). Kept unique IDs: Travis 386,240,
  Williamson 286,776, Hays 120,445 (793,461 in all), exactly the expected counts. Records
  read 386,752 / 287,194 / 121,110, matching the spec; skipped and merged counts match too
  (Travis 407 "0" and 46 repeated IDs; Williamson 132 blank and 284 repeated; Hays 257 blank,
  292 "0" and 100 repeated). 159 points (0.02%) fall outside every study block group
  (Travis 144, Williamson 10, Hays 5). `DATE_ACQ` 2026-07-01 (Travis, Williamson) and
  2026-02-01 (Hays); `TAX_YEAR` 2026. Stored properties are exactly county, prop_id, geo_id,
  acres, block_group, tract, parcel_as_of; all geometry is Point. A case-insensitive search of
  the stored file for owner, mail, care, legal, mkt, exempt and homestead found nothing.
- **Acreage is not reliable in this source; do not use `acres` yet.** Williamson's `GIS_AREA` is
  0 for all 286,776 parcels, and Williamson parcels also have no `GEO_ID` (Travis 6,633 and
  Hays 959 lack one). Hays acres total 870,356, about twice the county's land area. Travis
  (611,641) looks right. Nothing planned needs it: the CAD tasks take `land_acres` from the
  appraisal files. Owner decision needed: drop `acres` from the parcel record, or publish it as
  "not available" where the source is 0 (a follow-up fix, then one re-run).
- One Williamson property ID is the text "PRIVATE ROAD" (not a real property ID); P2-04 should
  ignore IDs that do not match the WCAD pattern.

## 2026-10-25 — P2-01 parcel-base implementation choices (Codex)

- Phase 2 and parcels 6/day are already approved in the owner's 2026-10-25 entry below.
  Add the specified five-second pacing and 30-minute cap; keep first live use gated.
  No map or non-map manifest is added. Annual cadence is declared by the adapter; the
  map-manifest-driven scheduler will include the source only with later publication work.
- Trim IDs but preserve case/leading zeros; skip only blank and exact "0". Use the first
  nonblank GEO_ID in DBF order. Count a GEO_ID conflict once per property; distinguish
  repeated properties from extra merged records so read/kept/skipped counts reconcile.
- Scan only selected DBF attributes first, retaining shape indices; read/union geometry
  one property at a time. This avoids keeping every parcel polygon in memory. Unselected
  fields are never unpacked/decoded. Raw retention/recording remain off; all downloaded
  archives and extracted components are temporary and gone before fetch returns, even
  on errors. Failed payloads suppress an automatic second large download.
- The task's compact response has one acquisition date per county, so require DATE_ACQ
  to be constant as well as TAX_YEAR (including skipped-ID rows). A mixed-date delivery
  fails instead of silently replacing per-property dates with the county's newest date.
  Records retain the county date; source_as_of is the latest date across the three counties.
- Repair only invalid source polygons, retain polygonal parts, and compute the point on
  the unsimplified EPSG:5070 union. Sum source GIS_AREA (Acres), then round to three decimals;
  do not substitute geometric acreage. WGS84 point coordinates use six decimals.
- Block-group covers includes boundaries; choose the smallest GEOID when several cover a
  point. Cross-county matches are valid. The 99% check is global across kept points and
  applies to fixtures too; tiny fixtures bypass only the production per-county 2% count
  guard. The tests exercise both thresholds without constructing large synthetic datasets.
- The non-spatial count-only audit follows APD and is included by live_summary; runtime
  includes downloads/parsing/assignment, and peak memory is the process high-water mark
  at finalization. The runner then validates/serializes records; check complete job resources
  too in the live run.
## 2026-10-26 — P1-11 FBI national check passed; ungated (Claude)

- First run 40232207700 (2025: violent 3.3, Part I 18.8 per 1,000) was held back: probe run
  40232292906 showed the summarized property series `P` includes arson exactly (P 5,174,662 =
  burglary 650,580 + larceny 3,824,966 + motor vehicle theft 666,315 + arson 32,801). DPS Part I
  excludes arson, so the adapter now also reads `ARS` (3 calls a run, inside the unchanged
  4/day budget) and uses violent + (P − ARS) (PR #86).
- Re-run 40249786937: 3 calls; US 2025 reported offenses: violent 3.3, Part I 18.7 per 1,000.
  Ungated. Only the first run's log line was merged (#90).
- A live run of a layer with `publish: none` made the web test "fixture builds are labeled
  Test data" fail (freshness comes from the run log); that test now checks published layers only.

## 2026-10-25 — P1-11 implementation choices (Codex)

- Benchmark validation/publication lives in `mm/benchmarks.py`. The adapter's safe benchmark
  records are also written per producer under ignored `web/public/data/benchmarks/`, so an
  independent fixture/live run replaces only its own comparisons. `benchmarks.json` merges
  those publications in the specified geography order, with a global fixture flag; both
  inline comparisons and the page banner say Test data whenever that flag is true. Existing
  canonical data without benchmarks produces no comparisons until that adapter is refreshed.
- Two optional popup-manifest fields, `benchmark_field` and `benchmark_format`, distinguish
  campus/district school statistics and display the A-or-B share as a percentage. Those
  benchmark field keys are `campus_overall_score/rating` and `district_overall_score/rating`;
  the geography label says "Texas (A or B)" for the share. The local rating is unchanged.
- A benchmark's optional `display` preserves a Census capped median as a range. A peer
  average requires all twelve finite, uncapped values; otherwise it is omitted. Missing
  peer populations or populations outside the chosen band warn without failing. The average
  is not a pooled median and its note lists all twelve cities; MOE remains null.
- FBI declares a benchmark target namespace (`benchmark_source = "dps_agency"`); a non-map,
  annual manifest lets the existing scheduler include it after ungating. Non-published
  metadata stays on Sources and is omitted from map toggles. Count each series
  over all twelve months and divide by its own mean participating population, then sum V/P
  rates for Part I. The first live check must verify P's arson definition before ungating;
  no separate arson series is added. Credentials stay only inside transport; errors withhold
  the URL and response, as in ACS.
- APD area rates use raw totals over eligible (at least 100 residents) area populations;
  density uses all APD-area counts and area. The comparison note identifies the combined raw
  method; no other crime source or peer city is attached to APD. DPS also supplies its own
  Austin PD jurisdiction rate, so the popup's Austin comparison uses the same DPS definition.
- Elections accumulate statewide totals while streaming the same four CSV members, before
  county filtering and before precinct suppression. Only native Party/Votes and TotalVR/TotalTO
  aggregate tables survive in the compact statewide response; dropped columns still never
  survive parsing. The existing three-county precinct checks remain unchanged.
- Popup lines use the specified four geography priorities; sources with none of those (access)
  show their available three-county comparison. Hover details and the comparison column show
  every available geography, MOE, period, source and note. Jurisdiction comparisons remain at
  the existing interior-point check; precinct votes are never joined to comparison block groups.
  No ranking, sorting, colour mode or benchmark direction was added (P1-12 stays separate).


## 2026-10-25 — P1-07 access live check passed; ungated (Claude)

- Run 40146625568: 4 calls, 11 min, peak memory 4.4 GB. OSM (Geofabrik 2026-10-23): walk graph
  2.92 M nodes, bike graph 1.99 M; destinations in the study area include 215 grocery, 1,415
  park, 752 school, 71 library. 21,924 populated blocks, 97.4% snapped. CapMetro feed
  261007_1345, service date 2026-10-28, 2,346 stops, 4,832 trips.
- Medians across block groups: walk to grocery 23 min, park 9, school 15, daily-needs basket 41
  (the basket is the slowest of five errands; libraries and hardware stores are sparse);
  bike to grocery 8. Transit median 0 departures/hour (most of the area has no CapMetro
  service); downtown about 73. Spot checks (Hyde Park, Downtown, Bouldin Creek, Circle C,
  Belterra, Steiner Ranch) are plausible.
- Caveat for the methodology page: OSM may miss some stores (215 groceries for three counties
  looks low), which would make some walk times longer than reality.
- `access` ungated.

## 2026-10-25 — P1-02c live: name polish published (Claude)

- Run 40146023339: 24 calls. No all-capital planning-area names remain (MLK, MLK-183, RMMA and
  UT kept as acronyms); no "Crk" or "Ests". WCAD-named block groups rose from 68 to 76 because
  abbreviated and spelled-out names now merge; Census place 633, Austin planning area 343,
  City of Austin subdivision 109, Hays County subdivision 18, fallback 27. Plain "Austin": 181.

## 2026-10-25 — Election results by precinct: owner approved adding; spec P1-10 (Claude)

- **Owner approval (2026-10-25, "Yes please add it"):** add general-election results by voting
  precinct as a context-only layer.
- Source: Texas Legislative Council Capitol Data Portal, CC BY (checked 2026-10-25): 2024
  general VTD election data (82 MB zip; 2020 and 2024 results on 2024 precincts) and 2024 VTD
  shapes (47 MB). Both reachable from GitHub (probe). Texas has no party registration.
- Treated like demographics: `demographic: true` (under "People (context only)", never a score
  input); precinct grain only, never apportioned to block groups; vote counts hidden where a
  precinct has under 50 votes; `SpanishSurnamePercent` and `TotalPop` never stored.
- **Pending owner approval:** budget `elections: {per_day: 4, min_interval_seconds: 5,
  max_minutes: 15}`, refresh annual (2 calls a run); new dependency `pyshp` (free, MIT).

## 2026-10-25 — Display fixes and TEA district ratings (Claude; owner requests)

- Austin PD layers: new violent-rate layer (breaks 1/2.5/5/10 per 1,000). Areas with
  100–999 residents get a note that shops, offices or hospitals can make per-resident rates
  look high (125 areas; added after smoothing, so rates are unchanged). Of the 36 areas at
  100+ per 1,000, 34 are mostly property crime. APD re-run 40152158630 (4 calls) to carry the
  note; totals unchanged (88,424).
- Empty note rows are hidden (`PopupField.hide_if_empty`) instead of showing "Not available".
- Campus ratings use distinct colours (A–F blue to red; not rated is a hollow grey ring).
- TEA district ratings: the 2024–25 release (`nui6-x374`) has 1,208 district rows, which the
  schools request had filtered out. Now requested in the same call (no budget change). Run
  40152646647: all 24 districts with campuses in the three counties rated (A 3, B 8, C 9,
  D 4); 7 edge districts based outside the counties show "No TEA district rating found".
  New layer `school_district_ratings`.

## 2026-10-25 — Owner approvals: P1-11 budgets; Phase 2 plan

- **Owner approval (2026-10-25):** `acs` budget 30 → 40 calls a day (still about one run a year;
  the cap leaves room for retries within that run) and the new `fbi_national` source (4/day,
  annual). The owner created the FBI key and saved it as the Actions secret `FBI_API_KEY`;
  probe run 40226938290 confirmed the documented API (2025: violent 1,098,778 reported
  offenses, 3.30 per 1,000; property 15.52 per 1,000).
- **Owner approval (2026-10-25): Phase 2 starts** as planned in `PLAN.md` ("Phase 2 plan"),
  including its call budgets: `parcels` 6/day, `tcad` 2/day, `wcad` 40/day, `hays_cad` 2/day,
  `fhfa_hpi` 2/day, `hmda` 6/day. Each task still gets a spec before it is built.
- P2-01 spec written after re-checking StratMap 2026 in the browser: WGS84, `DATE_ACQ`
  2026-07-01 (Travis, Williamson) and 2026-02-01 (Hays); Williamson IDs like `R070302`; blank,
  "0" and repeated IDs handled as specified.

## 2026-10-25 — Comparisons spec (P1-11) and Phase 2 plan (Claude; owner said yes to both)

- **Owner (2026-10-25):** yes to the comparisons idea and to planning Phase 2. The Phase 2 plan in
  `PLAN.md` still needs the owner's approval before any Phase 2 task is built.
- Comparisons (spec `docs/tasks/P1-11-benchmarks.md`), checked 2026-10-25:
  - Census ACS `ucgid` returns US, Texas, three counties, Austin metro (`310M700US12420`),
    Austin city and 15 large cities in one request (probe). Peer cities: the 12 US cities with
    700,000–1.5 million people (ACS 2020–2024). About 4 extra ACS calls a year.
  - DPS report 633 gives Texas statewide rates per 100,000 (2025 Part I ≈ 21.6 per 1,000).
  - FBI Crime Data API has 2025 national reported offenses (violent ≈ 3.3 per 1,000). The FBI
    asks users not to compare places with each other except city to state and state to nation,
    so crime compares with Austin, Texas and the US only, never peer cities.
  - **Pending owner approval:** `acs` budget 30 → 40/day; new `fbi_national` budget 4/day,
    annual; the owner creates a free api.data.gov key and saves it as the Actions secret
    `FBI_API_KEY`.
- Phase 2 sources re-checked: FHFA purchase-only HPI for the 100 largest metros (Austin included,
  quarterly through 2026 Q2); HMDA 2025 released 2026-06-23.

## 2026-10-25 — Phase 1 closing review (Claude)

- Reviewed the site with every real layer (63 layers, all current) in Chromium at 1440×900 and
  390×844: no page or console errors; filters, compare, shortlist, share links pass the smoke test.
- Fixes: the selected-area card is now a compact strip at the top of the map (it covered the
  "What's here?" popup); on phones a map tap folds the tools sheet so the popup is visible; the
  People note now covers election results; election margins read "Harris +61.8 pts" instead of
  a signed percentage (`pres_<year>_lead`, needs one elections re-run).
- Methodology page updated: violent rate and the under-1,000 note, agency-wide safety, district
  ratings, access, election results, and the monthly refresh with its publish checks.

## 2026-10-25 — P1-10 live check passed; `elections` ungated (Claude)

- Review fix before merging (PR #74): the real `VTDs_24PG.dbf` stores `VTDKEY` as a float field,
  which the adapter rejected; it now accepts whole-number floats, and a test runs a parsed
  shapefile with real field types through normalisation.
- Run 40161817419: 2 calls, 43 s, peak memory 114 MB. 553 precincts (Travis 300, Williamson
  166, Hays 87). 2024 President: D 612,262, R 384,529, other 22,507; 2020: D 637,693, R
  347,584. Registered 2024 1,564,474, ballots 1,024,839. Precincts under 50 votes: 27 (2024),
  28 (2020); one 2020 precinct has ballots above registration (turnout hidden). All match the
  source file checked in the browser. No `SpanishSurnamePercent` or `TotalPop` in stored data.
- `elections` ungated; refreshes annually.

## 2026-10-24 — Owner approvals: P1-10 elections

- **Owner approval:** `elections: {per_day: 4, min_interval_seconds: 5, max_minutes: 15}`,
  refreshed annually, approved in writing in the owner's P1-10 build request. A normal
  run downloads two files; live use stays gated awaiting Claude's first live check.
- **Owner approval:** add `pyshp>=2.3,<3` (MIT, pure Python) to read TLC's precinct shapefile,
  approved in writing in the same request.

## 2026-10-24 — P1-10 implementation choices (Codex)

- Tiny fixture mode bypasses only the production precinct-count and 2024 party-total guards;
  all field, join, duplicate, count, geometry and suppression checks still apply. Live mode
  always enforces 553 ± 30 precincts and both verified party totals within 1%. Tests exercise
  these checks separately and in a full-size synthetic run.
- Count a return once per year/precinct/party/candidate; multiple named write-ins are allowed.
  Require exactly one D and one R candidate row per precinct/year, even for a zero-vote
  precinct, so missing rows cannot silently become zeros. Store numeric VTD keys as canonical
  text while preserving original VTD labels. Compute margin from unrounded shares, then
  round all final ratios to three decimals with Python's nearest-even rounding.
- Prefix suppression/turnout notes with their year; combine them in `election_note`. Candidate
  names remain visible when vote values are suppressed. Zero registered voters with zero
  ballots has null turnout; any ballots above registration also gets the specified note.
- Use the latest election's date, 2024-11-05, as `source_as_of`, with TLC's 2020-to-2024
  re-tabulation explained in `source_note`. Source archive modification dates remain in SOURCES.
- Repair invalid source precinct polygons with `make_valid`, retain polygonal parts, then use
  the areas adapter's EPSG:5070 5 m simplification and six-decimal WGS84 display coordinates.
  Invalid/collapsed rounded display geometry fails. Read source projection from `.prj`.
- Temporary archives/extracted components are always deleted. Return a failed payload on
  download/parse errors to avoid the core's automatic second large download. Only safe
  selected fields survive CSV parsing; raw retention and recording are off. The count-only
  canonical audit follows APD and adds runtime/peak memory, also displayed by live_summary.

## 2026-10-24 — P1-05b live check passed; `dps_agency` ungated (Claude)

- First run 40108168966 failed safely after 1 call: real ORIs can contain letters
  (`TXDPD0000`, `TX227289E`); fixed in PR #60. Run 40108617517: 5 calls, 25 s. Both runs'
  calls are in the run log (6 of 10 today).
- 2025 data: 28 agencies and 25 places matched; 1,206 block groups: Austin PD 604, Travis
  County SO 125, Williamson County SO 106, Hays County SO 62, Round Rock 59, Georgetown 46,
  Cedar Park 44, Pflugerville 34, San Marcos 34, Leander 22, Kyle 16, Taylor 12, Lakeway 10,
  Hutto 9, others 1–5. Six block groups are split between agencies (not available).
- Austin PD: 35,685 Part I on 1,000,639 people = 35.7 per 1,000, as expected. Rates run from
  5.3 to 344.4 (Sunset Valley: 604 residents and a retail centre; the small-population note
  shows on 7 block groups).
- Six small-town police departments get no block group (Florence, Granger, Jarrell, Liberty
  Hill, Mustang Ridge, Thrall): each town is under half of every block group it touches, so
  those areas show their county sheriff's rate. This follows the spec's 50% rule; the popup
  names the agency and its share.
- Zero-population agencies (schools, universities, transit, constables) total about 1,660
  Part I offenses, the largest UT Austin PD (945); kept in the run summary only.
- `dps_agency` ungated. It refreshes annually through the monthly refresh.

## 2026-10-24 — Owner approvals: P1-05b DPS agency safety

- **Owner approval:** `dps_agency: {per_day: 10, min_interval_seconds: 2}`, refreshed
  annually, approved in writing in the owner's P1-05b build request. A normal run is five
  calls; live use remains gated awaiting Claude's first live check.
- **Owner approval:** publish the DPS UCR portal's agency figures as public government data
  with no stated license, credited to the Texas Department of Public Safety, under the
  owner's Q1 rule. Approved in writing in the same request; the layer leaves `license`
  empty so the site says "No license stated".

## 2026-10-24 — P1-05b implementation choices (Codex)

- If multiple cities qualify at half area, assign the greatest unrounded share, then
  ascending ORI for an exact tie. City priority over sheriff and the spec's 1e-9 tolerance
  remain unchanged. All counts and rates remain the entire agency's figures.
- The first workbook sheet is the agency table; preserve legend sheets in the parsed
  payload but do not treat them as agency records. Strict column matching recognizes the
  two specified assault/auto-theft spellings and whitespace/hyphen variants. Numeric text
  may have valid thousands separators or an integral decimal; blanks fail rather than zero.
- A separate non-spatial canonical `run_summary`, count-only stderr note, and
  `tools/live_summary.py` support persist the audit without changing pipeline core, as in
  APD. Per-agency block-group counts include all 28 ORIs, even those assigned no block groups;
  unmapped agencies retain violent/property/Part I and portal-total counts only, keyed by ORI.
- The required manifest description names 2025; it needs a prose update at the next annual
  review. Record-level year, period, retrieval and source-as-of dates are computed each run.

## 2026-10-24 — P1-05b: DPS agency data format checked; spec written (Claude)

- The *Crime in Texas 2025* PDF has agency tables for the Top 25 only. Every agency is in the
  DPS UCR portal's "Index Crime by Agency" reports, which download as XLSX (details in
  `SOURCES.md`). All 25 city police departments and 3 sheriffs covering Travis, Williamson and
  Hays are present for 2025; cities without a police department in DPS's data (e.g. Dripping
  Springs, Wimberley, Webberville, The Hills) fall under the county sheriff.
- The portal returns HTTP 500 to our standard user agent from GitHub; `Mozilla/5.0
  (compatible; metro-mapper/0.1 (+…))` works and still names the project. Used for this source only.
- Design (spec `docs/tasks/P1-05b-agency-safety.md`): one agency-wide rate per agency, shown on
  every block group it covers (≥ 50% in a city → that city's PD; ≥ 50% outside all PD cities →
  sheriff; otherwise not available). Never apportioned. Austin PD included on the same basis.
- **Pending owner approval:** budget `dps_agency: {per_day: 10, min_interval_seconds: 2}`,
  refresh annual (5 calls a run); and publishing the portal's figures under the Q1 rule
  (no stated license, credited).

## 2026-10-24 — P1-09 monthly refresh and validation (Claude)

- `refresh.yml` runs at 09:15 UTC on the 3rd of each month, the schedule proposed in the P1-09
  outline and approved with Phase 1. No budget or cadence changes: each adapter uses its own
  approved budget and each layer its approved `refresh` (monthly: FEMA, APD, access; annual:
  areas, ACS, schools). Manual runs default to a dry run with no source calls.
- "Due" now means the last live success is at least 25 days old (monthly) or 350 days
  (annual), instead of 30 days less 12 hours. With a run on the 3rd, the old rule skipped
  March (Feb 3 to Mar 3 is 28 days). This keeps the approved monthly cadence; it does not make
  refreshes more frequent.
- The workflow commits the run log and report to `main` every run, and stored data only when
  all hard checks pass; otherwise `data/canonical` is restored and the previous month stays
  live. It then starts `pages.yml`, because pushes made with the workflow token don't trigger
  other workflows. Direct data commits to `main` are the refresh's job (PLAN: "publishes");
  code still goes through PRs.
- APD's run summary gains "reports in block groups outside APD area" so the published
  block-group counts can be reconciled exactly against APD's independent total. That check
  is skipped until APD's next refresh stores the new count.
- The H3 stability check uses the property each non-demographic block-group layer colours by,
  hexagon overlap-weighted means and Spearman ≥ 0.8 (soft). New dependency: `h3` (free).
- First scheduled run (2026-11-03) will find nothing due (FEMA and APD ran 2026-10-23), so
  FEMA and APD refresh on 2026-12-03. Between about 2026-11-27 and 2026-12-03 the site will
  label them "stale" (35-day freshness window). One-time; accepted rather than refreshing
  early.
- Open question for the owner, not changed: the P1-02 spec says areas are "yearly (names
  monthly)", but the approved layer manifests say `refresh: annual`, so names refresh yearly.

## 2026-10-23 — Owner approvals: P1-07 access budget and ODbL

- **Owner approval:** `access: {per_day: 6, min_interval_seconds: 5, max_minutes: 25}`,
  refreshed monthly, confirmed in the owner's P1-07 build request. A normal run has four
  requests. The first live run remains gated for Claude's check.
- **Owner approval:** publish access values as a derivative database offered under
  **ODbL 1.0**, as explicitly approved in the P1-07 build request. Retain OpenStreetMap
  attribution, identify the derivation and make the derived values available on those
  terms. CapMetro's GTFS retains its CMTA Open Data License and attribution; Census inputs
  are public domain. Do not characterize the output as only a produced work to avoid the
  database share-alike obligation.

## 2026-10-23 — P1-07 access implementation choices (Codex)

- Tiny fixture mode bypasses only the production minimum volumes (100,000 walk nodes,
  50 study-area groceries, 1,000 stops/active trips, 20,000 populated blocks). Native schema,
  identifier, routing and 95% walking-snap checks remain active. Live mode always enforces
  the volume guards. Tests also exercise that distinction without live source calls.
- Walking/biking use undirected great-circle edges. Bike starts with the task's walking
  base, then applies its extra exclusions. Repeated edges take their minimum length rather
  than summing. Snapping is EPSG:5070, with a 1e-7-metre numerical tolerance at 300 m;
  snapped connector distances are not added to network times. Unreachable blocks contribute
  61 destination minutes and zero accessible CapMetro trips.
- Use the lower population-weighted median at an exact half-weight tie, avoiding interpolation
  of the 61 sentinel. Round final minutes to nearest-even whole numbers; transit is the median
  distinct-trip count divided by two. Per-measure notes distinguish capped values from finite
  values; `access_note` summarizes them. No populated blocks means nulls, never invented zeros.
- A Wednesday with any type-2 calendar removal is skipped as a holiday candidate; type-1
  additions apply on the selected date. Feed version is read from the ZIP's `feed_info.txt`
  when available and otherwise stays null. All routes count, and trips at several nearby stops
  count once per block. Stop searches hold one bounded distance vector at a time.
- Stream OSM with pyosmium's node/way callbacks, storing only bbox nodes, then compact to
  used nodes. Require node-before-way ordering, split ways at missing/outside refs, and
  ignore point parks with no measurable area. Park ways need 0.1 ha and add all boundary
  vertices. Destination ways crossing the clipping boundary cannot supply a complete vertex
  centroid and are ignored. No OSM relation destinations are added beyond the specified
  nodes/ways contract. Raw PBFs are deleted before fetch returns; OSM failures prevent a second
  core retry/download. Routing and extraction check the same 25-minute deadline.
- The unchanged adapter contract cannot append saved run notes. Print count-only notes and
  retain a separate canonical `run_summary` audit record, as in APD, with runtime and peak RSS.
  `tools/live_summary.py` displays it; map manifests select only block-group records. The layer
  as-of date is Geofabrik's Last-Modified date, with GTFS version and service date shown separately.
- pyosmium is imported only by the live-file parser. It is declared as a dependency and CI
  exercises a tiny native OSM file; offline local development can run compact fixtures without
  downloading the parser. The parser-specific test skips locally if it is not installed.

## 2026-10-24 — P1-02b live: better names published (Claude)

- Run 40044207313: 24 calls. 1,206 block groups named: Census place 641, City of Austin
  neighborhood planning area 343, City of Austin subdivision 109, WCAD subdivision 68, Hays
  County subdivision 18, fallback 27. Plain "Austin" names fell from 256 to 182.
- Spot checks read well ("Circle C Ranch", "Avalon", "Belterra", "Plum Creek", "Santa Rita
  Ranch"). Follow-ups for a later small task: planning-area names arrive in capitals ("NORTH
  AUSTIN CIVIC ASSOCIATION"); WCAD abbreviations such as "Crk" stay as given.

## 2026-10-24 — ACS published and ungated (Claude)

- Run 40043682058: 26 calls, 1,206 block groups and 471 tracts. Plain-language notes in place
  ("Census: too few survey responses to estimate" on 605 values); capped medians show ranges
  ("$250,000 or more" ×40, "$3,500 or more" ×29, "$2,000,000 or more" ×9, "2020 or later" ×8,
  "1939 or earlier" ×3, "$10,000 or less" ×1). `acs` ungated.

## 2026-10-23 — P1-02c name-polish details (Codex)

- A digit protects its entire whitespace-delimited planning-area token before hyphen
  casing; otherwise hyphen parts are cased independently, preserving `MLK` and applying
  `Mc` prefixes. Subdivision small words are lower case after the first lexical word,
  including within hyphenated names; the first word stays capitalized.
- WCAD reuses Austin's parenthesis scanner, including nested and truncated annotations.
  Strip annotations before removing repeated trailing plat qualifiers, using Austin's
  identifier grammar. Keep an ordinary word after `Sec`, and keep a non-trailing
  `Sec 1 West`; preserve numbered base names such as `Ranchettes #4`. Abbreviation
  expansion is limited to whole words in WCAD names. Hays keeps its existing qualifier
  behavior; all three subdivision sources get the small-word rule.
- Apply the polish during normalization, before the existing name-group union and share
  tests. Synthetic native-field fixtures exercise a planning name in capitals and WCAD
  spellings that combine to 45% only after polishing. No source, budget or coverage-rule
  changes; Claude checks the live output.

## 2026-10-23 — P1-08 filters and comparison choices (Codex)

- Identify named base areas by registry semantics (`join: block_group`, polygon geometry,
  a `name` popup field), never a layer id or source id. Filters and comparison use only
  block-group variants; no tract-to-block-group interpolation. Future eligible layers join
  automatically. Cache each local publication URL once for map, filters and comparison;
  load on demand, and never request a data-source API from these controls.
- Active numeric filters intersect inclusive ranges. A missing/non-finite value excludes
  the area; each missing count is measured against all loaded base areas independently of
  other filters. Disabled filters have no effect. Native shared-track range handles have
  exact numeric inputs; percentage values are converted from shares to percentage units.
  Observed bounds initialize the controls, and exact inputs may extend those bounds.
- People (context only) appears last, with the task's neutral wording, in filters, layers,
  comparison, sources and map inspection. People controls start off and collapsed; an
  explicitly shared or saved layer choice can restore them. No sorting control, ranking
  or combined score is added. Comparisons preserve the user's area order and reuse the
  popup formatter, including MOE, reliability, annotations, capped values and safe links.
- Jurisdiction context uses a scan-line interior point, avoiding holes and concave-boundary
  centres; only already-loaded jurisdiction polygons are queried. Show their name and
  link fields, with source/date, without assigning schools or attendance zones.
- The shortlist and free-text notes use the existing browser store, with a session-memory
  fallback for blocked storage and failed writes (including quota errors). Clearing a note
  preserves its saved area. Shortlist comparison takes the first four in saved order.
- Share links use versioned JSON in `#/?v=...`, explicitly allowing only camera, visible
  layer ids, geography choices, numeric filter bounds and up to four comparison GEOIDs.
  Notes, names and shortlist state are never serialized. Invalid/unknown registry choices
  are ignored. Existing page routes remain usable, and navigating between pages keeps the
  workbench mounted so private session state is not lost.
- At phone widths the tools are a collapsible bottom sheet with four tabs; comparison
  cells repeat area labels in a two-column grid rather than overflowing the page. Desktop
  comparison uses a native modal table with one column per selected area.
- Methodology is a text-only heading/paragraph Markdown subset, with no raw HTML rendering.
  Two `Claude: check` comments remain in the draft for naming wording and the APD explanation.
  Access-method text explicitly waits for P1-07 instead of inventing an unbuilt method.
- Local `npm run e2e` uses Python Playwright and preinstalled Chromium against a fixture
  `vite preview` build. External browser requests are fulfilled locally with a plain map
  background; no data sources are contacted. Screenshots cover 1440×900 and 390×844. The
  smoke runner and browser dependencies are not added to CI.

## 2026-10-23 — P1-05 merged; APD live check passed (Claude)

- First run 40041187416 failed (nothing published): TIGER's Austin city polygon is
  self-intersecting as served; now repaired with `make_valid` (PR #37).
- Run 40041503825: 4 calls. Period 2025-10-01 to 2026-09-30: 88,424 reports (464 without a
  block group); block-group counts sum exactly to the total. 712 block groups with reports
  (1 out-of-county code); 605 block groups in the APD area (≥50% inside 2020 city limits), 4 of
  them too few residents for a rate. Smoothed Part I rate quintiles about 10 / 18 / 30 / 51 per
  1,000, so the 10/25/50/100 breaks stay. Density quintiles about 36 / 85 / 157 / 311 per sq mi,
  so density breaks change from 50/150/400/1,000 to 25/75/150/300.
- `apd` ungated.

## 2026-10-23 — P1-05 APD aggregate safety layers (Codex)

- **Owner approval:** `apd: {per_day: 10, min_interval_seconds: 1}`, refreshed monthly,
  confirmed in the owner's P1-05 build request. Normal plan: four calls. Other adapters'
  budgets and gates stay unchanged; APD awaits Claude's first live check.
- Only grouped counts and an independent aggregate total are requested from APD. Reject
  unexpected response columns and duplicate group rows; never retain raw responses or
  enable recording. Socrata omits null-valued keys, so missing group/category cells mean
  unlocated/other; `n` is always required. Unknown non-null categories fail closed.
- The 99% vintage check uses distinct non-null codes, including out-of-county codes in
  its denominator. Every aggregate row still counts in reconciliation, including reports
  outside the city, outside the three counties and without a block group.
- Use unsimplified EPSG:5070 polygons for total area and city overlap; tolerate 1e-9
  floating-point error at exactly one-half. Leave population, area, share and period as
  context outside APD, but null every safety count, rate and density there. Inside APD,
  a missing group means a real zero; an independently verified zero-report period is valid.
- Apply the specified global empirical Bayes prior separately for Part I and violent
  reports, using only inside-area block groups with at least 100 residents. Zero mean or
  nonpositive between-area variance returns the common mean without division by zero.
  Round only final rates (one decimal) and densities (whole numbers), using Python's
  nearest-even rounding; retain full precision for area, overlap and the prior.
- The adapter seam cannot add saved IngestionRun notes without changing core. Emit count-only
  run notes to the job log and retain one non-spatial `run_summary` canonical audit record,
  separate from the block-group dataset. `tools/live_summary.py` displays its totals and
  period for a successful matching live run. Neither map layer publishes this audit record;
  both share the single `apd_block_group` file. No incident records or fields are stored.
- Use the source facts and 2020-code verification already recorded by Claude in the task
  and `SOURCES.md`; no source requests were made during development. Agency-wide safety
  layers remain deferred to P1-05b, as specified.

## 2026-10-23 — P1-06 merged; schools live check passed (Claude)

- First run 40038602598 failed (nothing published): one malformed NCES id somewhere in the
  statewide AskTED file. Statewide TEA rows that don't parse are now skipped and counted, and an
  NCES id claimed by two TEA campuses is dropped rather than guessed (PR #31).
- Run 40039008305: 5 calls. 31 districts kept, 596 campuses, 582 matched to a TEA campus
  number, 534 with a 2024–25 rating row (46 of them "Not Rated"), 62 with no rating found
  (mostly charters and special programs). 4 districts link to a school finder, 20 to their
  website, 7 fringe districts have no link. No personal columns requested or stored.
- `schools` ungated.

## 2026-10-23 — P1-06 schools implementation choices (Codex)

- Use synthetic fixtures large enough to meet the real production guards: 500 campuses,
  20 kept districts, 480 AskTED matches and 450 rating rows. No fixture-mode exception to
  the 500/20/90%/80% checks. District overlap uses unsimplified projected block-group area,
  with 1e-9 tolerance for floating-point error at exactly 0.5%.
- Socrata omits null-valued cells: require the selected column vocabulary across a response,
  require identifiers per row, and treat missing nullable cells as null. Identical duplicates
  collapse; conflicting identifiers or NCES/TEA district mappings fail. Unknown rating text
  fails; absent or non-numeric scores stay null. A Not Rated domain never gets a fake zero.
- Finder overrides use exact unshortened TIGER names. Fallback websites may come from any
  AskTED row with that TEA district number; choose HTTPS first, then alphabetical URL when
  several are provided. Reject unsafe protocols and credential-bearing URLs. The finder
  label appears as the link's popup annotation. No nearest-campus or attendance assignment.
- Report both rating-row coverage (the 80% guard) and actual A–F rated campuses separately
  from explicit Not Rated campuses. The adapter prints count-only run notes; the existing
  workflow summary tool adds them from successful published layers. The core adapter seam
  has no hook to add saved IngestionRun notes, so no core changes or raw-response retention.
- Source vintages are shown as NCES 2024–25 and TEA 2024–25, as verified in the task. Do not
  invent an exact source date from a school year; source_as_of stays unknown and the registry
  uses the successful run date. Current TIGER district geometry has no asserted calendar date.

## 2026-10-23 — Owner approval: `schools` budget 10 calls a day

- **Approved by the owner (2026-10-23):** `schools: {per_day: 10, min_interval_seconds: 1}`,
  refreshed yearly. A normal run is 5 calls (TIGERweb districts, TIGER block groups, NCES
  points, AskTED IDs, TEA ratings). The owner started P1-06 with the prompt stating this
  approval.
- P1-06 style correction (Codex's question, Claude agreed): district outlines use a
  transparent fill colour at opacity 1 with `fill-outline-color`, because `fill-opacity: 0`
  also hides the outline in MapLibre.

## 2026-10-23 — P1-02b naming details (Codex)

- Drop nested parenthetical annotations, including an unclosed final parenthesis caused
  by Austin's 50-character truncation. Treat "FINAL PLAT OF" as one removable phrase so
  cleaning cannot leave an orphan "Of". Preserve Roman numerals through XX in base names,
  matching the required "Met Center II" example while title-casing the rest.
- Hays subdivisions use the existing conservative subdivision cleaner (title case and
  trailing plat qualifiers); Austin alone uses the stronger cleaner. Each county's names
  are grouped and unioned only within its designated source. Existing alphabetical ties,
  coverage thresholds and projection tolerance stay as in P1-02.
- Austin paging accepts the GeoJSON transfer flag at the top level or in collection
  properties. An empty promised continuation fails, even if its final flag is false.
  Hays requests up to 2,000 records in its single call and fails on a transfer limit.
  Malformed pages preserve the last publication; short/empty cleaned Austin names are
  skipped and counted. The normal live plan is about 24 calls within the approved 30/day.
- Applied the owner's recorded areas budget approval by changing only that adapter's
  budget line. All other adapter budgets and live gates are untouched.
- (Claude, in review) A plat qualifier (SEC, PH, UNIT, BLOCK, LOT, …) is removed only with
  an identifier after it (a number, a single letter, a Roman numeral or ONE–TEN), so
  "Block House Creek Sec 2" stays "Block House Creek" rather than becoming "Creek".

## 2026-10-23 — ACS first live check; Census notes in plain words (Claude)

- Live run 40015773545: 26 calls in 38 s, no retries. 1,206 block groups and 471 tracts,
  each joined to exactly one ACS row. Population: Travis 1,330,015, Williamson 672,688,
  Hays 268,638; block-group and tract totals match exactly. No credential text in any output.
- Census annotation codes reached the popups raw ("-; MOE: **", "250,000+; MOE: ***"). They
  are now plain words ("Census: too few survey responses to estimate"), and capped medians
  show their range ("$250,000 or more", "1939 or earlier") instead of the stored number
  (250,001), which only sets the colour. New optional popup setting `display_field`.
- That run's data is not published; only its run log is merged, so its calls count. A fresh
  run (next UTC day, within the 30-call budget) publishes the cleaned version, then `acs`
  is ungated.

## 2026-10-23 — P1-04 merged; first live check of `fema_nfhl` passed (Claude)

- Live run 40012121921 (PR #22): 24 calls in about 7 minutes, no retries. 1,206 block
  groups (Travis 766, Williamson 324, Hays 116), one row each.
- 1% (SFHA) share: none 268, under 5% 306, 5–15% 410, 15–30% 143, 30% or more 67. The
  highest shares are along the San Marcos River, Onion Creek and the Colorado, as expected.
- 12 block groups read "not available" (FEMA coverage 95–99%), near the Travis–Williamson
  line. Checked one (484530341002) at full detail in a browser: about 5% of it has no FEMA
  polygon, a strip about 25 m wide where the two county flood maps don't meet. The 0.99
  rule stays; the label is accurate.
- `fema_nfhl` ungated. Today's spend: 34 of 40 calls.

## 2026-10-23 — FEMA paging: slower and gentler (Claude)

- Both first live checks of `fema_nfhl` from GitHub Actions ended with "connection reset" on
  the third FEMA page (offset 2000), and once on the first page. The same page loaded in
  about 1 s (0.8 MB, 1,000 polygons) from the owner's browser, so the page itself is fine.
- Changes: FEMA pages now start at least 15 s apart (`min_interval_seconds` 1 → 15; the
  daily limit stays 40), a run stops after 20 minutes, the one retry waits 60 s instead of
  5 s, and responses are requested gzip-compressed. This only makes us slower and lighter on
  FEMA's server, so it is not a budget increase. A full run is about 23 calls and 6 minutes.
- If resets continue, the next option is FEMA's official county NFHL downloads (3 files
  instead of about 22 pages), probed first.

## 2026-10-23 — Owner approval: `areas` budget 20 → 30 calls a day; wider study area

- **Approved by the owner in writing (2026-10-23):** raise `areas` from 20 to 30 calls a day
  for P1-02b (two more subdivision sources, about 24 calls per run). P1-02b makes the change.
- `study_bbox` widened to [-98.35, 29.70, -97.10, 30.95] (Claude, during P1-04 review): three
  eastern Williamson block groups (484910209001/003/004) reach -97.155, past the old east edge
  of -97.25, so FEMA zones beyond it were not fetched and those areas would have read "not
  available". Checked against the stored live block groups (extent -98.298, 29.752, -97.155, 30.904).

## 2026-10-23 — P1-04 flood-share choices (Codex)

- Use a spatial index to clip the intersecting FEMA polygons per block group, then union
  each category. Subtract the SFHA union from the 0.2% union, including overlaps across
  separate source features. This keeps the categories disjoint and avoids double counting.
- Compare unrounded mapped coverage to 0.99, with only 1e-9 tolerance for projection
  round-trip error at the exact boundary. A coverage value that merely rounds up to 0.990
  still makes both hazard shares null. Fully mapped areas with no hazards get actual zeros.
- A promised continuation page must contain features even if its own transfer-limit flag
  is false. An initially empty, complete NFHL response is allowed and yields zero mapped
  coverage with unavailable flood shares. Support transfer flags at the GeoJSON top level
  and in its collection properties. Paging always advances by the requested 1,000 rows.
- Require the requested attributes, nonempty zone text, T/F SFHA flags and text version
  identifiers; ignore extra service fields. Repair FEMA geometry, recursively retain all
  polygonal parts and print skipped-row counts per page. TIGER geometry remains strict.
- Collect distinct nonempty VERSION_ID strings from all usable NFHL polygons intersecting
  the block group, including boundary-only touches and AREA NOT INCLUDED. Sort them as text.
  VERSION_ID does not establish an effective date: leave `source_as_of` unknown, so the
  existing registry uses the successful run date without inventing a FEMA map vintage.
- Compute shares on unsimplified Census polygons in EPSG:5070. Simplify only their display
  geometry using the areas adapter's 5 m tolerance and six-decimal WGS84 coordinates.
  Hazard polygons are never published. No pipeline core or web application changes.

## 2026-10-23 — P1-03 ACS implementation choices (Codex)

- The adapter queues a single HTTP 5xx retry through `follow_up()`, rather than making an
  uncounted call inside `fetch()`. Retries obey the runner's budget and one-second pacing;
  the normal plan is 26 calls, leaving four retry calls inside the approved daily cap of 30.
  All transport errors discard URLs and response text so Census credentials cannot enter
  the run log. Only `fetch()` reads and adds the environment key.
- Keep unrounded numeric estimates and MOEs in canonical data. For a sum, any missing
  estimate makes the sum unavailable; any missing component MOE makes its uncertainty
  unknown. Missing numerator or denominator MOE preserves an otherwise valid share with
  unknown reliability. Shares outside 0–1 fail instead of silently clamping.
- Preserve EA and MA strings together, with MOE/numerator/denominator labels where needed.
  Raw Census cell names and intermediate cells never reach published properties.
- Use fixed legend breaks, identical at both scales: shares 20/40/60/80%; population
  500/1,000/2,000/4,000; income $50k/75k/100k/150k; home value $200k/350k/500k/750k;
  rent $1k/1.5k/2k/2.5k; year built 1960/1980/2000/2010; age 25/35/45/55. These are neutral
  display bins, not scores. Every measure uses the same five blue colors, with grey for null.
- Use the existing `data_bundle` seam: all metrics share one loaded map source/file per
  scale. (Claude, in review: the core publisher now writes one file per bundle, e.g.
  `data/layers/acs_block_group.geojson`, instead of an identical copy per layer, which
  would have been about 21 copies per scale. A bundle may not share a name with a layer id.)
- Simplify only display polygons, using the areas adapter's 5 m equal-area tolerance and
  six-decimal WGS84 coordinates. All ACS estimates describe the whole area without prorating.

## 2026-10-23 — P1-02 area naming choices (Codex)

- Union polygons in each cleaned WCAD name group before measuring coverage, so overlapping
  sections and replats never count the same land twice. Austin planning areas and Census
  places are compared individually. Choose the largest share, then alphabetical name for
  exact ties, independent of response order.
- Compare unrounded EPSG:5070 shares to the thresholds; allow only 1e-9 of floating-point
  projection error at exact edges. Round stored shares and square miles to three decimals.
- Reject invalid, missing or non-polygon geometry rather than repair it or silently drop
  rows. Enforce the requested native property sets; WCAD's selected `geometry` is the
  GeoJSON geometry, not an extra property. Claude must confirm this in the first live run.
- Add `boundary_note` to block-group properties and attach it to the Name popup through
  the existing manifest annotation field: "2020 Census boundaries; names as of <run date>".
  The run date comes from the runner; geometry `source_as_of` stays 2020-01-01.
- Fixtures include a full 2,000-row WCAD page, mostly identical synthetic polygons outside
  the study area, followed by one row completing a 45% naming group. This tests the real
  paging limit without any test-only behavior. The regeneration script makes no calls.

## 2026-10-23 — Owner decisions: no permission requests; stay public (Q1, Q2)

**Approved by the owner in writing (2026-10-23).** The owner prefers not to request written
permission to republish anything (a basic API-key signup is fine). Where a source would need
permission, take another route. The repo and site stay public. If the owner later decides to go
private, that is a separate decision that would revise these choices.

- **Q1 → publish public government data that has no stated license**, with credit to the
  publisher, its disclaimer, and personal fields stripped at ingest. Covers TCAD, WCAD and Hays
  CAD exports; Travis County and Hays County GIS; City of Austin GIS; and TEA's datasets on the
  Texas Open Data Portal. Gates on these sources in P1-02 and later tasks are open.
- **District attendance zones are not copied.** Each area shows its school district, nearby
  campuses, and a link to the district's own school finder. Showing zone outlines live in the
  browser from a district's own map service (with no copy stored) may be considered in P1-06,
  and would need the owner's approval then.
- **Q2 → TEA ratings come from TEA's own release on data.texas.gov**: "School Year 2024-2025
  Statewide Accountability Ratings" (`nui6-x374`, attribution "Performance Reporting Division
  at Texas Education Agency", updated 2026-06-14). It includes overall, School Progress and
  Academic Growth ratings and scores. No permission request. Trade-off: published ratings
  run a year behind TEA's website (2025–26 ratings are there now, final 2026-12-11). Use the
  newer year when TEA posts it to the portal. Content on tea.texas.gov itself (including the
  campus CSV broker) is not republished.
- Not legal advice. "No license stated" is a judgment call, judged low-risk because these are
  government records the agencies post for public download, and we always credit them.

## 2026-10-22 — Phase 0 results (Claude; for owner approval)

Details and citations in `docs/SOURCES.md`.

- **Hays County is in v1.** Hays CAD publishes free monthly exports with market value, living
  area and year built. CC0 parcel shapes cover it (StratMap 2026, plus Hays County GIS). The
  Comptroller's 2024 study covers it (median level 1.00, COD 7.12), and zone layers exist for Hays
  CISD and Dripping Springs ISD. Its gaps (crime only at agency level, little fixed-route transit)
  are the same as Williamson's.
- **Parcel shapes:** StratMap 2026 (CC0) for all three counties as the baseline. Fresher
  county layers (Travis County's monthly TCAD layer, WCAD's daily parcels, Hays County GIS) are
  used where they are fresher (Q1 decided 2026-10-23).
- **Williamson rolls come from WCAD's open-data portal** (Socrata API), not the certified-roll
  SharePoint links, which answered HTTP 401 from GitHub.
- **CapMetro GTFS from data.texas.gov** (`r4v4-vz24`). CapMetro's developer page points there and
  the feed is current (2026-10-07 to 2027-01-09). This replaces the earlier note that called that
  copy stale.
- **Crime:** APD block groups inside Austin PD's area; DPS agency-level elsewhere, labeled.
  No incident feeds found for other agencies.
- **Actions billing:** standard runners are free for public repos (GitHub docs, checked
  2026-10-22). The light-usage rules stay.
- **Validation targets** are set in `docs/PLAN.md` before any building.
- **Census API:** a key is required even for county-level requests. With the `CENSUS_API_KEY`
  secret it works from GitHub (run 39891997771). Two earlier 503s were transient.

## 2026-10-23 — P1-02 merged; first live check of `areas` passed (Claude)

- Review changes before merging (on the PR): extra service fields are ignored (only named
  fields are copied, so nothing extra can be published); naming polygons from the City,
  WCAD and Census places are repaired with `make_valid` or skipped and counted; Census
  boundaries stay strict.
- **Live run 40001981957** (Live run workflow, first check): success, 14/14 calls, 28 s.
  **1,206 block groups** (Travis 766, Williamson 324, Hays 116) and **471 tracts**, matching
  the Phase 0 count. Names: Census place 764, City of Austin planning area 343, WCAD
  subdivision 68, fallback 31. Stored data has boundary and name fields only. Merged as
  PR #13; the live site shows real boundaries. `areas` is ungated.
- CI on that data PR found that a fixture build labeled layers "Current" once the run log had
  a live run. Fixed in PR #14: the registry labels each layer from the file it publishes.
- **Naming is weak in Austin** (256 block groups named "Austin city"). Follow-up task P1-02b
  adds City of Austin and Hays County subdivisions and uses place base names. It needs the
  `areas` budget raised from 20 to 30 calls a day: **pending owner approval**.
- `Live run` workflow (PR #12): manual, budgeted, one adapter; pushes the run log and stored
  data to a `data/<adapter>-<run id>` branch for review; `first_check` bypasses the live gate
  for Claude's first check only.
- P1-03 trimmed to the measures in the brief (no commute, vehicle, language or moving
  measures), which fits its approved 30 calls a day. P1-04 publishes the per-area flood
  shares only; flood-zone outlines wait for a PMTiles publisher (too large as GeoJSON).

## 2026-10-23 — P1-01 skeleton: design choices (Claude)

Ported from Austin Watch piece by piece (package `aw` → `mm`), keeping only area layers.
Differences from Austin Watch, and why:

- **Canonical store is gzipped NDJSON**, written deterministically (no git churn when
  unchanged). DuckDB/Parquet are dropped until a task needs them, so the DuckDB 2.0
  breakage can't recur and CI installs less.
- **Partial live runs publish nothing** (Austin Watch published them). An incomplete area
  layer would show missing areas as gaps, so the last complete layer stays live.
- **No budget line means no live calls** (fails closed). Fixture runs are unaffected.
- **Raw live responses are gitignored** and kept only if an adapter opts in; **`mm record`
  is opt-in** per adapter. Public repo, and CAD files carry personal data.
- **Two guards from the ground rules:** `privacy.py` refuses to publish personal-looking
  property names (owner, mailing address, exemptions, agents, buyers/sellers…; property
  `situs_*` and ACS `owner_occupied*` allowed). `inputs.py` plus tests stop any field of a
  `demographic: true` layer from becoming a score or model input.
- **Missing values display as "Not available"**, never "—" or zero.
- **Site:** Map / Sources / Health / About pages, a footer on every page, a "Test data"
  banner whenever a visible layer shows fixtures, and layer choices and the map view
  remembered in the browser only. Basemap: OpenFreeMap (free, no key).
- **Pages deploy** runs `mm publish` (stored live data, fixtures elsewhere) and never calls
  a source. Turning Pages on (Settings → Pages → Source: GitHub Actions) is a one-time owner
  click; the API path is blocked for Claude here.

## 2026-10-23 — Owner approval: Phase 1 starts; Q3 decided

**Approved by the owner in writing (2026-10-23).**

- **Phase 1 approved** as planned in `docs/PLAN.md`, including the call budgets and refresh
  cadences proposed in `docs/tasks/P1-*.md`. Later changes to budgets or schedules need the
  owner again.
- **Q3 → WCAD per-sale sales ratios are used only for area-level checks.** For example, a median
  ratio by area with at least 30 sales. Never per property, and never published in a way that
  lets anyone work out an individual sale price. Before first use, confirm from WCAD's layout what
  the ratio compares (which year's value, which price).

## 2026-10-23 — Owner decisions: no permission requests; stay public (Q1, Q2)

**Approved by the owner in writing (2026-10-23).** The owner prefers not to request written
permission to republish anything (a basic API-key signup is fine). Where a source would need
permission, take another route. The repo and site stay public. If the owner later decides to go
private, that is a separate decision that would revise these choices.

- **Q1 → publish public government data that has no stated license**, with credit to the
  publisher, its disclaimer, and personal fields stripped at ingest. Covers TCAD, WCAD and Hays
  CAD exports; Travis County and Hays County GIS; City of Austin GIS; and TEA's datasets on the
  Texas Open Data Portal. Gates on these sources in P1-02 and later tasks are open.
- **District attendance zones are not copied.** Each area shows its school district, nearby
  campuses, and a link to the district's own school finder. Showing zone outlines live in the
  browser from a district's own map service (with no copy stored) may be considered in P1-06,
  and would need the owner's approval then.
- **Q2 → TEA ratings come from TEA's own release on data.texas.gov**: "School Year 2024-2025
  Statewide Accountability Ratings" (`nui6-x374`, attribution "Performance Reporting Division
  at Texas Education Agency", updated 2026-06-14). It includes overall, School Progress and
  Academic Growth ratings and scores. No permission request. Trade-off: published ratings
  run a year behind TEA's website (2025–26 ratings are there now, final 2026-12-11). Use the
  newer year when TEA posts it to the portal. Content on tea.texas.gov itself (including the
  campus CSV broker) is not republished.
- Not legal advice. "No license stated" is a judgment call, judged low-risk because these are
  government records the agencies post for public download, and we always credit them.

## 2026-10-22 — Phase 0 results (Claude; for owner approval)

Details and citations in `docs/SOURCES.md`.

- **Hays County is in v1.** Hays CAD publishes free monthly exports with market value, living
  area and year built. CC0 parcel shapes cover it (StratMap 2026, plus Hays County GIS). The
  Comptroller's 2024 study covers it (median level 1.00, COD 7.12), and zone layers exist for Hays
  CISD and Dripping Springs ISD. Its gaps (crime only at agency level, little fixed-route transit)
  are the same as Williamson's.
- **Parcel shapes:** StratMap 2026 (CC0) for all three counties as the baseline. Fresher
  county layers (Travis County's monthly TCAD layer, WCAD's daily parcels, Hays County GIS) are
  used where they are fresher (Q1 decided 2026-10-23).
- **Williamson rolls come from WCAD's open-data portal** (Socrata API), not the certified-roll
  SharePoint links, which answered HTTP 401 from GitHub.
- **CapMetro GTFS from data.texas.gov** (`r4v4-vz24`). CapMetro's developer page points there and
  the feed is current (2026-10-07 to 2027-01-09). This replaces the earlier note that called that
  copy stale.
- **Crime:** APD block groups inside Austin PD's area; DPS agency-level elsewhere, labeled.
  No incident feeds found for other agencies.
- **Actions billing:** standard runners are free for public repos (GitHub docs, checked
  2026-10-22). The light-usage rules stay.
- **Validation targets** are set in `docs/PLAN.md` before any building.
- **Census API:** a key is required even for county-level requests. With the `CENSUS_API_KEY`
  secret it works from GitHub (run 39891997771). Two earlier 503s were transient.

## Pending owner decisions

- **Q3. WCAD per-sale "sales ratios".** WCAD's open data includes a sales ratio for many sales,
  which together with the appraised value could reveal individual sale prices that Texas
  otherwise keeps private. Options: (a) don't use; (b) use only as area-level checks
  (e.g. median ratio by area with ≥ 30 sales), never per property; (c) use per property.
  **Claude recommends (b)**, after confirming with WCAD's layout what the ratio compares.

## 2026-10-22 — Source probe workflow (Phase 0)

- `tools/probe/probe.py` + `.github/workflows/probe.yml` (manual only). About 30 checks, one
  small request each: HEAD, byte ranges, count queries or a page fetch. Zip archives are
  inspected by reading only their directory, plus at most one small member (GTFS
  `feed_info.txt`). Output is counts, sizes, dates and status only — no personal data, since
  Actions logs in a public repo are public.
- Merged without CI: CI doesn't exist until Phase 1, and `workflow_dispatch` only works for
  workflows on the default branch. The script was syntax-checked and its zip reader was
  tested locally.

## 2026-10-22 — Owner approvals to start Phase 0

- **Phase 0 started** (owner: "Go", 2026-10-22). Phase 0 is discovery and verification, no
  app code.
- **One probe workflow and script allowed in Phase 0** (owner approved). Manual-only
  (`workflow_dispatch`), small requests or headers only, no bulk downloads, summary posted
  to the run page and as notice annotations.
- **Code license: MIT** (owner approved). Data keeps each publisher's terms.
- **Census API key:** the owner is adding it as the Actions secret `CENSUS_API_KEY`. Agents
  never sign up for services.
- **Austin Watch reference:** kept as `austin-watch-reference.zip` in the owner's Claude
  Project, never in this repo. Lessons and a reuse list are in
  `docs/reference/austin-watch-lessons.md`.

## 2026-10-22 — Docs-only PRs merge without CI

There is no CI yet, and the planned CI skips docs-only changes (`docs/**`, `**/*.md`). A
docs-only PR may merge after Claude's review against `AGENTS.md`. Any PR that changes code or
workflows needs green CI once CI exists.
