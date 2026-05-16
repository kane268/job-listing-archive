from __future__ import annotations

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
    def test_add_and_update_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sources.csv"
            status, row = add_or_update_source(
                "Anthropic",
                "https://www.anthropic.com/careers/jobs",
                tags="AI, research",
                path=path,
            )
            self.assertEqual(status, "added")
            self.assertEqual(row["id"], "anthropic")
            self.assertEqual(row["tags"], "ai,research")

            status, row = add_or_update_source(
                "Anthropic",
                "https://www.anthropic.com/careers/jobs",
                notes="Updated notes",
                path=path,
            )
            self.assertEqual(status, "updated")
            self.assertEqual(row["notes"], "Updated notes")
            self.assertEqual(len(read_sources(path)), 1)

    def test_match_sources_defaults_to_active(self) -> None:
        rows = [
            {"id": "active", "name": "Active", "url": "https://example.com", "status": "active", "tags": "", "type": "", "notes": ""},
            {"id": "inactive", "name": "Inactive", "url": "https://inactive.example.com", "status": "inactive", "tags": "", "type": "", "notes": ""},
        ]
        self.assertEqual([row["id"] for row in match_sources(rows, [])], ["active"])
        self.assertEqual([row["id"] for row in match_sources(rows, ["inactive"])], ["inactive"])

    def test_format_sources(self) -> None:
        rows = [
            {"id": "stripe", "name": "Stripe", "url": "https://stripe.com/jobs/search", "status": "active", "tags": "fintech", "type": "", "notes": ""},
        ]
        table = format_sources(rows)
        self.assertIn("Stripe", table)
        self.assertIn("https://stripe.com/jobs/search", table)


if __name__ == "__main__":
    unittest.main()
