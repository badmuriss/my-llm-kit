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
import time
from uuid import uuid4

from scrapinho import Client, ScrapinhoError


def source_input(item):
    if "query" in item:
        query, page, limit = item["query"], item.get("page", 0), item.get("limit", 10)
        if "url" in item or item.get("dynamic") or not isinstance(query, str) or not query.strip():
            raise ValueError("invalid_query")
        if type(page) is not int or page not in (0, 1) or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("invalid_search_pagination")
        engine = item.get("engine", "duckduckgo")
        if not isinstance(engine, str) or engine not in {"duckduckgo", "bing"} or (engine == "bing" and (page != 1 or limit > 10)):
            raise ValueError("invalid_continuation_engine")
        return {"query": query, "page": page, "limit": limit, "engine": engine}
    url = item.get("url")
    if not isinstance(url, str):
        raise ValueError("invalid_url")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid_url")
    if not isinstance(item.get("dynamic", False), bool):
        raise ValueError("invalid_dynamic")
    return {"url": url, "dynamic": item.get("dynamic", False)}


def load_sources(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("input_must_be_list")
    sources, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("invalid_source")
        slug = item.get("slug")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", slug) or slug in seen:
            raise ValueError("invalid_or_duplicate_slug")
        seen.add(slug)
        sources.append({"slug": slug, **source_input(item)})
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


def acquisition_request(source, project_scope, timeout):
    search = "query" in source
    inputs = {key: source[key] for key in ("query", "page", "limit", "engine")} if search else {"url": source["url"]}
    return {"operation": "search.web" if search else "fetch.page", "project_scope": project_scope,
            "input": inputs, "execution": "browser" if search or source.get("dynamic") else "static",
            "limits": {"timeout_ms": int(timeout * 1000), "attempts": 1,
                       "response_bytes": 2097152, "browser_bytes": 2097152}}


def collect(sources, out, client, project_scope, timeout):
    run_id = str(uuid4())
    if not isinstance(project_scope, str) or not project_scope.strip():
        raise ValueError("project_scope_required")
    requests = [acquisition_request(source, project_scope, timeout) for source in sources]
    # Invalidate the previous generation before any batch/network operation.
    for source in sources:
        target = out / source["slug"]
        target.mkdir(parents=True, exist_ok=True)
        for filename in ("page.html", "page.md", "record.json", "search.json"):
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
        record = {"schema_version": 1, "run_id": run_id, "provider": "scrapinho", "url": source.get("url"),
                  "query": source.get("query"), "project_scope": project_scope,
                  "job_id": job.get("job_id"), "source_id": job.get("source_id"), "accessed_at": None,
                  "sha256": None, "http_status": None, "status": job.get("status"), "error": None,
                  "proxy_bytes": None, "cost_usd": None,
                  "usage": job.get("usage"), "usage_basis": job.get("usage_basis"),
                  "acquisition_status": job.get("status"), "errors": job.get("errors", []),
                  "cancellation_unconfirmed": job.get("cancellation_unconfirmed", False),
                  "cache_hit": job.get("cache_hit", False), "max_age_s": job.get("max_age_s")}
        try:
            if job.get("status") != "succeeded" or not job.get("source_id"):
                errors = job.get("errors", [])
                raise ScrapinhoError(errors[0].get("code", "acquisition_incomplete")
                                     if errors else "acquisition_incomplete")
            deadline = time.monotonic() + timeout
            page = client.read_all(job["source_id"], timeout=timeout)
            if not page["acquisition_complete"]:
                raise ScrapinhoError("acquisition_incomplete")
            manifest = client.export_source(job["source_id"], timeout=max(0.001, deadline - time.monotonic()))
            body = client.export_source(job["source_id"], "raw", timeout=max(0.001, deadline - time.monotonic()))
            digest = hashlib.sha256(body).hexdigest()
            if digest != page["content_sha256"]:
                raise ScrapinhoError("source_integrity_mismatch")
            record.update({"sha256": digest, "accessed_at": page["fetched_at"], "http_status": manifest["target_status"]})
            if "query" in source:
                search = client.read_search(job["source_id"], timeout=max(0.001, deadline - time.monotonic()))
                if not search.get("acquisition_complete") or search.get("content_sha256") != digest:
                    raise ScrapinhoError("search_integrity_mismatch")
                atomic_write(target / "search.json", (json.dumps(search, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
                record["engine"] = search["engine"]
            atomic_write(target / "page.html", body)
            atomic_write(target / "page.md", (page["text"] + "\n").encode("utf-8"))
        except (ScrapinhoError, OSError, ValueError, KeyError, TypeError) as error:
            record["error"] = error.code if isinstance(error, ScrapinhoError) else "invalid_source_or_artifact"
            if job.get("status") == "succeeded":
                record["status"] = "failed"
            record["sha256"] = None
            for filename in ("page.html", "page.md", "search.json"):
                (target / filename).unlink(missing_ok=True)
        try:
            # The record is the commit marker for the newly published generation.
            atomic_write(target / "record.json", (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            for filename in ("page.html", "page.md", "search.json"):
                (target / filename).unlink(missing_ok=True)
            raise
        records.append(record)
    return records


def research_api_key(config_path):
    key = os.environ.get("SCRAPINHO_API_KEY")
    if not key and config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        consumer = config.get("research") if isinstance(config, dict) else None
        if not isinstance(consumer, dict):
            raise ValueError("research_configuration_invalid")
        key = consumer.get("api_key")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("research_api_key_missing")
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", default=Path("research/sources"), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", default=120, type=float)
    parser.add_argument("--project-scope", default=os.environ.get("SCRAPINHO_PROJECT_SCOPE"))
    parser.add_argument("--config", type=Path,
                        default=Path.home() / ".config" / "scrapinho" / "clients.json")
    args = parser.parse_args()
    try:
        sources = load_sources(args.input)
        if not 1 <= args.timeout <= 900:
            raise ValueError("invalid_timeout")
        if not args.project_scope or not args.project_scope.strip():
            raise ValueError("project_scope_required")
        if args.dry_run:
            for source in sources:
                print(json.dumps(acquisition_request(source, args.project_scope, args.timeout), ensure_ascii=False))
            print(f"dry run: {len(sources)} acquisitions; billed bytes and cost unknown")
            return 0
        key = research_api_key(args.config)
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
