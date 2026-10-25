# FBI national reported-crime comparisons

Two annual, budgeted requests read the FBI Crime Data API's summarized national V and P
series. The adapter publishes non-spatial benchmarks in the `dps_agency` namespace, never
map features, estimates or peer-city crime comparisons. `layers/fbi_national_benchmarks.yaml`
is non-published scheduling/source metadata so the existing annual refresh can discover it.

The selected year follows DPS: UTC run year minus one in July–December, minus two before
July. All twelve monthly counts and positive participating populations must exist. Annual
rate is total reported offenses divided by the mean participating population, per 1,000.
V and P each use their own participating-population denominator; add those rates for Part I.
The note distinguishes reported counts from FBI estimates and states approximate coverage.
The first live check must verify that summarized P excludes arson before ungating; no
separate arson series is requested or added. If the live definition includes arson, keep the
gate and settle its subtraction with Claude rather than publishing a mismatched comparison.

`FBI_API_KEY` is read from the environment only at the transport boundary. It is added to
that outbound URL as `API_KEY`, as required by this API, never to planned request params,
fixtures, records, logs or publications. Transport errors discard the URL and response.
Missing credentials fail clearly. Both live workflows pass the secret; agents never create
accounts or keys. Raw retention and recording remain off.

`v.json` and `p.json` are small synthetic native response shapes, not live observations.
Claude probes the documented endpoint and checks coverage, series definition and approximately
3.3 violent offenses per 1,000 before removing the first-live-check gate.
