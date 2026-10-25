# How Claude reviews a Codex PR and runs the first live check

The procedure every reviewing session follows (any Claude model). It turns AGENTS.md's
"before merging" rule into steps. When in doubt, stop and ask the owner; don't improvise.

## 0. Set up

- Work in a fresh clone of `Kwr2000/metro-mapper` on `main`. Read `AGENTS.md`,
  `docs/STATUS.md`, this file, and the task spec in `docs/tasks/`.
- Use `gh api` REST only (GraphQL may fail). Actions logs can't be downloaded; read a run's
  summary from its annotations:
  `gh api repos/Kwr2000/metro-mapper/check-runs/<job id>/annotations --jq '.[].message'`
  (job id from `gh api repos/Kwr2000/metro-mapper/actions/runs/<run id>/jobs --jq '.jobs[0].id'`).
- The workspace usually can't reach data sources (proxy 403). Live data only comes through the
  `Live run` workflow on GitHub. Never call a source from your own shell.
- Only one session works on a given PR. Don't touch PRs another session is handling.

## 1. Review the code against the spec

- `git fetch origin pull/<n>/head:review<n>`; read every changed file. Check each "Rules",
  "Checks", "Tests" and "Other requirements" item in the spec is actually implemented.
- Ground rules to check every time: no personal fields read or stored (owner, mail, exemption,
  legal description, names); demographic layers set `demographic: true`; missing values are
  null, never 0; every layer has attribution, license (or empty) and as-of; no source calls in
  tests; budgets and live gates exactly as approved in `docs/DECISIONS.md`.
- **Real data differs from fixtures.** Before the live run, compare the fixtures' field types and
  formats with what the spec says the real source holds (look for: numbers stored as decimals,
  codes with letters, blank vs "0" IDs, extra columns, quoted CSV fields, header spellings).
  Past misses: a precinct key stored as a float (`5450.0`), agency codes with letters
  (`TX227289E`). If a test only uses the convenient shape, add one with the real shape.
- Small fixes (a few lines plus a test): push them to the PR branch with a clear commit. Anything
  bigger, or a change to what the spec asked for: stop and report to the owner.

## 2. Test locally

- `pip install -e "pipeline[dev]" --break-system-packages`, `cd web && npm ci`.
- `make test` (full suite) must pass. If web code changed, also `cd web && npm run e2e`.
- CI must be green on the PR's latest commit:
  `gh api repos/Kwr2000/metro-mapper/commits/<sha>/check-runs --jq '.check_runs[] | .name+" "+.conclusion'`.
- Merge: `gh api -X PUT repos/Kwr2000/metro-mapper/pulls/<n>/merge -f merge_method=squash`.

## 3. Live check (sources the PR adds or changes)

- Start: `gh api -X POST repos/Kwr2000/metro-mapper/actions/workflows/live-run.yml/dispatches -f ref=main -f 'inputs[adapter]=<id>' -f 'inputs[first_check]=<true for a gated source, else false>'`.
- Check the budget first (`config/budgets.yaml` vs calls already made today in
  `data/runs/ingestion_runs.jsonl`, UTC day). Never exceed it; never change a budget or schedule.
- Read the summary annotations. Compare every number with the spec's "Done when" / expected
  values. A failed run publishes nothing and is safe: find the cause, fix it (step 1 rules), merge
  the fix, and run again within the budget.
- The workflow pushes `data/<adapter>-<run id>`. To merge it: fetch that branch with an explicit
  refspec (`git fetch origin "+refs/heads/data/<branch>:refs/remotes/origin/data/<branch>"`),
  branch from it, rebase on `main`, open a PR, wait for green CI, merge.
- **Also merge the run log line of any failed live run** (append it to
  `data/runs/ingestion_runs.jsonl` in time order) so its calls count against the budget.
- First check passed → in the same PR: remove the adapter from `config/live_gates.yaml`, update
  any test that asserts the gate (assert it is *not* gated, citing the run id), add a DECISIONS
  entry with the run id and key numbers.
- Grep stored data for personal-field names (e.g. `owner`, `mail`, `surname`) — expect none.

## 4. Close out

- Update `docs/STATUS.md` (Done, Next, Open issues, Waiting on the owner) and `docs/DECISIONS.md`.
  Docs-only PRs may merge without CI.
- Tidy obvious duplicates in DECISIONS (e.g. an owner approval recorded twice).
- Report to the owner in plain words: what was merged, live numbers vs expected, anything held
  back and why, and any decision they need to make. Keep it short.

## Stop and ask the owner (AGENTS.md) before

Starting a new phase, any spending, a source with unclear terms, changing a schedule or budget,
anything touching personal data, any change to how demographics are used, or a fix that changes
what the spec asked for.
