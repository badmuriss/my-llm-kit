"""Paid, opt-in browser smoke test. Uses an isolated Chrome profile and synthetic data."""

import base64
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from jev_browser import configure, run_agent


def main():
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        raise SystemExit("Chrome/Chromium is required")
    evidence = Path(sys.argv[1]).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jev-smoke-") as temporary:
        root = Path(temporary)
        (root / "index.html").write_text('''<!doctype html><meta charset="utf-8">
<title>Jev local smoke</title><h1>Local browser test</h1>
<form onsubmit="event.preventDefault();document.querySelector('output').textContent=
'Saved: '+document.querySelector('input').value+' / '+document.querySelector('select').value">
<label>Name <input required></label><label>Plan <select><option>Basic</option>
<option>Pro</option></select></label><button>Save</button></form><output></output>''')
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=temporary)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        profile = root / "chrome"
        process = subprocess.Popen(
            [chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
             "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        admin = None
        try:
            port_file = profile / "DevToolsActivePort"
            deadline = time.monotonic() + 20
            while not port_file.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Isolated Chrome did not start")
                time.sleep(0.1)
            port = int(port_file.read_text().splitlines()[0])
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as response:
                endpoint = json.load(response)["webSocketDebuggerUrl"]
            os.environ["BU_NAME"] = f"kit-jev-smoke-{os.getpid()}"
            os.environ["BU_CDP_WS"] = endpoint
            from browser_harness import admin
            from jev_ultrafast import Agent, model

            configure(model, os.environ)
            admin.ensure_daemon(wait=15)
            observations = {}

            class VerifiedAgent(Agent):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.browser.call("Target.activateTarget", targetId=self.browser.target)

                def __exit__(self, *args):
                    try:
                        observations["saved"] = self.browser.evaluate("document.querySelector('output').textContent")
                        observations["usage"] = [d.get("usage", {}) for d in self.state["decisions"]]
                        observations["text_usage"] = [d.get("usage", {}) for d in self.state["text_calls"]]
                        self.browser.call("Target.activateTarget", targetId=self.browser.target)
                        png = self.browser.call("Page.captureScreenshot", format="png")["data"]
                        (evidence / "saved.png").write_bytes(base64.b64decode(png))
                    finally:
                        super().__exit__(*args)

            result, code = run_agent(
                VerifiedAgent, f"http://127.0.0.1:{server.server_port}/index.html",
                "Enter Ana in Name, select Pro in Plan, click Save once, and stop when Saved: Ana / Pro is visible.", 12,
                evidence / "final",
            )
            result.update(observations)
            result["verified"] = code == 0 and observations.get("saved") == "Saved: Ana / Pro"
            (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result))
            return 0 if result["verified"] else 1
        finally:
            try:
                if admin:
                    admin.restart_daemon(os.environ["BU_NAME"], require_clean=True)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
