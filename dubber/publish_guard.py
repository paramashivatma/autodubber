"""Local duplicate-protection guard for ambiguous publish outcomes."""

import hashlib
import json
import os
from datetime import datetime

GUARD_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".publish_guard.json")
AMBIGUOUS_STATUSES = {"unconfirmed", "submitted_unconfirmed", "likely_live", "duplicate_live"}
CONFIRMED_STATUSES = {"ok", "published", "success"}
BLOCKING_STATUSES = AMBIGUOUS_STATUSES | CONFIRMED_STATUSES


def _utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _load_guard():
    if not os.path.exists(GUARD_FILE):
        return {}
    try:
        with open(GUARD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_guard(data):
    with open(GUARD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _sample_file_signature(path):
    if not path or not os.path.exists(path):
        return "missing"
    h = hashlib.sha256()
    size = os.path.getsize(path)
    h.update(str(size).encode("utf-8"))
    with open(path, "rb") as f:
        head = f.read(65536)
        h.update(head)
        if size > 131072:
            f.seek(max(0, size - 65536))
            h.update(f.read(65536))
    return h.hexdigest()


def _caption_for_platform(captions, platform):
    data = (captions or {}).get(platform, "")
    if isinstance(data, dict):
        title = str(data.get("title", "")).strip()
        caption = str(data.get("caption", "")).strip()
        return f"{title}\n{caption}".strip()
    return str(data or "").strip()


def _fingerprint(video_path, captions, platform):
    h = hashlib.sha256()
    h.update(str(platform or "").lower().encode("utf-8"))
    h.update(_sample_file_signature(video_path).encode("utf-8"))
    h.update(_caption_for_platform(captions, platform).encode("utf-8"))
    return h.hexdigest()

def _media_fingerprint(video_path, platform):
    """Platform+media fingerprint (caption-independent) for strict duplicate platforms."""
    h = hashlib.sha256()
    h.update(str(platform or "").lower().encode("utf-8"))
    h.update(_sample_file_signature(video_path).encode("utf-8"))
    return h.hexdigest()


def find_ambiguous_repost_blocks(video_path, captions, platforms):
    guard = _load_guard()
    blocked = []
    strict_media_guard_platforms = {"threads", "bluesky"}
    for platform in platforms or []:
        platform_l = str(platform or "").lower()
        key = _fingerprint(video_path, captions, platform_l)
        record = guard.get(key)
        if not isinstance(record, dict) and platform_l in strict_media_guard_platforms:
            media_key = _media_fingerprint(video_path, platform_l)
            record = guard.get(media_key)
        if not isinstance(record, dict):
            continue
        status = str(record.get("status", "")).lower()
        if status in BLOCKING_STATUSES:
            blocked.append({
                "platform": platform,
                "status": status,
                "timestamp": record.get("timestamp", ""),
                "note": record.get("note", ""),
            })
    return blocked


def record_ambiguous_publish_results(video_path, captions, publish_results):
    if not isinstance(publish_results, dict):
        return
    guard = _load_guard()
    changed = False
    strict_media_guard_platforms = {"threads", "bluesky"}
    for platform, result in publish_results.items():
        if not isinstance(result, dict):
            continue
        platform_l = str(platform or "").lower()
        status = str(result.get("status", "")).lower()
        key = _fingerprint(video_path, captions, platform_l)
        media_key = _media_fingerprint(video_path, platform_l) if platform_l in strict_media_guard_platforms else None
        if status in BLOCKING_STATUSES:
            payload = {
                "platform": platform,
                "status": status,
                "timestamp": _utc_now(),
                "note": result.get("error") or result.get("error_message") or "",
            }
            guard[key] = payload
            if media_key:
                guard[media_key] = payload
            changed = True
        elif status in {"error", "failed", "skipped", "skip"} and key in guard:
            del guard[key]
            if media_key and media_key in guard:
                del guard[media_key]
            changed = True
    if changed:
        _save_guard(guard)
