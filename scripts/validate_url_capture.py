#!/usr/bin/env python3
"""Validate URL capture against live listing URLs without changing the repo."""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path

from job_archive import ROOT, ingest_url, parse_frontmatter, role_title_is_generic


def index_urls() -> list[str]:
    urls: list[str] = []
    index_path = ROOT / "data" / "index.csv"
    if not index_path.exists():
        return urls
    with index_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            url = (row.get("source_url") or "").strip()
            if url and url not in urls:
                urls.append(url)
    return urls


def validate_url(url: str, root: Path, min_chars: int) -> None:
    result = ingest_url(url, root=root)
    if result.get("status") != "captured":
        raise AssertionError(f"{url}: expected captured, got {result}")

    destination = Path(result["destination"])
    metadata = parse_frontmatter(destination / "listing.md")
    text_path = destination / "raw.txt"
    text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
    company = str(metadata.get("company") or "")
    role_title = str(metadata.get("role_title") or "")

    if role_title_is_generic(role_title, company):
        raise AssertionError(f"{url}: generic role title: {role_title!r}")
    if len(text) < min_chars:
        raise AssertionError(f"{url}: raw text too short: {len(text)} chars")

    print(f"ok: {company or 'Unknown company'} - {role_title} ({len(text)} chars)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate live URL capture in a temporary repo.")
    parser.add_argument("urls", nargs="*", help="URLs to validate. Defaults to source URLs in data/index.csv.")
    parser.add_argument("--min-chars", type=int, default=500, help="Minimum raw.txt length")
    args = parser.parse_args(argv)

    urls = args.urls or index_urls()
    if not urls:
        raise SystemExit("No URLs to validate.")

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "repo"
        root.mkdir()
        for url in urls:
            validate_url(url, root, args.min_chars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
