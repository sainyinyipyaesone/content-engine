#!/usr/bin/env node

const fs = require("node:fs/promises");
const { execFileSync } = require("node:child_process");
const path = require("node:path");

function changedMarkdownFromGit(base, head) {
  const paths = execFileSync(
    "git",
    ["diff", "--name-only", "--diff-filter=ACMRT", `${base}...${head}`, "--", "content"],
    { encoding: "utf8" },
  )
    .split("\n")
    .filter((file) => file.endsWith(".md"));
  return paths.map((file) => ({
    file,
    text: execFileSync("git", ["show", `${head}:${file}`], { encoding: "utf8" }),
  }));
}

async function markdownFiles(target) {
  const stat = await fs.stat(target);
  if (stat.isFile()) {
    return target.endsWith(".md") ? [target] : [];
  }
  const entries = await fs.readdir(target, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map((entry) => markdownFiles(path.join(target, entry.name))),
  );
  return nested.flat();
}

function urlsInText(text) {
  return [...text.matchAll(/https?:\/\/[^\s<>"')\]]+/g)]
    .map((match) => match[0].replace(/[.,;:!?]+$/, ""))
    .filter(Boolean);
}

async function urlsInFile(file) {
  return urlsInText(await fs.readFile(file, "utf8"));
}

async function checkUrl(url) {
  const timeout = AbortSignal.timeout(15000);
  let response = await fetch(url, {
    method: "HEAD",
    headers: { "User-Agent": "content-engine-link-check/1.0" },
    signal: timeout,
    redirect: "follow",
  });
  if (response.status === 405 || response.status === 501) {
    response = await fetch(url, {
      method: "GET",
      headers: { "User-Agent": "content-engine-link-check/1.0" },
      signal: timeout,
      redirect: "follow",
    });
  }
  if (response.status === 403 || response.status === 429) {
    console.warn(`UNVERIFIED ${url}: HTTP ${response.status}`);
    return;
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}

async function main() {
  const targets = process.argv.slice(2);
  if (targets.length === 0) {
    throw new Error("Usage: node scripts/validate_links.js <markdown-file-or-directory> [...]");
  }
  let contents;
  if (targets[0] === "--git-diff") {
    if (targets.length !== 3) {
      throw new Error("Usage: node scripts/validate_links.js --git-diff <base-ref> <head-ref>");
    }
    contents = changedMarkdownFromGit(targets[1], targets[2]);
  } else {
    const files = (await Promise.all(targets.map(markdownFiles))).flat();
    contents = await Promise.all(
      files.map(async (file) => ({ file, urls: await urlsInFile(file) })),
    );
    contents = contents.map(({ file, urls }) => ({ file, urls }));
  }

  const links = new Map();
  for (const content of contents) {
    const urls = content.urls || urlsInText(content.text);
    for (const url of urls) {
      links.set(url, [...(links.get(url) || []), content.file]);
    }
  }

  const failures = [];
  for (const [url, sourceFiles] of links) {
    try {
      await checkUrl(url);
      console.log(`OK ${url}`);
    } catch (error) {
      failures.push({ url, sourceFiles, error });
      console.error(`FAIL ${url}: ${error.message} (${sourceFiles.join(", ")})`);
    }
  }
  if (failures.length > 0) {
    throw new Error(`${failures.length} link(s) failed validation`);
  }
  console.log(`Validated ${links.size} unique link(s) in ${contents.length} Markdown file(s).`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
