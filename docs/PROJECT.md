# Project Notes

## Origin

This repo started as a formal version of a personal habit: saving interesting tech job listings from Safari on phone and laptop for later reference.

The goal is not to build a job-search CRM, scraper, or application tracker. The goal is a durable public-safe archive where interesting roles can be captured quickly, normalized later, and analyzed only when there is enough data.

Initial imported files came from:

```text
a local import folder
```

Those files were mostly Safari-generated PDFs, plus one saved Apple page. The import scripts preserve original file names, macOS file creation times when available, PDF metadata when available, raw artifacts, extracted text, and a generated listing record.

## Design principles

- Capture fast, normalize later.
- Keep Markdown files as the source of truth.
- Keep capture notes public-safe because the web workflow uses public GitHub Pages and Issues.
- Treat fetched HTML, PDFs, and raw text as evidence.
- Use GitHub Issues as the mobile URL inbox.
- Use Pages CMS for structured source maintenance, not primary quick capture.
- Avoid scraping unless explicitly requested.
- Prefer small scripts and generated CSVs over a database.
- Keep metadata useful but not burdensome.

## What belongs here

### Job listings

Each listing lives at:

```text
listings/YYYY/<id>/listing.md
```

Optional raw files sit beside it:

```text
raw.pdf     original PDF snapshot
raw.html    original saved HTML page
source.txt  original saved text file
raw.txt     generated text extraction
```

`listing.md` is the canonical human-editable record. It has YAML front matter for filtering and Markdown sections for interpretation, notes, and requirement review.

### Job sources

Recurring places to look for jobs live in:

```text
data/job-sources.json
```

Examples include company career pages such as Anthropic, GitHub, Stripe, Apple, and Readwise.

### Generated data

`data/index.csv` is generated from all `listing.md` files. `archive/<id>/index.html` pages and the home page are generated from source files and `raw.txt`.

Rebuild generated data with:

```bash
mise run check
```

Do not hand-edit generated index rows, generated archive pages, or generated `raw.txt`. Edit the relevant `listing.md`, source artifact, or extraction script, then rebuild.

## Current workflow

### Mobile capture

Use the GitHub Pages web UI:

```text
https://kane268.github.io/job-listing-archive/
```

Paste a listing URL. The site opens a prefilled GitHub issue with an empty body and the URL in the title. GitHub Actions fetches the page, saves `raw.html`, extracts `raw.txt`, creates `listing.md`, rebuilds `data/index.csv`, rebuilds the static site, commits the result, labels the issue `ingested`, and closes it. If capture fails, Actions saves the URL in `data/captures.json` and the live site shows it as a backup for later parser fixes and re-capture.

Legacy PDF import remains available for old saved files, but PDF capture is no longer the normal path.

For a new source page, use the job source issue form:

```text
https://github.com/kane268/job-listing-archive/issues/new?template=job-source.yml
```

### Laptop sync

Most routine work should use:

```bash
mise run update
```

That imports legacy iCloud files, skips already imported files by SHA-256, rebuilds `data/index.csv`, runs checks, commits, and pushes.

Useful commands:

```bash
mise run import          # import legacy iCloud files only
mise run save            # check, commit, and push current changes
mise run check           # validate mise tasks, rebuild index and site, run tests
mise run sources         # list job source pages
mise run browse          # open active job source pages
mise run add-source      # add or update a source
mise run site            # rebuild static GitHub Pages site
mise run validate-capture # test live URL capture in a temp repo
mise run capture         # open web listing capture UI
mise run capture-source  # open source capture issue form
```

## Data model

Important `listing.md` front matter fields:

```yaml
id: "2026-05-09-readwise-senior-staff-engineer-backend-focus"
captured_at: "2026-05-09"
source_url: "https://readwise.io/careers/senior-staff-engineer"
company: "Readwise"
role_title: "Senior/Staff Engineer (Backend Focus)"
role_family: "backend"
seniority: "senior-staff"
location: "Remote"
employment_type: "Full time"
status: "extracted"
source_type: "pdf"
source_file_name: "Readwise.pdf"
source_file_created_at: "2026-05-09T22:14:54-04:00"
source_file_sha256: "..."
tags:
  - "imported"
  - "backend"
```

Metadata is for filtering and grouping. The Markdown body is for memory, judgment, and notes.

## Status meanings

- `captured`: saved quickly, not normalized yet
- `ingested`: imported into the repo
- `extracted`: raw text exists
- `reviewed`: requirements, tags, and notes reviewed
- `archived`: no more action needed

## Issue workflow

GitHub Issues are an inbox, not the permanent archive.

Listing issues:

1. New issue starts with `inbox` and keeps the URL in the title.
2. GitHub Actions captures the URL or records a failed attempt in `data/captures.json`.
3. Successful or duplicate captures get label `ingested`.
4. Failed captures stay open with `needs-text-extraction` until the parser is fixed and the URL is re-run.

Source issues:

1. New issue starts with `source`.
2. Add or update `data/job-sources.json`.
3. Close the issue once the source is tracked.

The `[job]` title prefix is no longer used. Labels and issue forms provide the categorization.

## Script responsibilities

```text
scripts/job_archive.py   core listing import, URL capture, extraction, metadata, index helpers
scripts/capture_url.py   CLI wrapper used by GitHub Actions URL capture and backup records
scripts/build_site.py    static GitHub Pages site generator
scripts/ingest_pdfs.py   CLI wrapper for importing saved files
scripts/build_index.py   CLI wrapper for rebuilding data/index.csv
scripts/job_sources.py   CLI for data/job-sources.json
scripts/workflow.py      mise task wrapper for common workflows
```

Tests live in:

```text
tests/
```

Run checks with:

```bash
mise run check
```

## Known limitations

- PDF extraction uses `pypdf`, so text can contain OCR or font extraction artifacts.
- Source URLs are not always present in Safari PDFs.
- Metadata inference is best-effort and should be reviewed.
- This repo intentionally does not scrape job boards.
- Large PDFs should be avoided. The workflow checks for files over 50 MiB.
- This repo is public for GitHub Pages, so capture URL-first and avoid personal notes in issues or listing bodies.

## Future directions

Only add complexity after the archive has enough examples to justify it. Plausible future work:

- Better conversion from GitHub issue to `listing.md`.
- More robust extraction for saved HTML pages.
- Requirement tagging and normalization.
- Skill frequency reports from `data/index.csv` and raw text.
- Optional browser bookmarklet or shortcut for faster capture.
