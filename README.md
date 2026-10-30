# Content Engine

Automates trend collection, newsletter and social draft creation, media processing, and the post-merge handoff to n8n.

## Workflow

- `01-ingest-and-draft.yml` runs weekly on Monday at 08:40 UTC, or on demand through `workflow_dispatch` or the `ingest_newsletter` `repository_dispatch` event. It fetches Hacker News and configured RSS feeds, asks OpenAI to create drafts, checks links, and opens a pull request.
- `02-process-assets.yml` converts images under `media/raw/` to square and 16:9 WebP variants under `media/processed/`.
- `03-publish-dispatch.yml` runs when a newsletter draft pull request is merged. It moves the issue into `content/newsletters/archives/` and sends the Markdown, issue metadata, and HTML template to n8n. The n8n workflow should create a **Mailchimp draft**, not send it automatically.

Drafts and source snapshots are written under `content/`. The configured RSS feeds include DEV Community articles tagged technology, programming, and AI, alongside arXiv, Hugging Face, and TechCrunch. Edit `config/sources.json` to change the feed URLs or Hacker News limit. Archived Markdown is ready for a static-site generator, but this repository does not yet include a site build or deployment target.

## GitHub setup

Add these under **Settings → Secrets and variables → Actions → Secrets**:

| Secret | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required for newsletter and social draft generation |
| `N8N_WEBHOOK_URL` | HTTPS production URL for the n8n webhook |
| `N8N_WEBHOOK_TOKEN` | Secret for the webhook `Authorization` header, configured in n8n Header Auth |

Set the optional `OPENAI_MODEL` repository variable to override the default `gpt-5-mini`. Any previously configured Reddit Actions secrets can be removed.

The first workflow needs permission to create branches and pull requests. The asset and publish workflows push generated files to their target branches; if branch protection blocks Actions writes, allow the GitHub Actions bot to update those branches or adjust the workflows.

To trigger ingestion from n8n, use the GitHub repository dispatch API with event type `ingest_newsletter`. The GitHub credential must have permission to dispatch repository events. For the post-merge workflow, configure an n8n Webhook node with header authentication, convert `newsletter_markdown` to HTML, apply `html_template`, and use the Mailchimp node to create a campaign draft.

## Local checks

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests
node scripts/validate_links.js README.md

```
