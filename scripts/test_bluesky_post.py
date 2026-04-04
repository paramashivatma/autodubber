"""
Isolated Bluesky test post (direct AT Proto only — BLUESKY_HANDLE + BLUESKY_APP_PASSWORD).

Run from repo root, e.g.:
  python scripts/test_bluesky_post.py -c "Test caption #KAILASA" --video workspace/output.mp4
  python scripts/test_bluesky_post.py -c "Flyer test" --image path/to/flyer.png
  python scripts/test_bluesky_post.py --caption-file workspace/some.txt --media workspace/output.mp4

--media picks video vs image from the file extension (.mp4, .mov, .webm, ... vs images).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main() -> int:
    root = _repo_root()
    sys.path.insert(0, str(root))

    parser = argparse.ArgumentParser(description="Test direct Bluesky post (caption + optional media).")
    parser.add_argument(
        "-c",
        "--caption",
        default="",
        help="Post text (Bluesky caption).",
    )
    parser.add_argument(
        "--caption-file",
        type=Path,
        default=None,
        help="Read caption from this UTF-8 file (combined with --caption if both given).",
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=None,
        help="Video file to attach (takes precedence over images).",
    )
    parser.add_argument(
        "--image",
        type=Path,
        action="append",
        dest="images",
        default=None,
        help="Image path (repeat for up to 4 images). Ignored if --video is set.",
    )
    parser.add_argument(
        "--media",
        type=Path,
        default=None,
        help="Single image or video path; type inferred from extension.",
    )
    parser.add_argument(
        "--alt",
        default="",
        help="Alt text for image or video embed.",
    )
    args = parser.parse_args()

    from dubber.config import load_env_into_process

    env_path = root / ".env"
    load_env_into_process(env_path if env_path.exists() else ".env")

    from dubber.bluesky_poster import get_bluesky_poster
    from dubber.utils import log

    parts = []
    if args.caption:
        parts.append(args.caption.strip())
    if args.caption_file:
        p = args.caption_file
        if not p.is_file():
            print(f"Caption file not found: {p}", file=sys.stderr)
            return 1
        parts.append(p.read_text(encoding="utf-8").strip())
    caption = "\n\n".join(p for p in parts if p)
    if not caption:
        print("Provide --caption and/or --caption-file.", file=sys.stderr)
        return 1

    video_path = None
    image_paths: list[str] = []

    if args.video:
        video_path = str(args.video.resolve())
        if not Path(video_path).is_file():
            print(f"Video not found: {video_path}", file=sys.stderr)
            return 1

    if args.media and not video_path:
        m = args.media.resolve()
        if not m.is_file():
            print(f"Media not found: {m}", file=sys.stderr)
            return 1
        if m.suffix.lower() in _VIDEO_EXTS:
            video_path = str(m)
        else:
            image_paths.append(str(m))

    if args.images and not video_path:
        for img in args.images:
            ip = str(img.resolve())
            if not Path(ip).is_file():
                print(f"Image not found: {ip}", file=sys.stderr)
                return 1
            image_paths.append(ip)

    poster = get_bluesky_poster()
    if not getattr(poster, "enabled", False):
        print(
            "BlueskyPoster is not enabled. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in .env, "
            "install atproto, and ensure login works. Check logs above for [BLUESKY] lines.",
            file=sys.stderr,
        )
        return 1

    kind = "text"
    if video_path:
        kind = f"video ({video_path})"
    elif image_paths:
        kind = f"{len(image_paths)} image(s)"

    log("BLUESKY", f"Test post: {kind}, caption_len={len(caption)}")

    try:
        resp = poster.post(
            caption,
            image_paths=image_paths if image_paths else None,
            image_alt=args.alt or "Test media",
            video_path=video_path,
        )
    except Exception as exc:
        print(f"Post failed: {exc!r}", file=sys.stderr)
        if getattr(exc, "__cause__", None):
            print(f"  cause: {exc.__cause__!r}", file=sys.stderr)
        return 1

    uri = getattr(resp, "uri", None)
    cid = getattr(resp, "cid", None)
    print("Posted OK.")
    if uri:
        print(f"  uri: {uri}")
    if cid:
        print(f"  cid: {cid}")
    if uri and str(uri).startswith("at://"):
        handle = (os.getenv("BLUESKY_HANDLE") or "").strip().lstrip("@")
        rkey = str(uri).rsplit("/", 1)[-1]
        if handle:
            print(f"  web: https://bsky.app/profile/{handle}/post/{rkey}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
