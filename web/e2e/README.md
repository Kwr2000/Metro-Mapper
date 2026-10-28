# Local browser smoke

Run `make test` at the repo root to create the fixture build, then `cd web && npm run e2e`.
This starts `vite preview` on 127.0.0.1:4173, runs Chromium at 1440×900 and 390×844,
and saves filter/comparison screenshots in `e2e/artifacts/`.

Needs Python's Playwright package and Chromium locally. It uses the preinstalled
`chromium`/`chromium-browser` executable when available; `CHROMIUM_PATH` can select another.
If none is present, it uses Playwright's installed Chromium. No browser download is automatic.
The smoke refuses a build with live data and intercepts all external browser requests with
a plain local map background. It checks filters, map selection, two-area comparison, URL
restoration, note privacy, shortlist persistence and horizontal overflow at both sizes.

This is intentionally separate from Vitest and is not run or installed by CI.

P2-07 adds fixture home checks at both sizes. The harness creates a temporary root with
no canonical files, calls the existing homes publisher on adapter fixtures with networking
blocked, and copies only its generated homes files into ignored `web/public/data/`.
The web build derives small ID locator buckets from those publications. Pipeline fixtures
use different block-group IDs, so the home browser context supplies a coherent synthetic
area/name join; no adapter fixtures or real data are changed.

The home checks cover a unit address, no match, keyboard selection among multiple records,
a fresh-browser ID-only link (one locator plus one address shard), asking-price persistence
and absence from every request URL/share URL, unpublished/published metadata, a zoom-16
map click, a phone bottom sheet and page overflow. The test-only published metadata and
hood table remain labeled Test data. All external map requests are fulfilled locally.
Screenshots `home-hidden-*`, `home-range-*` and `home-map-*` go into ignored `artifacts/`.
The build scans every generated JS/HTML file for prohibited home-value wording; browser
checks scan rendered page text too. Playwright remains a local check, outside CI.

P3-03 also publishes the score from native adapter fixtures in the isolated root. The score
browser context supplies a coherent, explicitly Test data GEOID join because the adapters'
independent fixtures use different areas. At both sizes it checks slider defaults, keyboard
changes, reload persistence, fresh-browser view links, score mode and partial legend, a
source/dated popup breakdown and unchanged score settings when a People layer is switched on.
`score-panel-*` and `score-popup-*` screenshots are ignored local artifacts. No source requests
or Playwright CI steps are added.
