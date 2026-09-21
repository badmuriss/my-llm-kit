# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "jev-ultrafast @ git+https://github.com/browser-use/jev-ultrafast@1231850a0bf1a0c0341fe408ef1668dbbfdfac46",
# ]
# ///
"""Run pinned Jev Ultrafast using OpenRouter decisions and its text helper."""

import argparse
import base64
import json
import os
from pathlib import Path
import sys

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
OPENROUTER_URL = "https://openrouter.ai/api/alpha/decisions"


class SetupError(ValueError):
    """A safe, actionable preflight diagnostic."""


def configure(model, env):
    """Adapt only the upstream decision transport; preserve its response guards."""
    key = env.get("OPENROUTER_API_KEY")
    if not key and not env.get("TYPESAFE_API_KEY"):
        raise SetupError("Set OPENROUTER_API_KEY or TYPESAFE_API_KEY")
    if key:
        upstream_post = model.post_json

        def post_json(url, original_key, body):
            if url == TYPESAFE_URL:
                return upstream_post(
                    OPENROUTER_URL, key,
                    {**body, "model": env.get("JEV_OPENROUTER_MODEL", "typesafe/jev-1.13")},
                )
            return upstream_post(url, original_key, body)

        model.post_json = post_json
        # Upstream reads this variable before calling the adapted transport.
        env["TYPESAFE_API_KEY"] = key
    if not env.get("TEXT_MODEL_API_KEY") and key:
        env["TEXT_MODEL_API_KEY"] = key
    env.setdefault("TEXT_MODEL_BASE_URL", "https://openrouter.ai/api/v1")
    env.setdefault("TEXT_MODEL", "inception/mercury-2.5")
    env.setdefault("TEXT_MODEL_REASONING", "none")
    return "openrouter" if key else "typesafe"


def probe(model):
    state = {"url": "https://example.invalid", "title": "Fixture",
             "text": "The requested result is visible.", "actions": []}
    result = model.choose(state, "Stop when the requested result is visible.", [])
    return {"model": result["model"], "operation": result["operation"],
            "latency_ms": result["latency_ms"], "usage": result["usage"]}


def save_evidence(browser, directory):
    directory.mkdir(parents=True, exist_ok=False)
    page = browser.observe(screenshot=False)
    (directory / "page.json").write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        png = browser.call("Page.captureScreenshot", format="png")["data"]
        (directory / "page.png").write_bytes(base64.b64decode(png, validate=True))
        return {"screenshot": "captured"}
    except Exception as error:
        return {"screenshot": "unobserved", "capture_error_type": type(error).__name__}


def run_agent(agent_factory, url, goal, max_steps, evidence_dir=None):
    with agent_factory(url, goal) as agent:
        state = agent.snapshot()
        for _ in range(max_steps):
            state = agent.command("tick")
            if state["status"] in {"done", "blocked"}:
                break
        status = state["status"]
        result = {"status": status if status in {"done", "blocked"} else "step_limit",
                  "actions": len(state["history"]), "elapsed_ms": state["elapsed_ms"],
                  "verified": False}
        if evidence_dir is not None:
            result["evidence"] = save_evidence(agent.browser, evidence_dir)
        return result, 0 if status == "done" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--probe", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--goal")
    parser.add_argument("--evidence-dir", type=Path,
                        help="Save observed final page and PNG before closing the owned tab")
    parser.add_argument("--max-steps", type=int, default=30, choices=range(1, 61), metavar="1..60")
    args = parser.parse_args(argv)
    if not (args.check or args.probe) and not (args.url and args.goal):
        parser.error("--url and --goal are required for a browser run")
    try:
        from jev_ultrafast import Agent, model
        from browser_harness.admin import daemon_browser_ready

        provider = configure(model, os.environ)
        if args.probe:
            print(json.dumps(probe(model)))
            return 0
        if not os.environ.get("TEXT_MODEL_API_KEY"):
            raise SetupError("Set TEXT_MODEL_API_KEY for text entry")
        connected = daemon_browser_ready()
        if args.check:
            print(json.dumps({"provider": provider, "browser_connected": connected,
                              "api_verified": False}))
            return 0 if connected else 2
        if not connected:
            raise SetupError("No active Browser Harness connection; run its --doctor")
        if args.evidence_dir is not None and args.evidence_dir.exists():
            raise SetupError("Use a new --evidence-dir; existing evidence is never overwritten")
        result, code = run_agent(Agent, args.url, args.goal, args.max_steps, args.evidence_dir)
        print(json.dumps(result))
        return code
    except SetupError as error:
        print(json.dumps({"status": "unavailable", "reason": str(error), "verified": False}), file=sys.stderr)
        return 2
    except (Exception, KeyboardInterrupt) as error:
        # Provider/browser exception text can contain URLs, page content or secrets.
        print(json.dumps({"status": "error", "error_type": type(error).__name__,
                          "verified": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
