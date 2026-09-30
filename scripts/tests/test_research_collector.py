import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "research" / "scripts"))
from collect_sources import collect, load_sources, research_api_key
from scrapinho import Client, ScrapinhoError


class CollectorTests(unittest.TestCase):
    def test_preserves_snapshot_provenance_and_removes_stale_artifacts_on_failed_refresh(self):
        body = b"<p>Fixture</p>"
        client = Mock()
        client.map.return_value = [{"job_id": "job", "source_id": "source", "status": "succeeded"}]
        client.read_all.return_value = {"acquisition_complete": True, "content_sha256": hashlib.sha256(body).hexdigest(), "fetched_at": "2026-09-22T00:00:00Z", "text": "Fixture"}
        client.export_source.side_effect = [{"target_status": 201}, body]
        sources = [{"slug": "fixture", "url": "https://example.com/", "dynamic": False}]
        with TemporaryDirectory() as directory:
            out = Path(directory)
            record = collect(sources, out, client, "test", 120)[0]
            self.assertEqual(record["http_status"], 201)
            self.assertEqual(record["accessed_at"], "2026-09-22T00:00:00Z")
            self.assertEqual((out / "fixture/page.html").read_bytes(), body)
            client.map.return_value = [{"job_id": "failed-job", "status": "blocked", "errors": [{"code": "target_blocked"}],
                                        "usage": {"attempts": 1, "bytes": 321, "browser_ms": 0},
                                        "usage_basis": "proxy_transport_or_reserved_envelope"}]
            failed = collect(sources, out, client, "test", 120)[0]
            self.assertEqual(failed["error"], "target_blocked")
            self.assertIsNone(failed["cost_usd"])
            self.assertEqual(failed["usage"], {"attempts": 1, "bytes": 321, "browser_ms": 0})
            self.assertEqual(failed["usage_basis"], "proxy_transport_or_reserved_envelope")
            self.assertFalse((out / "fixture/page.html").exists())
            self.assertFalse((out / "fixture/page.md").exists())
            self.assertNotEqual(failed["run_id"], record["run_id"])

    def test_rejects_path_traversal_and_duplicate_slugs_before_acquisition(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "sources.json"
            for entries in [[{"slug": "../escape", "url": "https://example.com/"}], [{"slug": "same", "url": "https://example.com/"}] * 2]:
                source.write_text(json.dumps(entries))
                with self.assertRaisesRegex(ValueError, "invalid_or_duplicate_slug"):
                    load_sources(source)

    def test_invalidates_old_artifacts_when_the_batch_raises(self):
        client = Mock()
        client.map.side_effect = ScrapinhoError("service_unavailable")
        sources = [{"slug": "fixture", "url": "https://example.com/", "dynamic": False}]
        with TemporaryDirectory() as directory:
            out = Path(directory)
            target = out / "fixture"
            target.mkdir()
            for name in ("page.html", "page.md", "record.json"):
                (target / name).write_text("old")
            record = collect(sources, out, client, "test", 120)[0]
            self.assertEqual(record["error"], "service_unavailable")
            self.assertFalse((target / "page.html").exists())
            self.assertFalse((target / "page.md").exists())
            self.assertEqual(json.loads((target / "record.json").read_text())["status"], "failed")

    def test_removes_new_pages_when_the_commit_record_cannot_be_published(self):
        body = b"<p>Fixture</p>"
        client = Mock()
        client.map.return_value = [{"job_id": "job", "source_id": "source", "status": "succeeded"}]
        client.read_all.return_value = {"acquisition_complete": True, "content_sha256": hashlib.sha256(body).hexdigest(), "fetched_at": "2026-09-22T00:00:00Z", "text": "Fixture"}
        client.export_source.side_effect = [{"target_status": 200}, body]
        original = Path.replace
        def replace(path, destination):
            if destination.name == "record.json":
                raise OSError("fixture write failure")
            return original(path, destination)
        with TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(Path, "replace", replace), self.assertRaises(OSError):
                collect([{"slug": "fixture", "url": "https://example.com/", "dynamic": False}], out, client, "test", 120)
            self.assertEqual(list((out / "fixture").iterdir()), [])

    def test_preserves_search_positions_and_discards_corrupted_search(self):
        body = b"<html>search evidence</html>"
        digest = hashlib.sha256(body).hexdigest()
        client = Mock()
        client.map.return_value = [{"job_id": "job", "source_id": "source", "status": "succeeded"}]
        client.read_all.return_value = {"acquisition_complete": True, "content_sha256": digest,
                                        "fetched_at": "2026-09-29T00:00:00Z", "text": "Results"}
        ranked = [{"position": 1, "url": "https://example.com/"}, {"position": 4, "url": "https://example.com/"}]
        client.read_search.return_value = {"acquisition_complete": True, "content_sha256": digest,
                                           "engine": "duckduckgo", "results": ranked, "has_next_page": True}
        source = {"slug": "search", "query": "public query", "engine": "duckduckgo", "page": 0, "limit": 10}
        with TemporaryDirectory() as directory:
            out = Path(directory)
            client.export_source.side_effect = [{"target_status": 200}, body]
            self.assertIsNone(collect([source], out, client, "project", 120)[0]["error"])
            self.assertEqual(json.loads((out / "search/search.json").read_text())["results"], ranked)
            client.read_search.return_value["content_sha256"] = "corrupted"
            client.export_source.side_effect = [{"target_status": 200}, body]
            self.assertEqual(collect([source], out, client, "project", 120)[0]["error"], "search_integrity_mismatch")
            self.assertFalse((out / "search/search.json").exists())
            self.assertFalse((out / "search/page.html").exists())

    def test_keeps_successful_siblings_when_a_source_is_partial(self):
        body = b"evidence"
        client = Mock()
        client.map.return_value = [{"source_id": "ok", "status": "succeeded"},
                                   {"status": "partial", "errors": [{"code": "body_limit"}]}]
        client.read_all.return_value = {"acquisition_complete": True, "content_sha256": hashlib.sha256(body).hexdigest(),
                                        "fetched_at": "2026-09-29T00:00:00Z", "text": "Evidence"}
        client.export_source.side_effect = [{"target_status": 200}, body]
        sources = [{"slug": name, "url": "https://example.com/", "dynamic": False} for name in ("ok", "partial")]
        with TemporaryDirectory() as directory:
            records = collect(sources, Path(directory), client, "project", 120)
            self.assertIsNone(records[0]["error"])
            self.assertEqual(records[1]["error"], "body_limit")
            self.assertEqual((Path(directory) / "ok/page.html").read_bytes(), body)
            self.assertFalse((Path(directory) / "partial/page.html").exists())

    def test_dry_run_does_not_require_credentials_or_contact_service(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(json.dumps([{"slug": "query", "query": "primary evidence", "page": 1}]))
            config = Path(directory) / "private.json"
            config.write_text("invalid JSON that dry-run must never read")
            env = {key: value for key, value in os.environ.items() if not key.startswith("SCRAPINHO_")}
            env["SCRAPINHO_BASE_URL"] = "http://127.0.0.1:1"
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] /
                                    "skills/research/scripts/collect_sources.py"), "--input", str(source),
                                    "--project-scope", "dry-test", "--config", str(config), "--dry-run"], env=env,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            request = json.loads(result.stdout.splitlines()[0])
            self.assertEqual(request["input"]["engine"], "duckduckgo")
            self.assertEqual(request["input"]["page"], 1)

    def test_loads_only_research_identity_from_private_configuration(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            config = Path(directory) / "private.json"
            config.write_text(json.dumps({"research": {"api_key": "research-fixture"},
                                          "lupa": {"api_key": "other-fixture"}}))
            self.assertEqual(research_api_key(config), "research-fixture")
            config.write_text(json.dumps({"lupa": {"api_key": "other-fixture"}}))
            with self.assertRaisesRegex(ValueError, "research_configuration_invalid"):
                research_api_key(config)

    def test_preserves_effective_engine_only_for_continuation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            item = {"slug": "next", "query": "public query", "page": 1, "engine": "bing"}
            path.write_text(json.dumps([item]))
            self.assertEqual(load_sources(path)[0]["engine"], "bing")
            for change in ({"page": 0}, {"limit": 20}, {"engine": []}):
                path.write_text(json.dumps([{**item, **change}]))
                with self.assertRaisesRegex(ValueError, "invalid_continuation_engine"):
                    load_sources(path)


class ClientTests(unittest.TestCase):
    def test_stops_admissions_after_refusal_without_retrying(self):
        client = Client("http://localhost", "fixture")
        client.submit = Mock(return_value={"job_id": "refused", "status": "blocked",
                                          "errors": [{"code": "target_rate_limited"}]})
        result = client.map([{}, {}])
        self.assertEqual(client.submit.call_count, 1)
        self.assertEqual(result[0]["errors"][0]["code"], "target_rate_limited")
        self.assertEqual(result[1]["errors"][0]["code"], "batch_stopped")

    def test_persists_latest_uncertain_cancellation_state_and_usage(self):
        client = Client("http://localhost", "fixture")
        client.submit = Mock(return_value={"job_id": "pending", "status": "running", "usage": 0})
        client.wait = Mock(side_effect=ScrapinhoError("client_deadline_exceeded"))
        client.cancel = Mock(return_value={"job_id": "pending", "status": "execution_unknown",
                                           "errors": [{"code": "termination_requested"}], "usage": 4096})
        with TemporaryDirectory() as directory:
            records = collect([{"slug": "fixture", "url": "https://example.com"}],
                              Path(directory), client, "scope", 1)
            saved = json.loads((Path(directory) / "fixture/record.json").read_text())
        self.assertEqual(records[0]["status"], "execution_unknown")
        self.assertEqual(saved["status"], "execution_unknown")
        self.assertEqual(saved["usage"], 4096)
        self.assertEqual(saved["errors"], [{"code": "client_deadline_exceeded"}])
        self.assertTrue(saved["cancellation_unconfirmed"])
        self.assertEqual(saved["error"], "client_deadline_exceeded")
        self.assertFalse((Path(directory) / "fixture/page.html").exists())

    def test_preserves_confirmed_cancel_state_and_usage_after_deadline(self):
        client = Client("http://localhost", "fixture")
        client.submit = Mock(return_value={"job_id": "pending", "status": "running"})
        client.wait = Mock(side_effect=ScrapinhoError("client_deadline_exceeded"))
        client.cancel = Mock(return_value={"job_id": "pending", "status": "cancelled", "usage": 512})
        result = client.map([{}])[0]
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["usage"], 512)
        self.assertFalse(result["cancellation_unconfirmed"])

    def test_marks_failed_cancellation_unconfirmed(self):
        client = Client("http://localhost", "fixture")
        client.submit = Mock(return_value={"job_id": "pending", "status": "running"})
        client.wait = Mock(side_effect=ScrapinhoError("client_deadline_exceeded"))
        client.cancel = Mock(side_effect=ScrapinhoError("service_unavailable"))
        result = client.map([{}])[0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], [{"code": "client_deadline_exceeded"}])
        self.assertTrue(result["cancellation_unconfirmed"])
    def test_reads_to_eof_and_rejects_changed_snapshot(self):
        client = Client("http://localhost", "fixture")
        first = {"text": "first ", "content_sha256": "digest", "fetched_at": "timestamp",
                 "next_cursor": "next", "acquisition_complete": True}
        last = {**first, "text": "last", "next_cursor": None}
        client.read_source = Mock(side_effect=[first, last])
        self.assertEqual(client.read_all("source")["text"], "first last")
        client.read_source = Mock(side_effect=[first, {**last, "content_sha256": "changed"}])
        with self.assertRaisesRegex(ScrapinhoError, "snapshot_changed"):
            client.read_all("source")
