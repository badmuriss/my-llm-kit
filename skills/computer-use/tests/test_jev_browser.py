import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

SPEC = importlib.util.spec_from_file_location(
    "jev_browser", Path(__file__).parents[1] / "scripts" / "jev_browser.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class ProviderRouting(unittest.TestCase):
    def test_routes_decisions_to_openrouter_without_redirecting_text_requests(self):
        post = Mock(return_value={"answers": {}})
        model = SimpleNamespace(post_json=post)
        env = {"OPENROUTER_API_KEY": "router-secret", "TYPESAFE_API_KEY": "native-secret",
               "TEXT_MODEL_API_KEY": "text-secret", "TEXT_MODEL_BASE_URL": "https://text.invalid/v1"}
        self.assertEqual(runner.configure(model, env), "openrouter")
        body = {"model": "jev-latest", "state": "fixture", "questions": {}}
        model.post_json(runner.TYPESAFE_URL, env["TYPESAFE_API_KEY"], body)
        post.assert_called_with(runner.OPENROUTER_URL, "router-secret",
                                {**body, "model": "typesafe/jev-1.13"})
        model.post_json("https://text.invalid/v1/chat/completions", "text-secret", body)
        post.assert_called_with("https://text.invalid/v1/chat/completions", "text-secret", body)
        self.assertEqual(body["model"], "jev-latest")
        self.assertEqual(env["TEXT_MODEL_API_KEY"], "text-secret")

    def test_keeps_native_transport_and_rejects_missing_credentials(self):
        post = Mock()
        model = SimpleNamespace(post_json=post)
        self.assertEqual(runner.configure(model, {"TYPESAFE_API_KEY": "native"}), "typesafe")
        self.assertIs(model.post_json, post)
        with self.assertRaises(ValueError):
            runner.configure(model, {})


class BoundedExecution(unittest.TestCase):
    def test_preserves_observation_when_screenshot_is_unavailable(self):
        browser = Mock()
        browser.observe.return_value = {"text": "Saved: Ana / Pro", "actions": []}
        browser.call.side_effect = TimeoutError("private provider detail")
        with tempfile.TemporaryDirectory() as temporary:
            result = runner.save_evidence(browser, Path(temporary) / "new")
            self.assertEqual(result, {"screenshot": "unobserved", "capture_error_type": "TimeoutError"})
            self.assertEqual(json.loads((Path(temporary) / "new" / "page.json").read_text())["text"], "Saved: Ana / Pro")
            self.assertFalse((Path(temporary) / "new" / "page.png").exists())

    def test_closes_the_agent_for_completion_blocking_budget_and_failure(self):
        for outcome, expected_code in (("done", 0), ("blocked", 2), ("ready", 2), (RuntimeError("failure"), None)):
            with self.subTest(outcome=outcome):
                state = {"status": outcome, "history": [], "elapsed_ms": 1}
                agent = Mock()
                agent.snapshot.return_value = state
                agent.command.side_effect = outcome if isinstance(outcome, Exception) else lambda _: state
                context = Mock()
                context.__enter__ = Mock(return_value=agent)
                context.__exit__ = Mock(return_value=False)
                if expected_code is None:
                    with self.assertRaises(RuntimeError):
                        runner.run_agent(Mock(return_value=context), "url", "goal", 2)
                else:
                    result, code = runner.run_agent(Mock(return_value=context), "url", "goal", 2)
                    self.assertEqual(code, expected_code)
                    self.assertFalse(result["verified"])
                    self.assertEqual(agent.command.call_count, 2 if outcome == "ready" else 1)
                    self.assertEqual(result["status"], "step_limit" if outcome == "ready" else outcome)
                context.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
