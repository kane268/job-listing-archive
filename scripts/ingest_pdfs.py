#!/usr/bin/env python3
"""Import saved job listing files into listings/YYYY/<id>/ folders."""

from job_archive import ingest_cli

if __name__ == "__main__":
    raise SystemExit(ingest_cli())
