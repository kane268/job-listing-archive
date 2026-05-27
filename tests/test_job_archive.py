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
    enrich_listing_file,
    extract_a24_labs_bundle_capture,
    extract_html_capture_metadata,
    html_capture_to_text,
    html_to_text,
    infer_company_from_url,
    infer_metadata_from_filename,
    ingest_url,
    parse_frontmatter,
    render_yaml,
    short_listing_slug,
    split_listing_file,
    write_listing_file,
    slugify,
)
from validation import validate_archive  # noqa: E402


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
        self.assertEqual(short_listing_slug("GitHub", "Staff Software Engineer"), "github-staff-software-engineer")

    def test_infer_metadata_from_plain_filenames(self) -> None:
        stripe = infer_metadata_from_filename("Stripe Staff Software Engineer, Data Movement.html")
        self.assertEqual(stripe["company"], "Stripe")
        self.assertEqual(stripe["role_title"], "Staff Software Engineer, Data Movement")
        self.assertEqual(stripe["seniority"], "staff")
        self.assertEqual(stripe["role_family"], "data")

        copilot = infer_metadata_from_filename("Head of Engineering @ Copilot Money.html")
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

    def test_ingest_url_from_fetched_html_writes_flat_listing(self) -> None:
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

            result = ingest_url(fetched.requested_url, root=root, fetched=fetched)
            self.assertEqual(result["status"], "fetched")
            listing_path = Path(result["destination"])
            self.assertRegex(listing_path.relative_to(root).as_posix(), r"^listings/\d{4}-\d{2}-\d{2}-anthropic-staff-developer-productivity\.md$")
            metadata, text = split_listing_file(listing_path)
            self.assertEqual(metadata["company"], "Anthropic")
            self.assertEqual(metadata["title"], "Staff+ Software Engineer, Developer Productivity")
            self.assertEqual(metadata["content_type"], "html")
            self.assertIn("Build developer tooling", text)

    def test_extract_a24_labs_bundle_markdown_from_react_route(self) -> None:
        bundle = '''
        Hz={path:"/jobs/devops",title:"A24 Labs Careers - DevOps Engineer"},
        $z=()=>P.jsxDEV("article",{children:[
          P.jsxDEV("p",{children:"A24 Labs Careers"}),
          P.jsxDEV("h1",{children:"DevOps Engineer | SRE | Platform Engineer"}),
          P.jsxDEV("p",{children:"A24 Labs is a technology startup within A24 Films."}),
          P.jsxDEV("p",{children:[P.jsxDEV("strong",{children:"Compensation:"})," $150k - $230k, plus bonus."]}),
          P.jsxDEV("p",{children:[P.jsxDEV("strong",{children:"Location:"})," Most of the labs team works from our New York office."]}),
          P.jsxDEV("h2",{children:"Required Skills & Experience"}),
          P.jsxDEV("ul",{children:[
            P.jsxDEV("li",{children:"Strong hands-on experience operating production systems on AWS"}),
            P.jsxDEV("li",{children:"CI/CD pipeline with GitHub Actions"})
          ]})
        ]}),Iz={path:"/jobs/designer",title:"A24 Labs Careers - Senior Web/Product Designer"}
        '''
        metadata = extract_a24_labs_bundle_capture(bundle, "https://labs.a24films.com/jobs/devops")
        text = metadata["markdown"]
        self.assertEqual(metadata["company"], "A24 Labs")
        self.assertEqual(metadata["role_title"], "DevOps Engineer | SRE | Platform Engineer")
        self.assertEqual(metadata["role_family"], "infra/platform")
        self.assertEqual(metadata["location"], "New York office")
        self.assertEqual(metadata["compensation"], "$150k - $230k")
        self.assertIn("# DevOps Engineer | SRE | Platform Engineer - A24 Labs", text)
        self.assertIn("## Required Skills & Experience", text)
        self.assertIn("- CI/CD pipeline with GitHub Actions", text)

    def test_extract_github_markdown_uses_job_posting_data(self) -> None:
        markup = """
        <!doctype html>
        <html><head>
          <script type="application/ld+json">
          {
            "@context": "http://schema.org",
            "@type": "JobPosting",
            "title": "Staff Software Engineer",
            "description": "<strong>About GitHub</strong><br><br>GitHub builds developer tools.<br><br><strong>Locations</strong><br><br>In this role you can work from Remote, United States<br><br><strong>Responsibilities</strong><br><br><ul><li>Build billing systems</li></ul><br><strong>Compensation Range</strong><br><br>The base salary range for this job is USD $140,400.00 - USD $372,300.00 /Yr.",
            "employmentType": "FULL_TIME",
            "hiringOrganization": {"@type": "Organization", "name": "GitHub, Inc."},
            "jobLocation": {"@type": "Place", "address": {"addressLocality": "UNAVAILABLE", "addressRegion": "UNAVAILABLE", "addressCountry": "United States"}}
          }
          </script>
        </head><body><nav>Skip to Main Content</nav></body></html>
        """
        metadata = extract_html_capture_metadata(markup, "https://www.github.careers/careers-home/jobs/5369?lang=en-us")
        text = html_capture_to_text(markup, metadata)
        self.assertEqual(metadata["company"], "GitHub")
        self.assertEqual(metadata["role_title"], "Staff Software Engineer")
        self.assertEqual(metadata["location"], "Remote, United States")
        self.assertEqual(metadata["employment_type"], "Full time")
        self.assertEqual(metadata["compensation"], "USD $140,400.00 - USD $372,300.00 /Yr")
        self.assertIn("# Staff Software Engineer - GitHub", text)
        self.assertIn("## Responsibilities", text)
        self.assertIn("- Build billing systems", text)
        self.assertNotIn("Skip to Main Content", text)

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
                        "minimumQualifications": "Excellent Swift programming\nDebugging skills",
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

    def test_parse_frontmatter_preserves_unicode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "listing.md"
            path.write_text(render_yaml({"company": "São Paulo AI", "title": "Ingénieur"}) + "\n", encoding="utf-8")
            metadata = parse_frontmatter(path)
            self.assertEqual(metadata["company"], "São Paulo AI")
            self.assertEqual(metadata["title"], "Ingénieur")

    def test_enrich_listing_file_updates_queued_listing_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            listing_path = root / "listings" / "queued.md"
            write_listing_file(
                listing_path,
                {
                    "source_url": "https://jobs.apple.com/en-us/details/123456789/software-engineer",
                    "saved_at": "2026-05-16",
                    "status": "queued",
                    "tags": [],
                    "requirements": [],
                    "nice_to_haves": [],
                },
            )
            fetched = URLFetch(
                requested_url="https://jobs.apple.com/en-us/details/123456789/software-engineer",
                final_url="https://jobs.apple.com/en-us/details/123456789/software-engineer",
                status=200,
                content_type="text/html; charset=utf-8",
                body=b"<html><body><h1>Software Engineer</h1><p>Build systems.</p></body></html>",
                encoding="utf-8",
                fetched_at="2026-05-16T12:00:00+00:00",
            )

            result = enrich_listing_file(listing_path, fetched=fetched)
            self.assertEqual(result["status"], "fetched")
            metadata, body = split_listing_file(listing_path)
            self.assertEqual(metadata["status"], "fetched")
            self.assertEqual(metadata["company"], "Apple")
            self.assertEqual(metadata["title"], "Software Engineer")
            self.assertIn("Build systems", body)

    def test_ingest_url_writes_flat_markdown_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            body = b"""
            <!doctype html>
            <html><body>
              <h1>Software Engineer</h1>
              <a href="https://jobs.apple.com/app/en-us/apply/123456789-0000">Apply</a>
              <p>Job type Full time Apply</p>
            </body></html>
            """
            fetched = URLFetch(
                requested_url="https://jobs.apple.com/en-us/details/123456789/software-engineer",
                final_url="https://jobs.apple.com/en-us/details/123456789/software-engineer",
                status=200,
                content_type="text/html; charset=utf-8",
                body=body,
                encoding="utf-8",
                fetched_at="2026-05-16T12:00:00+00:00",
            )

            result = ingest_url(fetched.requested_url, root=root, fetched=fetched)
            self.assertEqual(result["status"], "fetched")
            duplicate = ingest_url(fetched.requested_url, root=root, fetched=fetched)
            self.assertEqual(duplicate["status"], "skipped")
            self.assertEqual(duplicate["reason"], "already fetched URL")
            listing_path = Path(result["destination"])
            self.assertTrue(listing_path.exists())
            self.assertFalse((listing_path.parent / "raw.html").exists())
            self.assertFalse((listing_path.parent / "raw.md").exists())

            metadata = parse_frontmatter(listing_path)
            self.assertEqual(metadata["company"], "Apple")
            self.assertEqual(metadata["content_type"], "html")
            self.assertEqual(metadata["source_url"], "https://jobs.apple.com/en-us/details/123456789/software-engineer")

            index_path = build_index(root)
            with index_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["company"], "Apple")
            self.assertEqual(rows[0]["title"], "Software Engineer")

    def test_validate_archive_accepts_queued_listing_without_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            listing_path = root / "listings" / "queued.md"
            write_listing_file(
                listing_path,
                {
                    "source_url": "https://example.com/jobs/1",
                    "saved_at": "2026-05-16",
                    "status": "queued",
                    "tags": [],
                    "requirements": [],
                    "nice_to_haves": [],
                },
            )
            (root / "data").mkdir()
            (root / "data" / "job-sources.json").write_text(
                json.dumps({"sources": [{"name": "Example", "url": "https://example.com/jobs", "homepage_url": "https://example.com"}]}),
                encoding="utf-8",
            )
            self.assertEqual(validate_archive(root), [])


if __name__ == "__main__":
    unittest.main()
