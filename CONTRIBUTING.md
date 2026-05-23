# How I Use This Repo

Read `docs/PROJECT.md` first if you need the project origin, data model, workflow, and design principles.

## Add a listing quickly

Open the site with `?manage=1`, click **Add listing**, paste the public job listing URL in Pages CMS, and save. The listing starts as `status: queued`; GitHub Actions fetches the URL and writes the readable Markdown directly into the listing body.

## Add a place to look for jobs

Use the manage-mode **Edit companies** Pages CMS link. Each source should include `name`, jobs `url`, and `homepage_url` for favicon source.

## Review a listing

Use the listing page's manage-mode **Edit in Pages CMS** link and fill in only what is useful:

- why it was saved
- responsibilities
- explicit requirements
- implied requirements
- nice-to-haves
- public-safe notes

Keep filtering fields in YAML-style front matter. Keep interpretation and memory in the Markdown body. Avoid private notes because the repo and Pages site are public.
