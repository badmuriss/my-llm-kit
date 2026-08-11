# Playwright integration

Extend an existing Playwright configuration with the canonical projects. Keep authentication, web-server and fixture settings from the application.

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  projects: [
    {
      name: "visual-desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1920, height: 1080 },
      },
    },
    {
      name: "visual-notebook",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1366, height: 768 },
      },
    },
    {
      name: "visual-tablet",
      use: devices["iPad (gen 7)"],
    },
    {
      name: "visual-mobile",
      use: devices["iPhone 13"],
    },
  ],
});
```

Wait for observable application state, not a fixed timeout. Capture evidence in CSS pixels:

```ts
await expect(page.getByRole("main")).toBeVisible();
await page.screenshot({
  path: evidencePath,
  fullPage: true,
  animations: "disabled",
  caret: "hide",
  scale: "css",
});
```

If the project already owns stable baselines, keep `toHaveScreenshot()` as an additional regression check. Never update baselines merely to make a failing change green. Inspect the changed baseline and the evidence PNG with vision first.

Use project fixtures or public test seams to reach loading, empty, error and populated states. Do not use `page.evaluate()` to force layout, replace text or hide a defect. Mask only truly nondeterministic third-party content, and record the mask in the task note.
