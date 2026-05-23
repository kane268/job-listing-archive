# Project Notes

## Origin

This repo started as a formal version of a personal habit: saving interesting tech job listings from Safari for later reference.

The goal is not to build a job-search CRM, scraper, or application tracker. The goal is a durable public-safe archive where interesting roles can be saved quickly, normalized later, and analyzed only when there is enough data.

## Design principles

- Save URLs fast, normalize later.
- Keep Markdown files as the source of truth.
- Keep notes public-safe because the workflow uses public GitHub Pages and a public repository.
- Use Pages CMS for listing and source maintenance.
- Avoid scraping or crawling unless explicitly requested.
- Prefer small scripts and generated CSVs over a database.
- Keep metadata useful but not burdensome.

## What belongs here

### Job listings

Each listing is a flat Markdown file:

```text
listings/<saved-date-or-generated-name>.md
```

The YAML front matter stores filtering metadata. The Markdown body stores the readable listing text fetched from the source URL. There are no sidecar `raw.html` or `raw.md` files in the current data model; historical fetched evidence is represented by source URLs, final URLs, fetched timestamps, HTTP status, and checksums when available.

New listings begin as small Pages CMS files with a `source_url`, `saved_at`, and `status: queued`. GitHub Actions fetches queued listings and writes the extracted readable text directly into the body.

### Job sources

Saved companies and recurring places to look for jobs live in:

```text
data/job-sources.json
```

Each entry stores `name`, jobs `url`, and `homepage_url` for favicon source. Source IDs are generated from names, for example `If This Is Company Name` becomes `if-this-is-company-name`.

### Generated data and site artifact

`data/index.csv` is generated from listing front matter and is committed for easy analysis.

The static GitHub Pages site is generated into `_site/` and deployed as a Pages artifact. Generated Pages HTML is not committed. Rebuild generated data and the local site artifact with:

```bash
mise run check
```

Do not hand-edit generated index rows or `_site/` files. Edit the relevant listing, company source data, or script, then rebuild.

## Current workflow

### Add a listing

Use the GitHub Pages site in manage mode:

```text
https://kane268.github.io/job-listing-archive/?manage=1
```

Public visitors see only listings. Manage mode is stored per browser and shows owner tools such as Add listing, Edit companies, listing edit links, and GitHub links. Disable it with `?manage=0`. Manage mode is not security; it only hides owner tools in the browser.

Click **Add listing** and save a new Pages CMS entry with the public job listing URL. GitHub Actions fetches queued listing URLs, extracts readable Markdown, updates the listing body and metadata, rebuilds `data/index.csv`, and commits back to `main`.

If a fetch fails, the listing remains in `listings/` with `status: failed` and `fetch_error`. Fix the URL or parser, then set `status` back to `queued` in Pages CMS to retry.

### Source maintenance

Use Pages CMS from the manage-mode **Edit companies** link to edit `data/job-sources.json`.

Local operator workflows are not supported for archive maintenance. Local commands are only for development validation and CI parity.

## Developer validation commands

```bash
mise run check            # validate mise tasks, rebuild index/site artifact, run tests
mise run site             # rebuild the local static site artifact
```

## Data model

Important listing front matter fields:

```yaml
source_url: "https://readwise.io/careers/senior-staff-engineer"
saved_at: "2026-05-09"
status: "reviewed"
company: "Readwise"
title: "Senior/Staff Engineer (Backend Focus)"
source_final_url: ""
http_status: 200
fetched_at: "2026-05-16T12:00:00+00:00"
source_published_at: ""
role_family: "backend"
seniority: "senior-staff"
location: "Remote"
employment_type: "Full time"
compensation: ""
content_type: "markdown"
source_sha256: ""
tags:
  - "backend"
requirements:
  - "Senior-or-higher backend or infrastructure production experience"
nice_to_haves: []
```

Metadata is for filtering and grouping. The Markdown body is the durable human-readable listing record.

## Status meanings

- `queued`: Pages CMS has saved a URL and GitHub Actions should fetch it
- `fetched`: readable Markdown exists in the listing body
- `failed`: the fetch attempt failed; set back to `queued` to retry
- `reviewed`: requirements, tags, metadata, or notes reviewed
- `archived`: no more action needed

## Script responsibilities

```text
scripts/job_archive.py          URL fetching, extraction, metadata, and index helpers
scripts/enrich_listings.py      CLI used by GitHub Actions to fetch queued listing URLs
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
- This repo intentionally does not crawl job boards.
- Listing URLs and notes must remain public-safe because the repo and Pages site are public.
- Pages CMS commits small queued files first; the generated site may briefly show a queued listing before enrichment commits the fetched body.

## Future directions

Only add complexity after the archive has enough examples to justify it. Plausible future work:

- More robust extraction for saved HTML pages.
- Requirement tagging and normalization.
- Skill frequency reports from `data/index.csv` and listing bodies.
- Optional browser bookmarklet or shortcut for faster Pages CMS entry creation.
