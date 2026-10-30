from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import fetch_trends


class CollectTests(unittest.TestCase):
    def test_configured_feeds_and_hacker_news_are_collected_and_deduplicated(self) -> None:
        config = fetch_trends.load_sources()
        dev_feeds = {
            "https://dev.to/feed/tag/technology",
            "https://dev.to/feed/tag/programming",
            "https://dev.to/feed/tag/ai",
        }
        self.assertTrue(dev_feeds.issubset(config["rss_feeds"]))
        self.assertNotIn("reddit", config)

        def feed_response(url: str) -> bytes:
            if url in dev_feeds:
                return b"""<rss><channel><item>
                  <title>Community post</title>
                  <link>https://dev.to/example/community-post</link>
                  <description><![CDATA[An <b>example</b> post]]></description>
                  <pubDate>Fri, 30 Oct 2026 08:00:00 GMT</pubDate>
                </item></channel></rss>"""
            return b"<rss><channel /></rss>"

        story = {
            "title": "Hacker News story",
            "url": "https://example.com/story",
            "score": 42,
            "time": 1793347200,
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("scripts.fetch_trends.ROOT", Path(temporary)),
            patch("scripts.fetch_trends.request_bytes", side_effect=feed_response) as feeds,
            patch("scripts.fetch_trends.request_json", side_effect=[[123], story]),
        ):
            output = fetch_trends.collect("2026-10-30")
            snapshot = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            [call.args[0] for call in feeds.call_args_list],
            config["rss_feeds"],
        )
        self.assertEqual(snapshot["date"], "2026-10-30")
        self.assertEqual(len(snapshot["items"]), 2)
        self.assertEqual(snapshot["items"][0]["source"], "hacker_news")
        community = snapshot["items"][1]
        self.assertEqual(community["source"], "rss:https://dev.to/feed/tag/technology")
        self.assertEqual(community["title"], "Community post")
        self.assertEqual(community["url"], "https://dev.to/example/community-post")
        self.assertEqual(community["summary"], "An example post")
        self.assertEqual(community["published"], "Fri, 30 Oct 2026 08:00:00 GMT")

    def test_feed_failure_is_reported_without_writing_a_snapshot(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("scripts.fetch_trends.ROOT", Path(temporary)),
            patch("scripts.fetch_trends.fetch_hacker_news", return_value=[]),
            patch("scripts.fetch_trends.request_bytes", side_effect=RuntimeError("Feed unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "Feed unavailable"):
                fetch_trends.collect("2026-10-30")
            self.assertFalse((Path(temporary) / "content").exists())


if __name__ == "__main__":
    unittest.main()
