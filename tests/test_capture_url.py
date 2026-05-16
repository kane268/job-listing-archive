from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from capture_url import fields_from_issue_body, first_url  # noqa: E402


class CaptureURLTests(unittest.TestCase):
    def test_fields_from_issue_body(self) -> None:
        fields = fields_from_issue_body(
            """
### Source URL

https://example.com/job
"""
        )
        self.assertEqual(fields["source_url"], "https://example.com/job")

    def test_first_url_from_issue_title(self) -> None:
        self.assertEqual(first_url("Capture: https://example.com/job"), "https://example.com/job")


if __name__ == "__main__":
    unittest.main()
