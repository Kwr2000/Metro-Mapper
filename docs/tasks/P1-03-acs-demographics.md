# P1-03 — ACS demographics layers

- **Agent:** Codex. Branch `codex/p1-03-acs-demographics`.
- **Phase:** 1, wave 1a. **Depends on:** P1-01 and P1-02 merged. Read `AGENTS.md` first.

## Goal

ACS 2020–2024 5-year estimates for every block group and tract in Travis, Williamson and Hays,
with margins of error, as map layers and filters. Covers income, education, age, household
type, owner-occupancy, housing age, and race and ethnicity.

## Rules (non-negotiable; ground rule 4)

- Demographics are **context and filters only**. Tag every field `demographic: true` in its
  manifest. The demographics guard test from P1-01 must pass. Never feed them into any score,
  ranking, value or "value for money" field.
- Neutral presentation: one sequential single-hue palette (blue), no red/green, no "better/
  worse" wording. Legend says "estimate". Missing data shows in grey as "Estimate unavailable",
  never as zero.
- Every value shows its 90% MOE and a **low reliability** flag when MOE > 30% of the estimate
  (zero estimates with positive MOE are low reliability; missing MOE is "unknown"). Derived
  shares carry MOE using the Census formulas (`sqrt(MN² − p²·MD²)/D`, falling back to
  `sqrt(MN² + p²·MD²)/D` when the radicand is negative).
- Negative sentinel values (e.g. -666666666) become missing, never numbers.

## Source facts (from Austin Watch, re-verified 2026-10-22 where noted)

- Endpoint `https://api.census.gov/data/2024/acs/acs5`. **A key is required** (keyless requests
  redirect to `missing_key.html`, checked 2026-10-22). Read `CENSUS_API_KEY` from the environment,
  send it only at the transport boundary, and never log it or store it in fixtures. Non-JSON
  responses are failures.
- Request shape: `get=group(B01001)` as its own request; all other variables in explicit lists
  of ≤ 50; timeout 60 s. One request set per scale (block group, tract) per county, or
  `for=block group:*&in=state:48 county:453` style.
- Tables (from Austin Watch's adapter): B19013 income, B25077 home value, B25064 rent,
  B25035 year built, B01003 population, B25003 tenure, B01001 age/sex, B03002 Hispanic origin
  by race, B11001/B11003 household type, B15003 education, B08301 commute, B25044 vehicles,
  B16001 language, B07003 moved. Use the `_E`/`_M` pairs.
- As-of = survey period end, 2024-12-31. Label "ACS 2020–2024 5-year".
- **Risk:** on 2026-10-23 the API answered HTTP 503 to GitHub's runners. Build the adapter so
  the request layer can be swapped for the Census bulk summary-file download later. Don't build
  the fallback in this task.

## Requirements

- Synthetic fixtures with native variable names, covering sentinels, zero denominators and
  MOE edge cases.
- Layers at both scales with a block-group/tract toggle (variant family as in Austin Watch).
  None visible by default.
- Budget `acs`: 30/day (3 counties × 2 scales × ≤ 5 requests). Refresh: yearly in February.

## Done when

`make test` passes, including the demographics guard. Claude does the live run, with the owner's
budget approval recorded in DECISIONS, before merging.
