# Job Listing Archive

A public-safe archive of tech job listings I find interesting. The goal is simple URL capture first, optional cleanup later, and lightweight analysis when there is enough data.

For project background, design decisions, data model details, and known limitations, see [docs/PROJECT.md](docs/PROJECT.md).

## Quick workflow

### Capture a listing

Use the mobile-friendly site when you find an interesting listing:

[Open the job archive](https://kane268.github.io/job-listing-archive/)

Paste the listing URL and open the prefilled GitHub issue. The capture workflow fetches the page, writes `raw.html`, extracts `raw.txt`, creates `listing.md`, rebuilds the index and static site, and commits back to the repo. If capture fails, the URL is saved in `data/captures.json` and shown on the site as a backup.

Legacy PDF import is still available for old saved files, but URL capture is the normal path now.

### Maintain from the laptop

Most day-to-day capture should happen through the web UI and GitHub Actions. Use the laptop workflow for legacy imports, manual cleanup, or source maintenance:

```bash
mise run update
```

That imports any legacy iCloud files, skips files already imported, rebuilds `data/index.csv`, rebuilds the static site, runs tests, commits changes, and pushes to GitHub.

### Other common commands

```bash
mise run save            # test, commit, push current edits
mise run import          # import legacy iCloud files only
mise run capture         # open the web listing capture UI
mise run site            # rebuild the static site
mise run validate-capture # test live URL capture in a temp repo
mise run sources         # list places to look for jobs
mise run browse          # open active job source URLs
mise run capture-source  # open the job source issue form
mise run                 # show workflow help
```

Job sources live in `data/job-sources.json`. Seed examples include Anthropic, GitHub, Stripe, Apple, and Readwise. Pages CMS can edit this file through `.pages.yml` when you want a structured web editor.

## Structure

```text
.github/ISSUE_TEMPLATE/   GitHub issue configuration and source form
.github/workflows/        URL capture automation
.pages.yml                Pages CMS source editor configuration
archive/<id>/             generated web pages with captured text
inbox/                    temporary drop zone and notes
listings/YYYY/<id>/       one folder per saved listing
data/captures.json        saved capture attempts and failed capture backups
data/index.csv            generated listing index
data/job-sources.json     places to look for new listings
scripts/                  import, capture, site, and indexing helpers
templates/                Markdown template
```

Each saved listing should have:

```text
listing.md    canonical metadata, requirements, and notes
raw.pdf       optional original PDF snapshot
raw.html      optional original HTML/text snapshot
raw.txt       generated plain text extraction
```

First-time setup, only if Python package dependencies are missing:

```bash
mise run setup
```

## Task reference

<!-- mise-tasks -->
## `add-source`

- **Usage**: `add-source`

Add or update a job source

## `browse`

- **Usage**: `browse`

Open active job source URLs

## `capture`

- **Usage**: `capture`

Open the web listing capture UI

## `capture-source`

- **Usage**: `capture-source`

Open the GitHub job source capture form

## `check`

- **Usage**: `check`
- **Aliases**: `c`

Run tests and archive checks

## `default`

- **Usage**: `default`

Show the simple workflow

## `help`

- **Usage**: `help`
- **Aliases**: `h`

Show the simple workflow

## `import`

- **Usage**: `import`
- **Aliases**: `i`

Import legacy files from the iCloud Job Listings folder

## `index`

- **Usage**: `index`

Rebuild data/index.csv

## `save`

- **Usage**: `save`
- **Aliases**: `s`

Test, commit all changes, and push to GitHub

## `setup`

- **Usage**: `setup`

Install Python package requirements

## `site`

- **Usage**: `site`

Rebuild static GitHub Pages site

## `sources`

- **Usage**: `sources`
- **Aliases**: `src`

List places to look for jobs

## `status`

- **Usage**: `status`

Show archive count and git status

## `update`

- **Usage**: `update`
- **Aliases**: `u`

Import legacy iCloud listings, test, commit, and push

## `validate-capture`

- **Usage**: `validate-capture`

Validate live URL capture against archived source URLs
<!-- /mise-tasks -->

## Statuses

Use these values in `listing.md` front matter:

- `captured`: quickly saved, not cleaned up
- `ingested`: imported into the repo
- `extracted`: raw text exists
- `reviewed`: requirements, tags, and notes have been reviewed
- `archived`: no more action needed

## Analysis

Start with GitHub search and `data/index.csv`. Add scripts or notebooks only when a repeated question appears, such as:

- common requirements by role family
- seniority compared with expected skills
- platform, data, or developer experience role patterns
- remote and location patterns
