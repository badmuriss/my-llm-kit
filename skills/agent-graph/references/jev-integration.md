# Jev in the existing harness

Use the installed `computer-use` skill for browser tasks. A working `jev-agent`
installation may be reused; the kit also ships a pinned runner for hosts without
that local adaptation. Verify the browser connection, not only the wrapper's
credential check. Jev chooses bounded DOM actions; it does not own scheduling,
worker lifecycle, permission decisions or acceptance grades.

## Browser ownership

For direct work, the Jev runner creates and closes one tab on the connected
Browser Harness browser. It leaves the pre-existing browser and daemon alone.
After partial execution, inspect current state before handing the task to Orca.

In a graph run, register owned processes/browser resources through the existing
coordinator before side effects and retain cleanup evidence on that attempt.
Do not point Jev at another worker's browser. The current runner creates a fresh
tab; it cannot bind to an existing Orca `browser_page_id` or emit the driver's
reserve/bind/capture/release receipts. For tasks requiring that managed surface,
keep using the active driver's supported browser backend. Do not fabricate
surface receipts or represent an external CDP tab as an Orca-owned surface.

A separate, explicitly owned Browser Harness session can be used only where the
existing task contract permits externally managed resources and its coordinator
can verify their cleanup. Jev's `done` and process exit are not check evidence.
Capture the requested state and verify it independently before grading.

## Advisory evaluator

The coordinator can reuse Foreman's narrow semantic questions through Jev without
installing Foreman's scheduler. After `sync` collects fresh worker output, use the
run's pinned entrypoint:

```sh
python3 "<pinned-entrypoint>" assess --repo "<project>" --change <slug> --run-id <run-id> --generation <n> --attempt <attempt-id> --json
```

`OPENROUTER_API_KEY` is read from the coordinator environment. The request goes to
OpenRouter's `/api/alpha/decisions` with `typesafe/jev-1.13`. It sends the explicit
task contract and up to 12,000 characters of the latest poll's visible worker
output. Orca transcripts and terminal tails are supported, including Codex workers.
Hidden/unknown blocks and images are omitted and mark the observation incomplete.
The command does not fetch a diff or an entire session. Native host attempts with
no observable poll output return `worker_output_unavailable`.

The response contains probabilities for sufficient evidence, repeated failure,
scope drift, instruction drift, and meaningful progress. At least 0.8 evidence
sufficiency and 0.8 for a negative signal produce a fixed review suggestion. These
are heuristic thresholds, not calibrated error guarantees. Inspect the cited
observation before acting: absence of output and a normal wait do not prove a loop.
This evaluator does not check individual tool-call permissions or authorize them.

The existing journal stores `attempt_assessed`, its observation hash, source
receipt, revision, model, scores and reported usage. Unchanged successful
observations reuse the previous result. Calls are limited to one per 30 seconds
and 20 recorded evaluations per attempt, with a 10-second provider timeout and no
automatic retry. Concurrent state changes discard the result. These are request
limits, not a dollar cap; discarded concurrent requests may still incur provider
cost. A missing key, unsupported output or provider failure produces no guidance
and leaves the worker running.

Use this only as advice within the existing coordinator loop. It never sends a
message, interrupts a worker, dispatches, repairs, grants permissions, or changes
acceptance grades. Checks, ownership and cleanup remain authoritative. This is an
opt-in command; it does not install a background monitor or alter existing pinned
runs. New runs include the evaluator in their frozen runtime.

## No compaction

No compaction hook is enabled. The harness does not own the Codex-in-Orca host
transcript. Preserve task capsules, journal events, requirements and check receipts.

Evaluation and sources: [Jev research](../../../research/2026-09-21-jev-harness.md).
