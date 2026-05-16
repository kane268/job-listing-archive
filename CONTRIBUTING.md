# How I Use This Repo

Read `docs/PROJECT.md` first if you need the project origin, data model, issue workflow, and design principles.

## Add a listing quickly

Use the GitHub Pages capture page and paste the URL, optional title/company, and a public-safe note about why it was interesting.

## Add a saved file

For legacy saved files, save PDFs or saved pages to `iCloud Drive / Job Listings`, then run:

```bash
mise run update
```

That imports new files, rebuilds the index, runs checks, commits, and pushes.

If you only want to import without committing:

```bash
mise run import
```

## Add a place to look for jobs

Use `data/job-sources.json` for company career pages, job boards, aggregators, and newsletters worth checking.

```bash
mise run sources
mise run add-source "Anthropic" "https://www.anthropic.com/careers/jobs" "ai,research"
```

On mobile, use the GitHub **Job source capture** issue form.

## Review a listing

Open `listing.md` and fill in only what is useful:

- why it was saved
- responsibilities
- explicit requirements
- implied requirements
- nice-to-haves
- public-safe notes

Keep filtering fields in YAML. Keep interpretation and memory in the Markdown body. Avoid private notes because the repo and Pages site are public.
