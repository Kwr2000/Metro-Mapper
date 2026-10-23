# P1-08 — Filters, comparison, shortlist, methodology (outline)

- **Agent:** Codex. Wave 1c. **Depends on:** P1-02..P1-07.

- Filter panel built from layer manifests (range sliders, category toggles). Demographic filters
  sit in their own section with neutral labels, with no default selection.
- Compare up to 4 areas side by side: every layer value with source, as-of, MOE and reliability.
- Shortlist and notes saved in localStorage only. Shareable URL with view state, never notes.
- Methodology page: units, naming rule, shrinkage, flood shares, access method, what
  "not available" means, and the demographics rule. Sources page generated from the registry.
- Desktop-first layout that still works at 390 px wide; Playwright smoke at 1440×900 and 390×844.
