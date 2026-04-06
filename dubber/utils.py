import datetime
import os
import sys
import glob
import logging
from logging.handlers import RotatingFileHandler
from dubber.config import get_platform_accounts

_LOG_SUBSCRIBERS = []
_FILE_LOGGER = None
_LOG_DIR = None
_API_CALL_COUNTS = {"gemini": 0, "mistral": 0, "groq": 0, "total": 0}


def get_log_dir():
    """Get the logs directory path."""
    global _LOG_DIR
    if _LOG_DIR is None:
        _LOG_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
        )
    return _LOG_DIR


def _init_file_logger():
    """Initialize rotating file logger with 7-day retention."""
    global _FILE_LOGGER, _LOG_DIR, _API_CALL_COUNTS

    log_dir = get_log_dir()
    os.makedirs(log_dir, exist_ok=True)

    today = datetime.date.today().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"dubber_{today}.log")

    _FILE_LOGGER = logging.getLogger("dubber")
    _FILE_LOGGER.setLevel(logging.INFO)

    if not _FILE_LOGGER.handlers:
        handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=7, encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        _FILE_LOGGER.addHandler(handler)

    _API_CALL_COUNTS = {"gemini": 0, "mistral": 0, "groq": 0, "total": 0}
    _clean_old_logs(log_dir, keep_days=7)

    return log_file


def _clean_old_logs(log_dir, keep_days=7):
    """Remove log files older than keep_days."""
    try:
        pattern = os.path.join(log_dir, "dubber_*.log")
        for log_file in glob.glob(pattern):
            file_time = os.path.getmtime(log_file)
            file_date = datetime.datetime.fromtimestamp(file_time).date()
            if (datetime.date.today() - file_date).days > keep_days:
                try:
                    os.remove(log_file)
                except Exception:
                    pass
    except Exception:
        pass


def track_api_call(provider="gemini"):
    """Track an API call attempt."""
    global _API_CALL_COUNTS
    provider = provider.lower()
    if provider in _API_CALL_COUNTS:
        _API_CALL_COUNTS[provider] += 1
        _API_CALL_COUNTS["total"] += 1


def track_api_success(provider="gemini"):
    """Track a successful API call (increments success counter)."""
    global _API_CALL_COUNTS
    provider = provider.lower()
    if f"{provider}_success" not in _API_CALL_COUNTS:
        _API_CALL_COUNTS[f"{provider}_success"] = 0
    _API_CALL_COUNTS[f"{provider}_success"] += 1


def get_api_call_counts():
    """Return current API call counts."""
    return _API_CALL_COUNTS.copy()


def reset_api_call_counts():
    """Reset API call counts (typically called at start of new pipeline run)."""
    global _API_CALL_COUNTS
    _API_CALL_COUNTS = {"gemini": 0, "mistral": 0, "groq": 0, "total": 0}


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

    if _FILE_LOGGER:
        _FILE_LOGGER.info(f"[{tag}] {msg}")

    for callback in list(_LOG_SUBSCRIBERS):
        try:
            callback(line=line, tag=tag, msg=msg)
        except Exception:
            continue


def get_recent_logs(lines=100):
    """Return last N lines of current log file."""
    log_dir = get_log_dir()
    today = datetime.date.today().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"dubber_{today}.log")

    if not os.path.exists(log_file):
        return []

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return [l.strip() for l in all_lines[-lines:]]
    except Exception:
        return []


def count_api_calls_from_logs(log_file=None):
    """Count API calls from a specific log file or today's log."""
    if log_file is None:
        log_dir = get_log_dir()
        today = datetime.date.today().strftime("%Y%m%d")
        log_file = os.path.join(log_dir, f"dubber_{today}.log")

    if not os.path.exists(log_file):
        return {"gemini": 0, "mistral": 0, "groq": 0, "total": 0}

    counts = {"gemini": 0, "mistral": 0, "groq": 0, "total": 0}

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_lower = line.lower()
                if (
                    "gemini" in line_lower
                    or "[TRANSLATE" in line
                    or "[VISION" in line
                    or "[TEASER" in line
                    or "[CAPTION" in line
                ):
                    if "api call" in line_lower or "gemini" in line_lower:
                        counts["gemini"] += 1
                        counts["total"] += 1
                elif "mistral" in line_lower:
                    counts["mistral"] += 1
                    counts["total"] += 1
                elif "groq" in line_lower or "transcribe" in line_lower:
                    if "call" in line_lower or "groq" in line_lower:
                        counts["groq"] += 1
    except Exception:
        pass

    return counts


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
# Adjusted to balance engagement optimization with content preservation
OPTIMAL_RANGES = {
    "twitter": (100, 180),  # Tight platform - keep short
    "threads": (160, 300),  # Moderate length
    "bluesky": (100, 200),  # Moderate length
    "instagram": (80, 500),  # Expanded - supports bullet-rich posts
    "tiktok": (120, 250),  # Short form
    "facebook": (30, 600),  # Expanded - supports long devotional posts
    "youtube": (120, 800),  # Expanded - supports structured teachings
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
