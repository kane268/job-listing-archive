# How I Use This Repo

Read `docs/PROJECT.md` first if you need the project origin, data model, issue workflow, and design principles.

## Add a listing quickly

Use the GitHub Pages capture page and paste only the listing URL. The site opens a prefilled GitHub issue with the URL in the title and the `capture` label.

## Add a place to look for jobs

Use `data/job-sources.json` for saved companies worth checking. Each entry should include `name`, jobs `url`, and `homepage_url` for favicon source. The source ID is generated from the name, for example `If This Is Company Name` becomes `if-this-is-company-name`.

```bash
mise run sources
mise run add-source "Anthropic" "https://www.anthropic.com/careers/jobs" --homepage-url "https://www.anthropic.com"
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

Keep filtering fields in YAML-style front matter. Keep interpretation and memory in the Markdown body. Avoid private notes because the repo and Pages site are public. Run `mise run site` after manual listing edits when you want a local `_site/` preview, and `mise run save` when ready to validate, commit, and push.
