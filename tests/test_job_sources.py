from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from job_sources import (  # noqa: E402
    active_sources,
    format_sources,
    make_source_id,
    read_sources,
)


class JobSourceTests(unittest.TestCase):
    def test_read_sources_generates_runtime_id_without_storing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sources.json"
            path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "name": "If This Is Company Name",
                                "url": "https://example.com/jobs",
                                "homepage_url": "https://example.com",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rows = read_sources(path)
            self.assertEqual(rows[0]["id"], "if-this-is-company-name")
            self.assertEqual(make_source_id(rows[0]["name"]), "if-this-is-company-name")

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("id", stored["sources"][0])

    def test_active_sources_filters_incomplete_sources(self) -> None:
        rows = [
            {"name": "Active", "url": "https://example.com", "homepage_url": "https://example.com"},
            {"name": "Missing URL", "url": "", "homepage_url": "https://example.com"},
        ]
        self.assertEqual([row["id"] for row in active_sources(rows)], ["active"])

    def test_format_sources(self) -> None:
        rows = [
            {"name": "Stripe", "url": "https://stripe.com/jobs/search", "homepage_url": "https://stripe.com"},
        ]
        table = format_sources(rows)
        self.assertIn("Stripe", table)
        self.assertIn("https://stripe.com/jobs/search", table)
        self.assertIn("https://stripe.com", table)
        self.assertNotIn("status", table)


if __name__ == "__main__":
    unittest.main()
