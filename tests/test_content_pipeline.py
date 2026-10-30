from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts.archive_issue import archive_issue
from scripts.fetch_trends import deduplicate, parse_rss
from scripts.format_assets import process_image
from scripts.generate_drafts import find_issue_number, generate
from scripts.publish_dispatch import parse_metadata


class FetchTrendsTests(unittest.TestCase):
    def test_parse_rss_atom_namespace(self) -> None:
        feed = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Example &amp; update</title>
            <link href="https://example.com/post" />
            <summary>A useful &lt;b&gt;summary&lt;/b&gt;</summary>
            <published>2026-10-30T00:00:00Z</published>
          </entry>
        </feed>"""

        items = parse_rss(feed, "https://example.com/feed")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Example & update")
        self.assertEqual(items[0]["url"], "https://example.com/post")
        self.assertEqual(items[0]["summary"], "A useful summary")

    def test_deduplicate_keeps_first_matching_url(self) -> None:
        items = [
            {"title": "first", "url": "https://example.com/post"},
            {"title": "second", "url": "https://example.com/post/"},
        ]

        self.assertEqual(deduplicate(items), [items[0]])


class NewsletterTests(unittest.TestCase):
    def test_reads_generated_frontmatter(self) -> None:
        markdown = (
            '---\ntitle: "An \\"example\\" issue"\n'
            'issue: 7\ndate: "2026-10-30"\nstatus: archived\n---\n\nBody\n'
        )

        self.assertEqual(
            parse_metadata(markdown),
            ('An "example" issue', "2026-10-30"),
        )

    def test_reuses_same_day_draft_number(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            newsletter_dir = Path(temporary)
            (newsletter_dir / "draft-issue-007.md").write_text(
                '---\ndate: "2026-10-30"\n---\n', encoding="utf-8"
            )
            (newsletter_dir / "archives").mkdir()
            (newsletter_dir / "archives" / "issue-006.md").write_text(
                '---\ndate: "2026-10-29"\n---\n', encoding="utf-8"
            )

            self.assertEqual(find_issue_number("2026-10-30", newsletter_dir), 7)
            self.assertEqual(find_issue_number("2026-10-31", newsletter_dir), 8)

    def test_generate_writes_issue_and_platform_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "sources.json"
            source_path.write_text('{"items": [{"title": "Example"}]}', encoding="utf-8")
            prompts_path = root / "social-prompts.json"
            prompts_path.write_text("{}", encoding="utf-8")
            drafts = {
                "newsletter_title": "Weekly update",
                "newsletter_markdown": "## Highlights\n\nA summary.",
                "twitter": "Short post [newsletter link]",
                "linkedin": "A useful professional post [newsletter link]",
                "telegram": "A friendly update [newsletter link]",
            }

            with (
                patch("scripts.generate_drafts.ROOT", root),
                patch("scripts.generate_drafts.SOCIAL_PROMPTS_PATH", prompts_path),
                patch("scripts.generate_drafts.openai_response", return_value=drafts),
            ):
                issue_path = generate("2026-10-30", source_path)

            self.assertEqual(
                issue_path.relative_to(root).as_posix(),
                "content/newsletters/draft-issue-001.md",
            )
            self.assertIn("status: draft", issue_path.read_text(encoding="utf-8"))
            for platform in ("twitter", "linkedin", "telegram"):
                social_path = root / "content/social-drafts/2026-10-30-trends" / f"{platform}.md"
                self.assertTrue(social_path.is_file())

    def test_archives_issue_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "content/newsletters/draft-issue-007.md"
            source.parent.mkdir(parents=True)
            source.write_text(
                '---\ntitle: "Example"\nissue: 7\ndate: "2026-10-30"\nstatus: draft\n---\n\nBody\n',
                encoding="utf-8",
            )

            with patch("scripts.archive_issue.ROOT", root):
                archived = archive_issue("content/newsletters/draft-issue-007.md")
                self.assertFalse(source.exists())
                self.assertIn("status: archived", archived.read_text(encoding="utf-8"))
                self.assertEqual(
                    archive_issue("content/newsletters/draft-issue-007.md"),
                    archived,
                )


class AssetTests(unittest.TestCase):
    def test_process_image_writes_webp_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_dir = root / "raw"
            output_dir = root / "processed"
            raw_dir.mkdir()
            source = raw_dir / "sample.png"
            Image.new("RGB", (640, 480), "blue").save(source)

            outputs = process_image(source, raw_dir, output_dir)

            self.assertEqual(
                {path.name for path in outputs},
                {"sample-1x1.webp", "sample-16x9.webp"},
            )
            with Image.open(output_dir / "sample-16x9.webp") as image:
                self.assertEqual(image.size, (1200, 675))
                self.assertEqual(image.format, "WEBP")


if __name__ == "__main__":
    unittest.main()
