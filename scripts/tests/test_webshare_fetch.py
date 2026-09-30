from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import textwrap
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "webshare_fetch.py"


WEBSHARE_DOUBLE = r"""#!/usr/bin/env python3
import os
from pathlib import Path
import sys

plan = sys.argv[sys.argv.index("--plan") + 1]
with Path(os.environ["PLAN_LOG"]).open("a", encoding="utf-8") as log:
    log.write(plan + "\n")
print(f"http://user-{plan}:secret-{plan}@proxy.test:8080")
"""


CURL_DOUBLE = r"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import re
import sys

args = sys.argv[1:]
config = sys.stdin.read()
match = re.search(r"user-(\d+):secret-(\d+)@", config)
if not match or match.group(1) != match.group(2):
    sys.exit(2)
plan = match.group(1)
if any("secret-" in argument for argument in args):
    sys.exit(2)
with Path(os.environ["CURL_LOG"]).open("a", encoding="utf-8") as log:
    log.write(plan + "\n")
scenario = json.loads(os.environ["FETCH_SCENARIO"])[plan]
output = Path(args[args.index("--output") + 1])
output.write_bytes(scenario.get("body", "").encode())
sys.stderr.write(f"raw leak secret-{plan} http://proxy.test\n")
sys.stdout.write(str(scenario.get("status", "000")))
sys.exit(scenario.get("returncode", 0))
"""


class WebshareFetchBehavior(unittest.TestCase):
    def run_fetch(self, scenario: dict[str, dict[str, object]]) -> tuple[subprocess.CompletedProcess[bytes], list[str], list[str]]:
        with TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            bin_directory = directory / "bin"
            bin_directory.mkdir()
            for name, source in (("webshare", WEBSHARE_DOUBLE), ("curl", CURL_DOUBLE)):
                executable = bin_directory / name
                executable.write_text(textwrap.dedent(source), encoding="utf-8")
                executable.chmod(0o755)

            config = directory / "webshare.json"
            config.write_text(
                json.dumps({"datacenter_plan_id": 11, "residential_plan_id": 22}),
                encoding="utf-8",
            )
            plan_log = directory / "plans.log"
            curl_log = directory / "curl.log"
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{bin_directory}{os.pathsep}{environment.get('PATH', '')}",
                    "WEBSHARE_API_KEY": "test-only-key",
                    "PLAN_LOG": str(plan_log),
                    "CURL_LOG": str(curl_log),
                    "FETCH_SCENARIO": json.dumps(scenario),
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "https://example.com/resource",
                    "--config",
                    str(config),
                    "--timeout",
                    "2",
                ],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            plans = plan_log.read_text(encoding="utf-8").splitlines() if plan_log.exists() else []
            curls = curl_log.read_text(encoding="utf-8").splitlines() if curl_log.exists() else []
            return result, plans, curls

    def assert_no_private_output(self, result: subprocess.CompletedProcess[bytes]) -> None:
        combined = result.stdout + result.stderr
        self.assertNotIn(b"secret-", combined)
        self.assertNotIn(b"proxy.test", combined)
        self.assertNotIn(b"test-only-key", combined)

    def test_datacenter_success_does_not_resolve_residential_proxy(self) -> None:
        result, plans, curls = self.run_fetch(
            {"11": {"status": 200, "body": "datacenter body"}}
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"datacenter body")
        self.assertEqual(plans, ["11"])
        self.assertEqual(curls, ["11"])
        self.assert_no_private_output(result)

    def test_eligible_datacenter_failures_return_only_residential_body(self) -> None:
        for datacenter_result in (
            {"status": 403, "body": "blocked body"},
            {"status": "000", "body": "partial body", "returncode": 7},
        ):
            with self.subTest(datacenter_result=datacenter_result):
                result, plans, curls = self.run_fetch(
                    {
                        "11": datacenter_result,
                        "22": {"status": 200, "body": "residential body"},
                    }
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"residential body")
                self.assertEqual(plans, ["11", "22"])
                self.assertEqual(curls, ["11", "22"])
                self.assert_no_private_output(result)

    def test_not_found_does_not_consume_residential_proxy(self) -> None:
        result, plans, curls = self.run_fetch(
            {"11": {"status": 404, "body": "not found body"}}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(plans, ["11"])
        self.assertEqual(curls, ["11"])
        self.assertIn(b"HTTP 404", result.stderr)
        self.assert_no_private_output(result)

    def test_both_plans_fail_once_without_leaking_partial_bodies_or_credentials(self) -> None:
        result, plans, curls = self.run_fetch(
            {
                "11": {"status": "000", "body": "datacenter partial", "returncode": 7},
                "22": {"status": 503, "body": "residential failure"},
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(plans, ["11", "22"])
        self.assertEqual(curls, ["11", "22"])
        self.assertIn(b"no attempts remain", result.stderr)
        self.assert_no_private_output(result)


if __name__ == "__main__":
    unittest.main()
