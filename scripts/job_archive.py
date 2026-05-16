#!/usr/bin/env python3
"""Helpers for a small Markdown based job listing archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import logging
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
LISTINGS_DIR = ROOT / "listings"
INDEX_PATH = ROOT / "data" / "index.csv"

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".html", ".htm"}
URL_RE = re.compile(r"https?://[^\s<>\"']+")
DEFAULT_FETCH_USER_AGENT = "Mozilla/5.0 (compatible; JobListingArchive/1.0; +https://github.com/kane268/job-listing-archive)"
MAX_FETCH_BYTES = 8 * 1024 * 1024
KNOWN_COMPANIES = [
    "Anthropic",
    "Copilot Money",
    "GitHub",
    "Stripe",
    "Apple",
    "Privy",
    "Readwise",
]

FRONTMATTER_ORDER = [
    "id",
    "captured_at",
    "source_url",
    "source_final_url",
    "source_http_status",
    "source_fetched_at",
    "company",
    "role_title",
    "role_family",
    "seniority",
    "location",
    "employment_type",
    "compensation",
    "status",
    "source_type",
    "source_file_name",
    "source_file_created_at",
    "source_file_modified_at",
    "source_file_created_at_basis",
    "source_file_sha256",
    "pdf_created_at",
    "pdf_pages",
    "tags",
    "requirements",
    "nice_to_haves",
]

INDEX_COLUMNS = [
    "id",
    "captured_at",
    "company",
    "role_title",
    "role_family",
    "seniority",
    "location",
    "employment_type",
    "compensation",
    "status",
    "source_type",
    "source_url",
    "tags",
    "listing_path",
]


@dataclass(frozen=True)
class FileTimes:
    created_at: str
    modified_at: str
    created_at_basis: str


@dataclass(frozen=True)
class URLFetch:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    encoding: str
    fetched_at: str

    def text(self) -> str:
        return self.body.decode(self.encoding or "utf-8", errors="replace")


class SimpleHTMLTextExtractor(HTMLParser):
    """Small HTML to text converter for saved Safari pages."""

    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "section",
        "tr",
    }

    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")
        if tag == "a":
            href = dict(attrs).get("href")
            if href and href.startswith(("http://", "https://")):
                self.parts.append(f" {href} ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = []
        previous = ""
        for line in raw.splitlines():
            normalized = re.sub(r"\s+", " ", html.unescape(line)).strip()
            if not normalized:
                continue
            if normalized == previous:
                continue
            lines.append(normalized)
            previous = normalized
        return "\n".join(lines).strip() + ("\n" if lines else "")


class HTMLMetadataExtractor(HTMLParser):
    """Collect title, metadata, links, and JSON-LD scripts from a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.in_json_script = False
        self.title_parts: list[str] = []
        self.current_script: list[str] = []
        self.scripts: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_attrs = {name.lower(): value or "" for name, value in attrs}
        if tag == "title":
            self.in_title = True
            return
        if tag == "meta":
            key = normalized_attrs.get("name") or normalized_attrs.get("property")
            content = normalized_attrs.get("content")
            if key and content:
                self.meta[key.lower()] = content
            return
        if tag == "link":
            rels = {part.lower() for part in normalized_attrs.get("rel", "").split()}
            href = normalized_attrs.get("href")
            if "canonical" in rels and href:
                self.links["canonical"] = href
            return
        if tag == "script":
            script_type = normalized_attrs.get("type", "").lower()
            if "ld+json" in script_type:
                self.in_json_script = True
                self.current_script = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
            return
        if tag == "script" and self.in_json_script:
            script = "".join(self.current_script).strip()
            if script:
                self.scripts.append(script)
            self.current_script = []
            self.in_json_script = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_json_script:
            self.current_script.append(data)

    @property
    def title(self) -> str:
        return normalize_spaces("".join(self.title_parts))


def slugify(value: str) -> str:
    value = html.unescape(value).lower().strip()
    value = value.replace("&", " and ")
    value = value.replace("@", " at ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "listing"


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_listing_suffixes(stem: str) -> str:
    value = normalize_spaces(stem)
    suffixes = [
        " - Jobs - Careers at Apple",
        " - Careers at Apple",
        " - Jobs",
    ]
    for suffix in suffixes:
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
    return value


def clean_role_title(value: str, company: str = "") -> str:
    """Normalize common job board page titles into just the role title."""
    title = strip_listing_suffixes(value)
    title = re.sub(r"^Job Application for\s+", "", title, flags=re.IGNORECASE).strip()

    if " @ " in title:
        role, embedded_company = [part.strip() for part in title.split(" @ ", 1)]
        if not company or slugify(embedded_company) == slugify(company):
            title = role

    if company:
        patterns = [
            rf"\s+at\s+{re.escape(company)}$",
            rf"\s+-\s+{re.escape(company)}$",
            rf"\s+\|\s+{re.escape(company)}$",
        ]
        for pattern in patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE).strip()

    return normalize_spaces(title)


