#!/usr/bin/env python3
"""Build the static GitHub Pages UI for the archive."""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from job_archive import ROOT, clean_role_title, infer_company_from_url, listing_paths, parse_frontmatter
from job_sources import active_sources, read_sources

REPO_URL = "https://github.com/kane268/job-listing-archive"
PAGES_URL = "https://kane268.github.io/job-listing-archive"
PAGES_CMS_SOURCES_URL = "https://app.pagescms.org/kane268/job-listing-archive/main/file/job_sources"
ARCHIVE_DIR = ROOT / "archive"
CAPTURE_LEDGER = ROOT / "data" / "captures.json"
URL_RE = re.compile(r"https?://[^\s<>)]+")

CSS = """
:root { color-scheme: light dark; --bg: #fff; --fg: #111; --muted: #5f5f5f; --border: #d7d7d7; --surface: #f7f7f7; --accent: #111; --accent-fg: #fff; --danger: #9c5a00; }
@media (prefers-color-scheme: dark) { :root { --bg: #101010; --fg: #f3f3f3; --muted: #ababab; --border: #333; --surface: #191919; --accent: #f3f3f3; --accent-fg: #101010; --danger: #e2a34a; } }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 980px; padding: 18px 14px 40px; font: 16px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--fg); background: var(--bg); }
a { color: inherit; }
header { margin-bottom: 18px; }
h1 { margin: 0 0 4px; font-size: clamp(1.65rem, 6vw, 2.35rem); line-height: 1.08; }
h2 { margin: 0; font-size: 1.1rem; }
p { margin: 0 0 10px; }
.muted { color: var(--muted); }
.panel { border: 1px solid var(--border); border-radius: 10px; padding: 14px; background: var(--surface); }
.panel-header { display: flex; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.capture-form { display: grid; gap: 10px; }
label { display: grid; gap: 6px; font-weight: 650; }
input, button { width: 100%; border: 1px solid var(--border); border-radius: 8px; padding: 12px; font: inherit; }
input { color: var(--fg); background: var(--bg); }
button { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); font-weight: 750; cursor: pointer; }
.section-grid { display: grid; gap: 14px; margin-top: 14px; }
.stack { display: grid; gap: 10px; }
.card { display: block; color: inherit; text-decoration: none; border: 1px solid var(--border); border-radius: 10px; padding: 12px; background: var(--bg); }
.card:hover, .card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.card-title { display: block; margin-bottom: 3px; font-weight: 750; }
.url, .meta { display: block; color: var(--muted); font-size: .92rem; overflow-wrap: anywhere; }
.empty { color: var(--muted); padding: 4px 0; }
.backup { border-color: var(--danger); }
.backup .card-title { color: var(--danger); }
.action-link, .page-actions a { border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; text-decoration: none; background: var(--bg); white-space: nowrap; }
.page-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }
.markdown { border: 1px solid var(--border); border-radius: 10px; padding: 14px; background: var(--surface); }
.markdown h1, .markdown h2, .markdown h3, .markdown h4 { line-height: 1.18; margin: 1.2em 0 .45em; }
.markdown h1:first-child, .markdown h2:first-child, .markdown h3:first-child { margin-top: 0; }
.markdown h1 { font-size: 1.55rem; }
.markdown h2 { font-size: 1.25rem; }
.markdown h3 { font-size: 1.08rem; }
.markdown p { margin: 0 0 .9em; }
.markdown ul { margin: .25em 0 1em; padding-left: 1.35em; }
.markdown li { margin: .3em 0; }
@media (min-width: 720px) { body { padding: 28px 24px 56px; } .capture-form { grid-template-columns: minmax(0, 1fr) auto; align-items: end; } button { width: auto; min-width: 160px; } .section-grid { grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr); align-items: start; } }
""".strip()


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def site_path(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part)


def read_capture_records() -> list[dict[str, Any]]:
    if not CAPTURE_LEDGER.exists():
        return []
    payload = json.loads(CAPTURE_LEDGER.read_text(encoding="utf-8"))
    records = payload.get("captures", payload) if isinstance(payload, dict) else payload
    return records if isinstance(records, list) else []


def read_listing_text(listing_path: Path) -> str:
    raw_md = listing_path.parent / "raw.md"
    if raw_md.exists():
        return raw_md.read_text(encoding="utf-8", errors="replace").strip()
    raw_txt = listing_path.parent / "raw.txt"
    if raw_txt.exists():
        return raw_txt.read_text(encoding="utf-8", errors="replace").strip()
    text = listing_path.read_text(encoding="utf-8", errors="replace")
    end = text.find("\n---\n", 4) if text.startswith("---\n") else -1
    return text[end + 5 :].strip() if end != -1 else text.strip()


