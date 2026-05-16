# Job Listing Archive

A public-safe archive of tech job listings I find interesting. The goal is simple URL capture first, optional cleanup later, and lightweight analysis when there is enough data.

For project background, design decisions, data model details, and known limitations, see [docs/PROJECT.md](docs/PROJECT.md).

## Quick workflow

### Capture a listing

Use the mobile-friendly site when you find an interesting listing:

[Open the job archive](https://kane268.github.io/job-listing-archive/)

Public visitors see only the listings. Owner tools are available in manage mode: visit the site with `?manage=1` to show capture, saved companies, GitHub links, raw Markdown links, and extraction issue links. Disable manage mode with `?manage=0`. Manage mode is only browser-side UI hiding; the repository and site are public.

Paste the listing URL in manage mode and open the prefilled GitHub issue. The site adds the `capture` label. The capture workflow only acts on owner-created issues with the `capture` label, fetches the page, writes `raw.html`, extracts `raw.md`, creates `listing.md`, rebuilds the generated index, and commits back to the repo. If capture fails, the URL is saved in `data/captures.json` and shown in manage mode as a backup.

### Review or maintain data

Use GitHub, Pages CMS, and issue forms for archive maintenance:

- Review captured listing files in GitHub and keep notes public-safe.
- Edit saved companies through the manage-mode **Saved companies** editor link.
- Use the GitHub **Job source capture** issue form for new source pages.

Saved companies live in `data/job-sources.json` with `name`, jobs `url`, and `homepage_url` for favicon source. Source IDs are generated from names, for example `If This Is Company Name` becomes `if-this-is-company-name`.

## Structure

```text
.github/ISSUE_TEMPLATE/   GitHub issue configuration and source form
.github/workflows/        URL capture and Pages deployment automation
.pages.yml                Pages CMS source editor configuration
assets/                   CSS and JavaScript copied into the site artifact
_site/                    local generated Pages artifact, ignored by git
listings/YYYY/MM/DD/<slug>/ one folder per saved listing
data/captures.json        failed or pending capture backups only
data/index.csv            generated listing index
data/job-sources.json     places to look for new listings
scripts/                  capture, site, validation, and indexing helpers
templates/                Markdown template
```

Each saved listing should have:

```text
listing.md    canonical metadata, requirements, and notes
raw.html      optional original fetched HTML evidence
raw.md        generated readable Markdown extraction
```

GitHub Pages is deployed from a generated artifact containing only the static site files, not from the repository root.

## Developer validation

These commands are for validating repository changes, not for routine archive maintenance:

```bash
mise run check            # validate tasks, rebuild generated data/site artifact, run tests
mise run site             # rebuild the local _site artifact
mise run validate-capture # test live URL capture in a temp repo
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

## `validate-capture`

- **Usage**: `validate-capture`

Validate live URL capture against archived source URLs
<!-- /mise-tasks -->

## Statuses

Use these values in `listing.md` front matter:

- `captured`: URL saved quickly, not normalized yet
- `extracted`: readable Markdown exists
- `reviewed`: requirements, tags, and notes have been reviewed
- `archived`: no more action needed

## Analysis

Start with GitHub search and `data/index.csv`. Add scripts or notebooks only when a repeated question appears, such as:

- common requirements by role family
- seniority compared with expected skills
- platform, data, or developer experience role patterns
- remote and location patterns
