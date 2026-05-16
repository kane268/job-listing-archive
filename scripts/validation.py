#!/usr/bin/env python3
"""Archive and data validation helpers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from job_archive import (
    ROOT,
    listing_date_parts,
    listing_directory_slug,
    listing_paths,
    normalize_source_url,
    normalize_spaces,
    parse_frontmatter,
    slugify,
)

STATUS_VALUES = {"captured", "extracted", "reviewed", "archived"}
SOURCE_TYPE_VALUES = {"html", "markdown"}
CAPTURE_STATUS_VALUES = {"started", "failed"}


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_iso_datetime(value: str) -> bool:
    if not value:
        return True
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _artifact_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_capture_ledger(root: str | Path = ROOT) -> list[str]:
    root_path = Path(root)
    path = root_path / "data" / "captures.json"
    errors: list[str] = []
    if not path.exists():
        return errors
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"data/captures.json is invalid JSON: {exc}"]
    records = payload.get("captures", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return ["data/captures.json must contain a captures array"]
    seen_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            errors.append(f"data/captures.json record {index} must be an object")
            continue
        record_id = str(record.get("id") or "")
        if not record_id:
            errors.append(f"data/captures.json record {index} is missing id")
        elif record_id in seen_ids:
            errors.append(f"data/captures.json duplicate id: {record_id}")
        seen_ids.add(record_id)
        source_url = str(record.get("source_url") or "")
        if source_url and not _valid_url(source_url):
            errors.append(f"data/captures.json record {record_id or index} has invalid source_url")
        status = str(record.get("status") or "")
        if status not in CAPTURE_STATUS_VALUES:
            errors.append(f"data/captures.json record {record_id or index} status must be started or failed")
        if record.get("listing_path") or record.get("listing_id"):
            errors.append(f"data/captures.json record {record_id or index} should not duplicate successful listing data")
        for key in ("submitted_at", "updated_at"):
            value = str(record.get(key) or "")
            if value and not _valid_iso_datetime(value):
                errors.append(f"data/captures.json record {record_id or index} has invalid {key}")
    return errors


def validate_job_sources(root: str | Path = ROOT) -> list[str]:
    root_path = Path(root)
    path = root_path / "data" / "job-sources.json"
    errors: list[str] = []
    if not path.exists():
        return ["data/job-sources.json is missing"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"data/job-sources.json is invalid JSON: {exc}"]
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        return ["data/job-sources.json must contain a sources array"]
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            errors.append(f"data/job-sources.json source {index} must be an object")
            continue
        name = normalize_spaces(str(source.get("name") or ""))
        source_id = slugify(name)
        if not name:
            errors.append(f"data/job-sources.json source {index} is missing name")
        elif name.casefold() in seen_names:
            errors.append(f"data/job-sources.json duplicate source name: {name}")
        seen_names.add(name.casefold())
        if source_id in seen_ids:
            errors.append(f"data/job-sources.json duplicate source id: {source_id}")
        seen_ids.add(source_id)
        for key in ("url", "homepage_url"):
            value = str(source.get(key) or "")
            if not _valid_url(value):
                errors.append(f"data/job-sources.json source {name or index} has invalid {key}")
    return errors


def validate_archive(root: str | Path = ROOT) -> list[str]:
    root_path = Path(root)
    errors: list[str] = []
    seen_ids: dict[str, Path] = {}
    seen_urls: dict[str, Path] = {}
    seen_checksums: dict[str, Path] = {}
    listings = listing_paths(root_path)
    if not listings:
        errors.append("No listings found")

    for listing_path in listings:
        rel_listing = listing_path.relative_to(root_path).as_posix()
        metadata = parse_frontmatter(listing_path)
        listing_id = str(metadata.get("id") or "")
        captured_at = str(metadata.get("captured_at") or "")
        source_url = str(metadata.get("source_url") or "")
        status = str(metadata.get("status") or "")
        source_type = str(metadata.get("source_type") or "")
        raw_md = listing_path.parent / "raw.md"
        raw_html = listing_path.parent / "raw.html"
        raw_txt = listing_path.parent / "raw.txt"
        raw_pdf = listing_path.parent / "raw.pdf"

        for key in ("id", "captured_at", "company", "role_title", "status", "source_type"):
            if metadata.get(key) in (None, ""):
                errors.append(f"{rel_listing}: missing required frontmatter field {key}")

        if listing_id:
            prior = seen_ids.get(listing_id)
            if prior:
                errors.append(f"{rel_listing}: duplicate id also used by {prior.relative_to(root_path).as_posix()}")
            seen_ids[listing_id] = listing_path

        if captured_at and not _valid_date(captured_at):
            errors.append(f"{rel_listing}: captured_at must be YYYY-MM-DD")
        if captured_at and listing_id:
            expected_parts = ("listings", *listing_date_parts(captured_at), listing_directory_slug(listing_id, captured_at), "listing.md")
            expected = "/".join(expected_parts)
            if rel_listing != expected:
                errors.append(f"{rel_listing}: path should be {expected}")

        if source_url:
            if not _valid_url(source_url):
                errors.append(f"{rel_listing}: source_url is not a valid HTTP URL")
            normalized = normalize_source_url(source_url)
            prior = seen_urls.get(normalized)
            if prior:
                errors.append(f"{rel_listing}: duplicate source_url also used by {prior.relative_to(root_path).as_posix()}")
            seen_urls[normalized] = listing_path

        final_url = str(metadata.get("source_final_url") or "")
        if final_url:
            if not _valid_url(final_url):
                errors.append(f"{rel_listing}: source_final_url is not a valid HTTP URL")
            normalized = normalize_source_url(final_url)
            prior = seen_urls.get(normalized)
            if prior:
                errors.append(f"{rel_listing}: duplicate source_final_url also used by {prior.relative_to(root_path).as_posix()}")
            seen_urls[normalized] = listing_path

        if status not in STATUS_VALUES:
            errors.append(f"{rel_listing}: status must be one of {', '.join(sorted(STATUS_VALUES))}")
        if source_type not in SOURCE_TYPE_VALUES:
            errors.append(f"{rel_listing}: source_type must be html or markdown")

        if not raw_md.exists():
            errors.append(f"{rel_listing}: raw.md is required")
        if source_type == "html" and not raw_html.exists():
            errors.append(f"{rel_listing}: raw.html is required for html captures")
        if source_type == "markdown" and raw_html.exists():
            errors.append(f"{rel_listing}: markdown captures should not have raw.html")
        if raw_txt.exists():
            errors.append(f"{rel_listing}: raw.txt is obsolete; keep raw.md instead")
        if raw_pdf.exists():
            errors.append(f"{rel_listing}: raw.pdf is obsolete; keep raw.md instead")

        checksum = str(metadata.get("source_file_sha256") or "")
        if checksum:
            if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                errors.append(f"{rel_listing}: source_file_sha256 must be a lowercase SHA-256")
            prior = seen_checksums.get(checksum)
            if prior:
                errors.append(f"{rel_listing}: duplicate source_file_sha256 also used by {prior.relative_to(root_path).as_posix()}")
            seen_checksums[checksum] = listing_path
            if raw_html.exists() and _artifact_checksum(raw_html) != checksum:
                errors.append(f"{rel_listing}: source_file_sha256 does not match raw.html")

        for key in ("source_fetched_at", "source_published_at"):
            value = str(metadata.get(key) or "")
            if value and not _valid_iso_datetime(value):
                # Source systems sometimes publish date-only strings; accept those too.
                if not _valid_date(value):
                    errors.append(f"{rel_listing}: {key} must be ISO datetime or YYYY-MM-DD")

        for key in ("tags", "requirements", "nice_to_haves"):
            value = metadata.get(key)
            if not isinstance(value, list):
                errors.append(f"{rel_listing}: {key} must be a list")

    errors.extend(validate_job_sources(root_path))
    errors.extend(validate_capture_ledger(root_path))
    return errors