def listing_records() -> list[dict[str, Any]]:
    records = []
    for listing_path in listing_paths(ROOT):
        metadata = parse_frontmatter(listing_path)
        listing_id = str(metadata.get("id") or listing_path.parent.name)
        source_url = str(metadata.get("source_url") or "")
        company = str(metadata.get("company") or "") or infer_company_from_url(source_url) or "Unknown company"
        role = clean_role_title(str(metadata.get("role_title") or "Unknown role"), company)
        raw_path = (listing_path.parent / "raw.md") if (listing_path.parent / "raw.md").exists() else (listing_path.parent / "raw.txt")
        records.append(
            {
                "id": listing_id,
                "title": f"{role} - {company}",
                "role": role,
                "company": company,
                "captured_at": str(metadata.get("captured_at") or ""),
                "status": str(metadata.get("status") or ""),
                "source_url": source_url,
                "listing_path": listing_path.relative_to(ROOT).as_posix(),
                "raw_text_path": raw_path.relative_to(ROOT).as_posix(),
                "page_path": site_path("archive", listing_id, ""),
                "text": read_listing_text(listing_path),
            }
        )
    return sorted(records, key=lambda item: (item["captured_at"], item["id"]), reverse=True)


def inline_markdown(value: str) -> str:
    parts: list[str] = []
    last = 0
    for match in re.finditer(r"\[([^\]]+)]\(([^)]+)\)", value):
        parts.append(autolink(value[last : match.start()]))
        label = esc(match.group(1))
        href = esc(match.group(2))
        parts.append(f'<a href="{href}" target="_blank" rel="noreferrer">{label}</a>')
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
    list_open = False

    def close_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            rendered = "<br>\n".join(inline_markdown(line.rstrip()) for line in paragraph)
            html_parts.append(f"<p>{rendered}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            html_parts.append("</ul>")
            list_open = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            close_paragraph()
            close_list()
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            close_paragraph()
            close_list()
            level = min(4, len(heading.group(1)))
            html_parts.append(f"<h{level}>{inline_markdown(heading.group(2).strip())}</h{level}>")
            continue
        item = re.match(r"^\s*-\s+(.+)$", line)
        if item:
            close_paragraph()
            if not list_open:
                html_parts.append("<ul>")
                list_open = True
            html_parts.append(f"<li>{inline_markdown(item.group(1).strip())}</li>")
            continue
        close_list()
        paragraph.append(stripped)

    close_paragraph()
    close_list()
    return "\n".join(html_parts)


def layout(title: str, body: str, description: str = "Job listing archive") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <meta name="description" content="{esc(description)}">
  <title>{esc(title)}</title>
  <style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""


def source_card(source: dict[str, str]) -> str:
    return f"""<a class="card" href="{esc(source.get('url'))}" target="_blank" rel="noreferrer">
  <span class="card-title">{esc(source.get('name') or source.get('id'))}</span>
  <span class="url">{esc(source.get('url'))}</span>
  {f'<span class="meta">{esc(source.get("notes"))}</span>' if source.get('notes') else ''}
</a>"""


def listing_card(record: dict[str, Any]) -> str:
    href = site_path(record["page_path"])
    source = record.get("source_url") or "No source URL captured"
    meta_parts = [part for part in [record.get("captured_at"), record.get("status")] if part]
    return f"""<a class="card" href="{esc(href)}">
  <span class="card-title">{esc(record['title'])}</span>
  <span class="url">{esc(source)}</span>
  <span class="meta">{esc(' · '.join(meta_parts))}</span>
</a>"""


def backup_card(record: dict[str, Any]) -> str:
    source = record.get("source_url", "")
    issue = record.get("issue_url", "")
    href = issue or source or REPO_URL
    reason = record.get("reason") or "Capture did not produce a listing yet."
    return f"""<a class="card backup" href="{esc(href)}" target="_blank" rel="noreferrer">
  <span class="card-title">Capture needs attention</span>
  <span class="url">{esc(source)}</span>
  <span class="meta">{esc(reason)}</span>
</a>"""


def build_index_page(sources: list[dict[str, str]], listings: list[dict[str, Any]], captures: list[dict[str, Any]]) -> str:
    source_html = "\n".join(source_card(source) for source in active_sources(sources)) or '<p class="empty">No saved companies yet.</p>'
    listing_html = "\n".join(listing_card(record) for record in listings) or '<p class="empty">No captures yet.</p>'
    failed = [record for record in captures if record.get("status") in {"failed", "started"}]
    backup_html = ""
    if failed:
        backup_html = f"""
<section class="panel" style="margin-top:14px" aria-labelledby="backup-title">
  <div class="panel-header"><h2 id="backup-title">Capture backups</h2></div>
  <p class="muted">These URLs were saved even though capture did not finish. Fix the parser, then re-run capture.</p>
  <div class="stack">{' '.join(backup_card(record) for record in failed)}</div>
</section>"""

    body = f"""
<header>
  <h1>Job listing archive</h1>
  <p class="muted">URL capture, saved companies, and readable Markdown copies of saved listings.</p>
</header>

<section class="panel" aria-labelledby="capture-title">
  <div class="panel-header"><h2 id="capture-title">Capture URL</h2></div>
  <form id="capture-form" class="capture-form">
    <label>Listing URL
      <input id="source-url" name="url" type="url" inputmode="url" autocomplete="url" placeholder="https://..." required>
    </label>
    <button type="submit">Create issue</button>
  </form>
</section>

<div class="section-grid">
  <section class="panel" aria-labelledby="sources-title">
    <div class="panel-header">
      <h2 id="sources-title">Saved companies</h2>
      <a class="action-link" href="{PAGES_CMS_SOURCES_URL}" target="_blank" rel="noreferrer">Edit</a>
    </div>
    <div class="stack">{source_html}</div>
  </section>

  <section class="panel" aria-labelledby="listings-title">
    <div class="panel-header"><h2 id="listings-title">Listings</h2></div>
    <div class="stack">{listing_html}</div>
  </section>
</div>
{backup_html}

<script>
const REPO_URL = '{REPO_URL}';
document.getElementById('capture-form').addEventListener('submit', event => {{
  event.preventDefault();
  const url = document.getElementById('source-url').value.trim();
  if (!url) return;
  const params = new URLSearchParams({{ title: 'Capture: ' + url, labels: 'inbox,capture', body: '' }});
  window.location.href = REPO_URL + '/issues/new?' + params.toString();
}});
</script>
"""
    return layout("Job listing archive", body)


def report_issue_url(record: dict[str, Any]) -> str:
    body = f"""### Listing

{PAGES_URL}/{record['page_path']}

### Source URL

{record.get('source_url') or '_No source URL captured_'}

### GitHub record

{REPO_URL}/blob/main/{record['listing_path']}

### What looks wrong?

"""
    return f"{REPO_URL}/issues/new?{urlencode({'title': f'Extraction issue: {record["title"]}', 'labels': 'bug,needs-text-extraction', 'body': body})}"


def build_listing_page(record: dict[str, Any]) -> str:
    source_link = f'<a href="{esc(record["source_url"])}" target="_blank" rel="noreferrer">Source</a>' if record.get("source_url") else ""
    github_link = f'{REPO_URL}/blob/main/{record["listing_path"]}'
    raw_link = f'../../{esc(record["raw_text_path"])}'
    rendered_markdown = re.sub(r"^# .+\n+", "", record.get("text") or "No captured text available.", count=1)
    body = f"""
<header>
  <p><a href="../../">Job listing archive</a></p>
  <h1>{esc(record['title'])}</h1>
  <p class="muted">{esc(record.get('captured_at'))} {esc(record.get('status'))}</p>
</header>

<nav class="page-actions" aria-label="Listing links">
  {source_link}
  <a href="{esc(github_link)}" target="_blank" rel="noreferrer">View in GitHub</a>
  <a href="{raw_link}">Raw capture</a>
  <a href="{esc(report_issue_url(record))}" target="_blank" rel="noreferrer">Report extraction issue</a>
</nav>

<main class="markdown" aria-label="Rendered listing Markdown">
{markdown_to_html(rendered_markdown)}
</main>
"""
    return layout(record["title"], body, f"Captured Markdown for {record['title']}")


def build_site(root: str | Path = ROOT) -> None:
    root_path = Path(root)
    listings = listing_records()
    sources = read_sources(root_path / "data" / "job-sources.json")
    captures = read_capture_records()

    if ARCHIVE_DIR.exists():
        shutil.rmtree(ARCHIVE_DIR)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    for record in listings:
        page_dir = root_path / record["page_path"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(build_listing_page(record), encoding="utf-8")

    (root_path / "index.html").write_text(build_index_page(sources, listings, captures), encoding="utf-8")


def main() -> int:
    build_site(ROOT)
    print("Built static site")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
