#!/usr/bin/env python3
"""Build the static GitHub Pages UI for the archive."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urlparse

from job_archive import ROOT, clean_role_title, infer_company_from_url, listing_paths, parse_frontmatter
from job_sources import active_sources, read_sources

REPO_URL = "https://github.com/kane268/job-listing-archive"
PAGES_URL = "https://kane268.github.io/job-listing-archive"
PAGES_CMS_SOURCES_URL = "https://app.pagescms.org/kane268/job-listing-archive/main/file/job_sources"
URL_RE = re.compile(r"https?://[^\s<>)]+")
ICON_URL_OVERRIDES = {
    "apple.com": "https://www.apple.com/apple-touch-icon.png",
    "github.com": "https://icon.horse/icon/github.com",
}





def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def site_path(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part)


def format_absolute_date(value: str) -> str:
    if not value:
        return "unknown date"
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return value
    return f"{parsed:%b} {parsed.day}, {parsed:%Y}"


def capture_time_html(value: str) -> str:
    fallback = format_absolute_date(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        return f'Captured <relative-time datetime="{esc(value)}" title="{esc(fallback)}">{esc(fallback)}</relative-time>'
    return f"Captured {esc(fallback)}"


def icon_url_for_host(host: str, size: int = 256) -> str:
    host = host.lower().removeprefix("www.").strip()
    if not host:
        return ""
    if host in ICON_URL_OVERRIDES:
        return ICON_URL_OVERRIDES[host]
    return f"https://www.google.com/s2/favicons?{urlencode({'domain': host, 'sz': size})}"


def icon_url_for_source(name: str, url: str, homepage_url: str = "") -> str:
    host = urlparse(homepage_url or url).netloc
    return icon_url_for_host(host)


def company_homepage_map(sources: Iterable[dict[str, str]]) -> dict[str, str]:
    return {
        source.get("name", "").casefold(): source.get("homepage_url", "")
        for source in active_sources(sources)
        if source.get("name") and source.get("homepage_url")
    }


def url_label(url: str, *, include_path: bool = False) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if not host:
        return url.replace("https://", "").replace("http://", "").rstrip("/")
    if not include_path:
        return host
    path = parsed.path.rstrip("/")
    return f"{host}{path}" if path else host


def read_capture_records(root: str | Path = ROOT) -> list[dict[str, Any]]:
    capture_ledger = Path(root) / "data" / "captures.json"
    if not capture_ledger.exists():
        return []
    payload = json.loads(capture_ledger.read_text(encoding="utf-8"))
    records = payload.get("captures", payload) if isinstance(payload, dict) else payload
    return [record for record in records if isinstance(record, dict) and record.get("status") in {"failed", "started"}] if isinstance(records, list) else []


def read_listing_text(listing_path: Path) -> str:
    raw_md = listing_path.parent / "raw.md"
    if raw_md.exists():
        return raw_md.read_text(encoding="utf-8", errors="replace").strip()
    text = listing_path.read_text(encoding="utf-8", errors="replace")
    end = text.find("\n---\n", 4) if text.startswith("---\n") else -1
    return text[end + 5 :].strip() if end != -1 else text.strip()


def listing_records(root: str | Path = ROOT, company_homepages: dict[str, str] | None = None) -> list[dict[str, Any]]:
    root_path = Path(root)
    company_homepages = company_homepages or {}
    records = []
    for listing_path in listing_paths(root_path):
        metadata = parse_frontmatter(listing_path)
        listing_id = str(metadata.get("id") or listing_path.parent.name)
        source_url = str(metadata.get("source_url") or "")
        company = str(metadata.get("company") or "") or infer_company_from_url(source_url) or "Unknown company"
        role = clean_role_title(str(metadata.get("role_title") or "Unknown role"), company)
        raw_path = listing_path.parent / "raw.md"
        records.append(
            {
                "id": listing_id,
                "title": f"{role} - {company}",
                "role": role,
                "company": company,
                "captured_at": str(metadata.get("captured_at") or ""),
                "captured_time_html": capture_time_html(str(metadata.get("captured_at") or "")),
                "status": str(metadata.get("status") or ""),
                "source_url": source_url,
                "icon_url": icon_url_for_source(company, source_url, company_homepages.get(company.casefold(), "")),
                "listing_path": listing_path.relative_to(root_path).as_posix(),
                "listing_dir_path": listing_path.parent.relative_to(root_path).as_posix(),
                "raw_markdown_path": raw_path.relative_to(root_path).as_posix(),
                "search_text": " ".join(str(part) for part in [company, role, metadata.get("role_family", ""), metadata.get("seniority", ""), metadata.get("location", ""), metadata.get("tags", "")]),
                "page_path": site_path("archive", listing_id, ""),
                "text": read_listing_text(listing_path),
            }
        )
    return sorted(records, key=lambda item: (item["captured_at"], item["id"]), reverse=True)


def safe_markdown_href(href: str) -> str:
    parsed = urlparse(href.strip())
    if parsed.scheme.lower() in {"http", "https", "mailto"}:
        return href.strip()
    return ""


def inline_markdown(value: str) -> str:
    parts: list[str] = []
    last = 0
    for match in re.finditer(r"\[([^\]]+)]\(([^)]+)\)", value):
        parts.append(autolink(value[last : match.start()]))
        label = esc(match.group(1))
        href = safe_markdown_href(match.group(2))
        if href:
            parts.append(f'<a href="{esc(href)}" target="_blank" rel="noreferrer">{label}</a>')
        else:
            parts.append(label)
        last = match.end()
    parts.append(autolink(value[last:]))
    return "".join(parts)


def autolink(value: str) -> str:
    parts: list[str] = []
    last = 0
    for match in URL_RE.finditer(value):
        parts.append(esc(value[last : match.start()]))
        url = match.group(0)
        parts.append(f'<a href="{esc(url)}" target="_blank" rel="noreferrer">{esc(url)}</a>')
        last = match.end()
    parts.append(esc(value[last:]))
    return "".join(parts)


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    html_parts: list[str] = []
    paragraph: list[str] = []
    list_levels: list[int] = []
    list_items_open: list[bool] = []

    def close_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            rendered = "<br>\n".join(inline_markdown(line.rstrip()) for line in paragraph)
            html_parts.append(f"<p>{rendered}</p>")
            paragraph = []

    def open_list(level: int) -> None:
        html_parts.append("<ul>")
        list_levels.append(level)
        list_items_open.append(False)

    def close_current_list_item() -> None:
        if list_items_open and list_items_open[-1]:
            html_parts.append("</li>")
            list_items_open[-1] = False

    def close_one_list() -> None:
        close_current_list_item()
        html_parts.append("</ul>")
        list_levels.pop()
        list_items_open.pop()

    def close_lists() -> None:
        while list_levels:
            close_one_list()

    def start_list_item(level: int, content: str) -> None:
        close_paragraph()
        if not list_levels:
            open_list(level)
        elif level > list_levels[-1]:
            open_list(level)
        else:
            while list_levels and level < list_levels[-1]:
                close_one_list()
            if not list_levels:
                open_list(level)
            elif level == list_levels[-1]:
                close_current_list_item()
            else:
                open_list(level)
        html_parts.append(f"<li>{inline_markdown(content)}")
        list_items_open[-1] = True

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            close_paragraph()
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            close_paragraph()
            close_lists()
            level = min(4, len(heading.group(1)))
            html_parts.append(f"<h{level}>{inline_markdown(heading.group(2).strip())}</h{level}>")
            continue
        item = re.match(r"^([ \t]*)-\s+(.+)$", line)
        if item:
            indent = len(item.group(1).expandtabs(2))
            start_list_item(indent, item.group(2).strip())
            continue
        close_lists()
        paragraph.append(stripped)

    close_paragraph()
    close_lists()
    return "\n".join(html_parts)


def layout(title: str, body: str, description: str = "Job listing archive", asset_prefix: str = "") -> str:
    asset_prefix = asset_prefix.rstrip("/")
    asset_prefix = f"{asset_prefix}/" if asset_prefix else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <meta name="description" content="{esc(description)}">
  <title>{esc(title)}</title>
  <link rel="stylesheet" href="{asset_prefix}assets/site.css">
  <script src="{asset_prefix}assets/relative-time.js" defer></script>
  <script src="{asset_prefix}assets/manage-mode.js" defer></script>
  <script src="{asset_prefix}assets/archive-ui.js" defer></script>
</head>
<body>
{body}
</body>
</html>
"""


