# Agent Instructions

This is a public-safe personal archive of job listings. It started as a formal version of saving interesting tech job listings from Safari on phone and laptop. See `docs/PROJECT.md` for project background, workflow, data model, and known limitations.

## Project intent

- Keep capture fast and cleanup optional.
- Keep Markdown files as the source of truth.
- Do not turn this into a scraper, job-search CRM, or application tracker unless explicitly requested.
- Preserve provenance: original file names, creation times, source URLs, checksums, raw artifacts, and import notes matter.

## Source of truth

- Listings live in `listings/YYYY/<id>/listing.md`.
- Raw listing evidence lives beside `listing.md` as `raw.pdf`, `raw.html`, `source.txt`, generated `raw.md`, or generated `raw.txt`.
- Recurring places to look for jobs live in `data/job-sources.json`, with only `name` and `url`. Source IDs are generated from names.
- `data/index.csv` is generated from listing front matter. Do not hand-edit it.
- `archive/<id>/index.html` and `index.html` are generated web pages. Do not hand-edit them. Regenerate with `mise run site` or `mise run check`.
- `raw.md` and `raw.txt` are generated evidence. Do not hand-edit them. Regenerate from the source file instead.

## Privacy and safety

- Treat the repository and GitHub Pages site as public.
- Keep capture issues and listing bodies public-safe. Do not add private personal notes.
- Do not add scraping or crawling unless explicitly requested.
- Avoid adding large binaries. `mise run check` fails on files over 50 MiB in `listings/`.
- Do not attribute AI tools in commits, PRs, issues, discussions, or release notes.

## Routine commands

Prefer mise tasks for normal workflows:

```bash
mise run update          # import legacy iCloud files, check, commit, push
mise run import          # import legacy iCloud files only
mise run save            # check, commit, push current changes
mise run check           # validate tasks, rebuild index and site, run tests
mise run site            # rebuild static GitHub Pages site
mise run validate-capture # test live URL capture in a temp repo
mise run sources         # list job sources
mise run browse          # open active job source URLs
mise run capture         # open web listing capture UI
mise run capture-source  # open source capture issue form
```

Run `mise run check` after changing scripts, metadata, templates, issue forms, generated site inputs, or docs that mention tasks.

## Import behavior

- The iCloud source folder is configured by `JOB_LISTINGS_SOURCE` in `mise.toml`.
- Imports skip already imported files using `source_file_sha256` from listing front matter.
- Import scripts infer metadata from file names, source URLs, and extracted text. Treat this as best-effort.
- If inference is wrong, edit `listing.md`, then run `mise run index` or `mise run save`.

## Issue workflow

GitHub Issues are an inbox, not the permanent archive.

Listing issues:

1. New capture issues use the `inbox` and `capture` labels and keep the URL in the title.
2. GitHub Actions only acts on owner-created issues with the `capture` label.
3. Bug reports and markdown extraction issues should not use the `capture` label.
4. GitHub Actions captures the URL or records a failed attempt in `data/captures.json`.
5. Successful or duplicate captures get label `ingested` and close with a comment pointing to the listing path.
6. Failed captures stay open with `needs-text-extraction` until the parser is fixed and the URL is re-run.

Source issues:

1. New issues use the `source` label.
2. Add or update `data/job-sources.json`.
3. Close the issue once tracked.

The `[job]` title prefix is not used anymore. Labels and issue forms are enough.

## Editing guidance

- Keep `listing.md` metadata small and useful for filtering.
- Put interpretation, fit notes, and requirement review in the Markdown body.
- Keep generated files reproducible.
- Keep docs concise but sufficient for someone new to understand the origin and workflow.
- If adding a new task, update `mise.toml`, run `mise generate task-docs --inject --output README.md`, then run `mise run check`.
