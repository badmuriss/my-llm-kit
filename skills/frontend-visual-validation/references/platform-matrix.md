# Canonical platform matrix

Use every profile for each changed surface and state.

| Platform | Viewport | Browser engine | Input model |
| --- | --- | --- | --- |
| `desktop` | `1920x1080` | Chromium | mouse and keyboard |
| `notebook` | `1366x768` | Chromium | mouse and keyboard |
| `tablet` | `810x1080` | WebKit | touch |
| `mobile` | `390x664` | WebKit | touch |

The desktop and notebook viewports are fixed harness policies. The tablet and mobile profiles track Playwright's current iPad and iPhone CSS viewports. Set screenshot `scale: "css"` when the emulated device has a higher device scale factor.

Example for one state:

```text
Visual: dashboard-desktop | /dashboard | desktop | 1920x1080 | populated
Visual: dashboard-notebook | /dashboard | notebook | 1366x768 | populated
Visual: dashboard-tablet | /dashboard | tablet | 810x1080 | populated
Visual: dashboard-mobile | /dashboard | mobile | 390x664 | populated
```

Playwright can run the same tests through projects with different device and browser settings. Reuse project fixtures for authentication and state setup. Use Chromium for the wide profiles and WebKit device emulation for touch profiles. Add Firefox or branded-browser projects when the change touches browser-specific behavior, but do not remove a canonical profile.

Primary references, accessed 2026-08-11:

- Playwright projects: https://playwright.dev/docs/test-projects
- Playwright emulation: https://playwright.dev/docs/emulation
- Playwright visual comparisons: https://playwright.dev/docs/test-snapshots
- Playwright device registry: https://github.com/microsoft/playwright/blob/main/packages/isomorphic/deviceDescriptorsSource.json
- Storybook viewport configuration: https://storybook.js.org/docs/essentials/viewport
- Storybook visual tests: https://storybook.js.org/docs/writing-tests/visual-testing
- LambdaTest SmartUI skill: https://github.com/LambdaTest/agent-skills/blob/0491a3a29aa18558d2c3c64ff09367adb976c56f/smartui-skill/SKILL.md
