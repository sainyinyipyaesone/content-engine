#!/usr/bin/env python3
"""Move a merged draft issue into the newsletter archive."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISSUE_PATH_PATTERN = re.compile(r"content/newsletters/draft-issue-(\d+)\.md")


def archive_issue(relative_path: str) -> Path:
    match = ISSUE_PATH_PATTERN.fullmatch(relative_path)
    if not match:
        raise RuntimeError(f"Not a newsletter draft path: {relative_path}")

    issue_number = int(match.group(1))
    source = ROOT / relative_path
    destination = ROOT / "content" / "newsletters" / "archives" / f"issue-{issue_number:03d}.md"
    if source.exists():
        contents = source.read_text(encoding="utf-8")
        archived_contents, replacements = re.subn(
            r"(?m)^status:\s*draft\s*$",
            "status: archived",
            contents,
            count=1,
        )
        if replacements == 0 and not re.search(r"(?m)^status:\s*archived\s*$", contents):
            raise RuntimeError(f"Draft issue has no draft or archived status: {relative_path}")
        if replacements == 0:
            archived_contents = contents
        if destination.exists():
            if destination.read_text(encoding="utf-8") != archived_contents:
                raise RuntimeError(f"Archive already exists: {destination.relative_to(ROOT)}")
            source.unlink()
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = source.with_name(f".{source.name}.tmp")
            temporary.write_text(archived_contents, encoding="utf-8")
            temporary.replace(source)
            source.replace(destination)
    elif not destination.exists():
        raise RuntimeError(
            f"Neither draft nor archive exists for issue {issue_number:03d}"
        )

    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as output:
            output.write(f"archive_path={destination.relative_to(ROOT).as_posix()}\n")
    print(f"Archived issue {issue_number:03d}")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("draft_path")
    args = parser.parse_args()
    archive_issue(args.draft_path)


if __name__ == "__main__":
    main()
