import datetime
import sys
from dubber.config import get_platform_accounts

_LOG_SUBSCRIBERS = []


def add_log_subscriber(callback):
    if callback and callback not in _LOG_SUBSCRIBERS:
        _LOG_SUBSCRIBERS.append(callback)


def remove_log_subscriber(callback):
    if callback in _LOG_SUBSCRIBERS:
        _LOG_SUBSCRIBERS.remove(callback)


def log(tag, msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{tag:<12}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        safe = line.encode(enc, errors="replace").decode(enc, errors="replace")
        print(safe, flush=True)
    for callback in list(_LOG_SUBSCRIBERS):
        try:
            callback(line=line, tag=tag, msg=msg)
        except Exception:
            continue

# Standardized platform definitions
PLATFORMS = ["instagram", "facebook", "youtube", "threads", "twitter", "tiktok", "bluesky"]

PLATFORM_LIMITS = {
    "instagram": 2000,
    "facebook": 2000, 
    "threads": 380,
    "bluesky": 300,
    "twitter": 280,
    "tiktok": 180,
    "youtube": 5000,
}

SHORT_MINIMUMS = {
    "tiktok": 80,
    "twitter": 180, 
    "threads": 200,
    "bluesky": 180
}

REQUIRED_PLATFORMS = {"instagram", "facebook", "tiktok", "twitter", "youtube", "threads", "bluesky"}

# Zernio platform account IDs come from environment variables.
# Public repo defaults intentionally remain empty.
PLATFORM_ACCOUNTS = get_platform_accounts()

# Platform-specific teaser generation specs
PLATFORM_SPECS = {
    "instagram": {"min": 15, "max": 29,  "strategy": "hook_moment",    "label": "Instagram Reels"},
    "tiktok":    {"min":  7, "max": 15,  "strategy": "fastest_moment", "label": "TikTok"},
    "youtube":   {"min": 20, "max": 59,  "strategy": "peak_moment",    "label": "YouTube Shorts"},
    "facebook":  {"min": 15, "max": 44,  "strategy": "emotional_hook", "label": "Facebook"},
    "twitter":   {"min":  7, "max": 14,  "strategy": "fastest_moment", "label": "Twitter/X"},
    "threads":   {"min": 15, "max": 30,  "strategy": "hook_moment",    "label": "Threads"},
    "bluesky":   {"min": 10, "max": 20,  "strategy": "hook_moment",    "label": "Bluesky"},
}
