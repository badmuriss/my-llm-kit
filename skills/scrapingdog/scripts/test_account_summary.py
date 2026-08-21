#!/usr/bin/env python3
"""Prove account_summary.sh prints usage fields and never leaks account secrets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "account_summary.sh"
SECRETS = {"email": "owner@example.org", "username": "owner-name", "apiKey": "sk-very-secret-key"}


def run(env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("SCRAPINGDOG_API_KEY", "SCRAPINGDOG_ACCOUNT_FIXTURE")}
    env.update(env_extra)
    return subprocess.run([str(SCRIPT)], capture_output=True, text=True, env=env)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "account.json"
        fixture.write_text(json.dumps({**SECRETS, "requestUsed": 120, "requestLimit": 1000, "concurrencyLimit": 5, "pack": "Lite"}))
        result = run({"SCRAPINGDOG_ACCOUNT_FIXTURE": str(fixture)})
        combined = result.stdout + result.stderr
        assert result.returncode == 0, combined
        assert result.stdout.strip() == "120/1000 remaining=880 concurrency=5 pack=Lite", result.stdout
        for name, value in SECRETS.items():
            assert name not in combined and value not in combined, f"leaked {name}"

    missing = run({})
    assert missing.returncode == 2, f"expected exit 2 without key, got {missing.returncode}"
    assert missing.stdout == "", missing.stdout
    print("account_summary: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
