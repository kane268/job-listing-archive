from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from capture_url import fields_from_issue_body  # noqa: E402


class CaptureURLTests(unittest.TestCase):
    def test_fields_from_issue_body(self) -> None:
        fields = fields_from_issue_body(
            """
### Source URL

https://example.com/job

### Company

Example

### Role title

_No response_

### Public note

Interesting platform role.
"""
        )
        self.assertEqual(fields["source_url"], "https://example.com/job")
        self.assertEqual(fields["company"], "Example")
        self.assertEqual(fields["role_title"], "")
        self.assertEqual(fields["why"], "Interesting platform role.")


if __name__ == "__main__":
    unittest.main()
