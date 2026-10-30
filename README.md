# Content Engine

Automates trend collection, newsletter and social draft creation, media processing, and the post-merge handoff to n8n.

## Workflow

- `01-ingest-and-draft.yml` runs weekly on Monday at 08:40 UTC, or on demand through `workflow_dispatch` or the `ingest_newsletter` `repository_dispatch` event. It fetches Hacker News, configured Reddit communities and RSS feeds, asks OpenAI to create drafts, checks links, and opens a pull request.
- `02-process-assets.yml` converts images under `media/raw/` to square and 16:9 WebP variants under `media/processed/`.
- `03-publish-dispatch.yml` runs when a newsletter draft pull request is merged. It moves the issue into `content/newsletters/archives/` and sends the Markdown, issue metadata, and HTML template to n8n. The n8n workflow should create a **Mailchimp draft**, not send it automatically.

Drafts and source snapshots are written under `content/`. The RSS feed list starts empty; edit `config/sources.json` to add feed URLs and change subreddit or Hacker News limits. Reddit fetching is skipped with a clear warning until both Reddit credentials are configured. Archived Markdown is ready for a static-site generator, but this repository does not yet include a site build or deployment target.

## GitHub setup

Add these under **Settings → Secrets and variables → Actions → Secrets**:

| Secret | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required for newsletter and social draft generation |
| `REDDIT_CLIENT_ID` | Reddit OAuth app client ID |
| `REDDIT_CLIENT_SECRET` | Reddit OAuth app client secret |
| `REDDIT_REFRESH_TOKEN` | Optional Reddit OAuth refresh token with Data API `read` access |
| `N8N_WEBHOOK_URL` | HTTPS production URL for the n8n webhook |
| `N8N_WEBHOOK_TOKEN` | Secret for the webhook `Authorization` header, configured in n8n Header Auth |

`REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are optional if Reddit is disabled in `config/sources.json`. Set the optional `OPENAI_MODEL` repository variable to override the default `gpt-5-mini`.

For user-authorized Reddit access, follow [Reddit's OAuth guide](https://github.com/reddit-archive/reddit/wiki/OAuth2) to authorize the app with the `read` scope and obtain a refresh token. Store that token as the `REDDIT_REFRESH_TOKEN` Actions secret alongside the app's client ID and secret. Each run exchanges the refresh token for a short-lived access token. Without a refresh token, the fetcher uses the existing client-credentials grant. Reddit Data API access is required to fetch subreddit posts; Ads API access alone may not grant it. Never commit or share tokens.

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
