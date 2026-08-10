---
name: readme-pass
description: "Give a public repo README top-starred presentation with agent-first installation, without dropping prose. use_when: make a README pretty, add banner or badges, add a copyable agent install prompt, or run a readme presentation pass. do_not_use_when: rewriting the documentation content itself."
---

# readme-pass

Presentation pass for a repo README, grounded in how top-starred repos open
(block/buzz, mvanhorn/last30days). The existing prose is never rewritten,
it only moves. If the prose needs work, that is a job for the unslop skill,
not this one.

## Header block

Insert this, in this order, before the current content:

0. Existing brand wins. Before generating anything, search the repo for
   official brand assets (`find . -iname "*logo*" -o -iname "*brand*"`,
   check `assets/`, `public/`, design PDFs). If a real logo exists, use it
   instead of a generated banner, with GitHub's dark/light switching:

   ```html
   <p align="center">
     <picture>
       <source media="(prefers-color-scheme: dark)" srcset="assets/logo-white.png">
       <img src="assets/logo-black.png" width="140" alt="...">
     </picture>
   </p>
   <h1 align="center">Project Name</h1>
   ```

   Match badge accent colors to the brand's palette. Only generate a
   banner when the repo has no identity of its own.
1. Centered banner (only when step 0 found no brand assets):
   `<p align="center"><img src="docs/banner.png" width="720" alt="..."></p>`
2. Centered bold tagline, one line, concrete value, no hype. Reuse the
   repo's own first sentence when it fits.
3. Centered badge row, shields.io with `style=flat-square`:
   - license badge matching the repo's actual license (no LICENSE file =
     no license badge, never invent one)
   - a static "agent skill" badge linking https://skills.sh when the repo
     is an installable skill
   - dynamic stars: `https://img.shields.io/github/stars/<owner>/<repo>?style=flat-square`
   - last commit: `https://img.shields.io/github/last-commit/<owner>/<repo>?style=flat-square`
4. Centered nav line with anchor links to the README's main sections.
   Check each anchor against GitHub slug rules: lowercase, spaces to
   dashes, dots and slashes dropped ("What setup.sh does" is
   `#what-setupsh-does`).
5. The install section, moved up from wherever it lives. Put a copyable
   agent-install prompt before manual commands whenever setup changes the
   user's machine. Most users will ask an agent to install the project.
   The prompt must tell the agent to:
   - detect the operating system and choose the documented installer;
   - read repository instructions before mutation;
   - preserve local changes and user-owned configuration;
   - run the documented dry-run or preview first;
   - proceed only when the preview has no blocker;
   - verify the installed capability, rerun to prove idempotence when the
     installer claims it, and report backups, skips, and unverified steps.

   Use only commands and operating systems the repository actually
   supports. Never invent an installer. Keep the existing manual commands
   below the prompt as a fallback for debugging and constrained environments.

Then the existing content follows, with at most light heading
reorganization so the anchors work. Drop the old H1: the banner carries
the wordmark.

## Banner

Generate with the image-gen skill (Codex, native rendering). Art
direction, non-negotiable:

- Dark background always, never white. Typographic, premium, minimalist:
  big repo wordmark plus a small tagline underneath, one accent color.
- Banned: mockups, people, generic AI icons, purple AI glow, pulsing
  dots, background grids.
- No em dash anywhere in the banner text. Accented characters spelled
  out explicitly in the prompt.
- Target 1600x400. The model usually renders taller; center-crop to 4:1
  and resize with ImageMagick, which is legitimate post-processing.
  Rendering text with ImageMagick is not.
- Inspect every PNG by reading it as an image before accepting it.
  Garbled text means regenerate natively, never overlay text with a tool.
- If image generation is unavailable or the quality stays bad, do not
  commit a bad image: fall back to a typographic
  `<h1 align="center">` with no image, and say so in the report.

## Writing rules for any new line

No em dash, sentence case in headings, no decorative triads, no empty
promises. Taglines and alt text follow the same rules.

## Delivery

- Commit message: `docs: readme presentation pass (banner, badges, nav)`.
- Stage only the README and the banner when the working tree has
  unrelated changes.
- Before pushing a public repo, grep the staged diff for private terms
  (client names, internal hosts, project codenames) and stop on any hit.
