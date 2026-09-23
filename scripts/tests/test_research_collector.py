import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "research" / "scripts"))
from collect_sources import collect, load_sources
from scrapinho import ScrapinhoError


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
