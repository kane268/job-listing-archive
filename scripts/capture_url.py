#!/usr/bin/env python3
"""Capture a job listing URL into the Markdown archive."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from job_archive import ROOT, URL_RE, build_index, clean_url, ingest_url, normalize_source_url, slugify

CAPTURE_LEDGER = ROOT / "data" / "captures.json"
NO_RESPONSE_VALUES = {"", "_No response_", "No response"}


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def clean_issue_value(value: str) -> str:
    value = value.strip()
    return "" if value in NO_RESPONSE_VALUES else value


def first_url(value: str) -> str:
    match = URL_RE.search(value or "")
    return clean_url(match.group(0)) if match else ""


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
    source_url = ""
    for label in ("Source URL", "URL", "Listing URL"):
        source_url = raw.get(label, "")
        if source_url:
            break
    if not source_url:
        source_url = first_url(body)
    return {"source_url": source_url}


def load_capture_records(path: str | Path = CAPTURE_LEDGER) -> list[dict[str, Any]]:
    ledger_path = Path(path)
    if not ledger_path.exists():
        return []
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    records = payload.get("captures", payload) if isinstance(payload, dict) else payload
    return records if isinstance(records, list) else []


def write_capture_records(records: list[dict[str, Any]], path: str | Path = CAPTURE_LEDGER) -> Path:
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(records, key=lambda item: item.get("submitted_at", ""), reverse=True)
    ledger_path.write_text(json.dumps({"captures": records}, indent=2) + "\n", encoding="utf-8")
    return ledger_path


def capture_record_id(source_url: str) -> str:
    normalized = normalize_source_url(source_url)
    return slugify(normalized).removeprefix("https-").removeprefix("http-")[:96] or "capture"


def upsert_capture_record(record: dict[str, Any], root: str | Path = ROOT) -> None:
    path = Path(root) / "data" / "captures.json"
    records = load_capture_records(path)
    normalized = normalize_source_url(record.get("source_url", ""))
    for index, existing in enumerate(records):
        if existing.get("id") == record.get("id") or normalize_source_url(existing.get("source_url", "")) == normalized:
            merged = dict(existing)
            merged.update({key: value for key, value in record.items() if value != ""})
            merged["updated_at"] = record.get("updated_at") or now_iso()
            records[index] = merged
            write_capture_records(records, path)
            return
    records.append(record)
    write_capture_records(records, path)


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
    parser.add_argument("--issue-title", default="", help="GitHub issue title to parse")
    parser.add_argument("--issue-body-file", default="", help="Markdown issue body to parse")
    parser.add_argument("--issue-url", default="", help="GitHub issue URL for provenance")
    parser.add_argument("--force", action="store_true", help="Capture even if the URL or content already exists")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be captured without writing files")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""), help="GitHub Actions output file")
    args = parser.parse_args(argv)

    issue_fields: dict[str, str] = {}
    if args.issue_body_file:
        issue_fields = fields_from_issue_body(Path(args.issue_body_file).read_text(encoding="utf-8"))

    source_url = args.url or issue_fields.get("source_url", "") or first_url(args.issue_title)
    if not source_url:
        result = {"status": "failed", "reason": "No source URL provided."}
    else:
        submitted_at = now_iso()
        record = {
            "id": capture_record_id(source_url),
            "source_url": source_url,
            "submitted_at": submitted_at,
            "updated_at": submitted_at,
            "issue_url": args.issue_url,
            "status": "started",
            "reason": "",
            "listing_path": "",
            "listing_id": "",
        }
        try:
            result = ingest_url(source_url, root=args.repo_root, issue_url=args.issue_url, force=args.force, dry_run=args.dry_run)
        except Exception as exc:  # pragma: no cover - network and remote page behavior
            result = {"source": source_url, "status": "failed", "reason": str(exc)}

        status = str(result.get("status", ""))
        reason = str(result.get("reason", ""))
        if status == "skipped" and reason.startswith("HTTP "):
            status = "failed"
        record.update(
            {
                "status": status,
                "reason": reason,
                "listing_path": result.get("listing_path", ""),
                "listing_id": result.get("id", ""),
                "updated_at": now_iso(),
            }
        )
        if not args.dry_run:
            upsert_capture_record(record, root=args.repo_root)

        if result.get("status") == "captured" and not args.dry_run:
            build_index(args.repo_root)

    if result.get("id"):
        print(f"{result['status']}: {source_url} -> {result['id']}")
    elif result.get("listing_path"):
        print(f"{result['status']}: {source_url} ({result.get('reason')}: {result['listing_path']})")
    else:
        print(f"{result.get('status')}: {source_url} ({result.get('reason', '')})")

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
