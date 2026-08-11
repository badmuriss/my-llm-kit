---
name: frontend-visual-validation
description: Validate every rendered frontend change on its actual supported platforms with reproducible browser screenshots and vision review. Use whenever Codex creates, edits, fixes, refactors or reviews UI, CSS, responsive layouts, routes, components, visual states, interactions or frontend assets, and before declaring any frontend implementation complete.
---

# Frontend Visual Validation

Treat browser automation and vision as separate mandatory layers. Browser checks produce reproducible states and screenshots. Vision decides whether the rendered result is correct.

## Workflow

1. Inventory every changed route or component and every affected state. Include loading, empty, error, populated, disabled, expanded, modal and post-interaction states when the change can render them.
2. Read [platform-matrix.md](references/platform-matrix.md). Decide the supported platforms separately for each surface and state from product requirements, existing routes, distribution targets and adjacent tests. Use every profile for general responsive UI. Do not test nonexistent targets.
3. Record each decision as `Visual-Scope:` with a concrete reason. Never label a surface platform-specific merely because the other layouts are currently broken.
4. Run `agent-resource-guard check --intent heavy --prune` before starting or reusing browser automation.
5. Reuse the project's Playwright setup when present and read [playwright.md](references/playwright.md). Reuse Storybook for isolated component states when present. Do not add a hosted visual-testing dependency by default.
6. Stabilize data, time, animations and network responses. Reach the declared state through real behavior or an existing deterministic fixture. Do not edit the DOM into the expected appearance.
7. Capture one PNG per expectation under `.visual-evidence/<change>/`. With Playwright, use CSS-pixel screenshot scale so the PNG width matches the declared viewport.
8. Inspect every PNG individually with `view_image` or `computer-use`. Check all edges and the main content for clipping, overlap, overflow, unreadable text, broken hierarchy, incorrect state, unusable controls and touch-target problems.
9. Fix every observed defect, recapture the affected scope and inspect it again. A pixel diff can detect change, but it cannot replace vision review.
10. Record the exact screenshot hash and a concrete observation in the task manifest. Pass that manifest to `impl_state.py` as file evidence.

## Existing suites

- Prefer Playwright projects and `toHaveScreenshot()` when the application already uses Playwright.
- Prefer Storybook stories for exhaustive component states when Storybook already exists.
- Keep Chromatic, Percy, Argos and similar hosted baseline services optional. They add regression history, not semantic visual judgment.
- Keep the `impl` manifest as the completion gate even when another visual suite passes.

## Evidence contract

Use:

```text
Visual-Scope: <route-or-component> | <state> | <platforms> | <reason>
Visual: <id> | <route-or-component> | <platform> | <width>x<height> | <state>
```

The gate rejects a missing or vague scope, expectations outside the scope, missing declared platforms, noncanonical dimensions, corrupt PNGs, screenshots changed after review, failed observations and manifests that do not name a vision-capable reviewer.

## Stop conditions

If a platform cannot be captured or inspected, mark the evidence unobserved or the task blocked. Never pass on code tests, DOM output, accessibility trees, pixel diffs or file existence alone.
