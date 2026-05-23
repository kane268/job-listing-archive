# Agent Instructions

This is a public-safe personal archive of job listings. It started as a formal version of saving interesting tech job listings from Safari. See `docs/PROJECT.md` for project background, workflow, data model, and known limitations.

## Project intent

- Keep saving fast and cleanup optional.
- Keep Markdown files as the source of truth.
- Do not turn this into a scraper, job-search CRM, or application tracker unless explicitly requested.
- Preserve provenance where available: source URLs, final URLs, fetch timestamps, HTTP status, checksums, and fetched Markdown matter.

## Source of truth

- Always pull latest `main` with `git pull --ff-only` before making changes. New listings may be added through Pages CMS and GitHub Actions.
- Listings live as flat Markdown files in `listings/*.md`.
- Listing front matter is Pages CMS editable. The Markdown body is the readable listing text.
- Recurring places to look for jobs live in `data/job-sources.json`, with `name`, jobs `url`, and `homepage_url` for favicon source. Source IDs are generated from names.
- `data/index.csv` is generated from listing front matter. Do not hand-edit it.
- `_site/` is the generated local GitHub Pages artifact. Do not hand-edit it or commit it.

## Privacy and safety

- Treat the repository and GitHub Pages site as public.
- Keep listing bodies and notes public-safe. Do not add private personal notes.
- Do not add scraping or crawling unless explicitly requested.
- Avoid adding large binaries. `mise run check` fails on files over 50 MiB in `listings/`.
- Do not attribute AI tools in commits, PRs, issues, discussions, or release notes.

## Supported workflow

- Listing creation and editing happens through Pages CMS links shown in manage mode (`?manage=1`).
- New Pages CMS listings start with `status: queued`; GitHub Actions fetches the URL and writes the extracted Markdown body.
- Source maintenance happens through Pages CMS.
- Local operator workflows are not supported for archive maintenance. Do not add tasks that commit, push, open browser flows, or mutate archive data as an operator workflow.

## Validation commands

Use these only to validate repository changes and CI parity:

```bash
mise run check            # validate tasks, rebuild index/site artifact, run tests
mise run site             # rebuild the local static GitHub Pages artifact
```

Run `mise run check` after changing scripts, metadata, templates, generated site inputs, or docs that mention tasks.

## Fetch behavior

- URL fetch is triggered by listing files with `status: queued` or by empty listing bodies with a `source_url`.
- Successful fetches update the listing body directly with readable Markdown, fill best-effort metadata, set `status: fetched`, rebuild `data/index.csv`, and commit back to `main`.
- Failed fetches keep the listing file, set `status: failed`, and store the reason in `fetch_error`.
- To retry a failed or manually edited listing, set `status: queued` in Pages CMS.
- Do not overwrite reviewed or archived listing bodies unless explicitly requested.

## Editing guidance

- Keep listing metadata small and useful for filtering.
- Put interpretation, fit notes, and requirement review in the Markdown body only when public-safe.
- Keep generated files reproducible.
- Keep docs concise but sufficient for someone new to understand the origin and workflow.
- If adding a new task, update `mise.toml`, run `mise generate task-docs --inject --output README.md`, then run `mise run check`.
