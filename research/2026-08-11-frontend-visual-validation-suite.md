# Frontend visual validation suite

## Question and decision rule

Question: Which existing tooling should the harness reuse to validate every changed frontend surface across desktop, notebook, tablet and mobile?

Criterion: Choose a local-first browser suite that can reproduce routes, component states, viewports and browser engines, while retaining mandatory semantic inspection by a vision-capable tool.

Falsifier: Reject the approach if it cannot produce deterministic screenshots for all required profiles or if it treats a pixel comparison as proof that the interface is usable and correct.

## Findings

Playwright is the base capture suite. Its projects run the same tests with different browsers, devices and configurations. Its official examples include Chromium, Firefox, WebKit and emulated mobile devices. Source: https://playwright.dev/docs/test-projects, accessed 2026-08-11.

Playwright device emulation controls viewport, screen size, user agent and touch behavior. It also permits explicit viewport overrides. This supports a fixed harness matrix without coupling the harness to one application framework. Source: https://playwright.dev/docs/emulation, accessed 2026-08-11.

Playwright's screenshot assertion supplies baseline comparison, but its documentation warns that rendering varies with operating system, browser version, settings and hardware. Baselines therefore complement vision review and must run in a stable environment. Source: https://playwright.dev/docs/test-snapshots, accessed 2026-08-11.

Storybook is useful when a project already expresses component states as stories. Its viewport feature supports custom responsive profiles, and its visual-testing workflow turns stories into visual tests. The official visual service is hosted, so it is optional rather than a harness dependency. Sources: https://storybook.js.org/docs/essentials/viewport and https://storybook.js.org/docs/writing-tests/visual-testing, accessed 2026-08-11.

No installed local skill combined a complete responsive matrix, deterministic browser capture, per-image vision inspection and an executable completion gate. `computer-use` provides the inspection mechanism, but not coverage planning or evidence validation. Local source: `/home/badmuriss/.agents/skills/computer-use/SKILL.md`, inspected 2026-08-11.

A weak sample of three public skills confirmed useful reusable pieces but not the full contract. LambdaTest's SmartUI skill supplies multi-browser viewport baselines, Metaswarm's visual-review skill supplies Playwright capture followed by agent inspection, and TestDino's Playwright skill supplies reliable responsive and regression-test patterns. None of the sampled skills couples every changed state to a mandatory platform matrix and an executable vision-evidence gate. Sources: https://github.com/LambdaTest/agent-skills/blob/0491a3a29aa18558d2c3c64ff09367adb976c56f/smartui-skill/SKILL.md, https://github.com/dsifry/metaswarm/blob/33d39f776f7fe29098dcf048955756a237e8cb40/skills/visual-review/SKILL.md and https://github.com/testdino-hq/playwright-skill/blob/d3be9ca4d7303e2aee3eba4842963abf573117b0/core/SKILL.md, accessed 2026-08-11.

## Decision

Create `frontend-visual-validation` as the mandatory orchestration skill. Use Playwright when present, Storybook when present for isolated states, and the existing `impl` evidence validator as the final gate. Require the canonical platform matrix for every changed surface and state. Keep hosted regression services optional.

## Disagreements and limits

Pixel baselines detect visual change but do not establish semantic correctness. Vision review can detect semantic layout failures but does not provide stable historical regression comparison. The harness requires both when a baseline suite already exists and always requires vision review.

Emulated WebKit and device profiles are not physical-device testing. Production applications whose risk requires real hardware still need a device-lab or hosted real-device layer outside this harness.

## Sources consulted

- https://playwright.dev/docs/test-projects, accessed 2026-08-11.
- https://playwright.dev/docs/emulation, accessed 2026-08-11.
- https://playwright.dev/docs/test-snapshots, accessed 2026-08-11.
- https://github.com/microsoft/playwright/blob/main/packages/isomorphic/deviceDescriptorsSource.json, accessed 2026-08-11.
- https://storybook.js.org/docs/essentials/viewport, accessed 2026-08-11.
- https://storybook.js.org/docs/writing-tests/visual-testing, accessed 2026-08-11.
- https://github.com/LambdaTest/agent-skills/blob/0491a3a29aa18558d2c3c64ff09367adb976c56f/smartui-skill/SKILL.md, accessed 2026-08-11.
- https://github.com/dsifry/metaswarm/blob/33d39f776f7fe29098dcf048955756a237e8cb40/skills/visual-review/SKILL.md, accessed 2026-08-11.
- https://github.com/testdino-hq/playwright-skill/blob/d3be9ca4d7303e2aee3eba4842963abf573117b0/core/SKILL.md, accessed 2026-08-11.
