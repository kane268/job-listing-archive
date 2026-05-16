from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from job_sources import (  # noqa: E402
    add_or_update_source,
    format_sources,
    match_sources,
    read_sources,
)


class JobSourceTests(unittest.TestCase):
    def test_add_and_update_source_generates_id_without_storing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sources.json"
            status, row = add_or_update_source(
                "If This Is Company Name",
                "https://example.com/jobs",
                "https://example.com",
                path=path,
            )
            self.assertEqual(status, "added")
            self.assertEqual(row["id"], "if-this-is-company-name")

            status, row = add_or_update_source(
                "If This Is Company Name",
                "https://example.com/careers",
                "https://example.com",
                path=path,
            )
            self.assertEqual(status, "updated")
            self.assertEqual(row["url"], "https://example.com/careers")
            self.assertEqual(len(read_sources(path)), 1)

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                stored,
                {
                    "sources": [
                        {
                            "name": "If This Is Company Name",
                            "url": "https://example.com/careers",
                            "homepage_url": "https://example.com",
                        }
                    ]
                },
            )

    def test_match_sources_defaults_to_all_saved_companies(self) -> None:
        rows = [
            {"name": "Active", "url": "https://example.com"},
            {"name": "Inactive", "url": "https://inactive.example.com"},
        ]
        self.assertEqual([row["id"] for row in match_sources(rows, [])], ["active", "inactive"])
        self.assertEqual([row["id"] for row in match_sources(rows, ["inactive"])], ["inactive"])

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
