#!/usr/bin/env python3
"""Capture a job listing URL into the Markdown archive."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from job_archive import ROOT, build_index, ingest_url

NO_RESPONSE_VALUES = {"", "_No response_", "No response"}


def clean_issue_value(value: str) -> str:
    value = value.strip()
    return "" if value in NO_RESPONSE_VALUES else value


def parse_issue_body(body: str) -> dict[str, str]:
    fields: dict[str, list[str]] = {}
    current = ""
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if line.startswith("### "):
            current = line[4:].strip()
            fields[current] = []
            continue
        if current:
            fields[current].append(line)

    return {label: clean_issue_value("\n".join(lines)) for label, lines in fields.items()}


def fields_from_issue_body(body: str) -> dict[str, str]:
    raw = parse_issue_body(body)

    def get(*labels: str) -> str:
        for label in labels:
            value = raw.get(label, "")
            if value:
                return value
        return ""

    return {
        "source_url": get("Source URL", "URL", "Listing URL"),
        "company": get("Company"),
        "role_title": get("Role title", "Role"),
        "role_family": get("Role family"),
        "seniority": get("Seniority"),
        "why": get("Why did this catch your eye?", "Public note", "Why I saved this"),
    }


def write_github_outputs(path: str, values: dict[str, Any]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            text = "" if value is None else str(value)
            if "\n" in text:
                handle.write(f"{key}<<EOF\n{text}\nEOF\n")
            else:
                handle.write(f"{key}={text}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture a job listing URL.")
    parser.add_argument("url", nargs="?", help="Job listing URL")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repository root")
    parser.add_argument("--issue-body-file", default="", help="Markdown issue body to parse")
    parser.add_argument("--issue-url", default="", help="GitHub issue URL for provenance")
    parser.add_argument("--company", default="", help="Override company")
    parser.add_argument("--role-title", default="", help="Override role title")
    parser.add_argument("--role-family", default="", help="Override role family")
    parser.add_argument("--seniority", default="", help="Override seniority")
    parser.add_argument("--why", default="", help="Public-safe note for the listing")
    parser.add_argument("--force", action="store_true", help="Capture even if the URL or content already exists")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be captured without writing files")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""), help="GitHub Actions output file")
    args = parser.parse_args(argv)

    issue_fields: dict[str, str] = {}
    if args.issue_body_file:
        issue_fields = fields_from_issue_body(Path(args.issue_body_file).read_text(encoding="utf-8"))

    source_url = args.url or issue_fields.get("source_url", "")
    if not source_url:
        raise SystemExit("No source URL provided.")

    overrides = {
        "company": args.company or issue_fields.get("company", ""),
        "role_title": args.role_title or issue_fields.get("role_title", ""),
        "role_family": args.role_family or issue_fields.get("role_family", ""),
        "seniority": args.seniority or issue_fields.get("seniority", ""),
        "why": args.why or issue_fields.get("why", ""),
    }

    result = ingest_url(
        source_url,
        root=args.repo_root,
        overrides=overrides,
        issue_url=args.issue_url,
        force=args.force,
        dry_run=args.dry_run,
    )

    if result.get("status") in {"captured", "would-capture"} and not args.dry_run:
        build_index(args.repo_root)

    if result.get("id"):
        print(f"{result['status']}: {source_url} -> {result['id']}")
    elif result.get("listing_path"):
        print(f"{result['status']}: {source_url} ({result.get('reason')}: {result['listing_path']})")
    else:
        print(f"{result['status']}: {source_url} ({result.get('reason', '')})")

    write_github_outputs(
        args.github_output,
        {
            "status": result.get("status", ""),
            "reason": result.get("reason", ""),
            "id": result.get("id", ""),
            "listing_path": result.get("listing_path", ""),
            "source_url": source_url,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
