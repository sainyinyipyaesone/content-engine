from __future__ import annotations

import base64
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from scripts.fetch_trends import fetch_reddit, get_reddit_token


class RedditAuthTests(unittest.TestCase):
    def test_client_credentials_grant_remains_default(self) -> None:
        with patch("scripts.fetch_trends.request_json", return_value={"access_token": "access"}) as request:
            self.assertEqual(get_reddit_token("client", "secret"), "access")

        self.assertEqual(
            parse_qs(request.call_args.kwargs["data"].decode()),
            {"grant_type": ["client_credentials"]},
        )
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"],
            "Basic " + base64.b64encode(b"client:secret").decode(),
        )

    def test_refresh_token_grant(self) -> None:
        with patch("scripts.fetch_trends.request_json", return_value={"access_token": "access"}) as request:
            self.assertEqual(get_reddit_token("client", "secret", "refresh"), "access")

        self.assertEqual(
            parse_qs(request.call_args.kwargs["data"].decode()),
            {"grant_type": ["refresh_token"], "refresh_token": ["refresh"]},
        )

    def test_missing_access_token_fails(self) -> None:
        with patch("scripts.fetch_trends.request_json", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "did not return an access token"):
                get_reddit_token("client", "secret", "refresh")

    def test_fetch_reddit_uses_configured_refresh_token(self) -> None:
        env = {
            "REDDIT_CLIENT_ID": "client",
            "REDDIT_CLIENT_SECRET": "secret",
            "REDDIT_REFRESH_TOKEN": "refresh",
        }
        response = {
            "data": {"children": [{"data": {
                "title": "Example",
                "permalink": "/r/technology/comments/123/example/",
                "selftext": "Post text",
                "score": 5,
            }}]}
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch("scripts.fetch_trends.get_reddit_token", return_value="access") as token,
            patch("scripts.fetch_trends.request_json", return_value=response) as request,
        ):
            items = fetch_reddit(["technology"], 10)

        token.assert_called_once_with("client", "secret", "refresh")
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer access")
        self.assertEqual(items[0]["title"], "Example")
        self.assertEqual(items[0]["source"], "reddit:r/technology")


if __name__ == "__main__":
    unittest.main()
