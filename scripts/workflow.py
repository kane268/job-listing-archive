#!/usr/bin/env python3
"""Small workflow wrapper used by mise tasks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from build_site import build_site
from job_archive import ROOT, build_index, ingest_paths, listing_paths, print_ingest_results

DEFAULT_SOURCE = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Job Listings"
LARGE_FILE_LIMIT = 50 * 1024 * 1024


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    printable = " ".join(command)
    print(f"$ {printable}", flush=True)
    return subprocess.run(command, cwd=ROOT, text=True, check=check)


def output(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def source_dir() -> Path:
    return Path(os.environ.get("JOB_LISTINGS_SOURCE", str(DEFAULT_SOURCE))).expanduser()


def has_staged_changes() -> bool:
    return subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0


def upstream_exists() -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def branch_is_ahead() -> bool:
    if not upstream_exists():
        return False
    ahead = output(["git", "rev-list", "--count", "@{u}..HEAD"])
    return ahead != "0"


def verify_archive() -> None:
    listings = listing_paths(ROOT)
    large_files = [path for path in (ROOT / "listings").rglob("*") if path.is_file() and path.stat().st_size > LARGE_FILE_LIMIT]
    print(f"Archive check: {len(listings)} listings")
    if large_files:
        joined = "\n".join(f"- {path.relative_to(ROOT)}" for path in large_files)
        raise SystemExit(f"Files over 50 MiB should not be committed:\n{joined}")


def cmd_help(_: list[str]) -> int:
    print(
        """
Job Listing Archive workflow

Mobile:
  1. Open the GitHub Pages capture UI in manage mode.
  2. Paste a listing URL.
  3. Create the prefilled GitHub issue so Actions can capture the page.

Laptop:
  mise run update          Import legacy iCloud files, rebuild the index, site, test, commit, and push.
  mise run save            Rebuild the index and site, test, commit current changes, and push.
  mise run import          Only import legacy iCloud files.
  mise run check           Run tests and archive checks.
  mise run site            Rebuild the static web site.
  mise run validate-capture Validate live URL capture against archived URLs.
  mise run capture         Open the web listing capture UI in manage mode.
  mise run sources         List places to look for jobs.
  mise run browse          Open active job source URLs.
  mise run capture-source  Open the GitHub source capture form.

Most days, use only this:

  mise run update
""".strip()
    )
    return 0


def cmd_import(_: list[str]) -> int:
    source = source_dir()
    if not source.exists():
        raise SystemExit(f"Source folder does not exist: {source}")
    print(f"Import source: {source}")
    results = ingest_paths(source, root=ROOT)
    print_ingest_results(results)
    imported = sum(1 for result in results if result.get("status") == "ingested")
    skipped = sum(1 for result in results if result.get("status") == "skipped")
    print(f"Import summary: {imported} imported, {skipped} skipped")
    return 0


def cmd_index(_: list[str]) -> int:
    path = build_index(ROOT)
    print(path.relative_to(ROOT))
    return 0


def cmd_check(_: list[str]) -> int:
    if shutil.which("mise"):
        run(["mise", "tasks", "validate", "--errors-only"])
    cmd_index([])
    build_site(ROOT)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    verify_archive()
    return 0


def cmd_save(args: list[str]) -> int:
    message = " ".join(args).strip() or "Update job listing archive"
    cmd_check([])
    run(["git", "add", "-A"])

    if not has_staged_changes():
        print("No changes to commit.")
        if branch_is_ahead():
            run(["git", "push"])
        return 0

    run(["git", "commit", "-m", message])
    run(["git", "pull", "--rebase", "--autostash"])
    run(["git", "push"])
    return 0


def cmd_update(args: list[str]) -> int:
    cmd_import([])
    return cmd_save(args)


def cmd_status(_: list[str]) -> int:
    verify_archive()
    print("\nGit status:")
    run(["git", "status", "--short", "--branch"])
    return 0


def cmd_setup(_: list[str]) -> int:
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    return 0


def repo_url() -> str:
    try:
        return output(["gh", "repo", "view", "--json", "url", "--jq", ".url"])
    except Exception:
        return "https://github.com/kane268/job-listing-archive"


def open_issue_template(template: str) -> int:
    issue_url = f"{repo_url()}/issues/new?template={template}"
    print(issue_url)
    webbrowser.open(issue_url)
    return 0


def cmd_capture(_: list[str]) -> int:
    capture_url = "https://kane268.github.io/job-listing-archive/?manage=1"
    print(capture_url)
    webbrowser.open(capture_url)
    return 0


def cmd_capture_source(_: list[str]) -> int:
    return open_issue_template("job-source.yml")


def cmd_sources(_: list[str]) -> int:
    run([sys.executable, "scripts/job_sources.py", "list"])
    return 0


def cmd_browse(args: list[str]) -> int:
    run([sys.executable, "scripts/job_sources.py", "open", *args])
    return 0


def cmd_add_source(args: list[str]) -> int:
    if len(args) < 2:
        raise SystemExit('Usage: mise run add-source "Name" "https://example.com/jobs"')
    run([sys.executable, "scripts/job_sources.py", "add", *args])
    return 0


COMMANDS = {
    "help": cmd_help,
    "import": cmd_import,
    "index": cmd_index,
    "check": cmd_check,
    "save": cmd_save,
    "update": cmd_update,
    "status": cmd_status,
    "setup": cmd_setup,
    "capture": cmd_capture,
    "capture-source": cmd_capture_source,
    "sources": cmd_sources,
    "browse": cmd_browse,
    "add-source": cmd_add_source,
}


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "help"
    args = argv[1:]
    handler = COMMANDS.get(command)
    if handler is None:
        valid = ", ".join(sorted(COMMANDS))
        raise SystemExit(f"Unknown command: {command}\nValid commands: {valid}")
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
