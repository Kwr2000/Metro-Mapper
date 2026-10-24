# DPS agency-wide safety

Five annual requests: three DPS UCR agency workbooks, 25 current TIGER city limits,
and the three counties' 2020 block groups. Claude verified the portal and field layout
on 2026-10-24; see `docs/tasks/P1-05b-agency-safety.md` and `docs/SOURCES.md`.
The budget and publication under the owner's Q1 rule are approved in `docs/DECISIONS.md`.
Live use stays gated until Claude checks the figures.

Every assigned block group carries its agency's **whole** jurisdiction population,
counts and rates. These values are never apportioned by area or population. DPS totals
exclude arson and human trafficking for the seven-category Part I calculation; the
portal's full total is retained only for unmapped agencies in the count-only audit.
Missing prior-year figures and split areas stay null. Sheriff's coverage excludes the
union of all 25 PD cities, including cities crossing county lines.

Geometry shares use EPSG:5070 without simplification. Places are repaired with
`make_valid`; block groups must already be valid. City assignment precedes sheriff
assignment, using unrounded shares with 1e-9 tolerance. If two cities meet the threshold,
use the larger share, then ascending ORI to break an exact tie. Report this unusual case
in review if it occurs live; the method still assigns only one whole-agency statistic.

The standard-library XLSX parser honors workbook relationships and sheet order, sparse
cell references, rich/shared strings, inline strings and numeric text. The first sheet's
row 2 is the header. Unknown/duplicate/missing headers or unpaired/duplicate year rows
fail closed. The parser accepts formatted thousands and integral decimal strings for
counts, but never turns blanks into zero. Legend sheets are preserved in the parsed
payload; they are metadata, not additional agency tables. All three requested reports
must normalize successfully before finalization checks the 28 ORIs and 25 places.

The manifest's description names 2025, as required for the first release. At the next
annual review, update that prose to the newly selected year. Feature `year`, `period`,
`retrieved` and `source_as_of` always follow the run's UTC date rule.

`run_summary` is a non-spatial canonical audit record, excluded by the map's dataset
filter. It includes counts per ORI (including zero assigned block groups), split count,
matched totals and the unmapped agencies' offense counts. A count-only JSON note is
also printed; `tools/live_summary.py dps_agency` shows the saved audit. Neither individual
incidents nor personal data are requested or stored. Raw retention/recording stay off.

Fixtures are entirely synthetic, with native workbook/TIGER field names; they are not
live observations. Rebuild them with the installed pipeline environment:
`python adapters/dps_agency/make_fixtures.py`. The seven block groups cover city, county
crossing, county sheriff (including a no-PD city), split and half-area cases. Run tests
with `python -m pytest pipeline/tests/test_dps_agency.py` or the full `make test`.
