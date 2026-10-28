# P3-01 — Batch listing check

- **Agent:** Codex. Branch `codex/p3-01-batch-check`. Regular (not draft) PR to `main`.
- **Phase:** 3 (approved by the owner 2026-10-27; plan in `docs/PLAN.md`). **Depends on:** P2-07
  (the "Check a home" page and its TypeScript ports) and P2-08 (ranges switched on). Start only
  after both are merged. Read `AGENTS.md`, the Phase 2 and 3 plans, and the P2-05 to P2-07 specs.
- **Web only.** No pipeline, adapter, config or manifest changes. No network beyond the site's
  own static files. The owner's file never leaves the browser.

## What the owner sees

On the Check a home page, a second tab **Check many listings**:

1. **Drop or choose a file**: a Redfin "Download all" CSV of a saved search (up to 350 rows), or
   **paste lines**, one listing per line: an address and an asking price, e.g.
   `1008 S 8th St #2, Austin, TX 78704 — $725,000` or tab/comma separated
   (`address<TAB>price`). A short note says: "Your file stays in this browser. Nothing is uploaded
   or saved unless you choose Save."
2. **Table**, one row per listing, sortable on every numeric column, filterable by county,
   category and "has a range":
   - Address (as matched), county, category, beds/baths/sq ft from the file when present, the
     appraisal record's living area and year built (and a ⚠ when the listing's sq ft differs from
     the appraisal's by more than 10%).
   - Asking price; asking $ per sq ft (appraisal living area).
   - Appraisal-based value range (low–high) when published; **position**: how far the asking
     price is below or above the range, in % of the centre (e.g. "12% below the range",
     "inside the range", "6% above the range"), and the range width (±10% / ±20%) with its flags.
   - Neighbourhood $/sq ft percentile of the asking price (from `hoods.json`), with n.
   - Days on market and HOA per month from the file when present.
   - A link to the home's card (`#/home?id=…`) and the listing URL from the file (opens in a new
     tab; never fetched by the site).
   - Unmatched rows go to a separate list with the normalized address searched and the reason
     (not found, several matches — pick one, outside the three counties, no price).
3. **Default sort:** position against the range, lowest first, then the $/sq ft percentile. The
   header explains: "Listings priced furthest below their appraisal-based range come first. A
   low price often has a reason the appraisal can't see — condition, layout, noise. Check the
   home's card before deciding." No "good deal", "bargain", "undervalued", "fair value",
   "overpriced" or "worth" anywhere (extend P2-07's banned-words test with "bargain" and
   "undervalued").
4. **Save (optional):** keep this list in the browser (`store.ts`, key per list name; at most 5
   lists, 400 rows each) and **Export CSV** of the table (generated in the browser, a download the
   owner starts). Clear button removes everything.

## Parsing

- **Redfin CSV:** find columns by header name, case-insensitive, trimming spaces, with these
  aliases: address `ADDRESS`; city `CITY`; state `STATE OR PROVINCE`, `STATE`; zip
  `ZIP OR POSTAL CODE`, `ZIP`; price `PRICE`, `LIST PRICE`; beds `BEDS`; baths `BATHS`; sq ft
  `SQUARE FEET`; lot `LOT SIZE`; year `YEAR BUILT`; days `DAYS ON MARKET`; HOA `HOA/MONTH`;
  status `STATUS`; type `PROPERTY TYPE`; url the column whose header starts with `URL`; lat/lon
  `LATITUDE`/`LONGITUDE`. Redfin puts a disclaimer row at the end of some files — skip rows
  without an address and price. Quoted fields, commas inside quotes, BOM, CRLF all handled (use a
  small tested CSV parser, no new dependency unless already in `web/`).
- Build the query string `address, city, state zip` and use the P2-07 `normalizeQuery`. Match with
  the P2-05 contract; a unit in the listing narrows condo matches.
- **Paste mode:** the price is the last `$`-number or plain number ≥ 10,000 on the line; the rest
  is the address.
- **Claude will verify the real Redfin headers** with a file the owner downloads, during review,
  and add any alias needed. The parser must report unknown headers it ignored (names only).

## Rules

- Nothing about the listings is sent anywhere or written outside `localStorage` (and only on
  Save). No analytics, no third-party requests. A test intercepts `fetch` and fails on any request
  outside the site's own `data/` path while a file is processed.
- Numbers: missing → "Not available", never 0. When `value_range.published` is false, the range
  and position columns are hidden and the table sorts by $/sq ft percentile.
- Performance: 350 rows load at most the shards they need (cache as in P2-07) and render in a few
  seconds; no blocking of the main thread over ~200 ms (process in chunks).
- Phone: the table becomes a list of cards with the same fields; sort and filter controls stay.

## Tests

CSV parser (quotes, embedded commas, BOM, CRLF, trailing disclaimer row, alias headers, unknown
headers reported); paste parsing (prices with `$`, commas, "k"? — no, reject "725k" with a
message); matching incl. units and several matches; position arithmetic (below/inside/above at the
boundaries); $/sq ft percentile; sq ft mismatch warning; sort and filters; save/restore/clear and
limits; export CSV content; no network beyond `data/`; banned words. E2E at 1440×900 and 390×844
with a synthetic Redfin-style CSV of 25 fixture listings (made-up addresses that exist in the
fixture shards).

## Other requirements

`make test` and `cd web && npm run e2e` pass; methodology page gets a short "Checking many
listings" section (what the position means and doesn't). STATUS one entry; DECISIONS for unsettled
choices.

## Done when

CI green, tests pass. Claude then checks with a real Redfin download from the owner (header names,
match rate, a few rows against their cards) before closing.
