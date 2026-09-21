# Jev provider and evaluation notes

The pinned upstream runner uses a small transport adapter: only requests to the
TypeSafe decision endpoint are routed to OpenRouter. Upstream action selection,
DOM freshness, target validation and text generation remain upstream code. This
adapter exists because the pinned upstream does not expose decision-provider
configuration. The native TypeSafe transport remains available when no OpenRouter
key is set. No key is written to disk and no installed checkout is modified.

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Preferred decisions key and default text-helper key |
| `JEV_OPENROUTER_MODEL` | Defaults to `typesafe/jev-1.13` |
| `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` | Native fallback; upstream model default |
| `TEXT_MODEL_API_KEY` | Optional separate text-helper credential |
| `TEXT_MODEL_BASE_URL` | Defaults to `https://openrouter.ai/api/v1`; set with a non-OpenRouter text key |
| `TEXT_MODEL` | Defaults to `inception/mercury-2.5` |
| `TEXT_MODEL_REASONING` | Defaults to `none` |

Use `uv run <skill-dir>/scripts/jev_browser.py --probe` to verify the decision
API. It sends synthetic state and makes one paid call. `--check` makes no model
call and does not start a browser. To diagnose or establish a connection using
the same pinned dependency environment:

```sh
uv run --with 'browser-harness==0.1.13' browser-harness --doctor
```

Follow the upstream [connection guide](https://github.com/browser-use/browser-harness/blob/main/install.md)
when no connection is available. Reuse the user's configured daemon where possible.
The runner's step budget defaults to 30 prediction cycles and accepts `--max-steps`
from 1 to 60. Only `done` returns zero, but it still requires independent verification.
Connection errors and model failures never cause an automatic replay.

## Reproduce the paid local browser smoke test

This uses synthetic data, an isolated headless Chrome profile, a named daemon and
an ephemeral HTTP server. It closes its tab, stops its own daemon/browser/server,
and never attaches to the user's Chrome profile. Chrome/Chromium and uv must exist.
Run from any consumer project, resolving both scripts from this skill:

```sh
uv run --with 'jev-ultrafast @ git+https://github.com/browser-use/jev-ultrafast@1231850a0bf1a0c0341fe408ef1668dbbfdfac46' --python 3.12 python <skill-dir>/tests/smoke_browser.py .visual-evidence/jev-browser-integration
```

Inspect `saved.png` with vision and read `result.json`. The script independently
checks the saved DOM output; it does not treat the model's `DONE` as proof.
Linux Chrome was exercised. Native Windows and macOS execution remain unverified.

Sources accessed 2026-09-21: [TypeSafe API](https://docs.typesafe.ai/api.md),
[Jev Ultrafast](https://github.com/browser-use/jev-ultrafast),
[OpenRouter model](https://openrouter.ai/typesafe/jev-1.13).
