#!/usr/bin/env python3
"""Read saved companies for the archive."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from job_archive import ROOT, slugify

SOURCE_INDEX = ROOT / "data" / "job-sources.json"
RUNTIME_COLUMNS = ["id", "name", "url", "homepage_url"]


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


def active_sources(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in (normalize_source_row(row) for row in rows) if row.get("name") and row.get("url")]


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
