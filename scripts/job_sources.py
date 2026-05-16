#!/usr/bin/env python3
"""Track saved companies for the archive."""

from __future__ import annotations

import argparse
import csv
import json
import webbrowser
from pathlib import Path
from typing import Iterable

from job_archive import ROOT, slugify

SOURCE_INDEX = ROOT / "data" / "job-sources.json"
STORED_COLUMNS = ["name", "url", "homepage_url"]
RUNTIME_COLUMNS = ["id", *STORED_COLUMNS]


def make_source_id(name: str) -> str:
    return slugify(name)


def normalize_source_row(row: dict[str, str]) -> dict[str, str]:
    name = (row.get("name") or "").strip()
    return {
        "id": make_source_id(name),
        "name": name,
        "url": (row.get("url") or "").strip(),
        "homepage_url": (row.get("homepage_url") or row.get("homepage") or "").strip(),
    }


def stored_source_row(row: dict[str, str]) -> dict[str, str]:
    normalized = normalize_source_row(row)
    return {column: normalized[column] for column in STORED_COLUMNS}


def read_sources(path: str | Path = SOURCE_INDEX) -> list[dict[str, str]]:
    source_path = Path(path)
    if not source_path.exists():
        return []

    if source_path.suffix.lower() == ".json":
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        raw_rows = payload.get("sources", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            return []
        return [normalize_source_row(row) for row in raw_rows if isinstance(row, dict)]

    with source_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [normalize_source_row(row) for row in reader]


def write_sources(rows: Iterable[dict[str, str]], path: str | Path = SOURCE_INDEX) -> Path:
    source_path = Path(path)
    source_rows = [stored_source_row(row) for row in rows]
    source_path.parent.mkdir(parents=True, exist_ok=True)

    if source_path.suffix.lower() == ".json":
        payload = {"sources": source_rows}
        source_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return source_path

    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STORED_COLUMNS)
        writer.writeheader()
        writer.writerows(source_rows)
    return source_path


def add_or_update_source(
    name: str,
    url: str,
    homepage_url: str = "",
    *,
    path: str | Path = SOURCE_INDEX,
) -> tuple[str, dict[str, str]]:
    rows = read_sources(path)
    source_id = make_source_id(name)
    new_row = normalize_source_row({"name": name, "url": url, "homepage_url": homepage_url})
    if not new_row["homepage_url"]:
        raise ValueError("homepage_url is required")

    for index, row in enumerate(rows):
        if row.get("id") == source_id:
            rows[index] = new_row
            write_sources(rows, path)
            return "updated", new_row

    rows.append(new_row)
    rows.sort(key=lambda item: item.get("name", "").lower())
    write_sources(rows, path)
    return "added", new_row


def active_sources(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in (normalize_source_row(row) for row in rows) if row.get("name") and row.get("url")]


def match_sources(rows: Iterable[dict[str, str]], selectors: list[str]) -> list[dict[str, str]]:
    source_rows = [normalize_source_row(row) for row in rows]
    if not selectors:
        return active_sources(source_rows)
    matches: list[dict[str, str]] = []
    for selector in selectors:
        normalized = selector.lower()
        for row in source_rows:
            haystack = " ".join(
                [row.get("id", ""), row.get("name", ""), row.get("url", ""), row.get("homepage_url", "")]
            ).lower()
            if normalized in haystack and row not in matches:
                matches.append(row)
    return matches


def format_sources(rows: Iterable[dict[str, str]]) -> str:
    source_rows = list(rows)
    if not source_rows:
        return "No saved companies yet."

    columns = ["name", "url", "homepage_url"]
    widths = {
        column: max(len(column), *(len(row.get(column, "")) for row in source_rows))
        for column in columns
    }
    lines = [
        "  ".join(column.ljust(widths[column]) for column in columns),
        "  ".join("-" * widths[column] for column in columns),
    ]
    for row in source_rows:
        lines.append("  ".join(row.get(column, "").ljust(widths[column]) for column in columns))
    return "\n".join(lines)


def list_cli(args: argparse.Namespace) -> int:
    print(format_sources(active_sources(read_sources(args.file))))
    return 0


def add_cli(args: argparse.Namespace) -> int:
    status, row = add_or_update_source(args.name, args.url, args.homepage_url, path=args.file)
    print(f"{status}: {row['id']} -> {row['url']}")
    return 0


def open_cli(args: argparse.Namespace) -> int:
    rows = match_sources(read_sources(args.file), args.selectors)
    if not rows:
        raise SystemExit("No matching saved companies found.")
    for row in rows:
        print(f"open: {row['name']} -> {row['url']}")
        webbrowser.open(row["url"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage saved companies to check for job listings.")
    parser.add_argument("--file", default=str(SOURCE_INDEX), help="Source JSON or CSV path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List saved companies")
    list_parser.set_defaults(func=list_cli)

    add_parser = subparsers.add_parser("add", help="Add or update a saved company")
    add_parser.add_argument("name", help="Company name")
    add_parser.add_argument("url", help="Jobs or careers URL")
    add_parser.add_argument("--homepage-url", required=True, help="Company home page URL for icons")
    add_parser.set_defaults(func=add_cli)

    open_parser = subparsers.add_parser("open", help="Open saved companies")
    open_parser.add_argument("selectors", nargs="*", help="Optional id, name, or URL fragments")
    open_parser.set_defaults(func=open_cli)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
