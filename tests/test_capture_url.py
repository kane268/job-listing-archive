from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from capture_url import (  # noqa: E402
    fields_from_issue_body,
    first_url,
    load_capture_records,
    remove_capture_record,
    upsert_capture_record,
)


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

    def test_successful_capture_removes_pending_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()
            path = data / "captures.json"
            path.write_text(
                json.dumps(
                    {
                        "captures": [
                            {
                                "id": "example-com-job",
                                "source_url": "https://example.com/job",
                                "submitted_at": "2026-05-16T12:00:00+00:00",
                                "updated_at": "2026-05-16T12:00:00+00:00",
                                "status": "failed",
                                "reason": "temporary",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            remove_capture_record("https://example.com/job", root=root)
            self.assertEqual(load_capture_records(path), [])

    def test_failed_capture_records_do_not_duplicate_listing_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            upsert_capture_record(
                {
                    "id": "example-com-job",
                    "source_url": "https://example.com/job",
                    "submitted_at": "2026-05-16T12:00:00+00:00",
                    "updated_at": "2026-05-16T12:00:00+00:00",
                    "status": "failed",
                    "reason": "HTTP 500",
                },
                root=root,
            )
            records = load_capture_records(root / "data" / "captures.json")
            self.assertEqual(len(records), 1)
            self.assertNotIn("listing_path", records[0])
            self.assertNotIn("listing_id", records[0])


if __name__ == "__main__":
    unittest.main()
