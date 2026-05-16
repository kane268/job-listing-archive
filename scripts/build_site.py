#!/usr/bin/env python3
"""Build the static GitHub Pages UI for the archive."""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any

from job_archive import ROOT, clean_role_title, infer_company_from_url, listing_paths, parse_frontmatter
from job_sources import active_sources, read_sources

REPO_URL = "https://github.com/kane268/job-listing-archive"
PAGES_URL = "https://kane268.github.io/job-listing-archive"
ARCHIVE_DIR = ROOT / "archive"
CAPTURE_LEDGER = ROOT / "data" / "captures.json"

CSS = """
:root { color-scheme: light dark; --bg: #fff; --fg: #111; --muted: #606060; --border: #d7d7d7; --surface: #f7f7f7; --accent: #111; --accent-fg: #fff; }
@media (prefers-color-scheme: dark) { :root { --bg: #101010; --fg: #f3f3f3; --muted: #ababab; --border: #333; --surface: #191919; --accent: #f3f3f3; --accent-fg: #101010; } }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 980px; padding: 18px 14px 40px; font: 16px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--fg); background: var(--bg); }
a { color: inherit; }
header { margin-bottom: 18px; }
h1 { margin: 0 0 4px; font-size: clamp(1.65rem, 6vw, 2.35rem); line-height: 1.08; }
h2 { margin: 0 0 10px; font-size: 1.1rem; }
p { margin: 0 0 10px; }
.muted { color: var(--muted); }
.panel { border: 1px solid var(--border); border-radius: 10px; padding: 14px; background: var(--surface); }
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
.backup { border-color: #b36b00; }
.backup .card-title { color: #9c5a00; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; border: 1px solid var(--border); border-radius: 10px; padding: 14px; background: var(--surface); font: .92rem/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.page-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }
.page-actions a { border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; text-decoration: none; background: var(--surface); }
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
                "raw_text_path": (listing_path.parent / "raw.txt").relative_to(ROOT).as_posix(),
                "page_path": site_path("archive", listing_id, ""),
                "text": read_listing_text(listing_path),
            }
        )
    return sorted(records, key=lambda item: (item["captured_at"], item["id"]), reverse=True)


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
    source_html = "\n".join(source_card(source) for source in active_sources(sources)) or '<p class="empty">No sources yet.</p>'
    listing_html = "\n".join(listing_card(record) for record in listings[:12]) or '<p class="empty">No captures yet.</p>'
    failed = [record for record in captures if record.get("status") in {"failed", "started"}]
    backup_html = ""
    if failed:
        backup_html = f"""
<section class="panel" style="margin-top:14px" aria-labelledby="backup-title">
  <h2 id="backup-title">Capture backups</h2>
  <p class="muted">These URLs were saved even though capture did not finish. Fix the parser, then re-run capture.</p>
  <div class="stack">{' '.join(backup_card(record) for record in failed)}</div>
</section>"""

    body = f"""
<header>
  <h1>Job listing archive</h1>
  <p class="muted">URL-first capture, recurring sources, and readable text copies of saved listings.</p>
</header>

<section class="panel" aria-labelledby="capture-title">
  <h2 id="capture-title">Capture a listing</h2>
  <form id="capture-form" class="capture-form">
    <label>Listing URL
      <input id="source-url" name="url" type="url" inputmode="url" autocomplete="url" placeholder="https://..." required>
    </label>
    <button type="submit">Create issue</button>
  </form>
</section>

<div class="section-grid">
  <section class="panel" aria-labelledby="sources-title">
    <h2 id="sources-title">Places to look</h2>
    <div class="stack">{source_html}</div>
  </section>

  <section class="panel" aria-labelledby="listings-title">
    <h2 id="listings-title">Captured listings</h2>
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
  const params = new URLSearchParams({{ title: 'Capture: ' + url, labels: 'inbox', body: '' }});
  window.location.href = REPO_URL + '/issues/new?' + params.toString();
}});
</script>
"""
    return layout("Job listing archive", body)


def build_listing_page(record: dict[str, Any]) -> str:
    source_link = f'<a href="{esc(record["source_url"])}" target="_blank" rel="noreferrer">Source</a>' if record.get("source_url") else ""
    body = f"""
<header>
  <p><a href="../../">Job listing archive</a></p>
  <h1>{esc(record['title'])}</h1>
  <p class="muted">{esc(record.get('captured_at'))} {esc(record.get('status'))}</p>
</header>

<nav class="page-actions" aria-label="Listing links">
  {source_link}
  <a href="../../{esc(record['listing_path'])}">Markdown record</a>
  <a href="../../{esc(record['raw_text_path'])}">Plain text file</a>
</nav>

<section aria-labelledby="text-title">
  <h2 id="text-title">Captured text</h2>
  <pre>{esc(record.get('text') or 'No captured text available.')}</pre>
</section>
"""
    return layout(record["title"], body, f"Captured text for {record['title']}")


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
