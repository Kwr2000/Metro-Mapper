# P1-09 — Monthly refresh and validation report

- **Agent:** Claude. Wave 1c. **Depends on:** P1-02..P1-07. **Status:** built (2026-10-24).
- **No new budgets or cadences.** Uses each adapter's approved budget in `config/budgets.yaml`
  and each layer's approved `refresh` in `layers/*.yaml`. Changing the schedule, a budget or a
  cadence needs the owner's written approval (AGENTS.md).

## Schedule

`.github/workflows/refresh.yml`, cron `15 9 3 * *` (09:15 UTC on the 3rd of each month), as
proposed in this task's outline and approved with Phase 1. Manual runs default to a **dry run**
(lists what is due and validates; no source calls, no commit).

## What is due

`mm layers-due` / `pipeline/mm/layers_due.py`. An adapter is due when a layer it feeds has a
monthly or annual `refresh` and its last live success is at least 25 days old (monthly) or 350
days old (annual), or it has never succeeded live. Gated adapters (`config/live_gates.yaml`) and
manual layers are never due. The 25-day floor keeps a 28-day February-to-March gap from skipping
a month, while a manual run in the last 25 days still waits for the next month.

Today's cadences: monthly — `fema_nfhl`, `apd`, `access` (once ungated); annual — `areas`,
`acs`, `schools`.

## One refresh (`mm refresh --mode live`, `pipeline/mm/refresh.py`)

1. `mm publish`: last month's stored data is in place for every layer.
2. Each due adapter runs live through the budgeted runner (its own budget, pacing, time limit
   and empty-layer guard). A failed adapter keeps its previous data; the others carry on.
3. Validation (`pipeline/mm/validation.py`). If any **hard** check fails, `data/canonical` is put
   back byte for byte as it was before the refresh, so nothing new is published.
4. `data/validation/validation.json` and `data/validation/report.md` are written. The workflow
   commits them with the run log (always, so calls count and the schedule stays alive under the
   60-day rule) and the stored data (only when it passed), pushes to `main`, and starts
   `pages.yml` (a push by the workflow's own token does not trigger it). A hard failure turns
   the job red. `mm publish` serves the latest report at `/validation.json`.

## Checks (targets from `docs/PLAN.md`)

| Check | Kind | How |
|---|---|---|
| Every layer has attribution, an as-of date, a published file, and ≥ 50% of last month's features | Hard | Last month = `baseline` in the previous `validation.json` (live counts; a failed month keeps the earlier numbers). Test-data layers skip the count. |
| No demographic field feeds any score | Hard | `inputs.assert_no_demographics` on every `SCORE_INPUTS` entry (none until Phase 2), alongside the static test. |
| No personal fields in published files | Hard | `privacy.personal_keys` over every property of every published GeoJSON. |
| APD block-group counts reconcile with APD's total | Hard | Sum of published block-group `total` = APD period total − reports without a block group − reports in block groups outside the APD area. The last count is new in APD's run summary; until APD's next refresh the check reports "skipped". |
| Rankings stable between block groups and H3 res-8 hexagons | Soft | For each non-demographic block-group layer, the property its map style colours by. Each hexagon takes the overlap-weighted mean of its block groups; each block group then takes the overlap-weighted mean of its hexagons; Spearman between the two ≥ 0.8. Missing values are skipped. |
| Due adapters succeeded | Soft | Failures listed; their previous data stays. |
| No layer shows test data or is stale | Soft | From the published files and the registry. |
| HMDA and ZIP-median checks | Soft | Listed as "not applicable yet" until Phase 2. |

First check on stored live data (2026-10-24): hard checks pass (APD reconciliation skipped as
above); Spearman 0.91 APD density, 0.85 APD Part I rate, 0.82 FEMA 1% share; the nine access
layers are flagged as test data until `access` is ungated.

## Commands

```
mm validate                 # print the report on what is published; writes nothing
mm validate --write         # also write data/validation/
mm refresh --dry-run        # what is due + validation; no source calls, no writes
mm refresh --mode live      # what the workflow runs
```
