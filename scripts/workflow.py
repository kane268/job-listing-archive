#!/usr/bin/env python3
"""Small validation wrapper used by mise tasks."""

from __future__ import annotations

import shutil
import subprocess
import sys

from build_site import build_site
from job_archive import ROOT, build_index, listing_paths
from validation import validate_archive

LARGE_FILE_LIMIT = 50 * 1024 * 1024


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    printable = " ".join(command)
    print(f"$ {printable}", flush=True)
    return subprocess.run(command, cwd=ROOT, text=True, check=True)


def verify_archive() -> None:
    listings = listing_paths(ROOT)
    large_files = [path for path in (ROOT / "listings").rglob("*") if path.is_file() and path.stat().st_size > LARGE_FILE_LIMIT]
    print(f"Archive check: {len(listings)} listings")
    errors = validate_archive(ROOT)
    if large_files:
        errors.append("Files over 50 MiB should not be committed:\n" + "\n".join(f"- {path.relative_to(ROOT)}" for path in large_files))
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"Archive validation failed:\n{joined}")


def cmd_help(_: list[str]) -> int:
    print(
        """
Job Listing Archive validation commands

  mise run check            Validate tasks, rebuild generated data, build _site, and run tests.
  mise run site             Rebuild the local static site artifact in _site/.
  mise run validate-capture Validate live URL capture against archived URLs in a temp repo.
""".strip()
    )
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


COMMANDS = {
    "help": cmd_help,
    "index": cmd_index,
    "check": cmd_check,
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
