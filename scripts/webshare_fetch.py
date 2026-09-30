#!/usr/bin/env python3
"""Fetch one public HTTP(S) URL through Webshare with one bounded fallback."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_CONFIG = Path("~/.omp/agent/webshare.json")
FALLBACK_HTTP_STATUSES = {403, 407, 408, 429}
TRANSPORT_FAILURES = {5, 6, 7, 18, 28, 35, 52, 55, 56, 92}


class FetchError(RuntimeError):
    pass


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return timeout


def validate_public_url(value: str) -> str:
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise FetchError("URL contains whitespace or control characters")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as error:
        raise FetchError("URL is malformed") from error
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise FetchError("URL must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise FetchError("URL userinfo is not allowed")

    normalized_host = hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        if (
            "." not in normalized_host
            or normalized_host.replace(".", "").isdigit()
            or normalized_host.endswith(
                (".localhost", ".local", ".internal", ".home", ".lan")
            )
        ):
            raise FetchError("URL host must be public")
    else:
        if not address.is_global:
            raise FetchError("URL host must be public")
    return value


def load_config(path: Path) -> tuple[int, int]:
    try:
        parsed = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FetchError(f"config file not found: {path.expanduser()}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FetchError(f"cannot read config file: {error}") from error
    if not isinstance(parsed, dict):
        raise FetchError("config root must be a JSON object")

    plan_ids: list[int] = []
    for field in ("datacenter_plan_id", "residential_plan_id"):
        value = parsed.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise FetchError(f"config field {field} must be a positive integer")
        plan_ids.append(value)
    return plan_ids[0], plan_ids[1]


def resolve_proxy(plan_id: int, timeout: float) -> str:
    command = [
        "webshare",
        "--base-url",
        "https://proxy.webshare.io",
        "proxy-url",
        "--plan",
        str(plan_id),
        "--rotate",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise FetchError("webshare CLI is not installed or not on PATH") from error
    except subprocess.TimeoutExpired as error:
        raise FetchError("webshare CLI timed out while resolving a proxy") from error
    except OSError as error:
        raise FetchError("webshare CLI could not be started") from error
    if result.returncode != 0:
        raise FetchError("webshare CLI could not resolve a proxy")

    proxy_url = result.stdout.strip()
    if not proxy_url or not proxy_url.isascii() or any(
        character.isspace() or ord(character) < 32 or character in {'"', "\\"}
        for character in proxy_url
    ):
        raise FetchError("webshare CLI returned an invalid proxy URL")
    try:
        parsed = urlsplit(proxy_url)
        _ = parsed.port
    except ValueError as error:
        raise FetchError("webshare CLI returned an invalid proxy URL") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is None
        or parsed.password is None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise FetchError("webshare CLI returned an invalid proxy URL")
    return proxy_url


def fetch_once(url: str, proxy_url: str, timeout: float, output_path: Path) -> tuple[bool, bool, str]:
    command = [
        "curl",
        "--disable",
        "--silent",
        "--location",
        "--max-redirs",
        "10",
        "--proto",
        "=http,https",
        "--proto-redir",
        "=http,https",
        "--noproxy",
        "",
        "--connect-timeout",
        str(timeout),
        "--max-time",
        str(timeout),
        "--output",
        str(output_path),
        "--write-out",
        "%{http_code}",
        "--url",
        url,
        "--config",
        "-",
    ]
    curl_config = f"proxy = {json.dumps(proxy_url)}\n"
    try:
        result = subprocess.run(
            command,
            input=curl_config,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=timeout + 2,
        )
    except FileNotFoundError as error:
        raise FetchError("curl is not installed or not on PATH") from error
    except subprocess.TimeoutExpired:
        return False, True, "connection timed out"
    except OSError as error:
        raise FetchError("curl could not be started") from error

    status_text = result.stdout.strip()
    if result.returncode != 0:
        if result.returncode in TRANSPORT_FAILURES:
            return False, True, f"transport failed (curl code {result.returncode})"
        return False, False, f"curl failed locally (code {result.returncode})"
    if len(status_text) != 3 or not status_text.isascii() or not status_text.isdigit():
        raise FetchError("curl returned an invalid HTTP status")

    status = int(status_text)
    if 200 <= status < 300:
        return True, False, f"HTTP {status}"
    can_fallback = status in FALLBACK_HTTP_STATUSES or 500 <= status < 600
    return False, can_fallback, f"HTTP {status}"


def copy_response(path: Path) -> None:
    try:
        with path.open("rb") as response:
            shutil.copyfileobj(response, sys.stdout.buffer)
    except OSError as error:
        raise FetchError("could not write the completed response") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="public HTTP(S) URL to fetch")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="plan ID config path")
    parser.add_argument("--timeout", type=positive_timeout, default=30.0, help="seconds per attempt")
    args = parser.parse_args()

    try:
        url = validate_public_url(args.url)
        datacenter_plan_id, residential_plan_id = load_config(args.config)
        datacenter_proxy = resolve_proxy(datacenter_plan_id, args.timeout)
        with tempfile.TemporaryDirectory(prefix="webshare-fetch-") as temporary_directory:
            response_path = Path(temporary_directory) / "response"
            succeeded, can_fallback, result = fetch_once(
                url, datacenter_proxy, args.timeout, response_path
            )
            if succeeded:
                print(f"webshare-fetch: datacenter succeeded ({result})", file=sys.stderr)
                copy_response(response_path)
                return 0
            if not can_fallback:
                raise FetchError(f"datacenter failed ({result}); residential fallback not allowed")

            print(
                f"webshare-fetch: datacenter failed ({result}); falling back to residential",
                file=sys.stderr,
            )
            residential_proxy = resolve_proxy(residential_plan_id, args.timeout)
            succeeded, _, result = fetch_once(
                url, residential_proxy, args.timeout, response_path
            )
            if not succeeded:
                raise FetchError(f"residential failed ({result}); no attempts remain")
            print(f"webshare-fetch: residential succeeded ({result})", file=sys.stderr)
            copy_response(response_path)
            return 0
    except FetchError as error:
        print(f"webshare-fetch: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