def normalize_source_url(url: str) -> str:
    cleaned = clean_url(url)
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return cleaned
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def infer_metadata_from_filename(path: str | Path) -> dict[str, Any]:
    stem = strip_listing_suffixes(Path(path).stem)
    role_title = stem
    company = ""

    if " @ " in stem:
        role_title, company = [part.strip() for part in stem.split(" @ ", 1)]
    elif "Careers at Apple" in Path(path).stem or "Jobs - Careers at Apple" in Path(path).stem:
        company = "Apple"
        role_title = stem
        if role_title.startswith("US - "):
            role_title = role_title[5:].strip()
        role_title = role_title.replace("Specialist Full-Time", "Specialist: Full-Time")
    else:
        for known in KNOWN_COMPANIES:
            prefix = f"{known} "
            if stem.lower().startswith(prefix.lower()):
                company = known
                role_title = stem[len(prefix) :].strip()
                break

    role_title = normalize_spaces(role_title)
    company = normalize_spaces(company)
    seniority = infer_seniority(role_title)
    role_family = infer_role_family(role_title, company)
    tags = infer_tags(role_title, company, role_family, seniority)

    return {
        "company": company,
        "role_title": role_title,
        "role_family": role_family,
        "seniority": seniority,
        "tags": tags,
    }


def title_from_slug(value: str) -> str:
    words = [word for word in re.split(r"[-_/]+", value) if word]
    small_words = {"and", "or", "of", "the", "at", "to", "in", "for"}
    titled = []
    for index, word in enumerate(words):
        if index and word.lower() in small_words:
            titled.append(word.lower())
        else:
            titled.append(word[:1].upper() + word[1:])
    return " ".join(titled)


def infer_company_from_url(source_url: str) -> str:
    if not source_url:
        return ""
    parsed = urlparse(source_url)
    host = parsed.netloc.lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]

    known_hosts = {
        "anthropic.com": "Anthropic",
        "apple.com": "Apple",
        "jobs.apple.com": "Apple",
        "github.careers": "GitHub",
        "readwise.io": "Readwise",
        "stripe.com": "Stripe",
    }
    for suffix, company in known_hosts.items():
        if host == suffix or host.endswith(f".{suffix}"):
            return company

    if host.endswith("ashbyhq.com") and path_parts:
        return title_from_slug(path_parts[0])
    if host.endswith("greenhouse.io") and path_parts:
        board = path_parts[0]
        if board not in {"jobs", "embed", "boards"}:
            return title_from_slug(board)

    domain = host.split(".")[0]
    if domain in {"jobs", "careers", "boards", "job-boards"}:
        return ""
    return title_from_slug(domain)


def role_title_is_generic(role_title: str, company: str) -> bool:
    normalized_title = slugify(role_title)
    normalized_company = slugify(company)
    return not role_title or normalized_title in {"listing", "job", normalized_company}


def infer_role_title_from_text(text: str, current_role_title: str = "", company: str = "", source_url: str = "") -> str:
    if not role_title_is_generic(current_role_title, company):
        return current_role_title

    keywords = (
        "engineer",
        "developer",
        "manager",
        "architect",
        "specialist",
        "designer",
        "scientist",
        "analyst",
        "director",
        "head of",
    )
    for raw_line in text.splitlines()[:120]:
        line = normalize_spaces(raw_line)
        line = re.sub(r"^[- ]*Page \d+.*$", "", line).strip()
        if not line or len(line) > 140:
            continue
        lowered = line.lower()
        if lowered == company.lower() or lowered.startswith("http"):
            continue
        if "page " in lowered and " of " in lowered:
            continue
        if any(keyword in lowered for keyword in keywords):
            return clean_role_title(line, company)

    if source_url:
        parsed = urlparse(source_url)
        last_part = [part for part in parsed.path.split("/") if part]
        if last_part:
            return clean_role_title(title_from_slug(last_part[-1]), company)
    return clean_role_title(current_role_title, company)


def enrich_metadata_from_text(metadata: dict[str, Any], text: str, source_url: str) -> dict[str, Any]:
    enriched = dict(metadata)
    company = enriched.get("company", "") or infer_company_from_url(source_url)
    role_title = infer_role_title_from_text(text, clean_role_title(enriched.get("role_title", ""), company), company, source_url)

    enriched["company"] = normalize_spaces(company)
    enriched["role_title"] = normalize_spaces(clean_role_title(role_title, company))
    enriched["seniority"] = infer_seniority(enriched["role_title"])
    enriched["role_family"] = infer_role_family(enriched["role_title"], enriched["company"])
    enriched["tags"] = infer_tags(enriched["role_title"], enriched["company"], enriched["role_family"], enriched["seniority"])
    return enriched


