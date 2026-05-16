# Agent Instructions

This is a public-safe personal archive of job listings. It started as a formal version of saving interesting tech job listings from Safari. See `docs/PROJECT.md` for project background, workflow, data model, and known limitations.

## Project intent

- Keep capture fast and cleanup optional.
- Keep Markdown files as the source of truth.
- Do not turn this into a scraper, job-search CRM, or application tracker unless explicitly requested.
- Preserve provenance: source URLs, checksums, raw HTML, generated Markdown, and import notes matter.

## Source of truth

- Always pull latest `main` with `git pull --ff-only` before making changes. New listings may be added through the web UI and GitHub Actions.
- Listings live in `listings/YYYY/MM/DD/<short-slug>/listing.md`.
- Raw listing evidence lives beside `listing.md` as `raw.html` when fetched HTML is available.
- Generated readable listing evidence lives beside `listing.md` as `raw.md`.
- Recurring places to look for jobs live in `data/job-sources.json`, with `name`, jobs `url`, and `homepage_url` for favicon source. Source IDs are generated from names.
- `data/index.csv` is generated from listing front matter. Do not hand-edit it.
- `_site/` is the generated local GitHub Pages artifact. Do not hand-edit it or commit it.
- `raw.md` is generated evidence. Do not hand-edit it unless repairing historical generated output from its source evidence.

## Privacy and safety

- Treat the repository and GitHub Pages site as public.
- Keep capture issues and listing bodies public-safe. Do not add private personal notes.
- Do not add scraping or crawling unless explicitly requested.
- Avoid adding large binaries. `mise run check` fails on files over 50 MiB in `listings/`.
- Do not attribute AI tools in commits, PRs, issues, discussions, or release notes.

## Supported workflow

- URL capture through the GitHub Pages UI is the supported archive workflow.
- Source maintenance happens through Pages CMS or the job source issue form.
- Local operator workflows are not supported for archive maintenance. Do not add tasks that commit, push, open browser flows, or mutate archive data as an operator workflow.

## Validation commands

Use these only to validate repository changes and CI parity:

```bash
mise run check            # validate tasks, rebuild index/site artifact, run tests
mise run site             # rebuild the local static GitHub Pages artifact
mise run validate-capture # test live URL capture in a temp repo
```

Run `mise run check` after changing scripts, metadata, templates, issue forms, generated site inputs, or docs that mention tasks.

## Capture behavior

- URL capture is the only supported capture path.
- Capture issues use the `capture` label. No secondary triage label is used.
- GitHub Actions only acts on owner-created issues with the `capture` label.
- Successful captures write `raw.html` when HTML was fetched, write `raw.md`, create `listing.md`, rebuild `data/index.csv`, and commit back to the repo.
- Failed captures are saved in `data/captures.json` and shown in manage mode as parser-repair backups.
- Successful captures are not stored in `data/captures.json`; listing metadata and `data/index.csv` already cover them.

## Issue workflow

GitHub Issues are a capture queue, not the permanent archive.

Listing issues:

1. New capture issues use the `capture` label and keep the URL in the title.
2. GitHub Actions only acts on owner-created issues with the `capture` label.
3. Bug reports and markdown extraction issues should not use the `capture` label.
4. GitHub Actions captures the URL or records a failed attempt in `data/captures.json`.
5. Successful or duplicate captures get label `ingested` and close with a comment pointing to the listing path.
6. Failed captures stay open with `needs-text-extraction` until the parser is fixed and the URL is re-run.

Source issues:

1. New issues use the `source` label.
2. Add or update `data/job-sources.json`.
3. Close the issue once tracked.

## Editing guidance

- Keep `listing.md` metadata small and useful for filtering.
- Put interpretation, fit notes, and requirement review in the Markdown body.
- Keep generated files reproducible.
- Keep docs concise but sufficient for someone new to understand the origin and workflow.
- If adding a new task, update `mise.toml`, run `mise generate task-docs --inject --output README.md`, then run `mise run check`.
