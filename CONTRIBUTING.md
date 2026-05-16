# How I Use This Repo

Read `docs/PROJECT.md` first if you need the project origin, data model, issue workflow, and design principles.

## Add a listing quickly

Use the GitHub Pages capture page and paste only the listing URL. The site opens a prefilled GitHub issue with the URL in the title.

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

Use `data/job-sources.json` for saved companies worth checking. Each entry should only include `name` and `url`. The source ID is generated from the name, for example `If This Is Company Name` becomes `if-this-is-company-name`.

```bash
mise run sources
mise run add-source "Anthropic" "https://www.anthropic.com/careers/jobs"
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

Keep filtering fields in YAML. Keep interpretation and memory in the Markdown body. Avoid private notes because the repo and Pages site are public. Run `mise run site` after manual listing edits so the web copy stays current.
