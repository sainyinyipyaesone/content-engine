#!/usr/bin/env python3
"""Generate a newsletter issue and social drafts with the OpenAI Responses API."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOCIAL_PROMPTS_PATH = ROOT / "templates" / "social-prompts.json"
ISSUE_PATTERN = re.compile(r"(?:draft-issue-|issue-)(\d+)\.md$")

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "newsletter_title": {"type": "string"},
        "newsletter_markdown": {"type": "string"},
        "twitter": {"type": "string"},
        "linkedin": {"type": "string"},
        "telegram": {"type": "string"},
    },
    "required": [
        "newsletter_title",
        "newsletter_markdown",
        "twitter",
        "linkedin",
        "telegram",
    ],
}


def openai_response(items: list[dict], prompts: dict) -> dict[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set the OPENAI_API_KEY repository Actions secret")

    model = os.environ.get("OPENAI_MODEL") or "gpt-5-mini"
    instructions = (
        "Create an accurate newsletter draft from the supplied source items. "
        "Use only facts supported by those items, preserve source links, and "
        "clearly distinguish reporting from opinion. Do not invent details. "
        "Write concise, useful copy. Return the requested newsletter and "
        "platform-specific social drafts. Follow these platform prompts: "
        + json.dumps(prompts, ensure_ascii=False)
    )
    input_text = json.dumps(items, ensure_ascii=False)
    body = json.dumps(
        {
            "model": model,
            "instructions": instructions,
            "input": input_text,
            "max_output_tokens": 4000,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "newsletter_drafts",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                }
            },
        }
    ).encode()
    request = Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=90) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"OpenAI request failed with HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"OpenAI request failed: {error.reason}") from error

    if result.get("status") != "completed":
        raise RuntimeError(f"OpenAI response did not complete: {result.get('status', 'unknown')}")

    output_text = []
    for output_item in result.get("output", []):
        if output_item.get("type") == "message":
            for content_item in output_item.get("content", []):
                if content_item.get("type") == "output_text":
                    output_text.append(content_item.get("text", ""))
                elif content_item.get("type") == "refusal":
                    raise RuntimeError("OpenAI refused to generate the newsletter drafts")
    if not output_text:
        raise RuntimeError("OpenAI returned no text for the newsletter drafts")
    try:
        drafts = json.loads("".join(output_text))
    except json.JSONDecodeError as error:
        raise RuntimeError("OpenAI returned invalid structured output") from error
    if not all(isinstance(drafts.get(key), str) and drafts[key].strip() for key in OUTPUT_SCHEMA["required"]):
        raise RuntimeError("OpenAI returned an incomplete set of newsletter drafts")
    if len(drafts["twitter"]) > 280:
        raise RuntimeError("OpenAI returned a Twitter draft longer than 280 characters")
    if len(drafts["linkedin"].split()) > 180:
        raise RuntimeError("OpenAI returned a LinkedIn draft longer than 180 words")
    return drafts


def find_issue_number(date: str, newsletter_dir: Path) -> int:
    highest = 0
    same_day_draft = None
    for path in [*newsletter_dir.glob("draft-issue-*.md"), *(newsletter_dir / "archives").glob("issue-*.md")]:
        match = ISSUE_PATTERN.search(path.name)
        if not match:
            continue
        number = int(match.group(1))
        highest = max(highest, number)
        contents = path.read_text(encoding="utf-8")
        date_match = re.search(r'^date:\s*["\']?(\d{4}-\d{2}-\d{2})', contents, re.MULTILINE)
        if date_match and date_match.group(1) == date and path.name.startswith("draft-"):
            same_day_draft = number
    return same_day_draft if same_day_draft is not None else highest + 1


def write_github_output(key: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as output:
            output.write(f"{key}={value}\n")


def generate(date: str, source_path: Path) -> Path:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    items = source.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError(f"No source items found in {source_path}")

    prompts = json.loads(SOCIAL_PROMPTS_PATH.read_text(encoding="utf-8"))
    drafts = openai_response(items, prompts)
    newsletter_dir = ROOT / "content" / "newsletters"
    issue_number = find_issue_number(date, newsletter_dir)
    issue_path = newsletter_dir / f"draft-issue-{issue_number:03d}.md"
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"title: {json.dumps(drafts['newsletter_title'], ensure_ascii=False)}\n"
        f"issue: {issue_number}\n"
        f"date: {json.dumps(date)}\n"
        "status: draft\n"
        "---\n\n"
    )
    issue_path.write_text(
        frontmatter + drafts["newsletter_markdown"].strip() + "\n",
        encoding="utf-8",
    )

    social_dir = ROOT / "content" / "social-drafts" / f"{date}-trends"
    social_dir.mkdir(parents=True, exist_ok=True)
    for platform in ("twitter", "linkedin", "telegram"):
        (social_dir / f"{platform}.md").write_text(
            drafts[platform].strip() + "\n",
            encoding="utf-8",
        )

    relative_issue_path = issue_path.relative_to(ROOT).as_posix()
    write_github_output("issue_path", relative_issue_path)
    write_github_output("issue_number", str(issue_number))
    print(f"Generated issue {issue_number:03d} and social drafts")
    return issue_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument(
        "--source",
        type=Path,
        help="Path to fetched source JSON; defaults to content/blog-source/<date>-trends.json",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("--date must use YYYY-MM-DD")
    source_path = args.source or ROOT / "content" / "blog-source" / f"{args.date}-trends.json"
    generate(args.date, source_path)


if __name__ == "__main__":
    main()
