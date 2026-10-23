# P1-06 — Schools (outline; refined before build)

- **Agents:** Claude verifies, Codex builds. Wave 1b. **Depends on:** P1-02.

**Claude first:** finish the district list in `docs/SOURCES.md`: for every district touching
Travis, Williamson or Hays, its official school-finder link and the school year it covers.
Probe NCES school locations, TIGER unified school districts and TEA's data.texas.gov ratings
dataset (`nui6-x374`), and check whether TEA has posted 2025–26 ratings there.

**Build:**
- District boundaries (TIGER) and campus points (NCES), always.
- TEA ratings per campus from data.texas.gov (overall, Student Achievement, **School Progress**,
  **Academic Growth**, Closing the Gaps), labeled with their school year and "Source: Texas
  Education Agency via data.texas.gov". Growth is shown ahead of raw achievement.
- **No attendance zones are copied.** Each area shows "Assigned schools: check <district>'s
  school finder" with the link (owner decision 2026-10-23). Never draw zones around campuses or
  assign the nearest campus. Showing district zone layers live from the district's service is
  out of scope unless the owner approves it later.
- Content from tea.texas.gov itself is not republished.