def source_card(source: dict[str, str]) -> str:
    name = source.get("name") or source.get("id") or "Saved company"
    url = source.get("url", "")
    icon_url = icon_url_for_source(name, url, source.get("homepage_url", ""))
    return f"""<a class="card source-card" href="{esc(url)}" target="_blank" rel="noreferrer" title="{esc(url)}">
  <img class="icon" src="{esc(icon_url)}" alt="" loading="lazy" decoding="async" onerror="this.style.visibility='hidden'">
  <span class="card-content">
    <span class="card-title">{esc(name)}</span>
    <span class="card-subtitle">{esc(url_label(url, include_path=True))}</span>
  </span>
</a>"""


def listing_card(record: dict[str, Any]) -> str:
    href = site_path(record["page_path"])
    source_label = url_label(record.get("source_url", ""))
    meta_html = f"<span>{record['captured_time_html']}</span>"
    if source_label:
        meta_html += f"<span class=\"source-host\">{esc(source_label)}</span>"
    return f"""<a class="card listing-card" href="{esc(href)}" data-search="{esc(record.get('search_text', ''))}">
  <img class="icon" src="{esc(record['icon_url'])}" alt="" loading="lazy" decoding="async" onerror="this.style.visibility='hidden'">
  <span class="card-content">
    <span class="card-kicker">{esc(record['company'])}</span>
    <span class="card-title">{esc(record['role'])}</span>
    <span class="card-meta-row">{meta_html}</span>
  </span>
</a>"""


