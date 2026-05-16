from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from job_archive import (  # noqa: E402
    URLFetch,
    build_index,
    discover_source_url,
    extract_html_capture_metadata,
    html_capture_to_text,
    html_to_text,
    infer_company_from_url,
    infer_metadata_from_filename,
    ingest_file,
    ingest_url,
    parse_frontmatter,
    parse_pdf_date,
    short_listing_slug,
    slugify,
)


class JobArchiveTests(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(slugify("Connect Risk & Compliance"), "connect-risk-and-compliance")
        self.assertEqual(slugify(" Senior Staff Engineer, Core Infrastructure "), "senior-staff-engineer-core-infrastructure")

    def test_short_listing_slug(self) -> None:
        self.assertEqual(
            short_listing_slug("Anthropic", "Staff+ Software Engineer, Developer Productivity"),
            "anthropic-staff-developer-productivity",
        )
        self.assertEqual(short_listing_slug("Apple", "Software Engineer, System Experience"), "apple-system-experience")

    def test_infer_metadata_from_plain_filenames(self) -> None:
        stripe = infer_metadata_from_filename("Stripe Staff Software Engineer, Data Movement.pdf")
        self.assertEqual(stripe["company"], "Stripe")
        self.assertEqual(stripe["role_title"], "Staff Software Engineer, Data Movement")
        self.assertEqual(stripe["seniority"], "staff")
        self.assertEqual(stripe["role_family"], "data")

        copilot = infer_metadata_from_filename("Head of Engineering @ Copilot Money.pdf")
        self.assertEqual(copilot["company"], "Copilot Money")
        self.assertEqual(copilot["role_title"], "Head of Engineering")
        self.assertEqual(copilot["seniority"], "head")

    def test_infer_metadata_from_apple_filename(self) -> None:
        apple = infer_metadata_from_filename("Software Engineer, System Experience - Jobs - Careers at Apple.txt")
        self.assertEqual(apple["company"], "Apple")
        self.assertEqual(apple["role_title"], "Software Engineer, System Experience")
        self.assertEqual(apple["role_family"], "infra/platform")

    def test_html_to_text_skips_style_and_keeps_content(self) -> None:
        text = html_to_text("<html><head><style>p{}</style></head><body><h1>Role</h1><p>Hello <b>world</b></p></body></html>")
        self.assertIn("Role", text)
        self.assertIn("Hello", text)
        self.assertIn("world", text)
        self.assertNotIn("p{}", text)

    def test_discover_apple_apply_url(self) -> None:
        text = 'Apply at <a href="https://jobs.apple.com/app/en-us/apply/200602358-0836">Apply</a>'
        self.assertEqual(
            discover_source_url(text, "Software Engineer, System Experience"),
            "https://jobs.apple.com/en-us/details/200602358/software-engineer-system-experience",
        )

    def test_infer_company_from_greenhouse_url(self) -> None:
        self.assertEqual(
            infer_company_from_url("https://job-boards.greenhouse.io/anthropic/jobs/5110511008"),
            "Anthropic",
        )

    def test_extract_ashby_embedded_metadata(self) -> None:
        markup = """
        <!doctype html>
        <html><head><title>Head of Engineering @ Copilot Money</title></head>
        <body><script>
        {"posting":{"locationName":"New York City","descriptionPlain":"Who we are\\n\\nThe Position\\n\\nCopilot is looking for a Head of Engineering to lead the team."}}
        </script></body></html>
        """
        metadata = extract_html_capture_metadata(markup, "https://jobs.ashbyhq.com/copilot-money/abc")
        self.assertEqual(metadata["company"], "Copilot Money")
        self.assertEqual(metadata["role_title"], "Head of Engineering")
        self.assertEqual(metadata["location"], "New York City")
        self.assertIn("Head of Engineering", metadata["description_plain"])

    def test_ingest_url_from_fetched_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            body = b"""
            <!doctype html>
            <html><head><title>Job Application for Staff+ Software Engineer, Developer Productivity at Anthropic</title></head>
            <body>
              <h1>Staff+ Software Engineer, Developer Productivity</h1>
              <p>Responsibilities:</p>
              <p>Build developer tooling for researchers and engineers.</p>
            </body></html>
            """
            fetched = URLFetch(
                requested_url="https://job-boards.greenhouse.io/anthropic/jobs/5110511008",
                final_url="https://job-boards.greenhouse.io/anthropic/jobs/5110511008",
                status=200,
                content_type="text/html; charset=utf-8",
                body=body,
                encoding="utf-8",
                fetched_at="2026-05-16T12:00:00+00:00",
            )

            result = ingest_url(fetched.requested_url, root=root, fetched=fetched, overrides={"why": "Public note"})
            self.assertEqual(result["status"], "captured")
            self.assertRegex(
                Path(result["destination"]).relative_to(root).as_posix(),
                r"^listings/\d{4}/\d{2}/\d{2}/anthropic-staff-developer-productivity$",
            )
            listing_path = Path(result["destination"]) / "listing.md"
            metadata = parse_frontmatter(listing_path)
            self.assertEqual(metadata["company"], "Anthropic")
            self.assertEqual(metadata["role_title"], "Staff+ Software Engineer, Developer Productivity")
            self.assertEqual(metadata["source_type"], "html")
            self.assertTrue((Path(result["destination"]) / "raw.html").exists())
            self.assertTrue((Path(result["destination"]) / "raw.md").exists())
            self.assertTrue((Path(result["destination"]) / "raw.txt").exists())

    def test_extract_stripe_markdown_uses_job_content_not_navigation(self) -> None:
        markup = """
        <!doctype html>
        <html data-page-title="Full Stack Engineer, Developer Experience &amp; Product Platform">
          <head>
            <title>Full Stack Engineer, Developer Experience &amp; Product Platform</title>
            <meta property="og:title" content="Full Stack Engineer, Developer Experience &amp; Product Platform">
          </head>
          <body>
            <svg><title>Stripe logo</title></svg>
            <button>Open mobile navigation</button>
            <div class="ArticleMarkdown">
              <h2>Who we are</h2>
              <p>Stripe builds financial infrastructure.</p>
              <h3>Responsibilities</h3>
              <ul><li>Build developer platforms</li></ul>
            </div>
            <div class="JobDetailCardProperty">
              <p class="JobDetailCardProperty__title">Office locations</p>
              <p>Toronto</p>
            </div></div>
            <div class="JobDetailCardProperty">
              <p class="JobDetailCardProperty__title">Job type</p>
              <p>Full time</p>
            </div></div>
          </body>
        </html>
        """
        metadata = extract_html_capture_metadata(
            markup,
            "https://stripe.com/jobs/listing/full-stack-engineer-developer-experience-product-platform/6567104",
        )
        text = html_capture_to_text(markup, metadata)
        self.assertEqual(metadata["role_title"], "Full Stack Engineer, Developer Experience & Product Platform")
        self.assertEqual(metadata["location"], "Toronto")
        self.assertNotIn("Stripe logo", metadata["role_title"])
        self.assertNotIn("Open mobile navigation", text)
        self.assertIn("## Who we are", text)
        self.assertIn("- Build developer platforms", text)

    def test_extract_apple_markdown_includes_posted_date(self) -> None:
        payload = {
            "loaderData": {
                "jobDetails": {
                    "jobsData": {
                        "postingTitle": "Software Engineer, System Experience",
                        "jobNumber": "200602358",
                        "postingDate": "Oct 31, 2025",
                        "jobSummary": "Build future system experiences.",
                        "description": "Implement features and improve performance.",
                        "minimumQualifications": "Excellent Swift programming\\nDebugging skills",
                        "preferredQualifications": "Reusable APIs",
                        "locations": [
                            {"city": "Cupertino", "stateProvince": "California", "countryName": "United States"}
                        ],
                    }
                }
            }
        }
        markup = f'<script>window.__staticRouterHydrationData = JSON.parse({json.dumps(json.dumps(payload))});</script>'
        metadata = extract_html_capture_metadata(markup, "https://jobs.apple.com/en-us/details/200602358/software-engineer-system-experience")
        self.assertIn("Posted: Oct 31, 2025", metadata["markdown"])
        self.assertEqual(metadata["published_at"], "Oct 31, 2025")

    def test_parse_pdf_date(self) -> None:
        self.assertEqual(parse_pdf_date("D:20250815165320Z00'00'"), "2025-08-15T16:53:20+00:00")

    def test_ingest_text_file_can_infer_metadata_from_url_and_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            source = Path(temp) / "Readwise.txt"
            source.write_text(
                """
                Readwise
                https://readwise.io/careers/senior-staff-engineer
                Senior/Staff Engineer (Backend Focus)
                Engineering Remote Full time
                """,
                encoding="utf-8",
            )

            result = ingest_file(source, root=root)
            metadata = parse_frontmatter(Path(result["destination"]) / "listing.md")
            self.assertEqual(metadata["company"], "Readwise")
            self.assertEqual(metadata["role_title"], "Senior/Staff Engineer (Backend Focus)")
            self.assertEqual(metadata["seniority"], "senior-staff")
            self.assertEqual(metadata["role_family"], "backend")
            self.assertEqual(metadata["location"], "Remote")
            self.assertEqual(metadata["employment_type"], "Full time")
            self.assertEqual(metadata["source_url"], "https://readwise.io/careers/senior-staff-engineer")

    def test_ingest_html_file_and_build_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            source_dir = Path(temp) / "source"
            root.mkdir()
            source_dir.mkdir()
            source = source_dir / "Software Engineer - Jobs - Careers at Apple.txt"
            source.write_text(
                """
                <!doctype html>
                <html><body>
                  <h1>Software Engineer</h1>
                  <a href="https://jobs.apple.com/app/en-us/apply/123456789-0000">Apply</a>
                  <p>Job type Full time Apply</p>
                </body></html>
                """,
                encoding="utf-8",
            )

            result = ingest_file(source, root=root)
            self.assertEqual(result["status"], "ingested")
            duplicate = ingest_file(source, root=root)
            self.assertEqual(duplicate["status"], "skipped")
            self.assertEqual(duplicate["reason"], "already imported")
            listing_path = Path(result["destination"]) / "listing.md"
            self.assertTrue(listing_path.exists())
            self.assertTrue((Path(result["destination"]) / "raw.html").exists())
            self.assertTrue((Path(result["destination"]) / "raw.txt").exists())

            metadata = parse_frontmatter(listing_path)
            self.assertEqual(metadata["company"], "Apple")
            self.assertEqual(metadata["source_type"], "html")
            self.assertEqual(metadata["source_url"], "https://jobs.apple.com/en-us/details/123456789/software-engineer")

            index_path = build_index(root)
            with index_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["company"], "Apple")
            self.assertEqual(rows[0]["role_title"], "Software Engineer")


if __name__ == "__main__":
    unittest.main()
