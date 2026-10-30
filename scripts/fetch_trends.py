#!/usr/bin/env python3
"""Fetch configured Hacker News and RSS items into the content archive."""

from __future__ import annotations

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.json"
USER_AGENT = "content-engine-newsletter/1.0 (GitHub Actions)"


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str, limit: int = 1200) -> str:
    parser = TextExtractor()
    parser.feed(value)
    text = " ".join(" ".join(parser.parts).split())
    return html.unescape(text)[:limit]


def request_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=25) as response:
            return response.read()
    except HTTPError as error:
        raise RuntimeError(f"Request failed with HTTP {error.code}: {url}") from error
    except URLError as error:
        raise RuntimeError(f"Request failed: {url} ({error.reason})") from error


def request_json(url: str) -> dict | list:
    return json.loads(request_bytes(url))


def fetch_hacker_news(limit: int) -> list[dict[str, str | int]]:
    story_ids = request_json("https://hacker-news.firebaseio.com/v0/topstories.json")
    if not isinstance(story_ids, list):
        raise RuntimeError("Hacker News returned an invalid top stories response")

    def fetch_story(story_id: int) -> dict[str, str | int] | None:
        item = request_json(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
        if not isinstance(item, dict) or not item.get("title"):
            return None
        url = item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        return {
            "source": "hacker_news",
            "title": str(item["title"]),
            "url": str(url),
            "summary": plain_text(str(item.get("text", ""))),
            "score": int(item.get("score", 0)),
            "published": datetime.fromtimestamp(
                int(item.get("time", 0)), timezone.utc
            ).isoformat() if item.get("time") else "",
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        stories = list(executor.map(fetch_story, story_ids[:limit]))
    return [story for story in stories if story is not None]


def parse_rss(xml_data: bytes, feed_url: str) -> list[dict[str, str | int]]:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as error:
        raise RuntimeError(f"Could not parse RSS/Atom feed: {feed_url}") from error

    entries = [
        element for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}
    ]
    items: list[dict[str, str | int]] = []
    for entry in entries:
        fields = {
            child.tag.rsplit("}", 1)[-1].lower(): child
            for child in entry
        }
        title = fields.get("title")
        if title is None:
            continue
        link_element = fields.get("link")
        link = ""
        if link_element is not None:
            link = link_element.attrib.get("href", "") or (link_element.text or "").strip()
        description = next(
            (fields[key] for key in ("description", "summary", "encoded", "content") if fields.get(key) is not None),
            None,
        )
        published = next(
            (fields[key] for key in ("pubdate", "published", "updated") if fields.get(key) is not None),
            None,
        )
        items.append(
            {
                "source": f"rss:{feed_url}",
                "title": plain_text("".join(title.itertext()), 500),
                "url": link or feed_url,
                "summary": plain_text("".join(description.itertext()) if description is not None else ""),
                "score": 0,
                "published": plain_text("".join(published.itertext()), 100) if published is not None else "",
            }
        )
    return items


def fetch_rss(feeds: list[str]) -> list[dict[str, str | int]]:
    items = []
    for feed_url in feeds:
        items.extend(parse_rss(request_bytes(feed_url), feed_url))
    return items


def deduplicate(items: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
    seen: set[str] = set()
    unique = []
    for item in items:
        key = str(item.get("url") or item.get("title", "")).strip().rstrip("/")
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def load_sources() -> dict:
    try:
        return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read source configuration: {SOURCES_PATH}") from error


def collect(date: str) -> Path:
    config = load_sources()
    items: list[dict[str, str | int]] = []

    hacker_news = config.get("hacker_news", {})
    if hacker_news.get("enabled", False):
        items.extend(fetch_hacker_news(int(hacker_news.get("limit", 20))))

    items.extend(fetch_rss([str(url) for url in config.get("rss_feeds", [])]))
    items = deduplicate(items)
    if not items:
        raise RuntimeError("No items were fetched; enable and configure at least one source")

    output = ROOT / "content" / "blog-source" / f"{date}-trends.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "date": date,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Fetched {len(items)} items to {output.relative_to(ROOT)}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("--date must use YYYY-MM-DD")
    collect(args.date)


if __name__ == "__main__":
    main()
