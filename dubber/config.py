"""Shared environment/config helpers for runtime modules."""

import os
from pathlib import Path
from typing import Dict

ENV_FILE = ".env"

PLATFORM_ACCOUNT_ENV_MAP = {
    "instagram": "ZERNIO_INSTAGRAM_ACCOUNT_ID",
    "facebook": "ZERNIO_FACEBOOK_ACCOUNT_ID",
    "youtube": "ZERNIO_YOUTUBE_ACCOUNT_ID",
    "threads": "ZERNIO_THREADS_ACCOUNT_ID",
    "twitter": "ZERNIO_TWITTER_ACCOUNT_ID",
    "tiktok": "ZERNIO_TIKTOK_ACCOUNT_ID",
    "bluesky": "ZERNIO_BLUESKY_ACCOUNT_ID",
}


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def read_env_file(path=ENV_FILE) -> Dict[str, str]:
    env = {}
    env_path = Path(path)
    if not env_path.exists():
        return env

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            env[key] = value
    return env


def sync_process_env(values: Dict[str, str]) -> None:
    for key, value in values.items():
        clean_key = _clean(key)
        clean_value = _clean(value)
        if clean_key and clean_value:
            os.environ[clean_key] = clean_value


def load_env_into_process(path=ENV_FILE) -> Dict[str, str]:
    env = read_env_file(path)
    sync_process_env(env)
    return env


def save_env_updates(updates: Dict[str, str], path=ENV_FILE) -> Dict[str, str]:
    merged = read_env_file(path)
    for key, value in updates.items():
        clean_key = _clean(key)
        clean_value = _clean(value)
        if clean_key and clean_value:
            merged[clean_key] = clean_value

    env_path = Path(path)
    lines = [f"{key}={merged[key]}\n" for key in sorted(merged.keys())]
    env_path.write_text("".join(lines), encoding="utf-8")
    sync_process_env(merged)
    return merged


def first_env(*names, default="") -> str:
    for name in names:
        value = _clean(os.getenv(name))
        if value:
            return value
    return default


def get_gemini_api_key(explicit=None) -> str:
    explicit_value = _clean(explicit)
    if explicit_value:
        return explicit_value
    return first_env("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_VISION_KEY")


def get_mistral_api_key(explicit=None) -> str:
    explicit_value = _clean(explicit)
    if explicit_value:
        return explicit_value
    return first_env("MISTRAL_API_KEY", "OPENROUTER_API_KEY")


def get_zernio_api_key(explicit=None) -> str:
    explicit_value = _clean(explicit)
    if explicit_value:
        return explicit_value
    return first_env("ZERNIO_API_KEY")


def get_groq_api_key(explicit=None) -> str:
    explicit_value = _clean(explicit)
    if explicit_value:
        return explicit_value
    return first_env("GROQ_API_KEY")


def get_sheet_id(explicit=None) -> str:
    explicit_value = _clean(explicit)
    if explicit_value:
        return explicit_value
    return first_env("GOOGLE_SHEET_ID", "SHEET_ID")


def get_credentials_file(default="credentials.json") -> str:
    return first_env("GOOGLE_CREDENTIALS_FILE", default=default)


def get_platform_accounts(explicit=None) -> Dict[str, str]:
    accounts = {}
    provided = explicit or {}
    for platform, env_name in PLATFORM_ACCOUNT_ENV_MAP.items():
        explicit_value = _clean(provided.get(platform))
        env_value = first_env(env_name)
        value = explicit_value or env_value
        if value:
            accounts[platform] = value
    return accounts
