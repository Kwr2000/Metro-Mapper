# Metro Mapper — instructions for coding agents

Claude Code and Codex both read this file. The owner is not a programmer: agents build,
the owner reviews and decides. Keep replies short and plain.

**Start of every session:** read this file and `docs/STATUS.md`; read `docs/PLAN.md`,
`docs/DECISIONS.md` and `docs/SOURCES.md` as needed. The repo is the source of truth, not
earlier chats. **End of every session:** update `docs/STATUS.md`.

## What this is

A public, map-first static site for the Austin metro (Travis and Williamson counties; Hays
if Phase 0 finds it feasible) that helps the owner understand the housing market and judge
areas and individual homes found on Zillow and similar sites. It does **not** pull home
listings. See `docs/PLAN.md` for scope and phases.

## Ground rules (non-negotiable)

1. **Honest numbers.** Every number on the site shows its source and as-of date; estimates
   show a range and say what drives it; fixture/test data is labeled "Test data". Never
   present modeled or imputed values as observed.
2. **No sale prices exist here — say so.** Texas doesn't disclose sale prices. Until we have
   verified sale prices, the home estimate is an **"appraisal-based value range"**. Never
   label anything "fair value" or call a home a "good deal"; show where the asking price
   falls against the range instead.
3. **Don't invent spatial detail.** No spreading city-wide crime totals onto streets, no
   drawing school zones around campuses, no nearest-campus assignment. Where real data
   doesn't exist at a grain, show the coarser grain clearly labeled, or show "not
   available" — never zero.
4. **Demographics are context and filters, never model inputs.** Race and ethnicity (and the
   other ACS demographics) may be map layers and user-chosen filters, but never inputs to the
   value model or any combined score, ranking or "value for money" measure. A test enforces
   this. Present them neutrally (no "better/worse" color language), with margins of error.
5. **Nothing about people.** Publish property facts, never owner names, mailing addresses or
   exemption types that reveal age, disability or veteran status. Strip them at ingest.
6. **Publishable sources only.** Before any source's data appears on the public site, its
   license/terms for republication are recorded in `docs/SOURCES.md`. Sources that can't be
   republished are used only for checks, and only summary statistics are published.
7. **Polite source use.** Never call live sources while developing — use recorded fixtures.
   Live calls only through the pipeline's budgeted runner. Check every new endpoint with the
   probe workflow before relying on it.
8. **No secrets in code or the browser.** Keys in GitHub Actions secrets or a gitignored
   `.env`. Never create accounts or sign up for services on the owner's behalf.
9. **Keep Actions light and alive.** Data refresh monthly or slower; CI runs once per pull
   request on a fast test subset. Scheduled workflows in public repos are disabled after 60
   days without repository activity — the monthly job must commit or otherwise keep it active.
10. **$0 by default.** No monthly costs, no card on file. Ask before any one-time cost.

## Stop and ask the owner before

- starting a new phase;
- any spending;
- adding a source whose republication terms are unclear;
- changing a data refresh schedule or a call budget;
- publishing anything that touches personal data;
- any change to how demographics are used.

Record the owner's approvals in `docs/DECISIONS.md` ("Owner approval: …").

## How we work

- **Tasks** live in `docs/tasks/<id>.md`, self-contained, so either agent can pick one up.
  Claude plans, writes specs, verifies data, reviews and merges, and builds when it has
  capacity; Codex builds from specs. When a task is ready for Codex, Claude gives the owner
  the exact prompt to paste, complete, with nothing to fill in.
- **Branches and PRs.** One task per branch (`claude/<task>` or `codex/<task>`); regular
  (not draft) PRs; merge only with green CI (docs-only PRs have no CI and may merge after
  review). Before merging: review against this file and the task spec, run the full test
  suite locally, and test against real data where the task touches a live source. Codex
  develops on fixtures only.
- **CI** runs once per PR, skips docs-only changes, cancels superseded runs, and runs a fast
  test subset; slow full-rebuild tests are marked `slow` and run locally before merge. Watch
  for major dependency releases that break builds (DuckDB 2.0 did this before); pin or adapt.
- **Reviews and first live checks** follow `docs/REVIEW.md` (any Claude model).
- **GitHub API:** use `gh api` REST; GraphQL may be unavailable.
- **Verify facts at the publisher.** Earlier AI reviews stated licenses, data grain and field
  meanings wrongly. Check the publisher's own page or file before relying on a fact, and
  cite it in `docs/SOURCES.md` or `docs/DECISIONS.md` with the date checked.
- **Scope.** Keep phases and tasks small. Scope creep sank the previous project.

## Seams — how to extend without touching core code

- **New data source:** `adapters/<id>/adapter.py` defining `ADAPTER = <SourceAdapter subclass>`
  (contract in `pipeline/mm/adapter.py`: `plan → fetch → normalize`, plus `source_as_of`).
  Emit canonical records only (`pipeline/mm/schemas.py`); never leak source field names.
  Fixtures in `adapters/<id>/fixtures/<request key>.json` are **synthetic, with native field
  names** (real responses may hold personal data; `mm record` is opt-in per adapter via
  `recordable = True`). Add a budget line in `config/budgets.yaml`: an adapter without one
  cannot run live. New sources start in `config/live_gates.yaml` until the probe confirms them.
- **New map layer:** one YAML file in `layers/` (schema: `LayerManifest`); file name = `id`.
  Set `attribution`, `license` (or leave empty = "No license stated") and the publisher's
  `disclaimer`. Census demographics set `demographic: true`. No changes to `web/src`: a test
  fails if site code names a layer id.
- **Scores and models** (Phase 2+) declare their input fields in `pipeline/mm/inputs.py`;
  a test fails if any is a field of a demographic layer.
- **Personal data:** adapters strip it at ingest; `pipeline/mm/privacy.py` also refuses to
  publish personal-looking property names. Raw live responses (`data/raw/`) are gitignored.
- **Schema change:** edit `pipeline/mm/schemas.py`, run `mm schema` and
  `cd web && npm run gen:types`, commit both outputs.
- Personal notes, weights and saved areas live only in the browser (`web/src/store.ts`).

## Layout and commands

```
pipeline/mm/      Python package (CLI: mm)        adapters/<id>/  one folder per source
layers/*.yaml     one manifest per map layer      config/         app, budgets, live gates
data/canonical/   last good live records (committed)   data/runs/  run log (live: committed)
web/              Vite + React + MapLibre site    schemas/        exported JSON Schemas
tools/probe/      source probe (manual workflow)

make setup        # pip install -e pipeline[dev]; npm ci in web/
make test         # full suite: run before every merge
make test-fast    # the CI subset
make build        # fixtures -> layers, registry.json, health.json (labeled Test data)
make dev          # publish (stored live data, else fixtures) and serve on 127.0.0.1:5173
mm run --adapter <id> --mode live    # budgeted live run (normally only in workflows)
```

Workflows: `ci.yml` (once per PR, fast subset), `pages.yml` (deploys the site on push to
main from committed data; no source calls), `probe.yml` (manual source probe), `live-run.yml`
(one adapter, manual, to a review branch), `refresh.yml` (monthly on the 3rd: due adapters,
validation report, publishes only if hard checks pass; `mm refresh --dry-run` locally).

## Reference material

`docs/reference/austin-watch-lessons.md` summarizes the deleted Austin Watch project and
which of its pieces are worth reusing. Its code snapshot is a file in the owner's Claude
Project (`austin-watch-reference.zip`), not in this repo — never commit it or copy it
wholesale; reuse piece by piece with tests.
