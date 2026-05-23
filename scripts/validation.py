#!/usr/bin/env python3
"""Archive and data validation helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from job_archive import ROOT, listing_paths, normalize_source_url, normalize_spaces, parse_frontmatter, slugify, split_listing_file

STATUS_VALUES = {"queued", "fetched", "failed", "reviewed", "archived"}
CONTENT_TYPE_VALUES = {"", "html", "markdown"}


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
    seen_urls: dict[str, Path] = {}
    seen_checksums: dict[str, Path] = {}
    listings = listing_paths(root_path)
    if not listings:
        errors.append("No listings found")

    for listing_path in listings:
        rel_listing = listing_path.relative_to(root_path).as_posix()
        metadata, body = split_listing_file(listing_path)
        source_url = str(metadata.get("source_url") or "")
        saved_at = str(metadata.get("saved_at") or "")
        status = str(metadata.get("status") or "")
        content_type = str(metadata.get("content_type") or "")

        if listing_path.parent != root_path / "listings" or listing_path.suffix != ".md":
            errors.append(f"{rel_listing}: listing files must live directly under listings/ as Markdown files")

        for key in ("source_url", "saved_at", "status"):
            if metadata.get(key) in (None, ""):
                errors.append(f"{rel_listing}: missing required frontmatter field {key}")

        if saved_at and not _valid_date(saved_at):
            errors.append(f"{rel_listing}: saved_at must be YYYY-MM-DD")

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
        if content_type not in CONTENT_TYPE_VALUES:
            errors.append(f"{rel_listing}: content_type must be html, markdown, or blank")
        if status in {"fetched", "reviewed", "archived"}:
            for key in ("company", "title"):
                if metadata.get(key) in (None, ""):
                    errors.append(f"{rel_listing}: {key} is required once a listing is fetched")
            if not body.strip():
                errors.append(f"{rel_listing}: fetched listings should have a Markdown body")

        checksum = str(metadata.get("source_sha256") or "")
        if checksum:
            if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                errors.append(f"{rel_listing}: source_sha256 must be a lowercase SHA-256")
            prior = seen_checksums.get(checksum)
            if prior:
                errors.append(f"{rel_listing}: duplicate source_sha256 also used by {prior.relative_to(root_path).as_posix()}")
            seen_checksums[checksum] = listing_path

        http_status = metadata.get("http_status", "")
        if http_status not in (None, "") and not isinstance(http_status, int):
            errors.append(f"{rel_listing}: http_status must be a number when present")

        for key in ("fetched_at", "source_published_at"):
            value = str(metadata.get(key) or "")
            if value and not _valid_iso_datetime(value):
                if not _valid_date(value):
                    errors.append(f"{rel_listing}: {key} must be ISO datetime or YYYY-MM-DD")

        for key in ("tags", "requirements", "nice_to_haves"):
            value = metadata.get(key, [])
            if not isinstance(value, list):
                errors.append(f"{rel_listing}: {key} must be a list")

    errors.extend(validate_job_sources(root_path))
    return errors

