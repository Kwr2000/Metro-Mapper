# P1-05 — Safety layers (outline; refined before build)

- **Agents:** Claude verifies, Codex builds. Wave 1b. **Depends on:** P1-02.

**Claude first:** check whether APD's `census_block_group` codes are 2010 or 2020 vintage
(compare distinct codes since 2025-10-01 against the 2010 and 2020 block-group lists). If they
are 2010, specify the Census 2010→2020 block-group relationship file crosswalk. Check the DPS
Crime in Texas 2025 table layout (PDF; is a CSV/XLSX available?). Confirm agency jurisdictions
can be drawn from Census places (city PDs) and county remainders (sheriffs).

**Build:**
- APD reported incidents per block group over the last 12 full months (report date), by
  violent/property/other. Aggregate query only, never incident rows. Block groups outside APD's
  area are "not available (outside Austin PD)", not zero.
- Small counts are shrunk toward the surrounding area (empirical Bayes; the method is written on
  the methodology page). Show raw count, rate per 1,000 residents (ACS population, with MOE
  caveat), and density per square mile.
- Agency-level layer elsewhere: one value per agency jurisdiction, labeled "agency-wide
  average; not specific to any street".
- Hard check: block-group counts sum to the APD aggregate for located reports.
