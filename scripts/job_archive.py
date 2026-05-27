#!/usr/bin/env python3
"""Helpers for a small Markdown based job listing archive."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
LISTINGS_DIR = ROOT / "listings"
INDEX_PATH = ROOT / "data" / "index.csv"

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
    "A24 Labs",
]

FRONTMATTER_ORDER = [
    "source_url",
    "saved_at",
    "status",
    "company",
    "title",
    "source_final_url",
    "http_status",
    "fetched_at",
    "source_published_at",
    "role_family",
    "seniority",
    "location",
    "employment_type",
    "compensation",
    "content_type",
    "source_sha256",
    "fetch_error",
    "tags",
    "requirements",
    "nice_to_haves",
]

INDEX_COLUMNS = [
    "saved_at",
    "company",
    "title",
    "role_family",
    "seniority",
    "location",
    "employment_type",
    "compensation",
    "status",
    "content_type",
    "source_url",
    "tags",
    "listing_path",
]




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
        self.seen_document_title = False
        self.in_json_script = False
        self.title_parts: list[str] = []
        self.current_script: list[str] = []
        self.scripts: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_attrs = {name.lower(): value or "" for name, value in attrs}
        if tag == "title":
            if not self.seen_document_title:
                self.in_title = True
                self.seen_document_title = True
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
    if company:
        title = re.sub(rf"^{re.escape(company)}\s+Careers\s*[-|]\s*", "", title, flags=re.IGNORECASE).strip()

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
        if " at " in title:
            role, trailing_company = [part.strip() for part in title.rsplit(" at ", 1)]
            normalized_company = slugify(company)
            normalized_trailing = slugify(trailing_company)
            if normalized_trailing and (
                normalized_company.startswith(normalized_trailing) or normalized_trailing.startswith(normalized_company)
            ):
                title = role

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
        "labs.a24films.com": "A24 Labs",
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
    if any(term in title for term in ["devops", "infrastructure", "platform", "system", "sre", "reliability"]):
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
        "devops": "devops",
        "sre": "sre",
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


class MarkdownHTMLConverter(HTMLParser):
    """Small HTML to Markdown converter for job listing content blocks."""

    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.list_depth = 0
        self.skip_depth = 0
        self.href = ""
        self.link_parts: list[str] = []
        self.li_depth = 0

    def emit(self, value: str) -> None:
        self.parts.append(value)

    def ensure_newlines(self, count: int) -> None:
        text = "".join(self.parts)
        existing = len(text) - len(text.rstrip("\n"))
        if existing < count:
            self.parts.append("\n" * (count - existing))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2"}:
            self.ensure_newlines(2)
            self.emit("## ")
        elif tag == "h3":
            self.ensure_newlines(2)
            self.emit("### ")
        elif tag == "h4":
            self.ensure_newlines(2)
            self.emit("#### ")
        elif tag == "p":
            if not self.li_depth:
                self.ensure_newlines(2)
        elif tag in {"ul", "ol"}:
            self.list_depth += 1
            self.ensure_newlines(1)
        elif tag == "li":
            self.ensure_newlines(1)
            self.emit("  " * max(0, self.list_depth - 1) + "- ")
            self.li_depth += 1
        elif tag == "br":
            self.ensure_newlines(1)
        elif tag == "a":
            self.href = attrs_dict.get("href", "")
            self.link_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4"}:
            self.ensure_newlines(2)
        elif tag == "p":
            if not self.li_depth:
                self.ensure_newlines(2)
        elif tag in {"ul", "ol"}:
            self.list_depth = max(0, self.list_depth - 1)
            self.ensure_newlines(2)
        elif tag == "li":
            self.li_depth = max(0, self.li_depth - 1)
            self.ensure_newlines(1)
        elif tag == "a":
            text = normalize_spaces("".join(self.link_parts))
            if text and self.href:
                self.emit(f"[{text}]({self.href})")
            elif text:
                self.emit(text)
            self.href = ""
            self.link_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", html.unescape(data).replace("\xa0", " "))
        if not text.strip():
            return
        if self.href:
            self.link_parts.append(text)
        else:
            self.emit(text)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t]+$", "", line) for line in raw.splitlines()]
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text + ("\n" if text else "")


def html_to_markdown(markup: str) -> str:
    markup = markup or ""
    markup = re.sub(r"<p([^>]*)>\s*<strong>(.*?)</strong>\s*</p>", r"<h2>\2</h2>", markup, flags=re.S | re.I)

    def strong_heading(match: re.Match[str]) -> str:
        text = normalize_spaces(re.sub(r"<.*?>", "", html.unescape(match.group(1))))
        if not text or len(text) > 90:
            return match.group(0)
        return f"<h2>{text}</h2>"

    markup = re.sub(r"<strong>\s*(.*?)\s*</strong>\s*(?:<br\s*/?>\s*){1,2}", strong_heading, markup, flags=re.S | re.I)
    parser = MarkdownHTMLConverter()
    parser.feed(markup)
    parser.close()
    return parser.text()


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
    unavailable = {"", "n/a", "na", "none", "null", "unavailable", "undefined"}
    if isinstance(value, list):
        locations = [format_job_location(item) for item in value]
        return ", ".join(location for location in locations if location)
    if isinstance(value, dict):
        address = value.get("address")
        if isinstance(address, dict):
            parts = [
                normalize_spaces(str(part))
                for part in [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
                if normalize_spaces(str(part)).lower() not in unavailable
            ]
            text = ", ".join(parts)
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
                "published_at": str(item.get("datePosted") or ""),
            }
    return {}


def extract_balanced_json_after(markup: str, marker: str) -> dict[str, Any]:
    start = markup.find(marker)
    if start == -1:
        return {}
    brace = markup.find("{", start)
    if brace == -1:
        return {}
    depth = 0
    in_string = False
    escape = False
    for index in range(brace, len(markup)):
        char = markup[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(markup[brace : index + 1])
                    except json.JSONDecodeError:
                        return {}
    return {}


def markdown_join(parts: list[str]) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip()).strip() + "\n"


A24_LABS_LIST_HEADINGS = {
    "Core Responsibilities",
    "Example Projects You'd Work On",
    "Nice-to-Have Skills",
    "Qualifications",
    "Required Skills & Experience",
}


def decode_js_string_literal(literal: str) -> str:
    try:
        if literal.startswith('"'):
            return str(json.loads(literal))
        if literal.startswith("'"):
            return str(ast.literal_eval(literal))
    except (SyntaxError, ValueError, json.JSONDecodeError):
        pass
    return literal[1:-1].replace(r"\'", "'").replace(r'\"', '"').replace(r"\n", "\n")


def read_js_string_literal(source: str, offset: int) -> tuple[str, int]:
    quote = source[offset]
    index = offset + 1
    escaped = False
    while index < len(source):
        char = source[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return decode_js_string_literal(source[offset : index + 1]), index + 1
        index += 1
    return "", offset + 1


def find_matching_js(source: str, offset: int, opener: str, closer: str) -> int:
    depth = 0
    index = offset
    while index < len(source):
        char = source[index]
        if char in {'"', "'", "`"}:
            _, index = read_js_string_literal(source, index)
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def split_top_level_js_expressions(source: str) -> list[str]:
    parts: list[str] = []
    start = 0
    index = 0
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    while index < len(source):
        char = source[index]
        if char in {'"', "'", "`"}:
            _, index = read_js_string_literal(source, index)
            continue
        if char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth:
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]" and bracket_depth:
            bracket_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}" and brace_depth:
            brace_depth -= 1
        elif char == "," and paren_depth == bracket_depth == brace_depth == 0:
            parts.append(source[start:index])
            start = index + 1
        index += 1
    parts.append(source[start:])
    return parts


def extract_compiled_react_children_text(source: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while True:
        children_index = source.find("children:", index)
        if children_index == -1:
            break
        value_index = children_index + len("children:")
        while value_index < len(source) and source[value_index].isspace():
            value_index += 1
        values, end_index = extract_compiled_react_children_value(source, value_index)
        tokens.extend(values)
        index = end_index if end_index > children_index else children_index + len("children:")
    return tokens


def extract_compiled_react_children_value(source: str, offset: int) -> tuple[list[str], int]:
    while offset < len(source) and source[offset].isspace():
        offset += 1
    if offset >= len(source):
        return [], offset
    char = source[offset]
    if char in {'"', "'", "`"}:
        value, end = read_js_string_literal(source, offset)
        return [value], end
    if char == "[":
        end = find_matching_js(source, offset, "[", "]")
        if end == -1:
            return [], offset + 1
        tokens: list[str] = []
        for part in split_top_level_js_expressions(source[offset + 1 : end]):
            part_offset = 0
            while part_offset < len(part) and part[part_offset].isspace():
                part_offset += 1
            if part_offset >= len(part):
                continue
            if part[part_offset] in {'"', "'", "`"}:
                value, _ = read_js_string_literal(part, part_offset)
                tokens.append(value)
            elif part[part_offset] == "[":
                values, _ = extract_compiled_react_children_value(part, part_offset)
                tokens.extend(values)
            elif "children:" in part:
                tokens.extend(extract_compiled_react_children_text(part))
        return tokens, end + 1

    match = re.match(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\s*\(", source[offset:])
    if match:
        call_start = offset + match.group(0).rfind("(")
        end = find_matching_js(source, call_start, "(", ")")
        if end != -1:
            return extract_compiled_react_children_text(source[offset : end + 1]), end + 1
    return [], offset + 1


def same_origin_script_urls(markup: str, source_url: str) -> list[str]:
    source_host = urlparse(source_url).netloc.lower()
    urls: list[str] = []
    for match in re.finditer(r"<script\b(?P<attrs>[^>]*)>", markup, flags=re.I | re.S):
        attrs = match.group("attrs")
        src_match = re.search(r"\bsrc\s*=\s*(['\"])(.*?)\1", attrs, flags=re.I | re.S)
        if not src_match:
            continue
        url = urljoin(source_url, html.unescape(src_match.group(2)))
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc.lower() == source_host and url not in urls:
            urls.append(url)
    return urls


def fetch_text_asset(url: str, *, timeout: int = 20, max_bytes: int = MAX_FETCH_BYTES) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_FETCH_USER_AGENT,
            "Accept": "application/javascript,text/javascript,text/plain,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"Response is larger than {max_bytes} bytes")
        encoding = response.headers.get_content_charset() or "utf-8"
        return body.decode(encoding, errors="replace")


def extract_a24_labs_asset_texts(markup: str, source_url: str) -> list[str]:
    texts: list[str] = []
    for script_url in same_origin_script_urls(markup, source_url):
        if not urlparse(script_url).path.endswith(".js"):
            continue
        try:
            texts.append(fetch_text_asset(script_url))
        except Exception:
            continue
    return texts


def extract_a24_labs_route_segment(bundle: str, source_url: str) -> str:
    route_path = urlparse(source_url).path.rstrip("/") or "/"
    needles = [f'path:"{route_path}"', f'ogUrl:"{source_url.rstrip("/")}"']
    start = next((index for needle in needles if (index := bundle.find(needle)) != -1), -1)
    if start == -1:
        return ""
    suffix = bundle[start + 1 :]
    next_route = re.search(r",[A-Za-z_$][\w$]*=\{path:\"", suffix)
    end = start + 1 + next_route.start() if next_route else len(bundle)
    return bundle[start:end]


def cleaned_a24_labs_tokens(tokens: list[str]) -> list[str]:
    cleaned: list[str] = []
    previous = ""
    for value in tokens:
        text = normalize_spaces(value)
        if not text or text == previous:
            continue
        cleaned.append(value)
        previous = text
    return cleaned


def a24_labs_role_title_from_tokens(tokens: list[str], fallback: str = "") -> str:
    for value in tokens:
        text = normalize_spaces(value)
        if text in {"A24 Labs", "A24 Labs Careers", "Open Roles"}:
            continue
        if text.startswith("A24 Labs Careers"):
            continue
        if 2 <= len(text) <= 140:
            return clean_role_title(text, "A24 Labs")
    return clean_role_title(fallback, "A24 Labs")


def a24_labs_compensation_from_tokens(tokens: list[str]) -> str:
    text = normalize_spaces(" ".join(normalize_spaces(value) for value in tokens))
    match = re.search(r"\$[\d,]+k?\s*(?:-|to)\s*\$[\d,]+k?", text, flags=re.I)
    return normalize_spaces(match.group(0).replace(" to ", " - ")) if match else ""


def a24_labs_location_from_tokens(tokens: list[str]) -> str:
    normalized = [normalize_spaces(value) for value in tokens]
    for index, value in enumerate(normalized):
        if value == "Location:" and index + 1 < len(normalized):
            location_text = normalized[index + 1]
            if "new york" in location_text.lower():
                return "New York office"
            if re.search(r"\bremote\b", location_text, flags=re.I):
                return "Remote"
            return location_text
    for value in normalized:
        lowered = value.lower()
        if "new york" in lowered and "remote" in lowered:
            return "Remote or New York office"
        if "new york" in lowered:
            return "New York office"
        if re.search(r"\bremote\b", lowered):
            return "Remote"
    return ""


def a24_labs_token_starts_paragraph(value: str) -> bool:
    return value.startswith(
        (
            "*Our target",
            "A24 is an acclaimed",
            "A24 is seeking",
            "Our target",
            "Please note",
            "To apply",
            "We are looking",
            "While we are open",
            "You are ",
            "You'll ",
        )
    )


def a24_labs_markdown_from_tokens(tokens: list[str], source_url: str, role_title: str, location: str, compensation: str) -> str:
    header = [f"# {role_title} - A24 Labs", "", f"Source: {source_url}"]
    if location:
        header.append(f"Location: {location}")
    if compensation:
        header.append(f"Compensation: {compensation}")

    blocks = ["\n".join(header)]
    list_items: list[str] = []
    list_mode = False

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("\n".join(f"- {item}" for item in list_items))
            list_items = []

    index = 0
    while index < len(tokens):
        raw_value = tokens[index]
        value = normalize_spaces(raw_value)
        if not value or value in {"A24 Labs", "A24 Labs Careers", role_title}:
            index += 1
            continue
        if value in A24_LABS_LIST_HEADINGS:
            flush_list()
            blocks.append(f"## {value}")
            list_mode = True
            index += 1
            continue
        if list_mode:
            if a24_labs_token_starts_paragraph(value) or value in {"Compensation:", "Location:"}:
                flush_list()
                list_mode = False
                continue
            list_items.append(value)
            index += 1
            continue
        if value in {"Compensation:", "Location:"}:
            label = value.rstrip(":")
            fragments: list[str] = []
            next_index = index + 1
            while next_index < len(tokens):
                next_value = normalize_spaces(tokens[next_index])
                if next_value in A24_LABS_LIST_HEADINGS or next_value in {"Compensation:", "Location:"}:
                    break
                fragments.append(tokens[next_index])
                next_index += 1
                if label == "Location" or next_value.endswith((".", ").")):
                    break
            label_value = normalize_spaces("".join(fragments))
            label_value = label_value.replace("(*see more below).", "(see more below).")
            label_value = label_value.replace("(*see more below)", "(see more below)")
            if label_value:
                blocks.append(f"**{label}:** {label_value}")
            index = next_index
            continue
        if value.startswith("Please note"):
            paragraph = raw_value
            next_index = index + 1
            while next_index < len(tokens):
                next_value = normalize_spaces(tokens[next_index])
                if next_value in A24_LABS_LIST_HEADINGS or next_value in {"Compensation:", "Location:"}:
                    break
                if next_value.startswith(("*Our target", "seth at", "zeke at")):
                    break
                paragraph += tokens[next_index]
                next_index += 1
                if paragraph.rstrip().endswith("."):
                    break
            blocks.append(normalize_spaces(paragraph))
            index = next_index
            continue
        if value.startswith("*Our target"):
            blocks.append(f"\\{value}")
        else:
            blocks.append(value)
        index += 1
    flush_list()
    return markdown_join(blocks)


def extract_a24_labs_bundle_capture(bundle: str, source_url: str) -> dict[str, Any]:
    if urlparse(source_url).netloc.lower() != "labs.a24films.com" or "/jobs/" not in urlparse(source_url).path:
        return {}
    segment = extract_a24_labs_route_segment(bundle, source_url)
    if not segment:
        return {}
    tokens = cleaned_a24_labs_tokens(extract_compiled_react_children_text(segment))
    if not tokens:
        return {}
    title_match = re.search(r'title:"((?:\\.|[^"\\])*)"', segment)
    fallback_title = decode_js_string_literal(f'"{title_match.group(1)}"') if title_match else ""
    role_title = a24_labs_role_title_from_tokens(tokens, fallback_title)
    if not role_title:
        return {}
    location = a24_labs_location_from_tokens(tokens)
    compensation = a24_labs_compensation_from_tokens(tokens)
    return {
        "company": "A24 Labs",
        "role_title": role_title,
        "role_family": infer_role_family(role_title, "A24 Labs"),
        "location": location,
        "compensation": compensation,
        "markdown": a24_labs_markdown_from_tokens(tokens, source_url, role_title, location, compensation),
    }


def extract_a24_labs_capture(markup: str, source_url: str) -> dict[str, Any]:
    parsed = urlparse(source_url)
    if parsed.netloc.lower() != "labs.a24films.com" or "/jobs/" not in parsed.path:
        return {}
    bundle = "\n".join([markup, *extract_a24_labs_asset_texts(markup, source_url)])
    return extract_a24_labs_bundle_capture(bundle, source_url)


def extract_greenhouse_capture(markup: str, source_url: str) -> dict[str, Any]:
    data = extract_balanced_json_after(markup, "window.__remixContext")
    loader = data.get("state", {}).get("loaderData", {}) if isinstance(data, dict) else {}
    route = next((value for value in loader.values() if isinstance(value, dict) and isinstance(value.get("jobPost"), dict)), {})
    job = route.get("jobPost", {})
    if not job:
        return {}

    company = normalize_spaces(str(job.get("company_name") or infer_company_from_url(source_url)))
    role_title = clean_role_title(str(job.get("title") or ""), company)
    location = normalize_spaces(str(job.get("job_post_location") or ""))
    public_url = str(job.get("public_url") or source_url)
    parts = [f"# {role_title} - {company}", f"Source: {public_url}  \nLocation: {location}".strip()]
    for key in ("introduction", "content"):
        converted = html_to_markdown(str(job.get(key) or "")).strip()
        if converted:
            parts.append(converted)
    pay_ranges = job.get("pay_ranges") if isinstance(job.get("pay_ranges"), list) else []
    if pay_ranges:
        compensation_parts = ["## Compensation"]
        compensation = ""
        for pay_range in pay_ranges:
            if not isinstance(pay_range, dict):
                continue
            description = html_to_markdown(str(pay_range.get("description") or "")).strip()
            if description:
                compensation_parts.append(description)
            title = str(pay_range.get("title") or "Compensation").rstrip(":")
            value = normalize_spaces(f"{pay_range.get('min', '')} - {pay_range.get('max', '')} {pay_range.get('currency_type', '')}")
            if value != "-":
                compensation = f"{title}: {value}"
                compensation_parts.append(compensation)
        parts.append(markdown_join(compensation_parts))
    else:
        compensation = ""
    conclusion = html_to_markdown(str(job.get("conclusion") or "")).strip()
    if conclusion:
        parts.append(conclusion)
    return {
        "company": company,
        "role_title": role_title,
        "location": location,
        "source_url": public_url,
        "compensation": compensation,
        "published_at": str(job.get("published_at") or ""),
        "markdown": markdown_join(parts),
    }


def extract_ashby_capture(markup: str, source_url: str) -> dict[str, Any]:
    data = extract_balanced_json_after(markup, "window.__appData")
    if not data:
        return {}
    organization = data.get("organization", {}) if isinstance(data.get("organization"), dict) else {}
    job = data.get("posting", {}) if isinstance(data.get("posting"), dict) else {}
    if not job:
        return {}
    company = normalize_spaces(str(organization.get("name") or infer_company_from_url(source_url)))
    role_title = clean_role_title(str(job.get("title") or ""), company)
    location = normalize_spaces(str(job.get("locationName") or job.get("locationExternalName") or ""))
    description = html_to_markdown(str(job.get("descriptionHtml") or "")).strip()
    if not description:
        description = normalize_text_block(str(job.get("descriptionPlain") or "")).strip()
    parts = [f"# {role_title} - {company}", f"Source: {source_url}  \nLocation: {location}".strip(), description]
    return {
        "company": company,
        "role_title": role_title,
        "location": location,
        "employment_type": format_employment_type(job.get("employmentType", "")),
        "published_at": str(job.get("publishedDate") or job.get("createdAt") or ""),
        "markdown": markdown_join(parts),
    }


def extract_apple_capture(markup: str, source_url: str) -> dict[str, Any]:
    match = re.search(r"window\.__staticRouterHydrationData\s*=\s*JSON\.parse\((\".*?\")\);", markup, re.S)
    if not match:
        return {}
    try:
        data = json.loads(json.loads(match.group(1)))
    except json.JSONDecodeError:
        return {}
    job = data.get("loaderData", {}).get("jobDetails", {}).get("jobsData", {})
    if not isinstance(job, dict) or not job:
        return {}
    role_title = clean_role_title(str(job.get("postingTitle") or ""), "Apple")
    locations = []
    for location in job.get("locations") or []:
        if not isinstance(location, dict):
            continue
        value = ", ".join(str(part) for part in [location.get("city"), location.get("stateProvince"), location.get("countryName")] if part)
        if value and value not in locations:
            locations.append(value)
    location_text = "; ".join(locations)
    posted = str(job.get("postingDate") or job.get("postingDateMeta") or "")
    parts = [
        f"# {role_title} - Apple",
        f"Source: {source_url}  \nRole number: {job.get('jobNumber', '')}  \nPosted: {posted}  \nLocation: {location_text}".strip(),
    ]
    if job.get("jobSummary"):
        parts.append(f"## Summary\n\n{normalize_text_block(str(job['jobSummary'])).strip()}")
    if job.get("description"):
        parts.append(f"## Description\n\n{normalize_text_block(str(job['description'])).strip()}")
    for key, heading in [("minimumQualifications", "Minimum Qualifications"), ("preferredQualifications", "Preferred Qualifications")]:
        value = str(job.get(key) or "").strip()
        if value:
            items = [normalize_spaces(line) for line in value.splitlines() if normalize_spaces(line)]
            parts.append(f"## {heading}\n\n" + "\n".join(f"- {item}" for item in items))
    return {
        "company": "Apple",
        "role_title": role_title,
        "location": location_text,
        "employment_type": format_employment_type(job.get("employmentType", "")),
        "published_at": posted,
        "markdown": markdown_join(parts),
    }


def extract_readwise_capture(markup: str, source_url: str) -> dict[str, Any]:
    match = re.search(r'<article[^>]*class="[^"]*posting[^"]*"[^>]*>(.*?)</article>', markup, re.S | re.I)
    if not match:
        return {}
    article = match.group(1)
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", article, re.S | re.I)
    role_title = normalize_spaces(re.sub(r"<.*?>", "", html.unescape(title_match.group(1)))) if title_match else ""
    meta_match = re.search(r'<div[^>]*class="[^"]*posting-meta[^"]*"[^>]*>(.*?)</div>', article, re.S | re.I)
    meta_values: list[str] = []
    if meta_match:
        for value in re.findall(r"<span[^>]*>(.*?)</span>", meta_match.group(1), re.S | re.I):
            meta_values.append(normalize_spaces(re.sub(r"<.*?>", "", html.unescape(value))))
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", article, flags=re.S | re.I)
    body = re.sub(r'<div[^>]*class="[^"]*posting-meta[^"]*"[^>]*>.*?</div>', "", body, flags=re.S | re.I)
    converted = html_to_markdown(body).strip()
    meta_line = " | ".join(value for value in meta_values if value)
    parts = [f"# {role_title} - Readwise", f"Source: {source_url}" + (f"  \nMeta: {meta_line}" if meta_line else ""), converted]
    return {
        "company": "Readwise",
        "role_title": role_title,
        "role_family": "backend" if "backend" in role_title.lower() else "",
        "location": next((value for value in meta_values if value.lower() == "remote"), ""),
        "employment_type": next((value for value in meta_values if "time" in value.lower()), ""),
        "markdown": markdown_join(parts),
    }


def strip_html_text(value: str) -> str:
    return normalize_spaces(re.sub(r"<.*?>", "", html.unescape(value or "")))


def extract_compensation_range(text: str) -> str:
    normalized = normalize_spaces(text)
    match = re.search(
        r"((?:[A-Z]{3}\s*)?\$[\d,]+(?:\.\d+)?\s*-\s*(?:[A-Z]{3}\s*)?\$[\d,]+(?:\.\d+)?(?:\s*/\s*[A-Za-z]+)?)",
        normalized,
    )
    return normalize_spaces(match.group(1)) if match else ""


def extract_line_section(lines: list[str], heading: str, stop_headings: set[str]) -> str:
    start = -1
    for index, line in enumerate(lines):
        if line == heading:
            start = index + 1
            break
    if start == -1:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        if line in stop_headings:
            break
        if line:
            collected.append(line)
    return normalize_text_block("\n".join(collected)).strip()


def extract_stripe_details(markup: str) -> dict[str, str]:
    details: dict[str, str] = {}
    for match in re.finditer(r'<div class="JobDetailCardProperty">(.*?)</div>\s*</div>', markup, re.S):
        block = match.group(1)
        title_match = re.search(r'<p class="JobDetailCardProperty__title">(.*?)</p>', block, re.S)
        if not title_match:
            continue
        title = strip_html_text(title_match.group(1))
        values = [strip_html_text(value) for value in re.findall(r'<p(?:\s[^>]*)?>(.*?)</p>', block, re.S)]
        value = next((item for item in values if item and item != title), "")
        if title and value:
            details[title] = value
    return details


def extract_stripe_capture(markup: str, source_url: str) -> dict[str, Any]:
    role_title = ""
    for pattern in [
        r'data-page-title="([^"]+)"',
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        r"<title>(.*?)</title>",
    ]:
        match = re.search(pattern, markup, re.S | re.I)
        if match:
            role_title = clean_role_title(strip_html_text(match.group(1)), "Stripe")
            break
    if not role_title:
        return {}

    details = extract_stripe_details(markup)
    article = ""
    article_match = re.search(r'<div class="ArticleMarkdown">\s*(.*?)\s*</div>', markup, re.S | re.I)
    if article_match:
        article = html_to_markdown(article_match.group(1)).strip()

    page_lines = [normalize_spaces(line) for line in html_to_text(markup).splitlines() if normalize_spaces(line)]
    in_office = extract_line_section(page_lines, "In-office expectations", {"Pay and benefits", "Office locations", "Apply for this role"})
    pay = extract_line_section(page_lines, "Pay and benefits", {"Office locations", "Team", "Job type", "Apply for this role"})
    closing = extract_line_section(page_lines, "We look forward to hearing from you", {"Apply Now", "United States (English)"})

    compensation = ""
    compensation_match = re.search(r"([A-Z]{1,3}\$[\d,]+\s*-\s*[A-Z]{0,3}\$?[\d,]+)", pay)
    if compensation_match:
        compensation = compensation_match.group(1)

    meta_lines = [f"Source: {source_url}"]
    if details.get("Office locations"):
        meta_lines.append(f"Location: {details['Office locations']}")
    if details.get("Team"):
        meta_lines.append(f"Team: {details['Team']}")
    if details.get("Job type"):
        meta_lines.append(f"Job type: {details['Job type']}")

    parts = [f"# {role_title} - Stripe", "  \n".join(meta_lines), article]
    if in_office:
        parts.append(f"## In-office expectations\n\n{in_office}")
    if pay:
        parts.append(f"## Pay and benefits\n\n{pay}")
    if closing:
        parts.append(f"## We look forward to hearing from you\n\n{closing}")

    return {
        "company": "Stripe",
        "role_title": role_title,
        "location": details.get("Office locations", ""),
        "employment_type": details.get("Job type", ""),
        "compensation": compensation,
        "markdown": markdown_join(parts),
    }


def extract_github_capture(markup: str, source_url: str) -> dict[str, Any]:
    parser = HTMLMetadataExtractor()
    parser.feed(markup)
    parser.close()
    jsonld = extract_jsonld_job_metadata(parser.scripts)
    description_html = jsonld.get("description_html", "")
    role_title = clean_role_title(str(jsonld.get("role_title") or parser.title), "GitHub")
    if not role_title or not description_html:
        return {}

    description = html_to_markdown(description_html).strip()
    location = ""
    location_match = re.search(r"In this role you can work from\s+([^\n]+)", description, re.I)
    if location_match:
        location = normalize_spaces(location_match.group(1))
    if not location:
        location = normalize_spaces(str(jsonld.get("location") or ""))
    compensation = jsonld.get("compensation") or extract_compensation_range(description)

    meta_lines = [f"Source: {source_url}"]
    if location:
        meta_lines.append(f"Location: {location}")
    if jsonld.get("employment_type"):
        meta_lines.append(f"Job type: {jsonld['employment_type']}")
    if compensation:
        meta_lines.append(f"Compensation: {compensation}")

    return {
        "company": "GitHub",
        "role_title": role_title,
        "location": location,
        "employment_type": jsonld.get("employment_type", ""),
        "compensation": compensation,
        "published_at": str(jsonld.get("published_at") or ""),
        "markdown": markdown_join([f"# {role_title} - GitHub", "\n".join(meta_lines), description]),
    }


def extract_structured_capture(markup: str, source_url: str) -> dict[str, Any]:
    parsed = urlparse(source_url)
    host = parsed.netloc.lower()
    path = parsed.path
    if "labs.a24films.com" in host and "/jobs/" in path:
        return extract_a24_labs_capture(markup, source_url)
    if "github.careers" in host and "/jobs/" in path:
        return extract_github_capture(markup, source_url)
    if "stripe.com" in host and "/jobs/listing/" in path:
        return extract_stripe_capture(markup, source_url)
    if "greenhouse.io" in host:
        return extract_greenhouse_capture(markup, source_url)
    if "ashbyhq.com" in host:
        return extract_ashby_capture(markup, source_url)
    if "jobs.apple.com" in host:
        return extract_apple_capture(markup, source_url)
    if "readwise.io" in host:
        return extract_readwise_capture(markup, source_url)
    return {}


def extract_html_capture_metadata(markup: str, source_url: str = "") -> dict[str, Any]:
    parser = HTMLMetadataExtractor()
    parser.feed(markup)
    parser.close()

    structured = extract_structured_capture(markup, source_url)
    jsonld = extract_jsonld_job_metadata(parser.scripts)
    title = parser.title or normalize_spaces(parser.meta.get("og:title", ""))
    description = parser.meta.get("description") or parser.meta.get("og:description") or ""
    description_plain = find_embedded_json_string(markup, "descriptionPlain")
    description_html = jsonld.get("description_html") or find_embedded_json_string(markup, "descriptionHtml")
    canonical_url = parser.links.get("canonical", "")
    if canonical_url and source_url:
        canonical_url = urljoin(source_url, canonical_url)

    company = structured.get("company") or jsonld.get("company") or infer_company_from_url(source_url)
    role_title = structured.get("role_title") or jsonld.get("role_title") or clean_role_title(title, company)
    location = structured.get("location") or jsonld.get("location") or find_embedded_json_string(markup, "locationName")

    return {
        "title": title,
        "role_title": role_title,
        "role_family": structured.get("role_family", ""),
        "company": company,
        "description": description,
        "description_plain": description_plain,
        "description_html": description_html,
        "canonical_url": structured.get("source_url") or canonical_url,
        "location": normalize_spaces(location),
        "employment_type": structured.get("employment_type") or jsonld.get("employment_type", ""),
        "compensation": structured.get("compensation") or jsonld.get("compensation", ""),
        "published_at": structured.get("published_at", ""),
        "markdown": structured.get("markdown", ""),
    }


def html_capture_to_text(markup: str, metadata: dict[str, Any]) -> str:
    if metadata.get("markdown"):
        markdown = str(metadata["markdown"]).strip()
        return markdown + "\n"
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


def short_listing_slug(company: str, role_title: str) -> str:
    company_slug = slugify(company) or "company"
    role_tokens = slugify(clean_role_title(role_title, company)).split("-")
    stopwords = {
        "a",
        "an",
        "and",
        "application",
        "at",
        "engineer",
        "engineers",
        "focus",
        "for",
        "job",
        "of",
        "software",
        "the",
    }
    concise_tokens = [token for token in role_tokens if token and token not in stopwords]
    seniority_tokens = {"director", "head", "principal", "senior", "staff"}
    if concise_tokens and all(token in seniority_tokens for token in concise_tokens):
        concise_tokens = role_tokens
    role_slug = "-".join(concise_tokens[:4]) or "role"
    return f"{company_slug}-{role_slug}"


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "[]":
        return []
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            inner = value[1:-1]
            return inner.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
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


def split_listing_file(path: str | Path) -> tuple[dict[str, Any], str]:
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    return parse_frontmatter(path), text[end + 5 :]


def write_listing_file(path: str | Path, metadata: dict[str, Any], body: str = "") -> Path:
    listing_path = Path(path)
    listing_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_body = body.strip()
    text = render_yaml(metadata)
    if normalized_body:
        text += "\n" + normalized_body + "\n"
    listing_path.write_text(text, encoding="utf-8")
    return listing_path


def listing_paths(root: str | Path = ROOT) -> list[Path]:
    listings_root = Path(root) / "listings"
    flat_listings = sorted(path for path in listings_root.glob("*.md") if path.is_file())
    legacy_listings = sorted(listings_root.glob("**/listing.md"))
    return sorted(flat_listings + legacy_listings)


def listing_slug(path: str | Path) -> str:
    listing_path = Path(path)
    if listing_path.name == "listing.md":
        return listing_path.parent.name
    return listing_path.stem


def existing_source_sha256s(root: str | Path = ROOT) -> dict[str, Path]:
    """Return already fetched source checksums mapped to listing files."""
    checksums: dict[str, Path] = {}
    for listing_path in listing_paths(root):
        metadata = parse_frontmatter(listing_path)
        checksum = metadata.get("source_sha256") or metadata.get("source_file_sha256", "")
        if checksum:
            checksums[str(checksum)] = listing_path
    return checksums


def existing_source_urls(root: str | Path = ROOT) -> dict[str, Path]:
    """Return source URLs mapped to listing files."""
    urls: dict[str, Path] = {}
    for listing_path in listing_paths(root):
        metadata = parse_frontmatter(listing_path)
        for key in ("source_url", "source_final_url"):
            value = metadata.get(key, "")
            if value:
                urls[normalize_source_url(str(value))] = listing_path
    return urls


def listing_metadata_value(metadata: dict[str, Any], column: str) -> Any:
    legacy_keys = {
        "saved_at": "captured_at",
        "title": "role_title",
        "content_type": "source_type",
    }
    value = metadata.get(column, "")
    if value in (None, "") and column in legacy_keys:
        value = metadata.get(legacy_keys[column], "")
    return value


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
                row[column] = listing_metadata_value(metadata, column)
        rows.append(row)
    rows.sort(key=lambda row: (row.get("saved_at", ""), row.get("company", ""), row.get("title", "")), reverse=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def listing_filename(saved_at: str, company: str, title: str) -> str:
    prefix = saved_at if re.fullmatch(r"\d{4}-\d{2}-\d{2}", saved_at or "") else datetime.now().astimezone().date().isoformat()
    return f"{prefix}-{short_listing_slug(company, title)}.md"


def unique_listing_path(root: Path, filename: str, force: bool = False) -> Path:
    listings_root = root / "listings"
    listings_root.mkdir(parents=True, exist_ok=True)
    target = listings_root / filename
    if force or not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 2
    while True:
        candidate = listings_root / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def fetched_listing_metadata(
    source_url: str,
    fetch: URLFetch,
    *,
    existing: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    existing = existing or {}
    requested_url = clean_url(source_url)
    raw = fetch.text()
    is_html = "html" in fetch.content_type.lower() or looks_like_html(raw)
    page_metadata = extract_html_capture_metadata(raw, fetch.final_url or requested_url) if is_html else {}
    body = html_capture_to_text(raw, page_metadata) if is_html else raw if raw.endswith("\n") else raw + "\n"

    company = normalize_spaces(str(existing.get("company") or "")) or page_metadata.get("company", "") or infer_company_from_url(fetch.final_url or requested_url)
    title = normalize_spaces(str(existing.get("title") or existing.get("role_title") or "")) or page_metadata.get("role_title", "")
    title = infer_role_title_from_text(body, title, company, fetch.final_url or requested_url)
    title = clean_role_title(title, company)

    role_family = normalize_spaces(str(existing.get("role_family") or "")) or page_metadata.get("role_family", "") or infer_role_family(title, company)
    seniority = normalize_spaces(str(existing.get("seniority") or "")) or infer_seniority(title)
    location = normalize_spaces(str(existing.get("location") or "")) or page_metadata.get("location", "") or infer_location(body)
    employment_type = normalize_spaces(str(existing.get("employment_type") or "")) or page_metadata.get("employment_type", "") or infer_employment_type(body)
    compensation = normalize_spaces(str(existing.get("compensation") or "")) or page_metadata.get("compensation", "")
    content_type = "html" if is_html else "markdown"
    existing_tags = existing.get("tags", [])
    tags = existing_tags if isinstance(existing_tags, list) and existing_tags else infer_tags(title, company, role_family, seniority)

    metadata: dict[str, Any] = dict(existing)
    metadata.update(
        {
            "source_url": requested_url,
            "saved_at": str(existing.get("saved_at") or existing.get("captured_at") or datetime.now().astimezone().date().isoformat()),
            "status": "fetched" if body.strip() else "failed",
            "company": company,
            "title": title,
            "source_final_url": fetch.final_url if fetch.final_url != requested_url else str(existing.get("source_final_url") or ""),
            "http_status": fetch.status,
            "fetched_at": fetch.fetched_at,
            "source_published_at": page_metadata.get("published_at", existing.get("source_published_at", "")),
            "role_family": role_family,
            "seniority": seniority,
            "location": location,
            "employment_type": employment_type,
            "compensation": compensation,
            "content_type": content_type,
            "source_sha256": hashlib.sha256(fetch.body).hexdigest(),
            "fetch_error": "",
            "tags": tags,
            "requirements": existing.get("requirements", []) if isinstance(existing.get("requirements", []), list) else [],
            "nice_to_haves": existing.get("nice_to_haves", []) if isinstance(existing.get("nice_to_haves", []), list) else [],
        }
    )
    return metadata, body


def should_enrich_listing(metadata: dict[str, Any], body: str, *, force: bool = False) -> bool:
    if force:
        return bool(metadata.get("source_url"))
    status = str(metadata.get("status") or "").strip().lower()
    if status in {"queued", "failed"}:
        return bool(metadata.get("source_url"))
    return bool(metadata.get("source_url")) and not body.strip()


def enrich_listing_file(path: str | Path, *, force: bool = False, fetched: URLFetch | None = None) -> dict[str, Any]:
    listing_path = Path(path)
    metadata, body = split_listing_file(listing_path)
    source_url = clean_url(str(metadata.get("source_url") or ""))
    if not source_url.startswith(("http://", "https://")):
        metadata["status"] = "failed"
        metadata["fetch_error"] = "source_url must start with http or https"
        write_listing_file(listing_path, metadata, body)
        return {"status": "failed", "path": str(listing_path), "reason": metadata["fetch_error"]}
    if not should_enrich_listing(metadata, body, force=force):
        return {"status": "skipped", "path": str(listing_path), "reason": "not queued"}

    try:
        fetch = fetched or fetch_url(source_url)
    except Exception as exc:  # noqa: BLE001 - preserve fetch failures in the listing file.
        metadata["status"] = "failed"
        metadata["fetch_error"] = str(exc)
        write_listing_file(listing_path, metadata, body)
        return {"status": "failed", "path": str(listing_path), "reason": str(exc)}

    if fetch.status >= 400:
        metadata.update(
            {
                "status": "failed",
                "http_status": fetch.status,
                "fetched_at": fetch.fetched_at,
                "source_final_url": fetch.final_url if fetch.final_url != source_url else str(metadata.get("source_final_url") or ""),
                "fetch_error": f"HTTP {fetch.status}",
            }
        )
        write_listing_file(listing_path, metadata, body)
        return {"status": "failed", "path": str(listing_path), "reason": f"HTTP {fetch.status}"}

    enriched_metadata, enriched_body = fetched_listing_metadata(source_url, fetch, existing=metadata)
    write_listing_file(listing_path, enriched_metadata, enriched_body)
    return {"status": "fetched", "path": str(listing_path), "title": enriched_metadata.get("title", "")}


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
    force: bool = False,
    dry_run: bool = False,
    fetched: URLFetch | None = None,
) -> dict[str, Any]:
    """Fetch a URL into a flat Pages CMS friendly listing file."""
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
            "reason": "already fetched URL",
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
            "reason": "already fetched final URL",
            "listing_path": relative_to_root(existing_listing, root_path),
        }

    source_sha256 = hashlib.sha256(fetch.body).hexdigest()
    existing_listing = existing_source_sha256s(root_path).get(source_sha256)
    if existing_listing and not force:
        return {
            "source": requested_url,
            "status": "skipped",
            "reason": "already fetched content",
            "listing_path": relative_to_root(existing_listing, root_path),
        }

    existing = dict(overrides or {})
    if "role_title" in existing and "title" not in existing:
        existing["title"] = existing["role_title"]
    metadata, body = fetched_listing_metadata(requested_url, fetch, existing=existing)
    filename = listing_filename(str(metadata.get("saved_at") or ""), str(metadata.get("company") or ""), str(metadata.get("title") or ""))
    listing_path = unique_listing_path(root_path, filename, force=force)
    result = {
        "source": requested_url,
        "status": "would-fetch" if dry_run else "fetched",
        "destination": str(listing_path),
        "listing_path": relative_to_root(listing_path, root_path),
        "content_type": metadata.get("content_type", ""),
        "source_final_url": fetch.final_url,
    }
    if dry_run:
        return result
    write_listing_file(listing_path, metadata, body)
    return result


def index_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build data/index.csv from listing.md files.")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repository root")
    parser.add_argument("--output", default=None, help="Output CSV path")
    args = parser.parse_args(argv)
    path = build_index(args.repo_root, args.output)
    print(path)
    return 0
