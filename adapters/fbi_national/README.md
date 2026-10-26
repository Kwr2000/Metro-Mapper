# FBI national reported-crime comparisons

Three annual, budgeted requests read the FBI Crime Data API's summarized national V, P and
ARS (arson) series. The adapter publishes non-spatial benchmarks in the `dps_agency` namespace, never
map features, estimates or peer-city crime comparisons. `layers/fbi_national_benchmarks.yaml`
is non-published scheduling/source metadata so the existing annual refresh can discover it.

The selected year follows DPS: UTC run year minus one in July–December, minus two before
July. All twelve monthly counts and positive participating populations must exist. Annual
rate is total reported offenses divided by the mean participating population, per 1,000.
V and P each use their own participating-population denominator. Summarized P includes arson
(Claude's probe, 2026-10-25: P 5,174,662 = burglary 650,580 + larceny 3,824,966 + motor vehicle
theft 666,315 + arson 32,801), while DPS Part I excludes it, so Part I = V rate + (P - ARS) rate.
The note distinguishes reported counts from FBI estimates and states approximate coverage.

`FBI_API_KEY` is read from the environment only at the transport boundary. It is added to
that outbound URL as `API_KEY`, as required by this API, never to planned request params,
fixtures, records, logs or publications. Transport errors discard the URL and response.
Missing credentials fail clearly. Both live workflows pass the secret; agents never create
accounts or keys. Raw retention and recording remain off.

`v.json` and `p.json` are small synthetic native response shapes, not live observations.
Claude probes the documented endpoint and checks coverage, series definition and approximately
3.3 violent offenses per 1,000 before removing the first-live-check gate.
