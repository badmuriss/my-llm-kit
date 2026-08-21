#!/usr/bin/env python3
"""Snapshot web sources for a research finding.

Input: JSON list of {"slug", "url", "dynamic"?}.
Output per slug: <out>/<slug>/{page.html, page.md, record.json}.
Fetches through ScrapingDog /scrape with SCRAPINGDOG_API_KEY; static (1 credit)
unless "dynamic": true (5 credits). Stdlib only; html2text is used when installed.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://api.scrapingdog.com/scrape"
CREDITS = {False: 1, True: 5}
MAX_WORKERS = 4
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

try:
    import html2text  # type: ignore
except ImportError:  # pragma: no cover
    html2text = None


def load_sources(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("input must be a JSON list")
    seen: set[str] = set()
    sources = []
    for index, item in enumerate(raw):
        slug, url = item.get("slug"), item.get("url")
        if not slug or not SLUG.match(slug) or slug in seen:
            raise SystemExit(f"item {index}: slug must be unique and match {SLUG.pattern}")
        if not url or not url.startswith(("http://", "https://")):
            raise SystemExit(f"item {index}: url must start with http(s)://")
        seen.add(slug)
        sources.append({"slug": slug, "url": url, "dynamic": bool(item.get("dynamic", False))})
    return sources


def to_markdown(body: str) -> str:
    if html2text is not None:
        converter = html2text.HTML2Text()
        converter.body_width = 0
        return converter.handle(body)
    text = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", body)
    text = re.sub(r"(?i)</?(h[1-6]|p|li|div|br|tr)[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line) + "\n"


def fetch(source: dict, api_key: str, timeout: int) -> tuple[int, bytes]:
    params = urllib.parse.urlencode(
        {"api_key": api_key, "url": source["url"], "dynamic": str(source["dynamic"]).lower()}
    )
    request = urllib.request.Request(f"{API_URL}?{params}", headers={"User-Agent": "research-collect/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def collect(source: dict, out: Path, api_key: str, timeout: int) -> dict:
    target = out / source["slug"]
    target.mkdir(parents=True, exist_ok=True)
    record = {
        "url": source["url"],
        "accessed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoint": f"/scrape?dynamic={str(source['dynamic']).lower()}",
        "credits_est": CREDITS[source["dynamic"]],
        "sha256": None,
        "http_status": None,
        "error": None,
    }
    try:
        status, body = fetch(source, api_key, timeout)
        record["http_status"] = status
        if status == 200:
            (target / "page.html").write_bytes(body)
            (target / "page.md").write_text(to_markdown(body.decode("utf-8", "replace")), encoding="utf-8")
            record["sha256"] = hashlib.sha256(body).hexdigest()
        else:
            record["credits_est"] = 0
            record["error"] = body[:200].decode("utf-8", "replace")
    except Exception as exc:  # network or filesystem failure stays in the record
        record["credits_est"] = 0
        record["error"] = f"{type(exc).__name__}: {exc}"
    (target / "record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="JSON list of {slug, url, dynamic?}")
    parser.add_argument("--out", default=Path("research/sources"), type=Path, help="output root (default research/sources)")
    parser.add_argument("--dry-run", action="store_true", help="list planned requests and credits without calling the API")
    parser.add_argument("--timeout", default=60, type=int, help="seconds per request (default 60)")
    args = parser.parse_args()

    sources = load_sources(args.input)
    planned = sum(CREDITS[s["dynamic"]] for s in sources)
    if args.dry_run:
        for s in sources:
            print(f"{s['slug']}\t/scrape?dynamic={str(s['dynamic']).lower()}\t{CREDITS[s['dynamic']]}\t{s['url']}")
        print(f"dry run: {len(sources)} requests, {planned} credits estimated, out={args.out}")
        return 0

    api_key = os.environ.get("SCRAPINGDOG_API_KEY")
    if not api_key:
        print("SCRAPINGDOG_API_KEY missing; run scripts/key-env-check.sh", file=sys.stderr)
        return 2

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        records = list(pool.map(lambda s: collect(s, args.out, api_key, args.timeout), sources))

    failed = [s["slug"] for s, r in zip(sources, records) if r["http_status"] != 200]
    for s, r in zip(sources, records):
        print(f"{s['slug']}\t{r['http_status']}\t{r['credits_est']}\t{r['error'] or args.out / s['slug'] / 'page.md'}")
    print(f"collected {len(records) - len(failed)}/{len(records)}, {sum(r['credits_est'] for r in records)} credits estimated, failed={failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
