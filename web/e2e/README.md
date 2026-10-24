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
