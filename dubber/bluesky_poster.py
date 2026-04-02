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

    def post(self, text, image_paths=None, image_alt=""):
        if not self.enabled or not self.client:
            raise RuntimeError("BlueskyPoster is not available")
        text = str(text or "").strip()
        valid_images = [path for path in (image_paths or []) if path and os.path.exists(path)]
        if not valid_images:
            return self.client.send_post(text=text)

        image_bytes = []
        for path in valid_images[:4]:
            with open(path, "rb") as f:
                image_bytes.append(f.read())

        if len(image_bytes) == 1:
            return self.client.send_image(text=text, image=image_bytes[0], image_alt=image_alt or "Flyer image")

        image_alts = [(image_alt or "Flyer image")] * len(image_bytes)
        return self.client.send_images(text=text, images=image_bytes, image_alts=image_alts)


_BLUESKY_POSTER = None


def get_bluesky_poster():
    global _BLUESKY_POSTER
    if _BLUESKY_POSTER is None:
        _BLUESKY_POSTER = BlueskyPoster()
    return _BLUESKY_POSTER