def backup_card(record: dict[str, Any]) -> str:
    source = record.get("source_url", "")
    issue = record.get("issue_url", "")
    href = issue or source or REPO_URL
    reason = record.get("reason") or "Capture did not produce a listing yet."
    return f"""<a class="card backup" href="{esc(href)}" target="_blank" rel="noreferrer">
  <span class="icon attention-icon" aria-hidden="true">!</span>
  <span class="card-content">
    <span class="card-title">Capture needs attention</span>
    <span class="card-subtitle">{esc(url_label(source, include_path=True) or source)}</span>
    <span class="card-meta-row"><span>{esc(reason)}</span></span>
  </span>
</a>"""


def build_index_page(sources: list[dict[str, str]], listings: list[dict[str, Any]], captures: list[dict[str, Any]]) -> str:
    source_html = "\n".join(source_card(source) for source in active_sources(sources)) or '<p class="empty">No saved companies yet.</p>'
    listing_html = "\n".join(listing_card(record) for record in listings) or '<p class="empty">No captures yet.</p>'
    failed = [record for record in captures if record.get("status") in {"failed", "started"}]
    backup_html = ""
    if failed:
        backup_html = f"""
<section class="panel owner-only owner-block" style="margin-top:14px" aria-labelledby="backup-title">
  <div class="panel-header"><h2 id="backup-title">Capture backups</h2></div>
  <p class="muted">These URLs were saved even though capture did not finish. Fix the parser, then re-run capture.</p>
  <div class="stack">{' '.join(backup_card(record) for record in failed)}</div>
</section>"""

    body = f"""
<header>
  <h1>Job listing archive</h1>
  <p class="muted">Readable Markdown copies of saved job listings.</p>
</header>

<section class="panel owner-only owner-block" aria-labelledby="capture-title">
  <div class="panel-header"><h2 id="capture-title">Capture URL</h2></div>
  <form id="capture-form" class="capture-form" data-repo-url="{REPO_URL}">
    <label>Listing URL
      <input id="source-url" name="url" type="url" inputmode="url" autocomplete="url" placeholder="https://..." required>
    </label>
    <button type="submit">Create issue</button>
  </form>
  <p class="muted owner-note">Manage mode only hides owner tools in this browser. It is not access control; repository data remains public.</p>
</section>

<div class="section-grid">
  <section class="panel owner-only owner-block" aria-labelledby="sources-title">
    <div class="panel-header">
      <h2 id="sources-title">Saved companies</h2>
      <a class="action-link owner-only owner-inline" href="{PAGES_CMS_SOURCES_URL}" target="_blank" rel="noreferrer">Edit</a>
    </div>
    <div class="stack">{source_html}</div>
  </section>

  <section class="panel listings-panel" aria-labelledby="listings-title">
    <div class="panel-header"><h2 id="listings-title">Listings</h2></div>
    <form id="listing-filter" class="filter-form" role="search">
      <label>Filter listings
        <input id="listing-filter-input" type="search" autocomplete="off" placeholder="Company, role, location, tag">
      </label>
    </form>
    <div class="stack">{listing_html}</div>
  </section>
</div>
{backup_html}

"""
    return layout("Job listing archive", body)


