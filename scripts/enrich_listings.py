#!/usr/bin/env python3
"""Fetch queued Pages CMS listing URLs and write extracted Markdown bodies."""

from __future__ import annotations

import argparse
from pathlib import Path

from job_archive import ROOT, build_index, enrich_listing_file, listing_paths, split_listing_file, should_enrich_listing


def enrich_listings(root: str | Path = ROOT, *, force: bool = False) -> list[dict[str, object]]:
    root_path = Path(root)
    results: list[dict[str, object]] = []
    for listing_path in listing_paths(root_path):
        metadata, body = split_listing_file(listing_path)
        if not should_enrich_listing(metadata, body, force=force):
            continue
        results.append(enrich_listing_file(listing_path, force=force))
    if results:
        build_index(root_path)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch queued listing URLs and update their Markdown files.")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repository root")
    parser.add_argument("--force", action="store_true", help="Refetch every listing with a source_url")
    args = parser.parse_args(argv)

    results = enrich_listings(args.repo_root, force=args.force)
    if not results:
        print("No queued listings to enrich.")
        return 0
    for result in results:
        status = result.get("status")
        path = result.get("path")
        reason = result.get("reason")
        suffix = f" ({reason})" if reason else ""
        print(f"{status}: {path}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
