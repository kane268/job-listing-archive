from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_site import markdown_to_html  # noqa: E402


class BuildSiteTests(unittest.TestCase):
    def test_markdown_renderer_preserves_nested_bullets(self) -> None:
        html = markdown_to_html("- Parent\n  - Child\n  - Child 2\n- Sibling\n")
        self.assertRegex(html, re.compile(r"<li>Parent\s*<ul>\s*<li>Child", re.S))
        self.assertRegex(html, re.compile(r"</ul>\s*</li>\s*<li>Sibling", re.S))


if __name__ == "__main__":
    unittest.main()