def infer_seniority(role_title: str) -> str:
    title = role_title.lower()
    if "head of" in title:
        return "head"
    if "director" in title:
        return "director"
    if "principal" in title:
        return "principal"
    if "senior staff" in title or "senior/staff" in title:
        return "senior-staff"
    if "staff" in title:
        return "staff"
    if "senior" in title:
        return "senior"
    if "specialist" in title:
        return "specialist"
    return ""


def infer_role_family(role_title: str, company: str = "") -> str:
    title = role_title.lower()
    if "specialist" in title and company.lower() == "apple":
        return "retail"
    if "head of engineering" in title or "engineering manager" in title:
        return "engineering-management"
    if "developer experience" in title or "devex" in title:
        return "developer-experience"
    if "backend" in title:
        return "backend"
    if "data" in title:
        return "data"
    if any(term in title for term in ["infrastructure", "platform", "system", "sre", "reliability"]):
        return "infra/platform"
    if any(term in title for term in ["risk", "compliance", "security"]):
        return "security/compliance"
    if "software engineer" in title or "engineer" in title:
        return "software-engineering"
    return ""


def infer_tags(role_title: str, company: str, role_family: str, seniority: str) -> list[str]:
    title = role_title.lower()
    tags = ["imported"]
    if role_family:
        tags.extend(part for part in role_family.split("/") if part)
    if seniority:
        tags.append(seniority)
    keyword_tags = {
        "infrastructure": "infrastructure",
        "platform": "platform",
        "system": "systems",
        "data": "data",
        "developer experience": "developer-experience",
        "risk": "risk",
        "compliance": "compliance",
        "retail": "retail",
        "connect": "connect",
        "experimentation": "experimentation",
    }
    for needle, tag in keyword_tags.items():
        if needle in title:
            tags.append(tag)
    if company:
        tags.append(slugify(company))
    return sorted(set(tags), key=tags.index)


def local_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().replace(microsecond=0).isoformat()


def get_file_times(path: str | Path) -> FileTimes:
    file_path = Path(path)
    stat_result = file_path.stat()
    birthtime = getattr(stat_result, "st_birthtime", None)
    if birthtime and birthtime > 0:
        created_at = local_timestamp(birthtime)
        basis = "birthtime"
    else:
        created_at = local_timestamp(stat_result.st_mtime)
        basis = "mtime"
    return FileTimes(
        created_at=created_at,
        modified_at=local_timestamp(stat_result.st_mtime),
        created_at_basis=basis,
    )


def captured_date_from_times(times: FileTimes) -> str:
    return times.created_at[:10]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def looks_like_html(text: str) -> bool:
    sample = text[:500].lower()
    return "<html" in sample or "<!doctype html" in sample or "<body" in sample


def html_to_text(markup: str) -> str:
    parser = SimpleHTMLTextExtractor()
    parser.feed(markup)
    parser.close()
    return parser.text()


def normalize_text_block(value: str) -> str:
    lines = []
    previous = ""
    for raw_line in html.unescape(value).splitlines():
        line = normalize_spaces(raw_line)
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line
    return "\n".join(lines).strip() + ("\n" if lines else "")


def decode_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return html.unescape(value)


def find_embedded_json_string(markup: str, key: str) -> str:
    pattern = rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"'
    match = re.search(pattern, markup)
    return decode_json_string(match.group(1)) if match else ""


def iter_json_objects(value: Any) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    if isinstance(value, dict):
        objects.append(value)
        for child in value.values():
            objects.extend(iter_json_objects(child))
    elif isinstance(value, list):
        for child in value:
            objects.extend(iter_json_objects(child))
    return objects


def json_type_matches(value: Any, expected: str) -> bool:
    if isinstance(value, str):
        return value.lower() == expected.lower()
    if isinstance(value, list):
        return any(json_type_matches(item, expected) for item in value)
    return False


