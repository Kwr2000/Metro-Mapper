# P1-09 — Monthly refresh and validation report (outline)

- **Agent:** Claude. Wave 1c. **Depends on:** P1-02..P1-07.

- One scheduled workflow (monthly, e.g. the 3rd at 09:15 UTC) runs the adapters that are due,
  builds `validation.json` plus a readable report against the targets in `docs/PLAN.md`, and
  publishes. If a hard check fails, nothing new is published and the previous month stays live.
- The run log is committed every run (keeps the schedule alive under the 60-day rule).
- Changing this schedule later needs the owner's approval (AGENTS.md).
