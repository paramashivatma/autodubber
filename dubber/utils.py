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
PLATFORMS = [
    "instagram",
    "facebook",
    "youtube",
    "threads",
    "twitter",
    "tiktok",
    "bluesky",
]

# Real platform hard limits (character counts)
PLATFORM_LIMITS = {
    "instagram": 2200,
    "facebook": 63206,
    "threads": 500,
    "bluesky": 300,
    "twitter": 280,
    "tiktok": 2200,
    "youtube": 5000,
}

# Optimal engagement ranges — captions should target these, not get truncated at them
SHORT_MINIMUMS = {"tiktok": 120, "twitter": 80, "threads": 160, "bluesky": 80}

# Optimal engagement ranges for warning system (min, max)
OPTIMAL_RANGES = {
    "twitter": (80, 100),
    "threads": (160, 250),
    "bluesky": (80, 160),
    "instagram": (80, 300),
    "tiktok": (120, 250),
    "facebook": (30, 180),
    "youtube": (120, 200),
}

REQUIRED_PLATFORMS = {
    "instagram",
    "facebook",
    "tiktok",
    "twitter",
    "youtube",
    "threads",
    "bluesky",
}

# Zernio platform account IDs come from environment variables.
# Public repo defaults intentionally remain empty.
PLATFORM_ACCOUNTS = get_platform_accounts()

# Platform-specific teaser generation specs
PLATFORM_SPECS = {
    "instagram": {
        "min": 15,
        "max": 29,
        "strategy": "hook_moment",
        "label": "Instagram Reels",
    },
    "tiktok": {"min": 7, "max": 15, "strategy": "fastest_moment", "label": "TikTok"},
    "youtube": {
        "min": 20,
        "max": 59,
        "strategy": "peak_moment",
        "label": "YouTube Shorts",
    },
    "facebook": {
        "min": 15,
        "max": 44,
        "strategy": "emotional_hook",
        "label": "Facebook",
    },
    "twitter": {
        "min": 7,
        "max": 14,
        "strategy": "fastest_moment",
        "label": "Twitter/X",
    },
    "threads": {"min": 15, "max": 30, "strategy": "hook_moment", "label": "Threads"},
    "bluesky": {"min": 10, "max": 20, "strategy": "hook_moment", "label": "Bluesky"},
}
