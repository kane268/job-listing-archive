# Project Notes

## Origin

This repo started as a formal version of a personal habit: saving interesting tech job listings from Safari for later reference.

The goal is not to build a job-search CRM, scraper, or application tracker. The goal is a durable public-safe archive where interesting roles can be captured quickly, normalized later, and analyzed only when there is enough data.

## Design principles

- Capture fast, normalize later.
- Keep Markdown files as the source of truth.
- Keep capture notes public-safe because the workflow uses public GitHub Pages, GitHub Issues, and a public repository.
- Treat fetched HTML and extracted Markdown as evidence.
- Use GitHub Issues as the mobile URL queue.
- Use Pages CMS for structured source maintenance.
- Avoid scraping unless explicitly requested.
- Prefer small scripts and generated CSVs over a database.
- Keep metadata useful but not burdensome.

## What belongs here

### Job listings

Each listing lives at:

```text
listings/YYYY/MM/DD/<short-slug>/listing.md
```

Raw/generated files sit beside it:

```text
raw.html    optional original fetched HTML evidence
raw.md      generated readable Markdown extraction
```

`listing.md` is the canonical human-editable record. It has YAML-style front matter for filtering and Markdown sections for interpretation, notes, and requirement review.

The legacy PDF/iCloud import path has been removed. Historical listings keep public-safe provenance in `listing.md`, but new capture is URL-first.

### Job sources

Saved companies and recurring places to look for jobs live in:

```text
data/job-sources.json
```

Each entry stores `name`, jobs `url`, and `homepage_url` for favicon source. Source IDs are generated from names, for example `If This Is Company Name` becomes `if-this-is-company-name`.

### Generated data and site artifact

`data/index.csv` is generated from all `listing.md` files and is committed for easy analysis.

The static GitHub Pages site is generated into `_site/` and deployed as a Pages artifact. Generated Pages HTML is not committed. Rebuild generated data and the local site artifact with:

```bash
mise run check
```

Do not hand-edit generated index rows or `_site/` files. Edit the relevant `listing.md`, source artifact, or extraction script, then rebuild.

## Current workflow

### Mobile capture

Use the GitHub Pages web UI in manage mode:

```text
https://kane268.github.io/job-listing-archive/?manage=1
```

Public visitors see only listings. Manage mode is stored per browser and shows capture, saved companies, GitHub links, raw Markdown links, and extraction issue links. Disable it with `?manage=0`. Manage mode is not security; it only hides owner tools in the browser.

Paste a listing URL. The site opens a prefilled GitHub issue with an empty body, the URL in the title, and the `capture` label. GitHub Actions fetches the page, saves `raw.html`, extracts `raw.md`, creates `listing.md`, rebuilds `data/index.csv`, commits the result, labels the issue `ingested`, and closes it. If capture fails, Actions saves the URL in `data/captures.json` and manage mode shows it as a backup for later parser fixes and re-capture.

### Source maintenance

Use Pages CMS from the manage-mode **Saved companies** editor link, or use the job source issue form:

```text
https://github.com/kane268/job-listing-archive/issues/new?template=job-source.yml
```

Local operator workflows are not supported for archive maintenance. Local commands are only for development validation and CI parity.

## Developer validation commands

```bash
mise run check            # validate mise tasks, rebuild index/site artifact, run tests
mise run site             # rebuild the local static site artifact
mise run validate-capture # test live URL capture in a temp repo
```

## Data model

Important `listing.md` front matter fields:

```yaml
id: "2026-05-09-readwise-senior-staff-backend"
captured_at: "2026-05-09"
source_url: "https://readwise.io/careers/senior-staff-engineer"
source_final_url: ""
source_http_status: 200
source_fetched_at: "2026-05-16T12:00:00+00:00"
source_published_at: ""
company: "Readwise"
role_title: "Senior/Staff Engineer (Backend Focus)"
role_family: "backend"
seniority: "senior-staff"
location: "Remote"
employment_type: "Full time"
compensation: ""
status: "reviewed"
source_type: "markdown"
source_file_name: ""
source_file_sha256: ""
tags:
  - "captured"
  - "backend"
requirements:
  - "Senior-or-higher backend or infrastructure production experience"
nice_to_haves: []
```

Metadata is for filtering and grouping. The Markdown body is for memory, judgment, and notes.

## Status meanings

- `captured`: URL saved quickly, not normalized yet
- `extracted`: readable Markdown exists
- `reviewed`: requirements, tags, and notes reviewed
- `archived`: no more action needed

## Issue workflow

GitHub Issues are a capture queue, not the permanent archive.

Listing issues:

1. New capture issues use the `capture` label and keep the URL in the title.
2. GitHub Actions only acts on owner-created issues with the `capture` label.
3. Bug reports and markdown extraction issues should not use the `capture` label.
4. GitHub Actions captures the URL or records a failed attempt in `data/captures.json`.
5. Successful or duplicate captures get label `ingested`.
6. Failed captures stay open with `needs-text-extraction` until the parser is fixed and the URL is re-run.

Source issues:

1. New issue starts with `source`.
2. Add or update `data/job-sources.json`.
3. Close the issue once the source is tracked.

The `[job]` title prefix is not used anymore. Labels and issue forms provide categorization.

## Script responsibilities

```text
scripts/job_archive.py          core URL capture, extraction, metadata, and index helpers
scripts/capture_url.py          CLI wrapper used by GitHub Actions URL capture and backup records
scripts/build_site.py           static GitHub Pages artifact generator
scripts/build_index.py          CLI wrapper for rebuilding data/index.csv
scripts/validation.py           archive and JSON data validation helpers
scripts/job_sources.py          job source data readers used by the site generator
scripts/workflow.py             validation wrapper for mise check/index tasks
assets/                         site CSS and JavaScript copied into _site/
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

- Source metadata inference is best-effort and should be reviewed.
- This repo intentionally does not scrape job boards.
- Capture URL-first and avoid personal notes because the repo and Pages site are public.
- GitHub Pages is deployed from a limited artifact, but raw evidence in the repository is still public.

## Future directions

Only add complexity after the archive has enough examples to justify it. Plausible future work:

- More robust extraction for saved HTML pages.
- Requirement tagging and normalization.
- Skill frequency reports from `data/index.csv` and raw Markdown.
- Optional browser bookmarklet or shortcut for faster capture.