def report_issue_url(record: dict[str, Any]) -> str:
    body = f"""### Listing

{PAGES_URL}/{record['page_path']}

### Source URL

{record.get('source_url') or '_No source URL captured_'}

### GitHub folder

{REPO_URL}/tree/main/{record['listing_dir_path']}

### What looks wrong?

"""
    return f"{REPO_URL}/issues/new?{urlencode({'title': f'Extraction issue: {record["title"]}', 'labels': 'bug,needs-text-extraction', 'body': body})}"


def build_listing_page(record: dict[str, Any]) -> str:
    source_link = f'<a href="{esc(record["source_url"])}" target="_blank" rel="noreferrer">Source</a>' if record.get("source_url") else ""
    github_link = f'{REPO_URL}/tree/main/{record["listing_dir_path"]}'
    raw_link = f'{REPO_URL}/blob/main/{record["raw_markdown_path"]}'
    rendered_markdown = re.sub(r"^# .+\n+", "", record.get("text") or "No captured text available.", count=1)
    body = f"""
<header>
  <p><a href="../../">Job listing archive</a></p>
  <div class="title-row">
    <img class="icon" src="{esc(record['icon_url'])}" alt="" loading="lazy" decoding="async" onerror="this.style.visibility='hidden'">
    <div>
      <span class="card-kicker">{esc(record['company'])}</span>
      <h1>{esc(record['role'])}</h1>
      <p class="muted">{record['captured_time_html']}</p>
    </div>
  </div>
</header>

<nav class="page-actions owner-only owner-flex" aria-label="Listing links">
  {source_link}
  <a href="{esc(github_link)}" target="_blank" rel="noreferrer">View in GitHub</a>
  <a href="{esc(raw_link)}" target="_blank" rel="noreferrer">Raw Markdown</a>
  <a href="{esc(report_issue_url(record))}" target="_blank" rel="noreferrer">Report extraction issue</a>
</nav>

<main class="markdown" aria-label="Rendered listing Markdown">
{markdown_to_html(rendered_markdown)}
</main>
"""
    return layout(record["title"], body, f"Captured Markdown for {record['title']}", asset_prefix="../..")


def copy_assets(root_path: Path, site_dir: Path) -> None:
    asset_source = root_path / "assets"
    asset_destination = site_dir / "assets"
    if asset_destination.exists():
        shutil.rmtree(asset_destination)
    shutil.copytree(asset_source, asset_destination)


def build_site(root: str | Path = ROOT, output_dir: str | Path | None = None) -> Path:
    root_path = Path(root)
    site_dir = Path(output_dir) if output_dir else root_path / "_site"
    sources = read_sources(root_path / "data" / "job-sources.json")
    listings = listing_records(root_path, company_homepage_map(sources))
    captures = read_capture_records(root_path)

    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    copy_assets(root_path, site_dir)
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")

    archive_dir = site_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for record in listings:
        page_dir = site_dir / record["page_path"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(build_listing_page(record), encoding="utf-8")

    (site_dir / "index.html").write_text(build_index_page(sources, listings, captures), encoding="utf-8")
    return site_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the static GitHub Pages site.")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repository root")
    parser.add_argument("--output", default=None, help="Output directory, defaults to _site under the repository root")
    args = parser.parse_args(argv)
    site_dir = build_site(args.repo_root, args.output)
    print(f"Built static site: {site_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
