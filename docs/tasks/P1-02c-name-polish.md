# P1-02c — Area-name polish

- **Agent:** Codex. Branch `codex/p1-02c-name-polish`. Regular (not draft) PR to `main`.
- **Depends on:** P1-02b (merged; live 2026-10-24). Change only `adapters/areas/`, its tests and
  fixtures, and docs. **No network.** No budget or source changes. Claude does the live run.

## Why

The P1-02b live run (DECISIONS 2026-10-24) left cosmetic issues in published names.

## Changes

1. **City of Austin neighborhood planning areas arrive in capitals** ("NORTH AUSTIN CIVIC
   ASSOCIATION", "BOULDIN CREEK", "MLK-183", "PECAN SPRINGS-SPRINGDALE"). Title-case them, keeping
   `MLK` and any token containing a digit in capitals ("MLK-183" stays "MLK-183"). "MCKINNEY" → "McKinney" (words starting `MC` get `Mc` + capital).
   Hyphenated parts are each title-cased ("Pecan Springs-Springdale").
2. **WCAD abbreviations**, whole words only, case-insensitive: `Crk` → "Creek", `Ests` → "Estates".
   Also drop a trailing `Sec <identifier>` the WCAD cleaner leaves mid-name ("Brushy Crk Sec 1
   (South)" → "Brushy Creek"), using the same identifier rule as the Austin cleaner and also
   dropping parenthetical text. Leave numbered names like "Cedar Park Ranchettes #4" as they are.
3. **Small words** after the first word are lower case in all cleaned subdivision names: `At`,
   `Of`, `The`, `And`, `On` ("Crossing At Carriage Hills" → "Crossing at Carriage Hills",
   "Woods Of Brushy Crk" → "Woods of Brushy Creek").

Grouping and the area-share rules (P1-02b) apply to the polished names, so subdivisions that only
differed by abbreviation merge ("Block House Crk" and "Block House Creek").

## Tests

Parametrized cases for every example above, plus: "DOWNTOWN" → "Downtown", "HYDE PARK" →
"Hyde Park", "Of Brushy" stays "Of Brushy" at the start, "Mesa Park" unchanged, and that a name
already in title case is unchanged.

## Done when

`make test` passes, CI is green, and the PR lists files changed and says what Claude should
check in the live run (no all-capital planning-area names; no "Crk"/"Ests" left).
