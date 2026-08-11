---
name: frontend-visual-validation
description: Validate every rendered frontend change across desktop, notebook, tablet and mobile with reproducible browser screenshots and vision review. Use whenever Codex creates, edits, fixes, refactors or reviews UI, CSS, responsive layouts, routes, components, visual states, interactions or frontend assets, and before declaring any frontend implementation complete.
---

# Frontend Visual Validation

Treat browser automation and vision as separate mandatory layers. Browser checks produce reproducible states and screenshots. Vision decides whether the rendered result is correct.

## Workflow

1. Inventory every changed route or component and every affected state. Include loading, empty, error, populated, disabled, expanded, modal and post-interaction states when the change can render them.
2. Read [platform-matrix.md](references/platform-matrix.md). Declare the full canonical matrix for each surface and state. Do not collapse platforms into one responsive screenshot.
3. Run `agent-resource-guard check --intent heavy --prune` before starting or reusing browser automation.
4. Reuse the project's Playwright setup when present and read [playwright.md](references/playwright.md). Reuse Storybook for isolated component states when present. Do not add a hosted visual-testing dependency by default.
5. Stabilize data, time, animations and network responses. Reach the declared state through real behavior or an existing deterministic fixture. Do not edit the DOM into the expected appearance.
6. Capture one PNG per expectation under `.visual-evidence/<change>/`. With Playwright, use CSS-pixel screenshot scale so the PNG width matches the declared viewport.
7. Inspect every PNG individually with `view_image` or `computer-use`. Check all edges and the main content for clipping, overlap, overflow, unreadable text, broken hierarchy, incorrect state, unusable controls and touch-target problems.
8. Fix every observed defect, recapture the affected matrix and inspect it again. A pixel diff can detect change, but it cannot replace vision review.
9. Record the exact screenshot hash and a concrete observation in the task manifest. Pass that manifest to `impl_state.py` as file evidence.

## Existing suites

- Prefer Playwright projects and `toHaveScreenshot()` when the application already uses Playwright.
- Prefer Storybook stories for exhaustive component states when Storybook already exists.
- Keep Chromatic, Percy, Argos and similar hosted baseline services optional. They add regression history, not semantic visual judgment.
- Keep the `impl` manifest as the completion gate even when another visual suite passes.

## Evidence contract

Use:

```text
Visual: <id> | <route-or-component> | <platform> | <width>x<height> | <state>
```

The gate rejects an incomplete platform matrix, noncanonical dimensions, missing or corrupt PNGs, screenshots changed after review, failed observations and manifests that do not name a vision-capable reviewer.

## Stop conditions

If a platform cannot be captured or inspected, mark the evidence unobserved or the task blocked. Never pass on code tests, DOM output, accessibility trees, pixel diffs or file existence alone.
