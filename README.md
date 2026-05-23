# Job Listing Archive

A public-safe archive of tech job listings I find interesting. The goal is quick URL saves through Pages CMS, lightweight cleanup later, and simple analysis when there is enough data.

For project background, design decisions, data model details, and known limitations, see [docs/PROJECT.md](docs/PROJECT.md).

## Quick workflow

### Add a listing

Use the site in manage mode:

[Open the job archive](https://kane268.github.io/job-listing-archive/?manage=1)

Public visitors see only the listings. Manage mode is stored per browser and shows owner tools such as **Add listing**, **Edit companies**, Pages CMS edit links, and GitHub links. Disable manage mode with `?manage=0`. Manage mode is only browser-side UI hiding; the repository and site are public.

Click **Add listing**, paste the public job listing URL into Pages CMS, and save. GitHub Actions fetches queued listing URLs, writes the extracted readable Markdown directly into the listing body, fills best-effort metadata, rebuilds `data/index.csv`, and commits the update back to `main`.

### Review or maintain data

Use Pages CMS and GitHub for archive maintenance:

- Edit listing metadata and Markdown through Pages CMS links shown in manage mode.
- Edit saved companies through the manage-mode **Edit companies** link.
- Keep all listing notes public-safe.

Saved companies live in `data/job-sources.json` with `name`, jobs `url`, and `homepage_url` for favicon source. Source IDs are generated from names, for example `If This Is Company Name` becomes `if-this-is-company-name`.

## Structure

```text
.github/workflows/        Pages deployment and queued listing enrichment
.pages.yml                Pages CMS listing and company editor configuration
assets/                   CSS and JavaScript copied into the site artifact
_site/                    local generated Pages artifact, ignored by git
listings/*.md             one Pages CMS editable Markdown file per listing
data/index.csv            generated listing index
data/job-sources.json     places to look for new listings
scripts/                  fetching, extraction, site, validation, and indexing helpers
```

Each listing is a single Markdown file with YAML front matter and the fetched readable listing text as the Markdown body.

GitHub Pages is deployed from a generated artifact containing only the static site files, not from the repository root.

## Developer validation

These commands are for validating repository changes, not for routine archive maintenance:

```bash
mise run check            # validate tasks, rebuild generated data/site artifact, run tests
mise run site             # rebuild the local _site artifact
```

## Task reference

<!-- mise-tasks -->
## `check`

- **Usage**: `check`
- **Aliases**: `c`

Run tests and archive checks

## `default`

- **Usage**: `default`

Show validation help

## `help`

- **Usage**: `help`
- **Aliases**: `h`

Show validation help

## `index`

- **Usage**: `index`

Rebuild data/index.csv

## `site`

- **Usage**: `site`

Rebuild static GitHub Pages site artifact
<!-- /mise-tasks -->

## Statuses

Use these values in listing front matter:

- `queued`: Pages CMS has saved the URL and GitHub Actions should fetch it
- `fetched`: readable Markdown exists in the listing body
- `failed`: the fetch attempt failed; set back to `queued` to retry
- `reviewed`: metadata, requirements, tags, or notes have been reviewed
- `archived`: no more action needed

## Analysis

Start with GitHub search and `data/index.csv`. Add scripts or notebooks only when a repeated question appears, such as:

- common requirements by role family
- seniority compared with expected skills
- platform, data, or developer experience role patterns
- remote and location patterns
