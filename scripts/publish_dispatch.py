#!/usr/bin/env python3
"""Send a merged newsletter issue to the configured n8n webhook."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ISSUE_PATTERN = re.compile(r"content/newsletters/archives/issue-(\d+)\.md")


def parse_metadata(markdown: str) -> tuple[str, str]:
    frontmatter = re.match(r"\A---\n(.*?)\n---\n", markdown, re.DOTALL)
    if not frontmatter:
        raise RuntimeError("Archived newsletter has no YAML front matter")
    title_match = re.search(r"^title:\s*(.*?)\s*$", frontmatter.group(1), re.MULTILINE)
    date_match = re.search(r'^date:\s*["\']?(\d{4}-\d{2}-\d{2})', frontmatter.group(1), re.MULTILINE)
    if not title_match or not date_match:
        raise RuntimeError("Archived newsletter is missing title or date metadata")
    try:
        title = json.loads(title_match.group(1))
    except json.JSONDecodeError:
        title = title_match.group(1).strip("\"'")
    if not isinstance(title, str) or not title:
        raise RuntimeError("Archived newsletter title is invalid")
    return title, date_match.group(1)


def current_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Could not determine the archive commit") from error


def send_issue(relative_path: str) -> None:
    match = ISSUE_PATTERN.fullmatch(relative_path)
    if not match:
        raise RuntimeError(f"Not an archived newsletter path: {relative_path}")

    webhook_url = os.environ.get("N8N_WEBHOOK_URL", "")
    webhook_token = os.environ.get("N8N_WEBHOOK_TOKEN", "")
    if not webhook_url or not webhook_token:
        raise RuntimeError("Set N8N_WEBHOOK_URL and N8N_WEBHOOK_TOKEN repository Actions secrets")
    if not webhook_url.startswith("https://"):
        raise RuntimeError("N8N_WEBHOOK_URL must use HTTPS")

    issue_path = ROOT / relative_path
    markdown = issue_path.read_text(encoding="utf-8")
    title, issue_date = parse_metadata(markdown)
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    branch = os.environ.get("GITHUB_BASE_REF") or os.environ.get("GITHUB_REF_NAME", "main")
    issue_number = int(match.group(1))
    payload = {
        "event": "newsletter_issue_merged",
        "repository": repository,
        "issue_number": issue_number,
        "title": title,
        "date": issue_date,
        "newsletter_markdown": markdown,
        "html_template": (ROOT / "templates" / "newsletter-template.html").read_text(encoding="utf-8"),
        "archive_path": relative_path,
        "commit_sha": current_commit(),
        "url": (
            f"{server_url}/{repository}/blob/{quote(branch, safe='')}/"
            f"{quote(relative_path, safe='/')}"
        ),
    }
    request = Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={
            "Authorization": f"Bearer {webhook_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            print(f"n8n accepted newsletter issue {issue_number:03d} (HTTP {response.status})")
    except HTTPError as error:
        raise RuntimeError(f"n8n webhook failed with HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach n8n webhook: {error.reason}") from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive_path")
    args = parser.parse_args()
    send_issue(args.archive_path)


if __name__ == "__main__":
    main()