def format_employment_type(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    text = normalize_spaces(str(value or ""))
    replacements = {
        "FULL_TIME": "Full time",
        "PART_TIME": "Part time",
        "CONTRACTOR": "Contractor",
        "TEMPORARY": "Temporary",
        "INTERN": "Intern",
    }
    return replacements.get(text.upper(), text.replace("_", " ").title() if text.isupper() else text)


def format_job_location(value: Any, remote_hint: Any = None) -> str:
    if isinstance(value, list):
        locations = [format_job_location(item) for item in value]
        return ", ".join(location for location in locations if location)
    if isinstance(value, dict):
        address = value.get("address")
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            text = ", ".join(normalize_spaces(str(part)) for part in parts if part)
            if text:
                return text
        for key in ("name", "addressLocality"):
            if value.get(key):
                return normalize_spaces(str(value[key]))
        return "Remote" if remote_hint else ""
    if remote_hint:
        return "Remote"
    return normalize_spaces(str(value or ""))


def format_compensation(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    currency = value.get("currency") or value.get("salaryCurrency") or ""
    amount = value.get("value")
    if isinstance(amount, dict):
        minimum = amount.get("minValue")
        maximum = amount.get("maxValue")
        unit = amount.get("unitText") or ""
        if minimum and maximum:
            return normalize_spaces(f"{currency} {minimum}-{maximum} {unit}")
        if amount.get("value"):
            return normalize_spaces(f"{currency} {amount.get('value')} {unit}")
    return ""


def extract_jsonld_job_metadata(scripts: list[str]) -> dict[str, Any]:
    for script in scripts:
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        for item in iter_json_objects(payload):
            if not json_type_matches(item.get("@type"), "JobPosting"):
                continue
            organization = item.get("hiringOrganization")
            company = ""
            if isinstance(organization, dict):
                company = normalize_spaces(str(organization.get("name") or ""))
            elif organization:
                company = normalize_spaces(str(organization))
            return {
                "role_title": clean_role_title(str(item.get("title") or ""), company),
                "company": company,
                "description_html": str(item.get("description") or ""),
                "location": format_job_location(item.get("jobLocation"), item.get("applicantLocationRequirements")),
                "employment_type": format_employment_type(item.get("employmentType")),
                "compensation": format_compensation(item.get("baseSalary")),
            }
    return {}


def extract_html_capture_metadata(markup: str, source_url: str = "") -> dict[str, Any]:
    parser = HTMLMetadataExtractor()
    parser.feed(markup)
    parser.close()

    jsonld = extract_jsonld_job_metadata(parser.scripts)
    title = parser.title or normalize_spaces(parser.meta.get("og:title", ""))
    description = parser.meta.get("description") or parser.meta.get("og:description") or ""
    description_plain = find_embedded_json_string(markup, "descriptionPlain")
    description_html = jsonld.get("description_html") or find_embedded_json_string(markup, "descriptionHtml")
    canonical_url = parser.links.get("canonical", "")
    if canonical_url and source_url:
        canonical_url = urljoin(source_url, canonical_url)

    company = jsonld.get("company") or infer_company_from_url(source_url)
    role_title = jsonld.get("role_title") or clean_role_title(title, company)
    location = jsonld.get("location") or find_embedded_json_string(markup, "locationName")

    return {
        "title": title,
        "role_title": role_title,
        "company": company,
        "description": description,
        "description_plain": description_plain,
        "description_html": description_html,
        "canonical_url": canonical_url,
        "location": normalize_spaces(location),
        "employment_type": jsonld.get("employment_type", ""),
        "compensation": jsonld.get("compensation", ""),
    }


def html_capture_to_text(markup: str, metadata: dict[str, Any]) -> str:
    page_text = html_to_text(markup)
    embedded_parts = []
    for key in ("description_plain", "description_html", "description"):
        value = metadata.get(key, "")
        if not value:
            continue
        text = html_to_text(value) if looks_like_html(value) else normalize_text_block(value)
        if text and text.strip() not in page_text:
            embedded_parts.append(text.strip())

    header = []
    for value in (metadata.get("role_title"), metadata.get("company"), metadata.get("location")):
        if value and value not in header:
            header.append(str(value))

    parts = []
    if page_text:
        parts.append(page_text.strip())
    if embedded_parts:
        if len(page_text) < 800:
            parts = ["\n".join(header + embedded_parts).strip()]
        else:
            parts.extend(embedded_parts)
    text = "\n\n".join(part for part in parts if part).strip()
    return text + ("\n" if text else "")


def parse_pdf_date(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    if text.startswith("D:"):
        text = text[2:]
    match = re.match(
        r"^(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?([Z+-])?(\d{2})?'?(\d{2})?'?",
        text,
    )
    if not match:
        return ""
    year, month, day, hour, minute, second, tz_sign, tz_hour, tz_minute = match.groups()
    hour = hour or "00"
    minute = minute or "00"
    second = second or "00"
    tzinfo = None
    if tz_sign == "Z":
        tzinfo = timezone.utc
    elif tz_sign in {"+", "-"}:
        offset = timedelta(hours=int(tz_hour or 0), minutes=int(tz_minute or 0))
        if tz_sign == "-":
            offset = -offset
        tzinfo = timezone(offset)
    try:
        parsed = datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            tzinfo=tzinfo,
        )
    except ValueError:
        return ""
    return parsed.isoformat()


def extract_pdf_text_and_metadata(path: str | Path) -> tuple[str, dict[str, Any], str]:
    try:
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - depends on local environment
        return "", {}, f"pypdf unavailable: {exc}"

    try:
        reader = PdfReader(str(path))
        metadata = dict(reader.metadata or {})
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            page_text = page_text.strip()
            if page_text:
                pages.append(f"--- Page {index} ---\n{page_text}")
        text = "\n\n".join(pages).strip()
        if text:
            text += "\n"
        pdf_metadata = {
            "pdf_pages": len(reader.pages),
            "pdf_created_at": parse_pdf_date(metadata.get("/CreationDate")),
        }
        return text, pdf_metadata, ""
    except Exception as exc:  # pragma: no cover - depends on PDF shape
        return "", {}, f"PDF text extraction failed: {exc}"


def clean_url(url: str) -> str:
    url = html.unescape(url).strip()
    return url.rstrip(".,;:)]}\u201d\u2019\"'")


def fetch_url(url: str, *, timeout: int = 25, max_bytes: int = MAX_FETCH_BYTES) -> URLFetch:
    requested_url = clean_url(url)
    request = urllib.request.Request(
        requested_url,
        headers={
            "User-Agent": DEFAULT_FETCH_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError(f"Response is larger than {max_bytes} bytes")
            headers = response.headers
            encoding = headers.get_content_charset() or "utf-8"
            return URLFetch(
                requested_url=requested_url,
                final_url=response.geturl(),
                status=response.status,
                content_type=headers.get("content-type", ""),
                body=body,
                encoding=encoding,
                fetched_at=datetime.now().astimezone().replace(microsecond=0).isoformat(),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"Error response is larger than {max_bytes} bytes") from exc
        encoding = exc.headers.get_content_charset() or "utf-8"
        return URLFetch(
            requested_url=requested_url,
            final_url=exc.geturl(),
            status=exc.code,
            content_type=exc.headers.get("content-type", ""),
            body=body,
            encoding=encoding,
            fetched_at=datetime.now().astimezone().replace(microsecond=0).isoformat(),
        )


def discover_source_url(text: str, role_title: str = "") -> str:
    if not text:
        return ""
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        url = clean_url(match.group(0))
        if url and url not in urls:
            urls.append(url)

    for url in urls:
        match = re.search(r"jobs\.apple\.com/app/en-us/apply/(\d+)(?:-\d+)?", url)
        if match:
            role_slug = slugify(role_title) if role_title else "job"
            return f"https://jobs.apple.com/en-us/details/{match.group(1)}/{role_slug}"

    preferred_domains = [
        "jobs.ashbyhq.com",
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.apple.com/en-us/details",
        "stripe.com/jobs",
    ]
    for domain in preferred_domains:
        for url in urls:
            if domain in url:
                return url

    ignored = ("w3.org", "apple.com/mac", "apple.com/ipad", "apple.com/iphone")
    for url in urls:
        if not any(domain in url for domain in ignored):
            return url
    return ""


def infer_location(text: str) -> str:
    collapsed = normalize_spaces(text.replace("Te a m", "Team"))
    labels = "Office locations|Remote locations|Location Type|Employment Type|Department|Team|Job type|Apply|Who we are|Summary|Role Number"
    patterns = [
        rf"Office locations\s+(.+?)(?=\s+(?:{labels})\b)",
        rf"Location\s+(.+?)(?=\s+(?:{labels})\b)",
    ]
    for pattern in patterns:
        match = re.search(pattern, collapsed, flags=re.IGNORECASE)
        if match:
            value = normalize_spaces(match.group(1))
            if 0 < len(value) <= 140:
                return value
    if re.search(r"\bremote\b", collapsed, flags=re.IGNORECASE):
        return "Remote"
    return ""


def infer_employment_type(text: str) -> str:
    collapsed = normalize_spaces(text.replace("Te a m", "Team"))
    patterns = [
        r"Job type\s+(.+?)(?=\s+(?:Apply|Who we are|Office locations|Remote locations|Team)\b)",
        r"Employment Type\s+(.+?)(?=\s+(?:Location|Location Type|Department|Team|Who we are)\b)",
    ]
    for pattern in patterns:
        match = re.search(pattern, collapsed, flags=re.IGNORECASE)
        if match:
            value = normalize_spaces(match.group(1))
            if 0 < len(value) <= 80:
                return value
    if re.search(r"full[- ]time\b", collapsed, flags=re.IGNORECASE):
        return "Full time"
    if re.search(r"part[- ]time\b", collapsed, flags=re.IGNORECASE):
        return "Part time"
    return ""


def yaml_quote(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def render_yaml(data: dict[str, Any]) -> str:
    lines: list[str] = ["---"]
    keys = [key for key in FRONTMATTER_ORDER if key in data]
    keys.extend(key for key in data if key not in keys)
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {yaml_quote(item)}")
            else:
                lines.append(f"{key}: []")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {yaml_quote(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def render_listing(data: dict[str, Any], import_notes: list[str], why: str = "TODO") -> str:
    company = data.get("company") or "Unknown company"
    role = data.get("role_title") or "Unknown role"
    why_text = why.strip() or "TODO"
    lines = [
        render_yaml(data).rstrip(),
        "",
        f"# {role} - {company}",
        "",
        "## Why I saved this",
        "",
        why_text,
        "",
        "## Responsibilities",
        "",
        "TODO",
        "",
        "## Requirements",
        "",
        "### Explicitly required",
        "",
        "- TODO",
        "",
        "### Implied",
        "",
        "- TODO",
        "",
        "### Nice-to-have",
        "",
        "- TODO",
        "",
        "## My notes",
        "",
        "TODO",
        "",
        "## Import notes",
        "",
    ]
    lines.extend(f"- {note}" for note in import_notes)
    lines.append("")
    return "\n".join(lines)


def make_listing_id(captured_at: str, company: str, role_title: str) -> str:
    name = f"{company} {role_title}".strip() or "listing"
    return f"{captured_at}-{slugify(name)}"


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "[]":
        return []
    if value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        return bytes(inner, "utf-8").decode("unicode_escape")
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.isdigit():
        return int(value)
    return value


def parse_frontmatter(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    body = text[4:end]
    data: dict[str, Any] = {}
    current_key = ""
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("  - ") and current_key:
            data.setdefault(current_key, []).append(parse_scalar(line[4:]))
            continue
        current_key = ""
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            data[key] = []
            current_key = key
        else:
            data[key] = parse_scalar(value)
    return data


def listing_paths(root: str | Path = ROOT) -> list[Path]:
    listings_root = Path(root) / "listings"
    return sorted(listings_root.glob("*/*/listing.md"))


def existing_source_sha256s(root: str | Path = ROOT) -> dict[str, Path]:
    """Return already imported source checksums mapped to their listing files."""
    checksums: dict[str, Path] = {}
    for listing_path in listing_paths(root):
        metadata = parse_frontmatter(listing_path)
        checksum = metadata.get("source_file_sha256", "")
        if checksum:
            checksums[str(checksum)] = listing_path
    return checksums


def existing_source_urls(root: str | Path = ROOT) -> dict[str, Path]:
    """Return captured source URLs mapped to their listing files."""
    urls: dict[str, Path] = {}
    for listing_path in listing_paths(root):
        metadata = parse_frontmatter(listing_path)
        for key in ("source_url", "source_final_url"):
            value = metadata.get(key, "")
            if value:
                urls[normalize_source_url(str(value))] = listing_path
    return urls


def build_index(root: str | Path = ROOT, index_path: str | Path | None = None) -> Path:
    root_path = Path(root)
    output_path = Path(index_path) if index_path else root_path / "data" / "index.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for listing_path in listing_paths(root_path):
        metadata = parse_frontmatter(listing_path)
        row = {column: "" for column in INDEX_COLUMNS}
        for column in INDEX_COLUMNS:
            if column == "listing_path":
                row[column] = listing_path.relative_to(root_path).as_posix()
            elif column == "tags":
                tags = metadata.get("tags", [])
                row[column] = ",".join(tags) if isinstance(tags, list) else str(tags)
            else:
                row[column] = metadata.get(column, "")
        rows.append(row)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def source_text_and_artifact(path: Path) -> tuple[str, str, str, dict[str, Any], str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, pdf_metadata, warning = extract_pdf_text_and_metadata(path)
        return text, "raw.pdf", "pdf", pdf_metadata, warning

    original = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".html", ".htm"} or looks_like_html(original):
        return html_to_text(original), "raw.html", "html", {}, ""
    return original if original.endswith("\n") else original + "\n", "source.txt", "text", {}, ""


def unique_destination(root: Path, listing_id: str, force: bool) -> tuple[str, Path]:
    year = listing_id[:4]
    base = root / "listings" / year / listing_id
    if force or not base.exists():
        return listing_id, base
    counter = 2
    while True:
        candidate_id = f"{listing_id}-{counter}"
        candidate = root / "listings" / year / candidate_id
        if not candidate.exists():
            return candidate_id, candidate
        counter += 1


def ingest_file(path: str | Path, root: str | Path = ROOT, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    source_path = Path(path)
    root_path = Path(root)
    if source_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return {"source": str(source_path), "status": "skipped", "reason": "unsupported suffix"}

    source_sha256 = sha256_file(source_path)
    existing_listing = existing_source_sha256s(root_path).get(source_sha256)
    if existing_listing and not force:
        return {
            "source": str(source_path),
            "status": "skipped",
            "reason": "already imported",
            "listing_path": str(existing_listing),
        }

    times = get_file_times(source_path)
    captured_at = captured_date_from_times(times)
    inferred = infer_metadata_from_filename(source_path)
    extracted_text, raw_artifact_name, source_type, pdf_metadata, extraction_warning = source_text_and_artifact(source_path)

    raw_txt_name = "raw.txt" if extracted_text else ""
    source_url = discover_source_url(extracted_text, inferred["role_title"])
    inferred = enrich_metadata_from_text(inferred, extracted_text, source_url)
    company = inferred["company"]
    role_title = inferred["role_title"]
    listing_id = make_listing_id(captured_at, company, role_title)
    listing_id, destination = unique_destination(root_path, listing_id, force)

    location = infer_location(extracted_text)
    employment_type = infer_employment_type(extracted_text)
    status = "extracted" if extracted_text else "ingested"
    tags = list(inferred["tags"])
    if source_type not in tags:
        tags.append(source_type)

    metadata: dict[str, Any] = {
        "id": listing_id,
        "captured_at": captured_at,
        "source_url": source_url,
        "company": company,
        "role_title": role_title,
        "role_family": inferred["role_family"],
        "seniority": inferred["seniority"],
        "location": location,
        "employment_type": employment_type,
        "compensation": "",
        "status": status,
        "source_type": source_type,
        "source_file_name": source_path.name,
        "source_file_created_at": times.created_at,
        "source_file_modified_at": times.modified_at,
        "source_file_created_at_basis": times.created_at_basis,
        "source_file_sha256": source_sha256,
        "pdf_created_at": pdf_metadata.get("pdf_created_at", ""),
        "pdf_pages": pdf_metadata.get("pdf_pages", ""),
        "tags": tags,
        "requirements": [],
        "nice_to_haves": [],
    }

    import_notes = [
        f"Original file: `{source_path.name}`",
        f"Source file created at: `{times.created_at}` using `{times.created_at_basis}`",
        f"Source file modified at: `{times.modified_at}`",
        f"Raw artifact: `{raw_artifact_name}`",
    ]
    if raw_txt_name:
        import_notes.append(f"Extracted text: `{raw_txt_name}`")
    if source_url:
        import_notes.append(f"Discovered source URL: {source_url}")
    else:
        import_notes.append("Source URL: not found in imported file")
    if extraction_warning:
        import_notes.append(f"Extraction warning: {extraction_warning}")

    result = {
        "source": str(source_path),
        "status": "would-ingest" if dry_run else "ingested",
        "id": listing_id,
        "destination": str(destination),
        "source_type": source_type,
        "raw_artifact": raw_artifact_name,
        "raw_text": raw_txt_name,
    }
    if dry_run:
        return result

    if force and destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination / raw_artifact_name)
    if extracted_text:
        (destination / raw_txt_name).write_text(extracted_text, encoding="utf-8")
    (destination / "listing.md").write_text(render_listing(metadata, import_notes), encoding="utf-8")
    return result


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def ingest_url(
    source_url: str,
    root: str | Path = ROOT,
    *,
    overrides: dict[str, str] | None = None,
    issue_url: str = "",
    force: bool = False,
    dry_run: bool = False,
    fetched: URLFetch | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    requested_url = clean_url(source_url)
    if not requested_url.startswith(("http://", "https://")):
        return {"source": requested_url, "status": "skipped", "reason": "source URL must start with http or https"}

    known_urls = existing_source_urls(root_path)
    existing_listing = known_urls.get(normalize_source_url(requested_url))
    if existing_listing and not force:
        return {
            "source": requested_url,
            "status": "skipped",
            "reason": "already captured URL",
            "listing_path": relative_to_root(existing_listing, root_path),
        }

    fetch = fetched or fetch_url(requested_url)
    if fetch.status >= 400:
        return {"source": requested_url, "status": "skipped", "reason": f"HTTP {fetch.status}"}

    existing_listing = known_urls.get(normalize_source_url(fetch.final_url))
    if existing_listing and not force:
        return {
            "source": requested_url,
            "status": "skipped",
            "reason": "already captured final URL",
            "listing_path": relative_to_root(existing_listing, root_path),
        }

    source_sha256 = hashlib.sha256(fetch.body).hexdigest()
    existing_listing = existing_source_sha256s(root_path).get(source_sha256)
    if existing_listing and not force:
        return {
            "source": requested_url,
            "status": "skipped",
            "reason": "already captured content",
            "listing_path": relative_to_root(existing_listing, root_path),
        }

    overrides = overrides or {}
    raw = fetch.text()
    is_html = "html" in fetch.content_type.lower() or looks_like_html(raw)
    page_metadata = extract_html_capture_metadata(raw, fetch.final_url or requested_url) if is_html else {}
    extracted_text = html_capture_to_text(raw, page_metadata) if is_html else raw if raw.endswith("\n") else raw + "\n"

    company = normalize_spaces(overrides.get("company", "")) or page_metadata.get("company", "") or infer_company_from_url(fetch.final_url or requested_url)
    role_title = normalize_spaces(overrides.get("role_title", "")) or page_metadata.get("role_title", "")
    role_title = infer_role_title_from_text(extracted_text, role_title, company, fetch.final_url or requested_url)
    role_title = clean_role_title(role_title, company)

    role_family = normalize_spaces(overrides.get("role_family", "")) or infer_role_family(role_title, company)
    seniority = normalize_spaces(overrides.get("seniority", "")) or infer_seniority(role_title)
    location = page_metadata.get("location", "") or infer_location(extracted_text)
    employment_type = page_metadata.get("employment_type", "") or infer_employment_type(extracted_text)
    compensation = page_metadata.get("compensation", "")
    captured_at = datetime.now().astimezone().date().isoformat()
    listing_id = make_listing_id(captured_at, company, role_title)
    listing_id, destination = unique_destination(root_path, listing_id, force)

    source_type = "html" if is_html else "text"
    raw_artifact_name = "raw.html" if is_html else "source.txt"
    tags = [tag for tag in infer_tags(role_title, company, role_family, seniority) if tag != "imported"]
    tags.insert(0, "captured")
    if source_type not in tags:
        tags.append(source_type)

    metadata: dict[str, Any] = {
        "id": listing_id,
        "captured_at": captured_at,
        "source_url": requested_url,
        "source_final_url": fetch.final_url if fetch.final_url != requested_url else "",
        "source_http_status": fetch.status,
        "source_fetched_at": fetch.fetched_at,
        "company": company,
        "role_title": role_title,
        "role_family": role_family,
        "seniority": seniority,
        "location": location,
        "employment_type": employment_type,
        "compensation": compensation,
        "status": "extracted" if extracted_text else "ingested",
        "source_type": source_type,
        "source_file_name": "",
        "source_file_created_at": "",
        "source_file_modified_at": "",
        "source_file_created_at_basis": "url-fetch",
        "source_file_sha256": source_sha256,
        "pdf_created_at": "",
        "pdf_pages": "",
        "tags": tags,
        "requirements": [],
        "nice_to_haves": [],
    }

    import_notes = [
        f"Captured from URL: {requested_url}",
        f"Fetched at: `{fetch.fetched_at}`",
        f"HTTP status: `{fetch.status}`",
        f"Raw artifact: `{raw_artifact_name}`",
        "Extracted text: `raw.txt`" if extracted_text else "Extracted text: not available",
    ]
    if fetch.final_url != requested_url:
        import_notes.append(f"Final URL: {fetch.final_url}")
    if issue_url:
        import_notes.append(f"Capture issue: {issue_url}")

    result = {
        "source": requested_url,
        "status": "would-capture" if dry_run else "captured",
        "id": listing_id,
        "destination": str(destination),
        "listing_path": relative_to_root(destination / "listing.md", root_path),
        "source_type": source_type,
        "raw_artifact": raw_artifact_name,
        "raw_text": "raw.txt" if extracted_text else "",
        "source_final_url": fetch.final_url,
    }
    if dry_run:
        return result

    if force and destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / raw_artifact_name).write_bytes(fetch.body)
    if extracted_text:
        (destination / "raw.txt").write_text(extracted_text, encoding="utf-8")
    (destination / "listing.md").write_text(render_listing(metadata, import_notes, overrides.get("why", "")), encoding="utf-8")
    return result


def iter_importable_files(source_dir: str | Path) -> list[Path]:
    root = Path(source_dir)
    if root.is_file():
        return [root]
    return sorted(path for path in root.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES)


def ingest_paths(source_dir: str | Path, root: str | Path = ROOT, force: bool = False, dry_run: bool = False) -> list[dict[str, Any]]:
    results = []
    for path in iter_importable_files(source_dir):
        results.append(ingest_file(path, root=root, force=force, dry_run=dry_run))
    if not dry_run:
        build_index(root)
    return results


def print_ingest_results(results: list[dict[str, Any]]) -> None:
    for result in results:
        status = result.get("status")
        source_name = Path(result.get("source", "")).name
        if "id" in result:
            print(f"{status}: {source_name} -> {result['id']}")
        elif result.get("listing_path"):
            print(f"{status}: {source_name} ({result.get('reason', '')}: {result['listing_path']})")
        else:
            print(f"{status}: {source_name} ({result.get('reason', '')})")


def ingest_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import saved job listing PDFs or text files.")
    parser.add_argument("source", help="Source file or directory to import")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repository root")
    parser.add_argument("--force", action="store_true", help="Overwrite matching generated destination")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without writing files")
    args = parser.parse_args(argv)
    results = ingest_paths(args.source, root=args.repo_root, force=args.force, dry_run=args.dry_run)
    print_ingest_results(results)
    return 0


def index_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build data/index.csv from listing.md files.")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repository root")
    parser.add_argument("--output", default=None, help="Output CSV path")
    args = parser.parse_args(argv)
    path = build_index(args.repo_root, args.output)
    print(path)
    return 0
