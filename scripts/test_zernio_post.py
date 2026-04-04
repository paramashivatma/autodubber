"""
Single-platform Zernio test publish (video + caption).

Loads repo-root .env (ZERNIO_API_KEY, ZERNIO_*_ACCOUNT_ID).

Example:
  python scripts/test_zernio_post.py --platform threads --video output.mp4 \\
      --caption-file workspace/caption_threads.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def main() -> int:
    root = _root()
    sys.path.insert(0, str(root))

    parser = argparse.ArgumentParser(description="Test Zernio publish for one platform.")
    parser.add_argument(
        "--platform",
        required=True,
        help="Platform id, e.g. threads, instagram, facebook",
    )
    parser.add_argument("--video", type=Path, required=True, help="Video file path")
    parser.add_argument(
        "--caption-file",
        type=Path,
        help="UTF-8 caption text file",
    )
    parser.add_argument(
        "--caption-json",
        type=Path,
        help="Use captions[\"platform\"].caption from this JSON (e.g. workspace/captions.json)",
    )
    parser.add_argument(
        "--caption",
        default="",
        help="Inline caption (used with or without --caption-file)",
    )
    args = parser.parse_args()

    platform = str(args.platform or "").strip().lower()
    if not platform:
        print("Invalid --platform", file=sys.stderr)
        return 1

    video = (root / args.video) if not args.video.is_absolute() else args.video
    if not video.is_file():
        print(f"Video not found: {video}", file=sys.stderr)
        return 1

    caption_text = (args.caption or "").strip()
    if args.caption_file:
        cf = args.caption_file if args.caption_file.is_absolute() else root / args.caption_file
        if not cf.is_file():
            print(f"Caption file not found: {cf}", file=sys.stderr)
            return 1
        extra = cf.read_text(encoding="utf-8").strip()
        caption_text = "\n\n".join(p for p in (caption_text, extra) if p)
    elif args.caption_json:
        jf = args.caption_json if args.caption_json.is_absolute() else root / args.caption_json
        if not jf.is_file():
            print(f"Caption JSON not found: {jf}", file=sys.stderr)
            return 1
        data = json.loads(jf.read_text(encoding="utf-8"))
        entry = data.get(platform) or data.get(platform.capitalize())
        if isinstance(entry, dict):
            caption_text = str(entry.get("caption") or "").strip()
        elif isinstance(entry, str):
            caption_text = entry.strip()
        if not caption_text:
            print(f"No caption for '{platform}' in {jf}", file=sys.stderr)
            return 1
    if not caption_text:
        print("Provide --caption, --caption-file, or --caption-json", file=sys.stderr)
        return 1

    from dubber.config import get_zernio_api_key, load_env_into_process
    from dubber.sdk_publisher import publish_to_platforms_sdk

    env_path = root / ".env"
    load_env_into_process(env_path if env_path.exists() else ".env")

    api_key = get_zernio_api_key()
    if not api_key:
        print("ZERNIO_API_KEY missing in .env", file=sys.stderr)
        return 1

    captions = {platform: {"caption": caption_text}}
    results = publish_to_platforms_sdk(
        api_key=api_key,
        video_path=str(video),
        captions=captions,
        platforms=[platform],
        publish_now=True,
        fallback_files={"main_video": str(video)},
    )
    print(results)
    if isinstance(results, dict) and results.get("error") and len(results) == 1:
        return 1
    ent = results.get(platform) if isinstance(results, dict) else None
    if isinstance(ent, dict):
        st = str(ent.get("status", "")).lower()
        if st in {"error", "failed", "fail"}:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
