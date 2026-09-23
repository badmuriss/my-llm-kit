#!/usr/bin/env python3
"""Collect private Scrapinho snapshots into page.html, page.md and record.json."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from uuid import uuid4

from scrapinho import Client, ScrapinhoError


def load_sources(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("input_must_be_list")
    sources, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("invalid_source")
        slug, url = item.get("slug"), item.get("url")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", slug) or slug in seen:
            raise ValueError("invalid_or_duplicate_slug")
        if not isinstance(url, str):
            raise ValueError("invalid_url")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid_url")
        if not isinstance(item.get("dynamic", False), bool):
            raise ValueError("invalid_dynamic")
        seen.add(slug)
        sources.append({"slug": slug, "url": url, "dynamic": item.get("dynamic", False)})
    return sources


def atomic_write(path, body):
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(body)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def collect(sources, out, client, project_scope, timeout):
    run_id = str(uuid4())
    requests = [{"operation": "fetch.page", "project_scope": project_scope,
                 "input": {"url": source["url"]}, "execution": "browser" if source["dynamic"] else "static",
                 "limits": {"timeout_ms": int(timeout * 1000)}} for source in sources]
    # Invalidate the previous generation before any batch/network operation.
    for source in sources:
        target = out / source["slug"]
        target.mkdir(parents=True, exist_ok=True)
        for filename in ("page.html", "page.md", "record.json"):
            (target / filename).unlink(missing_ok=True)
    try:
        jobs = client.map(requests, timeout=timeout)
    except (ScrapinhoError, OSError, ValueError) as error:
        code = error.code if isinstance(error, ScrapinhoError) else "batch_acquisition_failed"
        jobs = [{"status": "failed", "errors": [{"code": code}]} for _ in sources]
    records = []
    for source, job in zip(sources, jobs, strict=True):
        target = out / source["slug"]
        target.mkdir(parents=True, exist_ok=True)
        record = {"schema_version": 1, "run_id": run_id, "provider": "scrapinho", "url": source["url"],
                  "job_id": job.get("job_id"), "source_id": job.get("source_id"), "accessed_at": None,
                  "sha256": None, "http_status": None, "status": job.get("status"), "error": None,
                  "proxy_bytes": None, "cost_usd": None,
                  "usage": job.get("usage"), "usage_basis": job.get("usage_basis"),
                  "cache_hit": job.get("cache_hit", False), "max_age_s": job.get("max_age_s")}
        try:
            if job.get("status") != "succeeded" or not job.get("source_id"):
                raise ScrapinhoError(next(iter(job.get("errors", [])), {}).get("code", "acquisition_incomplete"))
            page = client.read_all(job["source_id"])
            if not page["acquisition_complete"]:
                raise ScrapinhoError("acquisition_incomplete")
            manifest = client.export_source(job["source_id"])
            body = client.export_source(job["source_id"], "html")
            digest = hashlib.sha256(body).hexdigest()
            if digest != page["content_sha256"]:
                raise ScrapinhoError("source_integrity_mismatch")
            record.update({"sha256": digest, "accessed_at": page["fetched_at"], "http_status": manifest["target_status"]})
            atomic_write(target / "page.html", body)
            atomic_write(target / "page.md", (page["text"] + "\n").encode("utf-8"))
        except (ScrapinhoError, OSError) as error:
            record["error"] = error.code if isinstance(error, ScrapinhoError) else "artifact_write_failed"
            record["status"] = "failed"
            record["sha256"] = None
            record["http_status"] = None
            for filename in ("page.html", "page.md"):
                (target / filename).unlink(missing_ok=True)
        try:
            # The record is the commit marker for the newly published generation.
            atomic_write(target / "record.json", (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            for filename in ("page.html", "page.md"):
                (target / filename).unlink(missing_ok=True)
            raise
        records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", default=Path("research/sources"), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", default=120, type=float)
    parser.add_argument("--project-scope", default=os.environ.get("SCRAPINHO_PROJECT_SCOPE", "research"))
    args = parser.parse_args()
    try:
        sources = load_sources(args.input)
        if not 1 <= args.timeout <= 900:
            raise ValueError("invalid_timeout")
        if args.dry_run:
            for source in sources:
                print(f"{source['slug']}\tfetch.page\t{'browser' if source['dynamic'] else 'static'}\t{source['url']}")
            print(f"dry run: {len(sources)} acquisitions; billed bytes and cost unknown")
            return 0
        key = os.environ.get("SCRAPINHO_API_KEY")
        if not key:
            print("SCRAPINHO_API_KEY missing", file=sys.stderr)
            return 2
        client = Client(os.environ.get("SCRAPINHO_BASE_URL", "https://scrapinho.dev"), key)
        records = collect(sources, args.out, client, args.project_scope, args.timeout)
        for source, record in zip(sources, records, strict=True):
            print(f"{source['slug']}\t{record['status']}\t{record['error'] or args.out / source['slug'] / 'page.md'}")
        return int(any(record["error"] for record in records))
    except (OSError, ValueError, ScrapinhoError) as error:
        print(error.code if isinstance(error, ScrapinhoError) else "invalid_input_or_output", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
