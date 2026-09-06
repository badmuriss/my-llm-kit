---
name: readme-pass
description: Make a public repository README easier to understand and use. Apply when README structure or presentation is requested.
---

# readme-pass

Make the README useful before making it pretty. Optimize for a distracted reader who wants to know what the project does, how to install it, and whether it fits their stack.

## Workflow

1. Read the repository instructions, README, installer files, and manifest. Do not document unsupported behavior.
2. Find existing brand assets before generating a banner. Check `assets/`, `public/`, `docs/`, logos, and brand files.
3. Cut before adding. Remove repeated claims, generic motivation, stale implementation detail, and sections that restate a table.
4. Put the sections in this order when the project supports them:
   - one-line value
   - agent-first install
   - core workflow or example
   - included capabilities
   - compatibility
   - advanced setup and safety
   - credits and license
5. Apply the `writing` skill. Preserve facts, commands, links, names, and licenses.
6. Add presentation only after the content is lean.
7. Verify commands, anchors, links, supported operating systems, and the changed diff.

## Attention budget

- Answer "what is this?" in one sentence.
- Keep paragraphs to one idea and usually one to three sentences.
- Prefer a short table for repeated mappings such as skill to purpose or host to support.
- Show the main workflow once. Link or move deep internals instead of explaining them twice.
- Put copyable prompts and commands before implementation details.
- Keep examples small enough to understand without scrolling back.
- Delete any sentence that only announces importance or repeats the heading.
- Do not preserve prose merely because it already exists.

## Agent-first install

When setup changes the user's machine, place a copyable agent-install prompt before manual commands. Tell the agent to:

- detect the operating system and select a documented installer;
- read repository instructions before mutation;
- preserve local changes and user-owned configuration;
- run the documented dry-run or preview first;
- continue only when no blocker remains;
- verify the installed capability and report backups, skips, failures, and unverified steps.

Use only commands and operating systems present in the repo. Keep manual commands below the prompt as a fallback.

## Presentation

Preserve existing branding. Add a banner, badges or navigation only when the
requested presentation work benefits from them. A text cleanup does not require
image generation. Use a plain heading when no visual identity is available.

## Writing rules

Use sentence-case headings, plain words, and concrete claims. Avoid em dashes, decorative triads, boldface spam, empty promises, and repeated feature lists.

## Delivery

- Stage files only when staging, committing or PR preparation is requested.
- Inspect the changed content for private information before an authorized publication.
- Report what was cut, what moved, what was added, and what remains unverified.
