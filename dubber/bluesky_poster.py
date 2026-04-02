"""Direct Bluesky posting helper."""

import os

from .utils import log

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


class BlueskyPoster:
    def __init__(self):
        handle = os.getenv("BLUESKY_HANDLE")
        password = os.getenv("BLUESKY_APP_PASSWORD")
        self.client = None
        self.enabled = False

        try:
            from atproto import Client
        except Exception as exc:
            log("BLUESKY", f"atproto not installed — skipping direct Bluesky publish: {exc}")
            return

        if not handle or not password:
            log("BLUESKY", "Missing BLUESKY_HANDLE or BLUESKY_APP_PASSWORD — skipping direct Bluesky publish.")
            return

        try:
            client = Client()
            client.login(handle, password)
            self.client = client
            self.enabled = True
            log("BLUESKY", f"Logged in as {handle}")
        except Exception as exc:
            log("BLUESKY", f"Login failed — skipping direct Bluesky publish: {exc}")

    def post(self, text):
        if not self.enabled or not self.client:
            raise RuntimeError("BlueskyPoster is not available")
        return self.client.send_post(text=str(text or "").strip())


_BLUESKY_POSTER = None


def get_bluesky_poster():
    global _BLUESKY_POSTER
    if _BLUESKY_POSTER is None:
        _BLUESKY_POSTER = BlueskyPoster()
    return _BLUESKY_POSTER
