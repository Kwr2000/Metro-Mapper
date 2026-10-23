# P1-06 — Schools (outline; refined after Q1 and Q2)

- **Agents:** Claude verifies, Codex builds. Wave 1b. **Depends on:** P1-02, owner decisions Q1, Q2.

**Claude first:** finish the district inventory in `docs/SOURCES.md` (Round Rock, Georgetown,
Manor, Del Valle, Eanes, Lake Travis, San Marcos, Liberty Hill, Lago Vista, Jarrell, Wimberley,
Pflugerville, Leander, Hutto, Elgin, Taylor, Hays CISD, Dripping Springs, AISD). For each:
the current school year of the zones, a machine-readable layer (yes/no), and the official
finder link. Probe NCES school locations and TIGER unified school districts.

**Build:**
- District boundaries (TIGER) and campus points (NCES), always.
- TEA 2026 ratings and the School Progress / Academic Growth domains per campus if Q2 allows,
  marked preliminary until the 2026-12-11 final release; otherwise a link to the campus's TEA
  page.
- Attendance zones only for districts with a current, machine-readable layer and Q1 approval.
  Elsewhere the area shows "Zones not available — use <district>'s finder" with the link.
  Never draw zones around campuses or assign the nearest campus.
